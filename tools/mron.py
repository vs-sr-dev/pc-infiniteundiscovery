#!/usr/bin/env python3
"""
mron.py -- reader for the NORM ("MRON") resource archive used by tri-Ace's
ASKA engine, as shipped in Infinite Undiscovery (Xbox 360, 2008).

The game ships its entire content as two monolithic containers, ud1.bin and
ud2.bin.  Neither has a global table of contents.  Instead each container is a
*sequence* of self-describing archives laid end to end on 2048-byte boundaries,
with unrelated blobs (compressed blocks, ASF video streams) occupying the gaps.

Every archive begins with the eight ASCII bytes "MRON00.2".  Read as a
little-endian FourCC that is `NORM` version `2.00`, and the same reversal
applies to every resource type tag in the archive: the bytes `HSEM` mean MESH,
`MINA` mean ANIM, `XETM` mean MTEX, and so on.  This tool reverses them for
you; every tag it prints is in readable form.

Archive header (big-endian, 32 bytes)
-------------------------------------
    0x00  8  magic "MRON00.2"
    0x08  4  entry count
    0x0C  4  alignment applied to the start of the data region
    0x10  4  group id -- archives that belong to one game area share it
    0x14 12  reserved, zero

Entry table (big-endian, 32 bytes per entry, starting at 0x20)
--------------------------------------------------------------
    0x00  4  type tag, byte-reversed FourCC
    0x04  2  sub-index within the group
    0x06  2  group id (usually the archive's own, sometimes a reference out)
    0x08  4  size in bytes
    0x0C  4  offset, relative to the start of the archive header
    0x10 16  reserved, zero

The data region starts at `align_up(0x20 + count * 32, alignment)` and entries
are stored contiguously in offset order, so the archive's total length is
`align_up(max(offset + size), 2048)`.  That is what makes the sequential walk
possible without any index.

Usage
-----
    python tools/mron.py scan   <file> [--offset N] [--length N]
    python tools/mron.py scan   <file> --csv entries.csv
    python tools/mron.py census <file> [--offset N] [--length N]

`--offset` and `--length` let the tool read a container in place inside a disc
image, so ud1.bin and ud2.bin never have to be extracted.  Get the numbers from
`xdvdfs.py list --csv`.
"""

from __future__ import annotations

import argparse
import collections
import csv
import os
import struct
import sys

SECTOR = 2048
MAGIC = b"MRON00.2"

# Blob magics that occupy the gaps between archives.
GAP_MAGICS = [
    (b"SLZ", "SLZ compressed block"),
    (bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c"), "ASF/WMV stream"),
    (b"RIFF", "RIFF"),
]

# Resource type tags observed so far, with the reading each one supports.
# Anything not listed here is reported verbatim so new tags stand out.
KNOWN_TAGS = {
    "MESH": "geometry",
    "ANIM": "animation",
    "MTEX": "texture, material-bound",
    "TTEX": "texture",
    "IMG-": "image",
    "SOND": "sound",
    "AREA": "area / level",
    "NODE": "scene node",
    "COLL": "collision",
    "SCE-": "scene",
    "SIG-": "signal / trigger",
    "MAIF": "unknown",
    "EPAC": "packed data (E)",
    "APAC": "packed data (A)",
    "TTD-": "unknown",
    "RMD-": "unknown",
    "WEAP": "weapon (identical set on both discs)",
    "SKAC": "unknown, travels with skeletons",
    "SEEK": "unknown, small and numerous -- seek table?",
    "MINI": "unknown, ~16 bytes each",
    "LNS-": "unknown, rare",
}


def align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        return value
    return (value + alignment - 1) // alignment * alignment


class Archive:
    """One MRON archive: its header fields plus its parsed entry table."""

    def __init__(self, offset, count, alignment, group_id, entries, total_size):
        self.offset = offset
        self.count = count
        self.alignment = alignment
        self.group_id = group_id
        self.entries = entries
        self.total_size = total_size


class Gap:
    """A stretch between archives that is not itself an archive."""

    def __init__(self, offset, length, kind):
        self.offset = offset
        self.length = length
        self.kind = kind


class Container:
    """Sequential reader over a ud*.bin container, in place inside any file."""

    def __init__(self, path, offset=0, length=None):
        self.path = path
        self.base = offset
        self.fh = open(path, "rb")
        file_size = os.path.getsize(path)
        self.length = length if length is not None else file_size - offset
        if self.base + self.length > file_size:
            self.length = file_size - self.base

    def read(self, offset, size):
        self.fh.seek(self.base + offset)
        return self.fh.read(size)

    # -- archive parsing --------------------------------------------------

    def parse_archive(self, offset):
        """Parse the archive at `offset`, or return None if there isn't one."""
        head = self.read(offset, 32)
        if len(head) < 32 or head[:8] != MAGIC:
            return None
        count, alignment, group_id = struct.unpack_from(">III", head, 8)
        # Guard against a stray magic in payload data.
        if count > 0x10000 or alignment > 0x100000:
            return None

        table_end = 0x20 + count * 32
        if offset + table_end > self.length:
            return None
        raw = self.read(offset + 0x20, count * 32)
        if len(raw) < count * 32:
            return None

        data_start = align_up(table_end, alignment)
        entries = []
        end = data_start
        for i in range(count):
            tag, sub, grp, size, eoff = struct.unpack_from(">4sHHII", raw, i * 32)
            name = tag[::-1].decode("latin-1")
            entries.append({
                "tag": name,
                "sub": sub,
                "group": grp,
                "size": size,
                "offset": eoff,
            })
            end = max(end, eoff + size)

        if end > self.length - offset:
            return None
        return Archive(offset, count, alignment, group_id, entries,
                       align_up(end, SECTOR))

    # -- gap classification ------------------------------------------------

    def classify(self, offset):
        head = self.read(offset, 16)
        for magic, name in GAP_MAGICS:
            if head.startswith(magic):
                return name
        return "unclassified"

    def next_archive(self, offset):
        """Next sector-aligned MRON magic at or after `offset`, else None."""
        offset = align_up(offset, SECTOR)
        chunk = 1 << 24
        pos = offset
        while pos < self.length:
            buf = self.read(pos, min(chunk, self.length - pos))
            if not buf:
                return None
            for s in range(0, len(buf) - 8, SECTOR):
                if buf[s:s + 8] == MAGIC:
                    return pos + s
            pos += (len(buf) // SECTOR) * SECTOR
            if len(buf) < SECTOR:
                return None
        return None

    # -- the walk ----------------------------------------------------------

    def walk(self):
        """Yield Archive and Gap objects covering the whole container."""
        pos = 0
        while pos < self.length:
            archive = self.parse_archive(pos)
            if archive is not None:
                yield archive
                pos = archive.offset + archive.total_size
                continue
            nxt = self.next_archive(pos + SECTOR)
            end = nxt if nxt is not None else self.length
            yield Gap(pos, end - pos, self.classify(pos))
            pos = end


# -- commands -------------------------------------------------------------


def open_container(args):
    return Container(args.file, args.offset, args.length)


def cmd_scan(args):
    con = open_container(args)
    writer = None
    fo = None
    if args.csv:
        fo = open(args.csv, "w", newline="", encoding="utf-8")
        writer = csv.writer(fo)
        writer.writerow(["archive_offset", "group_id", "entry_index", "tag",
                         "sub_index", "entry_group", "entry_offset", "size"])

    n_arch = n_gap = n_ent = 0
    gap_bytes = 0
    for item in con.walk():
        if isinstance(item, Gap):
            n_gap += 1
            gap_bytes += item.length
            if not args.csv:
                print("GAP     0x%08X  %10d bytes  %s"
                      % (item.offset, item.length, item.kind))
            continue
        n_arch += 1
        n_ent += item.count
        if args.csv:
            for i, e in enumerate(item.entries):
                writer.writerow([item.offset, item.group_id, i, e["tag"],
                                 e["sub"], e["group"],
                                 item.offset + e["offset"], e["size"]])
        else:
            tally = collections.Counter(e["tag"] for e in item.entries)
            summary = " ".join("%s:%d" % kv for kv in tally.most_common(8))
            print("ARCHIVE 0x%08X  gid=0x%-5X cnt=%-4d align=0x%-5X size=0x%-9X %s"
                  % (item.offset, item.group_id, item.count, item.alignment,
                     item.total_size, summary))

    if fo:
        fo.close()
        print("wrote %d entries to %s" % (n_ent, args.csv))
    print("archives %d, entries %d, gaps %d (%d bytes, %.1f%% of container)"
          % (n_arch, n_ent, n_gap, gap_bytes, 100.0 * gap_bytes / con.length),
          file=sys.stderr)
    return 0


def cmd_census(args):
    con = open_container(args)
    tags = collections.Counter()
    tag_bytes = collections.Counter()
    gaps = collections.Counter()
    gap_bytes = collections.Counter()
    groups = set()
    n_arch = 0
    for item in con.walk():
        if isinstance(item, Gap):
            gaps[item.kind] += 1
            gap_bytes[item.kind] += item.length
            continue
        n_arch += 1
        groups.add(item.group_id)
        for e in item.entries:
            tags[e["tag"]] += 1
            tag_bytes[e["tag"]] += e["size"]

    print("container : %s" % os.path.basename(args.file))
    print("region    : offset 0x%X, length %d bytes (%.2f GiB)"
          % (con.base, con.length, con.length / 2 ** 30))
    print("archives  : %d in %d distinct groups" % (n_arch, len(groups)))
    print()
    print("%-6s %8s %14s  %s" % ("tag", "count", "bytes", "meaning"))
    print("%-6s %8s %14s  %s" % ("-" * 6, "-" * 8, "-" * 14, "-" * 24))
    for tag, count in tags.most_common():
        print("%-6s %8d %14d  %s"
              % (tag, count, tag_bytes[tag], KNOWN_TAGS.get(tag, "UNKNOWN -- new tag")))
    print()
    print("%-24s %8s %14s" % ("gap kind", "count", "bytes"))
    print("%-24s %8s %14s" % ("-" * 24, "-" * 8, "-" * 14))
    for kind, count in gaps.most_common():
        print("%-24s %8d %14d" % (kind, count, gap_bytes[kind]))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Reader for the NORM/MRON resource archive of tri-Ace's ASKA engine.")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, func, helptext in (
        ("scan", cmd_scan, "walk the container, listing archives and gaps"),
        ("census", cmd_census, "summarise resource types and gap kinds"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("file", help="ud1.bin / ud2.bin, or a disc image")
        s.add_argument("--offset", type=lambda x: int(x, 0), default=0,
                       help="byte offset of the container inside the file")
        s.add_argument("--length", type=lambda x: int(x, 0), default=None,
                       help="length of the container in bytes")
        if name == "scan":
            s.add_argument("--csv", help="write every entry to a CSV instead")
        s.set_defaults(func=func)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
