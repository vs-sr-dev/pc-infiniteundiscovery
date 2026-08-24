#!/usr/bin/env python3
"""
xdbf.py -- reader for XDBF, the Xbox 360 title metadata database.

Every Xbox 360 title embeds an XDBF blob (often called the SPA) inside its
executable's resource section. It is what the dashboard reads to show the
game's name, its icon, and its achievement list -- so it holds the achievement
names, both descriptions (locked and unlocked), gamerscore values, and the PNG
icons, in every language the title shipped with.

Finding it: the XEX `RESOURCE_INFO` optional header gives a virtual address and
a size. Subtract the image base address to get an offset into the decrypted PE.
For Infinite Undiscovery that is `0x82AB0000 - 0x82000000 = 0xAB0000`.

Container layout
----------------
    0x00  4  magic "XDBF"
    0x04  4  version (0x00010000)
    0x08  4  entry table capacity, in entries
    0x0C  4  entries used
    0x10  4  free table capacity, in entries
    0x14  4  free entries used
    0x18  .. entry table, 18 bytes per slot
    ..    .. free table, 8 bytes per slot
    ..    .. data

The data region begins at `0x18 + entry_capacity * 18 + free_capacity * 8`, and
every entry's offset is relative to that point, not to the file.

Entry (18 bytes, big-endian)
----------------------------
    0x00  2  namespace: 1 metadata, 2 image, 3 string table
    0x02  8  id
    0x0A  4  offset into the data region
    0x0E  4  length

Metadata entries carry a FourCC as their id -- `XACH` achievements, `XTHD`
title header, `XSTR` string tables and so on. Image entries are raw PNG, keyed
by image id, with `0x8000` conventionally the title icon. String table entries
are keyed by language id.

String table (`XSTR`)
---------------------
    0x00  4  magic "XSTR"
    0x04  4  version
    0x08  4  size
    0x0C  2  string count
    0x0E  .. repeated: u16 id, u16 byte length, UTF-8 bytes

Achievement table (`XACH`)
--------------------------
    0x00  4  magic "XACH"
    0x04  4  version
    0x08  4  size
    0x0C  2  achievement count
    0x0E  .. repeated, 36 bytes each:
             0x00  2  achievement id
             0x02  2  string id, name
             0x04  2  string id, description once unlocked
             0x06  2  string id, description while locked
             0x08  4  image id
             0x0C  2  gamerscore
             0x0E  2  reserved
             0x10  4  flags
             0x14 16  reserved

The gamerscore field being 16-bit rather than 32-bit was settled empirically:
read as `u16` the fifty values sum to exactly 1000, which is the title's
advertised total.

Usage
-----
    python tools/xdbf.py info         <pe-image> [--offset 0xAB0000]
    python tools/xdbf.py achievements <pe-image> [--language 1]
    python tools/xdbf.py strings      <pe-image> [--language 1]
    python tools/xdbf.py images       <pe-image> <outdir>
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

MAGIC = b"XDBF"

NAMESPACE_NAMES = {1: "metadata", 2: "image", 3: "string"}

# Language ids as the dashboard uses them.
LANGUAGE_NAMES = {
    1: "English", 2: "Japanese", 3: "German", 4: "French", 5: "Spanish",
    6: "Italian", 7: "Korean", 8: "Chinese (traditional)", 9: "Portuguese",
    10: "Chinese (simplified)", 11: "Polish", 12: "Russian",
}


class Entry:
    __slots__ = ("namespace", "id", "offset", "length")

    def __init__(self, namespace, entry_id, offset, length):
        self.namespace = namespace
        self.id = entry_id
        self.offset = offset
        self.length = length

    @property
    def fourcc(self):
        """Metadata ids are a FourCC in the low 32 bits; others are numbers."""
        packed = struct.pack(">Q", self.id)
        if packed[:4] == b"\0\0\0\0" and all(32 <= c < 127 for c in packed[4:]):
            return packed[4:].decode("latin-1")
        return None

    def label(self):
        return self.fourcc or ("0x%X" % self.id)


class Xdbf:
    def __init__(self, path, offset=None, length=None):
        with open(path, "rb") as fh:
            blob = fh.read()
        if offset is None:
            offset = blob.find(MAGIC)
            if offset < 0:
                raise ValueError("no XDBF blob found in %s" % path)
        self.data = blob[offset:offset + length] if length else blob[offset:]
        if self.data[:4] != MAGIC:
            raise ValueError("no XDBF magic at offset 0x%X" % offset)

        (_, self.version, entry_capacity, entry_count,
         free_capacity, self.free_count) = struct.unpack_from(">4sIIIII", self.data, 0)
        self.data_start = 0x18 + entry_capacity * 18 + free_capacity * 8

        self.entries = []
        for i in range(entry_count):
            ns, eid, off, ln = struct.unpack_from(">HQII", self.data, 0x18 + i * 18)
            self.entries.append(Entry(ns, eid, off, ln))

    def payload(self, entry):
        base = self.data_start + entry.offset
        return self.data[base:base + entry.length]

    def find(self, namespace, fourcc=None, entry_id=None):
        for e in self.entries:
            if e.namespace != namespace:
                continue
            if fourcc is not None and e.fourcc != fourcc:
                continue
            if entry_id is not None and e.id != entry_id:
                continue
            return e
        return None

    # -- typed tables ------------------------------------------------------

    def string_table(self, language=1):
        entry = self.find(3, entry_id=language)
        if entry is None:
            return {}
        blob = self.payload(entry)
        count = struct.unpack_from(">H", blob, 0x0C)[0]
        pos = 0x0E
        out = {}
        for _ in range(count):
            if pos + 4 > len(blob):
                break
            sid, size = struct.unpack_from(">HH", blob, pos)
            pos += 4
            out[sid] = blob[pos:pos + size].decode("utf-8", "replace")
            pos += size
        return out

    def languages(self):
        return sorted(e.id for e in self.entries if e.namespace == 3)

    def achievements(self):
        entry = self.find(1, fourcc="XACH")
        if entry is None:
            return []
        blob = self.payload(entry)
        count = struct.unpack_from(">H", blob, 0x0C)[0]
        out = []
        for i in range(count):
            base = 0x0E + i * 36
            if base + 36 > len(blob):
                break
            aid, name_id, unlocked_id, locked_id = struct.unpack_from(">HHHH", blob, base)
            image_id = struct.unpack_from(">I", blob, base + 0x08)[0]
            gamerscore = struct.unpack_from(">H", blob, base + 0x0C)[0]
            flags = struct.unpack_from(">I", blob, base + 0x10)[0]
            out.append({
                "id": aid, "name_id": name_id, "unlocked_id": unlocked_id,
                "locked_id": locked_id, "image_id": image_id,
                "gamerscore": gamerscore, "flags": flags,
            })
        return out


def _utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def open_xdbf(args):
    return Xdbf(args.image, args.offset, getattr(args, "length", None))


def cmd_info(args):
    _utf8_stdout()
    db = open_xdbf(args)
    print("version     : 0x%08X" % db.version)
    print("entries     : %d" % len(db.entries))
    print("data starts : 0x%X" % db.data_start)
    print("languages   : %s" % ", ".join(
        "%d (%s)" % (i, LANGUAGE_NAMES.get(i, "?")) for i in db.languages()))
    print()
    print("%-9s %-10s %10s %10s  %s" % ("namespace", "id", "offset", "length", "head"))
    print("%-9s %-10s %10s %10s  %s" % ("-" * 9, "-" * 10, "-" * 10, "-" * 10, "-" * 24))
    for e in sorted(db.entries, key=lambda x: (x.namespace, x.id)):
        head = db.payload(e)[:8]
        note = ""
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            note = "  PNG"
        print("%-9s %-10s %10d %10d  %s%s"
              % (NAMESPACE_NAMES.get(e.namespace, e.namespace), e.label(),
                 e.offset, e.length, head.hex(" "), note))
    return 0


def cmd_achievements(args):
    _utf8_stdout()
    db = open_xdbf(args)
    text = db.string_table(args.language)
    rows = db.achievements()
    total = sum(r["gamerscore"] for r in rows)
    print("%d achievements, %d gamerscore, language %d (%s)"
          % (len(rows), total, args.language,
             LANGUAGE_NAMES.get(args.language, "?")))
    print()
    for r in rows:
        print("%3d  %5dG  img %-3d flags 0x%X  %s"
              % (r["id"], r["gamerscore"], r["image_id"], r["flags"],
                 text.get(r["name_id"], "?")))
        print("          unlocked: %s" % text.get(r["unlocked_id"], "?"))
        if r["locked_id"] != r["unlocked_id"]:
            print("          locked  : %s" % text.get(r["locked_id"], "?"))
    return 0


def cmd_strings(args):
    _utf8_stdout()
    db = open_xdbf(args)
    table = db.string_table(args.language)
    for sid in sorted(table):
        print("%5d  0x%04X  %s" % (sid, sid, table[sid]))
    print("%d strings" % len(table), file=sys.stderr)
    return 0


def cmd_images(args):
    db = open_xdbf(args)
    os.makedirs(args.outdir, exist_ok=True)
    n = 0
    for e in db.entries:
        if e.namespace != 2:
            continue
        blob = db.payload(e)
        suffix = "png" if blob[:8] == b"\x89PNG\r\n\x1a\n" else "bin"
        name = "title" if e.id == 0x8000 else "image_%d" % e.id
        dest = os.path.join(args.outdir, "%s.%s" % (name, suffix))
        with open(dest, "wb") as fo:
            fo.write(blob)
        n += 1
    print("wrote %d images to %s" % (n, args.outdir))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Reader for XDBF, the Xbox 360 title metadata database.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("image", help="a decrypted PE image, or a bare XDBF blob")
        s.add_argument("--offset", type=lambda x: int(x, 0), default=None,
                       help="offset of the XDBF blob (default: search for the magic)")
        s.add_argument("--length", type=lambda x: int(x, 0), default=None)
        return s

    s = common(sub.add_parser("info", help="header and entry table"))
    s.set_defaults(func=cmd_info)

    s = common(sub.add_parser("achievements", help="the achievement list"))
    s.add_argument("--language", type=int, default=1)
    s.set_defaults(func=cmd_achievements)

    s = common(sub.add_parser("strings", help="one language's string table"))
    s.add_argument("--language", type=int, default=1)
    s.set_defaults(func=cmd_strings)

    s = common(sub.add_parser("images", help="write the embedded PNGs out"))
    s.add_argument("outdir")
    s.set_defaults(func=cmd_images)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
