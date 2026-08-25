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

Two of those five collide with something else and are reported with a
structural check for that reason. `ASF ` is also Microsoft's Advanced Systems
Format, the container WMV ships in, and a disc with video on it has a great
deal of that -- Infinite Undiscovery's first disc carries 630 MB of it in the
container gaps alone. `AAC ` is also the audio codec, which is not what
tri-Ace means by it. Neither collision is a problem once the length field
behind the magic has to make sense as well.

**Structural constants.** The `SLZ` wrapper and its version byte; the
`0x0131F119` that opens an AI node field; the `MRON` entry table shape.

**The art pipeline.** Names the artists typed in Maya that survived onto the
shipped disc: the `R:M:` node prefix, `pColSphere` / `pColCube` / `pColCapsule`,
and `Tri_ace` itself, which is a node in the opening logo scene. These are
weaker evidence about the engine and stronger evidence about the studio, and
they survive changes to the binary formats that the magics would not.

**The shader toolchain.** `AHSL`, which names the shader cache the engine
writes -- `AHSLDiskCacheXe` on the Xbox 360, `AHSLDiskCachePs3_*` shipped as
loose files in the PlayStation 3 build -- and the profile data beside it. It is
listed among the pipeline names rather than above them because four ASCII
letters are four ASCII letters; what makes it worth sweeping for is that it is
the one name so far seen to survive a change of *platform*.

**The engine namespace.** `Aska::` in an executable's RTTI settles the question
outright. Two manglings are looked for, because tri-Ace did not stay on one
compiler: MSVC writes `@Aska@@`, which is what an Xbox 360 XEX carries once
`xex.py` has decrypted it, and the Itanium ABI that Clang and GCC use writes
its namespace length-prefixed, so `Aska` becomes `4Aska` inside `_ZN4Aska...`.
A PlayStation build will be the second kind.

**Endianness.** The ASCII *names* -- the versioned magics, the Maya node
prefixes, the namespace -- match unchanged whatever the byte order. The
**payload magics do not**, which was learned from a specimen rather than
assumed: a FourCC written out as a 32-bit word comes out reversed on a
little-endian build, and Star Ocean: Anamnesis on Android stores `AIF ` as
` FIA`. Those five, the `SLZ` wrapper and the node field constant are all
looked for both ways round. That asymmetry
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
LOOKBACK = 64              # so neither a signature nor a validator's field
                           # can fall between two chunks


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
    # A FourCC written out as a 32-bit word comes out reversed on a
    # little-endian build. Star Ocean: Anamnesis on Android stores `AIF ` as
    # ` FIA`, so the payload magics are looked for both ways round, and so is
    # the compression wrapper.
    ("ASF scene LE",     rb"\x20FSA",           "payload"),
    ("AAF animation LE", rb"\x20FAA",           "payload"),
    ("ACF collision LE", rb"\x20FCA",           "payload"),
    ("AIF image LE",     rb"\x20FIA",           "payload"),
    ("AAC audio LE",     rb"\x20CAA",           "payload"),
    ("SLZ wrapper LE",   rb"[\x00-\x0f]ZLS",    "structural"),
    ("AI node field",    rb"\x01\x31\xf1\x19",  "structural"),
    ("AI node field LE", rb"\x19\xf1\x31\x01",  "structural"),
    ("Aska:: namespace", rb"(?:Aska@@|@Aska@@|Aska::)", "namespace"),
    ("Aska, Itanium",    rb"(?:_ZN4Aska|N4Aska\d)", "namespace"),
    ("R:M: node prefix", rb"R:M:",              "pipeline"),
    ("pCol primitives",  rb"pCol(?:Sphere|Cube|Capsule)", "pipeline"),
    ("Tri_ace node",     rb"Tri_ace",           "pipeline"),
    ("AHSL shader tool", rb"AHSL",              "pipeline"),
]

WEIGHT = {"versioned": "conclusive", "namespace": "conclusive",
          "structural": "strong", "payload": "strong", "pipeline": "supporting"}


# A four-byte magic turns up by chance about once per four gigabytes, and an
# image is bigger than that, so raw counts are not worth much on their own.
# Where a signature is followed by a field of a knowable shape, check it -- in
# the sweep itself, while the bytes are still in the buffer.
#
# Sampling the first few hits instead does not work, and the way it fails is
# instructive: the earliest `SLZ` in a disc image is always a chance match in
# compressed data long before the containers begin, so a first-N sample scores
# zero and reads as evidence against a format that is in fact present 1 812
# times.

def _sane_mron(blob, at):
    if at + 16 > len(blob):
        return None
    count, align = struct.unpack_from(">2I", blob, at + 8)
    return 0 < count < 100000 and align and not align & (align - 1)


def _sane_slz(blob, at):
    """All three revisions of the wrapper.

    The name is the same in every title from 2005 on; the header is not.

    * **PlayStation 2**, Radiata Stories and Valkyrie Profile 2: little-endian,
      the compressed and uncompressed sizes at +0x04 and +0x08, a zero word at
      +0x0C, payload at +0x10.
    * **Xbox 360**, Infinite Undiscovery and Star Ocean 4: big-endian, a word
      inserted at +0x04 holding 0x20, so the size pair moves to +0x08 and
      +0x0C; an XCompress stream begins at +0x18.
    * **PlayStation 3**, Star Ocean 5: the size pair stays at +0x08 and +0x0C
      and the 0x20 moves to +0x14, where it really is the header size, because
      the payload begins at +0x20.

    Each revision is tested on its own terms, and the size pair has to make
    sense in all of them, which is what keeps a chance match out.
    """
    if at + 0x18 > len(blob):
        return None
    # PS2
    packed, plain, zero = struct.unpack_from("<3I", blob, at + 4)
    if 0 < packed <= plain and zero == 0:
        return True
    # Xbox 360 and PlayStation 3
    header, packed, plain = struct.unpack_from(">3I", blob, at + 4)
    later = struct.unpack_from(">I", blob, at + 0x14)[0]
    return 0 < packed <= plain and 0x20 in (header, later)


def _sane_length(blob, at):
    """ASF, AIF: a self-declared total length at +4 that is not absurd."""
    if at + 8 > len(blob):
        return None
    total = struct.unpack_from(">I", blob, at + 4)[0]
    return 0x20 <= total <= (1 << 28)


def _sane_node_field(blob, at, swap=False):
    if at + 0x2C > len(blob):
        return None
    fmt = "<7I" if swap else ">7I"
    _, spare, nodes, links, parts, at_nodes, at_links = \
        struct.unpack_from(fmt, blob, at)
    return (spare == 0 and 0 < nodes < 200000 and links < 400000
            and parts <= nodes and at_nodes == 0x2C and at_links > at_nodes)


def _sane_aac(blob, at):
    """`AAC `: a total size that makes sense, over two words that are zero.

    Added after Resonance of Fate, where the raw count was 185 on 7.3 GiB --
    a hundred times what chance produces -- and there was no test to say so,
    which is exactly the failure this column exists to prevent. The two zero
    words at +0x08 and +0x0C are zero in both revisions of the header seen so
    far, and two zero words behind a plausible size is not a chance match.
    """
    if at + 0x14 > len(blob):
        return None
    total, a, b = struct.unpack_from(">3I", blob, at + 4)
    return 0x40 <= total <= (1 << 26) and a == 0 and b == 0


def _sane_length_le(blob, at):
    """The same self-declared length, read the other way round."""
    if at + 8 > len(blob):
        return None
    total = struct.unpack_from("<I", blob, at + 4)[0]
    return 0x20 <= total <= (1 << 28)


def _sane_slz_le(blob, at):
    if at + 0x18 > len(blob):
        return None
    header, packed, plain = struct.unpack_from("<3I", blob, at + 4)
    later = struct.unpack_from("<I", blob, at + 0x14)[0]
    return 0 < packed <= plain and 0x20 in (header, later)


VALIDATORS = {
    "MRON container":  _sane_mron,
    "SLZ wrapper":     _sane_slz,
    "SLZ wrapper LE":  _sane_slz_le,
    "ASF scene":       _sane_length,
    "AIF image":       _sane_length,
    "AAC audio":       _sane_aac,
    "ASF scene LE":    _sane_length_le,
    "AIF image LE":    _sane_length_le,
    "AI node field":   _sane_node_field,
    "AI node field LE": lambda b, a: _sane_node_field(b, a, swap=True),
}


class Hit(object):

    __slots__ = ("name", "kind", "count", "sound", "checked", "where",
                 "good_where", "variants")

    def __init__(self, name, kind):
        self.name, self.kind = name, kind
        self.count = 0            # every match
        self.sound = 0            # matches whose following field is plausible
        self.checked = 0          # matches a validator could look at
        self.where = []
        self.good_where = []      # offsets that passed, which are the useful ones
        self.variants = {}

    def add(self, at, text, keep, sound):
        self.count += 1
        if len(self.where) < keep:
            self.where.append(at)
        if sound is not None:
            self.checked += 1
            if sound:
                self.sound += 1
                if len(self.good_where) < keep:
                    self.good_where.append(at)
        label = text.decode("latin-1", "replace")
        self.variants[label] = self.variants.get(label, 0) + 1

    @property
    def shown(self):
        """Offsets worth printing: the ones that passed, if any test applies."""
        return self.good_where if self.checked else self.where


def above_chance(size):
    """How many hits a signature with no structural test needs to mean anything.

    A specific four-byte sequence appears by chance about once per 2**32 bytes,
    so the expected count on an image is `size / 2**32`. Eight times that, and
    never fewer than four, is the bar used here: it passes every real row in
    [docs/aska-across-titles.md](../docs/aska-across-titles.md) and rejects
    every row that document already calls chance.
    """
    return max(4, 8.0 * size / float(1 << 32))


def sweep(path, keep=4, progress=None):
    """One pass over the file, collecting every signature at once."""
    pattern = re.compile(b"|".join(b"(" + p + b")" for _, p, _ in SIGNATURES))
    hits = [Hit(name, kind) for name, _, kind in SIGNATURES]
    checks = [VALIDATORS.get(name) for name, _, _ in SIGNATURES]
    size = os.path.getsize(path)
    done = 0
    with open(path, "rb") as fh:
        carry = b""        # tail of the previous chunk, prepended to this one
        start = 0          # global offset of `data`
        frontier = 0       # global offset up to which matches are accounted for
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            data = carry + block
            done += len(block)
            end = start + len(data)

            # The overlap means every chunk boundary is read twice, so each
            # match has to be attributed to exactly one of the two passes.
            # A match that begins in the last LOOKBACK bytes is left to the
            # next chunk, where the field its validator wants is present as
            # well; one that begins before that is taken here and skipped
            # there. At end of file there is no next chunk, so take the lot.
            limit = end if done >= size else end - LOOKBACK
            for match in pattern.finditer(data):
                at = start + match.start()
                if at < frontier or at >= limit:
                    continue
                which = match.lastindex - 1
                check = checks[which]
                sound = None if check is None else check(data, match.start())
                hits[which].add(at, match.group(), keep, sound)
            frontier = limit

            if progress:
                progress(done, size)
            carry = data[-LOOKBACK:]
            start = end - len(carry)
    return hits, size


# -- commands --------------------------------------------------------------

def cmd_identify(args):
    # A 7.8 GiB image takes about half an hour, and the cost is the matching
    # rather than the reading, so a faster disc does not help. Report progress
    # to the terminal continuously and to a redirected stdout every tenth, so a
    # run in the background is not silent for the whole of it.
    step = [0]

    def tick(done, size):
        if args.quiet:
            return
        share = 100.0 * done / max(size, 1)
        if sys.stderr.isatty():
            sys.stderr.write("\r  scanning %5.1f%%" % share)
            sys.stderr.flush()
        elif share >= step[0] + 10:
            step[0] = int(share // 10) * 10
            print("  scanning %3d%%" % step[0], flush=True)

    hits, size = sweep(args.file, args.limit, tick)
    if not args.quiet and sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 24 + "\r")

    print("%s  (%.2f GiB)" % (args.file, size / float(1 << 30)))
    print()
    print("%-20s %-12s %9s %11s  %s"
          % ("signature", "weight", "hits", "sound", "found at"))
    print("%-20s %-12s %9s %11s  %s"
          % ("-" * 20, "-" * 12, "-" * 9, "-" * 11, "-" * 30))
    for hit in hits:
        if not hit.count:
            continue
        where = ", ".join("0x%X" % w for w in hit.shown) or "-"
        sound = "%d" % hit.sound if hit.checked else ""
        print("%-20s %-12s %9d %11s  %s"
              % (hit.name, WEIGHT[hit.kind], hit.count, sound, where))
        if hit.kind == "versioned" and len(hit.variants) > 1:
            print("%-20s %s" % ("", "versions: " + ", ".join(
                "%s x%d" % (k, v) for k, v in sorted(hit.variants.items()))))
        elif hit.kind == "versioned":
            print("%-20s %s" % ("", "version: " + list(hit.variants)[0]))

    print()
    print("  \"sound\" counts the matches whose following field has a plausible")
    print("  shape. Where a signature has such a test, only sound matches are")
    print("  counted towards the verdict -- a bare four-byte magic turns up by")
    print("  chance about once per four gigabytes. Where there is no such test,")
    print("  a signature needs %d hits on a file this size to count at all."
          % int(above_chance(size)))

    print()
    found = {}
    for hit in hits:
        if hit.checked:
            # A signature with a structural test is judged on that test alone.
            strong = hit.sound > 0
        else:
            # One without a test is judged against chance. A four-byte magic
            # turns up about once per 4 GiB, so on a disc image a count of one
            # or three means nothing -- and before session 16 it was enough to
            # make this tool answer "probably ASKA". Eternal Sonata is the
            # worked example: every tested signature scored zero sound and
            # three untested ones scored 1, 1 and 3 on 7.3 GiB, and the verdict
            # came out positive on noise.
            strong = hit.count >= above_chance(size)
        if strong:
            found[hit.kind] = True
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
