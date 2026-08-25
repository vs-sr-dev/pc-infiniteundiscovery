#!/usr/bin/env python3
"""
pkg.py -- reader for the PlayStation 3 .pkg package.

Every other reader in this repository opens something tri-Ace wrote. This one
opens the wrapper Sony put around it, and exists for one reason: the third
specimen in the cross-title test -- Star Ocean: Integrity and Faithlessness,
Japanese PS3 build -- does not ship as a disc image. It ships as a PSN package,
and until the package is opened there is nothing for `aska.py` to sweep.

What a package is
-----------------
A 0xC0-byte big-endian header, a metadata block of typed records, and then one
encrypted run holding everything else: a table of items, the filenames those
items point at, and the file bodies. Offsets inside that run are relative to
its start, so the run decrypts as one stream and the table is read out of the
plaintext.

The encryption is AES-128 in counter mode. The key is the same for every retail
PS3 package and has been documented for many years; the counter starts at the
16-byte value the header carries at +0x70, which Sony's own tools call the
package RIV. Counter mode is what makes it possible to pull one file out of a
12 GB package without touching the rest: any offset decrypts on its own once
the counter has been advanced by the blocks in front of it.

What it does *not* do
---------------------
The NPDRM SELF executables in a game package -- `EBOOT.BIN` and its friends --
carry a second layer of encryption keyed by the licence in the accompanying
`.rap`, and this reader does not touch it. Those are the files an RTTI dump
would want, so on a PSN specimen **the executable route is closed** and the
evidence has to come from the data files, which are plain once the package is
open.

Self-checks
-----------
The same discipline as the other readers, and for a sharper reason here: a
wrong key produces a table of garbage that still prints. The item table must
lie inside the data run; every item body must lie inside it too; every filename
must be printable ASCII and must sit between the table and the first body; the
header's total size must match the file. `list` and `extract` refuse to run
until all of them pass.

Reproducing
-----------
    python tools/pkg.py info <pkg>
    python tools/pkg.py list <pkg> [--only SUBSTRING] [--type N]
    python tools/pkg.py extract <pkg> <outdir> [--only SUBSTRING]
    python tools/pkg.py decrypt <pkg> <out.bin>
"""

import argparse
import os
import re
import struct
import sys

try:
    from Crypto.Cipher import AES
except ImportError:                                        # pragma: no cover
    AES = None


MAGIC = b"\x7fPKG"

# The retail PS3 package key -- a constant, the same in every retail package.
PS3_AES_KEY = bytes.fromhex("2e7b71d7c9c9a14ea3221f188828b8f8")

HEADER_SIZE = 0xC0
ITEM_SIZE = 0x20
CHUNK = 1 << 24

# The low byte of an item's flag word says what the body is.
ITEM_TYPES = {
    0x01: "NPDRM SELF",
    0x02: "NPDRM EDAT",
    0x03: "file",
    0x04: "directory",
    0x09: "SDAT",
}

# Metadata record ids worth naming; the rest print by number.
META_NAMES = {
    0x01: "drm type",
    0x02: "content type",
    0x03: "package type",
    0x04: "package size",
    0x05: "make_package_npdrm revision",
    0x06: "title id",
    0x07: "qa digest",
    0x08: "software version",
    0x09: "unknown-9",
    0x0A: "install directory",
    0x0B: "unknown-B",
    0x0D: "unknown-D",
}

DRM_TYPES = {0: "none", 1: "network", 2: "local (needs a .rap)", 3: "free"}

# The content-type numbers are Sony's and the published tables disagree about
# several of them, so only the number is printed. Nothing here depends on it.


class Package(object):
    """A package opened but not yet trusted: the checks are separate."""

    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        self.fh = open(path, "rb")
        head = self.fh.read(HEADER_SIZE)
        if head[:4] != MAGIC:
            raise ValueError("not a PKG: magic is %r" % head[:4])
        (self.revision, self.pkg_type, self.meta_offset, self.meta_count,
         self.header_size, self.item_count, self.total_size, self.data_offset,
         self.data_size) = struct.unpack_from(">2H4I3Q", head, 4)
        self.content_id = head[0x30:0x54].split(b"\0")[0].decode("latin-1")
        self.digest = head[0x60:0x70]
        self.riv = head[0x70:0x80]
        # 0x8000 is the retail revision. The evidence for that reading is
        # empirical and it is in `checks()`: the retail key is the one that
        # turns this file into a table of printable filenames.
        self.retail = self.revision == 0x8000
        self._table = None

    # -- the encrypted run -------------------------------------------------

    def _cipher_at(self, at):
        """A cipher positioned `at` bytes into the data run."""
        if AES is None:
            raise SystemExit("pkg.py needs pycryptodome "
                             "(pip install pycryptodome)")
        counter = (int.from_bytes(self.riv, "big") + (at // 16)) \
            & ((1 << 128) - 1)
        return AES.new(PS3_AES_KEY, AES.MODE_CTR, nonce=b"",
                       initial_value=counter.to_bytes(16, "big"))

    def read(self, at, length):
        """Plaintext of `length` bytes at `at` inside the data run."""
        skew = at % 16
        base = at - skew
        self.fh.seek(self.data_offset + base)
        raw = self.fh.read(length + skew)
        return self._cipher_at(base).decrypt(raw)[skew:skew + length]

    # -- the item table ----------------------------------------------------

    @property
    def table(self):
        if self._table is None:
            self._table = self._read_table()
        return self._table

    def _read_table(self):
        blob = self.read(0, self.item_count * ITEM_SIZE)
        items = []
        for i in range(self.item_count):
            name_at, name_len, body_at, body_len, flags = \
                struct.unpack_from(">2I2QI", blob, i * ITEM_SIZE)
            items.append({"index": i, "name_at": name_at, "name_len": name_len,
                          "at": body_at, "size": body_len, "flags": flags,
                          "type": flags & 0xFF, "name": None})
        # The names sit in one run just past the table. Read it whole rather
        # than seeking once per item -- there are tens of thousands of them.
        if items:
            lo = min(it["name_at"] for it in items)
            hi = max(it["name_at"] + it["name_len"] for it in items)
            if 0 <= lo <= hi <= self.data_size and hi - lo < (1 << 26):
                names = self.read(lo, hi - lo)
                for it in items:
                    start = it["name_at"] - lo
                    it["name"] = names[start:start + it["name_len"]]
        return items

    def checks(self):
        """Every invariant, as (description, ok, detail)."""
        out = [("magic and revision", True, "%s, revision 0x%04X"
                % ("retail" if self.retail else "debug", self.revision)),
               ("total size matches the file", self.total_size == self.size,
                "header says %d, file is %d" % (self.total_size, self.size)),
               ("data run inside the file",
                self.data_offset + self.data_size <= self.size,
                "0x%X + 0x%X" % (self.data_offset, self.data_size))]
        table_end = self.item_count * ITEM_SIZE
        out.append(("item table inside the data run",
                    table_end <= self.data_size,
                    "%d items, 0x%X bytes" % (self.item_count, table_end)))
        if table_end > self.data_size:
            return out

        items = self.table
        outside = [it for it in items if it["at"] + it["size"] > self.data_size]
        out.append(("every body inside the data run", not outside,
                    "%d outside" % len(outside)))
        printable = [it for it in items
                     if re.fullmatch(rb"[\x20-\x7e]+", it["name"] or b"")]
        out.append(("every filename printable ASCII",
                    len(printable) == len(items),
                    "%d of %d" % (len(printable), len(items))))
        first = min((it["at"] for it in items if it["size"]), default=0)
        names_end = max((it["name_at"] + it["name_len"] for it in items),
                        default=0)
        out.append(("names between the table and the first body",
                    table_end <= names_end <= (first or names_end),
                    "table ends 0x%X, names end 0x%X, first body 0x%X"
                    % (table_end, names_end, first)))
        return out


def human(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return "%d B" % size if unit == "B" else "%.1f %s" % (value, unit)
        value /= 1024.0


def _open_checked(path):
    pkg = Package(path)
    if not all(good for _, good, _ in pkg.checks()):
        raise SystemExit("checks failed -- run `info`. A wrong key gives a "
                         "table of garbage that still prints.")
    return pkg


# -- commands --------------------------------------------------------------

def cmd_info(args):
    pkg = Package(args.file)
    print("%s  (%s)" % (os.path.basename(args.file), human(pkg.size)))
    print()
    print("  content id     %s" % pkg.content_id)
    print("  package type   0x%04X (%s)" % (pkg.pkg_type,
          {1: "PS3", 2: "PSP/PSVita"}.get(pkg.pkg_type, "?")))
    print("  items          %d" % pkg.item_count)
    print("  data run       0x%X .. 0x%X  (%s)"
          % (pkg.data_offset, pkg.data_offset + pkg.data_size,
             human(pkg.data_size)))
    print("  riv            %s" % pkg.riv.hex())
    print("  qa digest      %s" % pkg.digest.hex())

    # The metadata block runs from where the header points at it to the start
    # of the encrypted run; `header_size` at +0x10 is the header's own size and
    # is not a bound on it.
    pkg.fh.seek(pkg.meta_offset)
    meta = pkg.fh.read(max(0, pkg.data_offset - pkg.meta_offset))
    print()
    print("  metadata")
    at = 0
    for _ in range(pkg.meta_count):
        if at + 8 > len(meta):
            break
        rid, size = struct.unpack_from(">2I", meta, at)
        body = meta[at + 8:at + 8 + size]
        at += 8 + size
        name = META_NAMES.get(rid, "record 0x%02X" % rid)
        if rid == 0x06:
            shown = body.split(b"\0")[0].decode("latin-1")
        elif rid == 0x01:
            value = int.from_bytes(body[:4], "big")
            shown = "%d (%s)" % (value, DRM_TYPES.get(value, "?"))
        elif rid == 0x02:
            shown = "%d" % int.from_bytes(body[:4], "big")
        elif rid == 0x04:
            shown = human(int.from_bytes(body[:8], "big"))
        elif rid == 0x0A:
            shown = body[8:].split(b"\0")[0].decode("latin-1")
        else:
            shown = body.hex()[:32] + ("..." if size > 16 else "")
        print("    %-28s %s" % (name, shown))

    print()
    print("  checks")
    ok = True
    for what, good, detail in pkg.checks():
        ok = ok and bool(good)
        print("    %-4s %-44s %s" % ("ok" if good else "BAD", what, detail))
    print()
    print("  %s" % ("all checks pass -- the key is right and the table is real"
                    if ok else "CHECKS FAILED -- do not trust the table"))
    return 0 if ok else 1


def cmd_list(args):
    pkg = _open_checked(args.file)
    kinds, total = {}, 0
    for it in pkg.table:
        name = (it["name"] or b"?").decode("latin-1")
        kind = ITEM_TYPES.get(it["type"], "type 0x%02X" % it["type"])
        kinds[kind] = kinds.get(kind, 0) + 1
        total += it["size"]
        if args.type is not None and it["type"] != args.type:
            continue
        if args.only and args.only not in name:
            continue
        print("%6d  %-12s %12d  0x%011X  %s"
              % (it["index"], kind, it["size"], it["at"], name))
    print()
    print("  %d items, %s of bodies" % (len(pkg.table), human(total)))
    print("  " + ", ".join("%s x%d" % (k, v) for k, v in sorted(kinds.items())))

    ext = {}
    for it in pkg.table:
        if it["type"] == 4:
            continue
        name = (it["name"] or b"").decode("latin-1")
        suffix = os.path.splitext(name)[1].lower() or "(none)"
        entry = ext.setdefault(suffix, [0, 0])
        entry[0] += 1
        entry[1] += it["size"]
    print()
    print("  by extension")
    for suffix, (count, size) in sorted(ext.items(),
                                        key=lambda kv: -kv[1][1])[:20]:
        print("    %-12s %6d files  %10s" % (suffix, count, human(size)))
    return 0


def cmd_extract(args):
    pkg = _open_checked(args.file)
    written = 0
    for it in pkg.table:
        name = (it["name"] or b"").decode("latin-1")
        if it["type"] == 4 or not name:
            continue
        if args.only and args.only not in name:
            continue
        if args.max_size and it["size"] > args.max_size:
            continue
        dest = os.path.join(args.outdir, name.replace("\\", "/"))
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        left, at = it["size"], it["at"]
        with open(dest, "wb") as out:
            while left:
                take = min(left, CHUNK)
                out.write(pkg.read(at, take))
                at += take
                left -= take
        written += 1
        print("  %12d  %s" % (it["size"], name))
    print()
    print("  %d files written to %s" % (written, args.outdir))
    return 0


def cmd_decrypt(args):
    """The whole data run as one plaintext file, offsets preserved.

    This is what `aska.py identify` wants: one stream to sweep, in which an
    offset means the same thing it means inside the package.
    """
    pkg = Package(args.file)
    at, left, done = 0, pkg.data_size, 0
    with open(args.out, "wb") as out:
        while left:
            take = min(left, CHUNK)
            out.write(pkg.read(at, take))
            at += take
            left -= take
            done += take
            if sys.stderr.isatty():
                sys.stderr.write("\r  decrypting %5.1f%%"
                                 % (100.0 * done / pkg.data_size))
                sys.stderr.flush()
    if sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 24 + "\r")
    print("  %s -> %s (%s)" % (os.path.basename(args.file), args.out,
                               human(pkg.data_size)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Reader for PlayStation 3 .pkg packages.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="header, metadata and self-checks")
    p.add_argument("file")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("list", help="list the items")
    p.add_argument("file")
    p.add_argument("--only", help="only names containing this")
    p.add_argument("--type", type=int, help="only this item type")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("extract", help="write item bodies out")
    p.add_argument("file")
    p.add_argument("outdir")
    p.add_argument("--only", help="only names containing this")
    p.add_argument("--max-size", type=int, help="skip bodies larger than this")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("decrypt", help="the whole data run as plaintext")
    p.add_argument("file")
    p.add_argument("out")
    p.set_defaults(func=cmd_decrypt)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
