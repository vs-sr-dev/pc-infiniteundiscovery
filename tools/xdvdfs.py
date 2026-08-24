#!/usr/bin/env python3
"""
xdvdfs.py -- reader for the XDVDFS filesystem used by Xbox / Xbox 360 discs.

XDVDFS ("MICROSOFT*XBOX*MEDIA") is the on-disc filesystem Microsoft used on
both the original Xbox and the Xbox 360.  It is a flat, read-only, 2048-byte
sector filesystem whose directories are stored as balanced binary trees
rather than as linear lists, which is the one genuinely unusual thing about
it: sibling lookup is O(log n) and the on-disc order is sorted by a
case-insensitive, length-then-value comparison.

Layout of a disc image
----------------------
A raw XDVDFS image starts the filesystem at offset 0.  Retail images embed it
at a fixed base offset, past the DVD-Video padding area:

    XGD1 (original Xbox)   0x18300000
    XGD2 (Xbox 360)        0x0FD90000
    XGD3 (Xbox 360, late)  0x02080000

The volume descriptor always lives at sector 32 relative to that base.

Volume descriptor (one 2048-byte sector)
----------------------------------------
    0x000  20  magic "MICROSOFT*XBOX*MEDIA"
    0x014   4  root directory table start sector (relative to partition base)
    0x018   4  root directory table size in bytes
    0x01C   8  volume creation time (Windows FILETIME)
    0x024 1992 unused
    0x7EC  20  magic again (guards against a truncated/garbage sector)

Directory entry (4-byte aligned, inside the directory table)
------------------------------------------------------------
    0x00  2  left  child offset, in 4-byte units from table start (0xFFFF = nil)
    0x02  2  right child offset, in 4-byte units from table start (0xFFFF = nil)
    0x04  4  start sector of the file/subdirectory table
    0x08  4  size in bytes
    0x0C  1  attributes (see ATTR_*)
    0x0D  1  filename length
    0x0E  n  filename, ASCII

Usage
-----
    python tools/xdvdfs.py info    <image>
    python tools/xdvdfs.py list    <image> [--csv out.csv]
    python tools/xdvdfs.py extract <image> <outdir> [--only PREFIX]
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import struct
import sys

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"

# Offsets of the game partition inside a full retail disc image.
PARTITION_BASES = {
    "raw": 0x00000000,
    "xgd3": 0x02080000,
    "xgd2": 0x0FD90000,
    "xgd1": 0x18300000,
}

ATTR_READONLY = 0x01
ATTR_HIDDEN = 0x02
ATTR_SYSTEM = 0x04
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE = 0x20
ATTR_NORMAL = 0x80

NIL = 0xFFFF


def attr_str(a: int) -> str:
    """Render an attribute byte the way `attrib` would, for readable listings."""
    return "".join(
        c if a & bit else "-"
        for bit, c in (
            (ATTR_DIRECTORY, "D"),
            (ATTR_ARCHIVE, "A"),
            (ATTR_READONLY, "R"),
            (ATTR_HIDDEN, "H"),
            (ATTR_SYSTEM, "S"),
            (ATTR_NORMAL, "N"),
        )
    )


def filetime_to_iso(ft: int) -> str:
    """Windows FILETIME (100ns ticks since 1601-01-01 UTC) -> ISO 8601."""
    if ft == 0:
        return ""
    try:
        epoch = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
        return (epoch + datetime.timedelta(microseconds=ft // 10)).isoformat()
    except (OverflowError, OSError, ValueError):
        return "<invalid:0x%016X>" % ft


class Entry:
    """One directory entry, resolved to an absolute path within the volume."""

    __slots__ = ("name", "path", "sector", "size", "attributes")

    def __init__(self, name, path, sector, size, attributes):
        self.name = name
        self.path = path
        self.sector = sector
        self.size = size
        self.attributes = attributes

    @property
    def is_dir(self) -> bool:
        return bool(self.attributes & ATTR_DIRECTORY)

    def __repr__(self) -> str:
        return "<Entry %s sector=%d size=%d>" % (self.path, self.sector, self.size)


class XdvdfsImage:
    """Random-access reader over an XDVDFS volume inside a disc image."""

    def __init__(self, path, base=None):
        self.path = path
        self.fh = open(path, "rb")
        self.base_name = "given"
        self.base = base if base is not None else self._find_base()
        if self.base is None:
            raise ValueError("no XDVDFS volume descriptor found in " + path)
        self._read_volume_descriptor()

    # -- setup ------------------------------------------------------------

    def _probe(self, base):
        """True if a valid volume descriptor sits at sector 32 past `base`."""
        try:
            self.fh.seek(base + 32 * SECTOR)
        except OSError:
            return False
        sec = self.fh.read(SECTOR)
        return (
            len(sec) == SECTOR
            and sec[:20] == MAGIC
            and sec[0x7EC:0x7EC + 20] == MAGIC
        )

    def _find_base(self):
        for name, base in PARTITION_BASES.items():
            if self._probe(base):
                self.base_name = name
                return base
        # Fall back to a linear scan on sector boundaries: some tools produce
        # images with the partition at a non-standard offset.
        size = os.path.getsize(self.path)
        for off in range(0, min(size, 0x20000000), SECTOR):
            if self._probe(off):
                self.base_name = "scanned"
                return off
        return None

    def _read_volume_descriptor(self):
        self.fh.seek(self.base + 32 * SECTOR)
        sec = self.fh.read(SECTOR)
        self.root_sector, self.root_size = struct.unpack_from("<II", sec, 0x14)
        self.filetime = struct.unpack_from("<Q", sec, 0x1C)[0]
        self.vd_unused = sec[0x24:0x7EC]

    # -- raw access -------------------------------------------------------

    def read_sectors(self, sector, length):
        self.fh.seek(self.base + sector * SECTOR)
        return self.fh.read(length)

    # -- directory walking ------------------------------------------------

    def _walk_table(self, sector, size, parent, out):
        """Walk one directory table (a binary tree packed into `size` bytes)."""
        if size == 0 or size > 0x1000000:
            return
        table = self.read_sectors(sector, size)
        if len(table) < size:
            return

        # Iterative traversal; `seen` guards against corrupt/looping offsets.
        stack = [0]
        seen = set()
        while stack:
            off = stack.pop() * 4
            if off in seen or off + 14 > len(table):
                continue
            seen.add(off)

            left, right, start, fsize, attrs, namelen = struct.unpack_from(
                "<HHIIBB", table, off
            )
            # A run of 0xFF padding marks the end of a sector's worth of entries.
            if left == NIL and right == NIL and start == 0xFFFFFFFF:
                continue
            if off + 14 + namelen > len(table):
                continue

            name = table[off + 14:off + 14 + namelen].decode("latin-1")
            if left != NIL and left != 0:
                stack.append(left)
            if right != NIL and right != 0:
                stack.append(right)

            path = (parent + "/" + name) if parent else ("/" + name)
            entry = Entry(name, path, start, fsize, attrs)
            out.append(entry)
            if entry.is_dir:
                self._walk_table(start, fsize, path, out)

    def entries(self):
        """Every entry on the volume, sorted by path."""
        out = []
        self._walk_table(self.root_sector, self.root_size, "", out)
        out.sort(key=lambda e: e.path.lower())
        return out

    # -- extraction -------------------------------------------------------

    def extract(self, entry, dest, chunk=4 << 20):
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.fh.seek(self.base + entry.sector * SECTOR)
        remaining = entry.size
        with open(dest, "wb") as fo:
            while remaining > 0:
                buf = self.fh.read(min(chunk, remaining))
                if not buf:
                    break
                fo.write(buf)
                remaining -= len(buf)

    def close(self):
        self.fh.close()


# -- commands -------------------------------------------------------------


def cmd_info(args):
    img = XdvdfsImage(args.image, args.base)
    size = os.path.getsize(args.image)
    print("image            : %s" % os.path.basename(args.image))
    print("image size       : %d bytes (%.3f GiB)" % (size, size / 2 ** 30))
    print("partition base   : 0x%08X (%s)" % (img.base, img.base_name))
    print("root dir sector  : %d (0x%X)" % (img.root_sector, img.root_sector))
    print("root dir size    : %d bytes" % img.root_size)
    print("volume timestamp : 0x%016X  %s" % (img.filetime, filetime_to_iso(img.filetime)))
    filler = sorted(set(img.vd_unused))
    print("vd filler bytes  : %d distinct value(s) %s" % (len(filler), filler[:8]))

    entries = img.entries()
    files = [e for e in entries if not e.is_dir]
    dirs = [e for e in entries if e.is_dir]
    total = sum(e.size for e in files)
    print("directories      : %d" % len(dirs))
    print("files            : %d" % len(files))
    print("total file bytes : %d (%.3f GiB)" % (total, total / 2 ** 30))
    img.close()
    return 0


def cmd_list(args):
    img = XdvdfsImage(args.image, args.base)
    entries = img.entries()
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fo:
            w = csv.writer(fo)
            w.writerow(["path", "kind", "sector", "offset", "size", "attributes"])
            for e in entries:
                w.writerow([
                    e.path,
                    "dir" if e.is_dir else "file",
                    e.sector,
                    img.base + e.sector * SECTOR,
                    e.size,
                    attr_str(e.attributes),
                ])
        print("wrote %d entries to %s" % (len(entries), args.csv))
    else:
        for e in entries:
            kind = "d" if e.is_dir else "-"
            print("%s %s %9d %12d  %s" % (kind, attr_str(e.attributes), e.sector, e.size, e.path))
    img.close()
    return 0


def cmd_extract(args):
    img = XdvdfsImage(args.image, args.base)
    entries = img.entries()
    # Accept "foo/bar", "/foo/bar" and "\foo\bar" alike. MSYS2 shells rewrite a
    # leading "/" into a Windows path, so a bare prefix has to work too.
    only = args.only
    if only:
        only = "/" + only.replace("\\", "/").lstrip("/")
        only = only.upper()
    n = 0
    total = 0
    for e in entries:
        if e.is_dir:
            continue
        if only and not e.path.upper().startswith(only):
            continue
        dest = os.path.join(args.outdir, e.path.lstrip("/").replace("/", os.sep))
        img.extract(e, dest)
        n += 1
        total += e.size
        if n % 200 == 0:
            print("  ... %d files, %.0f MiB" % (n, total / 2 ** 20), file=sys.stderr)
    print("extracted %d files, %d bytes to %s" % (n, total, args.outdir))
    img.close()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Reader for the XDVDFS filesystem on Xbox / Xbox 360 discs.")
    p.add_argument("--base", type=lambda s: int(s, 0), default=None,
                   help="force the partition base offset (default: autodetect)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="print volume descriptor and totals")
    s.add_argument("image")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("list", help="list every entry on the volume")
    s.add_argument("image")
    s.add_argument("--csv", help="write a CSV manifest instead of stdout")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("extract", help="extract files to a directory")
    s.add_argument("image")
    s.add_argument("outdir")
    s.add_argument("--only", help="only paths starting with this prefix")
    s.set_defaults(func=cmd_extract)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
