#!/usr/bin/env python3
"""
aska.py -- is this tri-Ace's ASKA engine?

Everything else in this repository assumes the answer is yes and reads
Infinite Undiscovery. This one asks the question, of any file: a disc image, a
container, an executable, a loose payload. Point it at something and it reports
which ASKA signatures are present and where.

The point is that the signatures are *arbitrary*. Nothing forced tri-Ace to
reverse a FourCC and staple an ASCII version to it, or to call a compression
wrapper `SLZ`, or to open a navigation mesh with `0x0131F119`. Those are
choices, and a choice repeated in another title is evidence in a way that a
common structure never is.

What it looks for
-----------------
**Versioned magics.** A byte-reversed FourCC then an ASCII version, the
convention the container uses for itself and five payloads use after it. The
version digits are reported rather than required, because a later title is very
likely to have bumped them -- and a bumped version is a more interesting
finding than an exact match, since the difference between two revisions of the
same format tends to explain the fields that a single revision leaves opaque.

**Payload magics.** The `A?F` family -- an A for Aska, a letter for the
content, an F for file, padded to four bytes -- plus `AAC `, which breaks the
naming because it is a container rather than a file.

**Structural constants.** The `SLZ` wrapper and its version byte; the
`0x0131F119` that opens an AI node field; the `MRON` entry table shape.

**The art pipeline.** Names the artists typed in Maya that survived onto the
shipped disc: the `R:M:` node prefix, `pColSphere` / `pColCube` / `pColCapsule`,
and `Tri_ace` itself, which is a node in the opening logo scene. These are
weaker evidence about the engine and stronger evidence about the studio, and
they survive changes to the binary formats that the magics would not.

**The engine namespace.** `Aska::` in an executable's RTTI settles the question
outright. Two manglings are looked for, because tri-Ace did not stay on one
compiler: MSVC writes `@Aska@@`, which is what an Xbox 360 XEX carries once
`xex.py` has decrypted it, and the Itanium ABI that Clang and GCC use writes
its namespace length-prefixed, so `Aska` becomes `4Aska` inside `_ZN4Aska...`.
A PlayStation build will be the second kind.

**Endianness.** Every signature above except one is ASCII, so a little-endian
title -- a PC port, or anything on x86 -- matches them unchanged. The exception
is the node field constant, which is looked for both ways round. That asymmetry
is worth knowing: **the conclusive tests survive a change of byte order, and
the readers do not.** Finding the magics on a little-endian title would say the
format is the same while every `struct` format string in this repository would
still need flipping to read it.

Reading the result
------------------
The tests are asymmetric, and the summary says so. A hit on the versioned
magics or the namespace is conclusive. **A miss proves very little**: a studio
can change its container while keeping its scene format, and the platform layer
-- texture tiling, audio codec, compression -- is expected to differ on
anything that is not an Xbox 360.

Reproducing
-----------
    python tools/aska.py identify <file>
    python tools/aska.py identify <file> --limit 8 --json out.json
"""

import argparse
import json
import os
import re
import struct
import sys

CHUNK = 1 << 24            # 16 MB at a time
LOOKBACK = 64              # so a signature cannot fall between two chunks


# (name, pattern, kind) -- kind decides how the summary weighs it.
SIGNATURES = [
    ("MRON container",   rb"MRON\d\d\.\d",      "versioned"),
    ("SNC scene script", rb"-CNS\d\d\.\d",      "versioned"),
    ("AREA",             rb"AERA\d\d\.\d",      "versioned"),
    ("MINI",             rb"INIM\d\d\.\d",      "versioned"),
    ("SIG- signal",      rb"-GIS\d\d\.\d",      "versioned"),
    ("ASF scene",        rb"ASF ",              "payload"),
    ("AAF animation",    rb"AAF ",              "payload"),
    ("ACF collision",    rb"ACF ",              "payload"),
    ("AIF image",        rb"AIF ",              "payload"),
    ("AAC audio",        rb"AAC ",              "payload"),
    ("SLZ wrapper",      rb"SLZ[\x00-\x0f]",    "structural"),
    ("AI node field",    rb"\x01\x31\xf1\x19",  "structural"),
    ("AI node field LE", rb"\x19\xf1\x31\x01",  "structural"),
    ("Aska:: namespace", rb"(?:Aska@@|@Aska@@|Aska::)", "namespace"),
    ("Aska, Itanium",    rb"(?:_ZN4Aska|N4Aska\d)", "namespace"),
    ("R:M: node prefix", rb"R:M:",              "pipeline"),
    ("pCol primitives",  rb"pCol(?:Sphere|Cube|Capsule)", "pipeline"),
    ("Tri_ace node",     rb"Tri_ace",           "pipeline"),
]

WEIGHT = {"versioned": "conclusive", "namespace": "conclusive",
          "structural": "strong", "payload": "strong", "pipeline": "supporting"}


class Hit(object):

    __slots__ = ("name", "kind", "count", "where", "variants")

    def __init__(self, name, kind):
        self.name, self.kind = name, kind
        self.count = 0
        self.where = []
        self.variants = {}

    def add(self, at, text, keep):
        self.count += 1
        if len(self.where) < keep:
            self.where.append(at)
        label = text.decode("latin-1", "replace")
        self.variants[label] = self.variants.get(label, 0) + 1


def sweep(path, keep=4, progress=None):
    """One pass over the file, collecting every signature at once."""
    pattern = re.compile(b"|".join(b"(" + p + b")" for _, p, _ in SIGNATURES))
    hits = [Hit(name, kind) for name, _, kind in SIGNATURES]
    size = os.path.getsize(path)
    done = 0
    with open(path, "rb") as fh:
        carry = b""
        base = 0
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            data = carry + block
            for match in pattern.finditer(data):
                which = match.lastindex - 1
                hits[which].add(base - len(carry) + match.start(),
                                match.group(), keep)
            base += len(block)
            done += len(block)
            if progress:
                progress(done, size)
            carry = data[-LOOKBACK:]
    return hits, size


def validate(path, hits):
    """Cheap structural checks on the two signatures that carry a shape.

    A four-byte magic turns up by chance roughly once per four gigabytes, so
    the counts alone are not worth much on their own. These are.
    """
    out = {}
    with open(path, "rb") as fh:
        for hit in hits:
            if hit.name == "MRON container":
                good = 0
                for at in hit.where:
                    fh.seek(at + 8)
                    raw = fh.read(8)
                    if len(raw) < 8:
                        continue
                    count, align = struct.unpack(">2I", raw)
                    if 0 < count < 100000 and align and not align & (align - 1):
                        good += 1
                out["MRON entry table is sane"] = (good, len(hit.where))
            if hit.name == "SLZ wrapper":
                good = 0
                for at in hit.where:
                    fh.seek(at + 4)
                    raw = fh.read(12)
                    if len(raw) < 12:
                        continue
                    header, packed, plain = struct.unpack(">3I", raw)
                    if header == 0x20 and packed and plain >= packed:
                        good += 1
                out["SLZ header is sane"] = (good, len(hit.where))
    return out


# -- commands --------------------------------------------------------------

def cmd_identify(args):
    def tick(done, size):
        if args.quiet or not sys.stderr.isatty():
            return
        sys.stderr.write("\r  scanning %5.1f%%" % (100.0 * done / max(size, 1)))
        sys.stderr.flush()

    hits, size = sweep(args.file, args.limit, tick)
    if not args.quiet and sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 24 + "\r")

    print("%s  (%.2f GiB)" % (args.file, size / float(1 << 30)))
    print()
    print("%-20s %-12s %9s  %s" % ("signature", "weight", "hits", "first at"))
    print("%-20s %-12s %9s  %s" % ("-" * 20, "-" * 12, "-" * 9, "-" * 30))
    for hit in hits:
        if not hit.count:
            continue
        where = ", ".join("0x%X" % w for w in hit.where)
        print("%-20s %-12s %9d  %s" % (hit.name, WEIGHT[hit.kind],
                                       hit.count, where))
        if hit.kind == "versioned" and len(hit.variants) > 1:
            print("%-20s %s" % ("", "versions: " + ", ".join(
                "%s x%d" % (k, v) for k, v in sorted(hit.variants.items()))))
        elif hit.kind == "versioned":
            print("%-20s %s" % ("", "version: " + list(hit.variants)[0]))

    checks = validate(args.file, hits)
    if checks:
        print()
        for what, (good, total) in sorted(checks.items()):
            if total:
                print("  %-34s %d of the %d sampled" % (what, good, total))

    print()
    found = dict((h.kind, True) for h in hits if h.count)
    if found.get("versioned") or found.get("namespace"):
        print("  VERDICT: ASKA. A byte-reversed FourCC with an ASCII version, or")
        print("           the engine namespace, is not something another studio")
        print("           arrives at by coincidence.")
    elif found.get("structural") or found.get("payload"):
        print("  VERDICT: probably ASKA, on payload magics alone. Look for a")
        print("           container before believing it.")
    elif found.get("pipeline"):
        print("  VERDICT: tri-Ace art, engine unproven. The Maya names survived")
        print("           but none of the binary formats did.")
    else:
        print("  VERDICT: nothing found -- which settles very little. The")
        print("           container may have changed while the payloads did")
        print("           not, and the file may be packed or encrypted. Try an")
        print("           executable through xex.py and rtti.py instead.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"file": os.path.basename(args.file), "size": size,
                       "hits": [{"name": h.name, "kind": h.kind,
                                 "count": h.count, "where": h.where,
                                 "variants": h.variants}
                                for h in hits if h.count]}, fh, indent=2)
        print("\nwrote %s" % args.json)
    return 0


def cmd_compare(args):
    """Put two sweeps side by side -- one title against another."""
    reports = []
    for path in args.files:
        with open(path, encoding="utf-8") as fh:
            reports.append(json.load(fh))
    names = [r["file"] for r in reports]
    print("%-20s %s" % ("signature", "  ".join("%18s" % n[:18] for n in names)))
    print("%-20s %s" % ("-" * 20, "  ".join("%18s" % ("-" * 18) for _ in names)))
    every = []
    for name, _, _ in SIGNATURES:
        if any(any(h["name"] == name for h in r["hits"]) for r in reports):
            every.append(name)
    for name in every:
        cells = []
        for report in reports:
            hit = next((h for h in report["hits"] if h["name"] == name), None)
            if hit is None:
                cells.append("%18s" % "-")
            elif hit["kind"] == "versioned":
                cells.append("%18s" % ("%d %s" % (hit["count"],
                                                  sorted(hit["variants"])[0])))
            else:
                cells.append("%18d" % hit["count"])
        print("%-20s %s" % (name, "  ".join(cells)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Test a file for tri-Ace ASKA engine signatures.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("identify", help="sweep a file for ASKA signatures")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=4,
                   help="how many offsets to remember per signature")
    s.add_argument("--json", help="also write the result as JSON")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_identify)

    s = sub.add_parser("compare", help="put JSON reports side by side")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_compare)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
