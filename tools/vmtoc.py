#!/usr/bin/env python3
"""
vmtoc.py -- Eternal Sonata's archive index and the two compression layers
behind it.

Eternal Sonata (tri-Crescendo, Xbox 360, 2007) ships an ordinary directory
tree with no container, and an index called `index.vmtoc` that says, per file,
how big it is uncompressed and which of four methods compressed it. Session 16
read the index and method 1; session 18 read the rest, off `default.xex`.

The index
---------
1 105 records of 48 bytes, big-endian:

    0x00  32  path, lower case, backslash-separated, NUL-padded
    0x20   4  uncompressed size
    0x24   4  method, in the top byte; the rest zero
    0x28   4  zero
    0x2C   4  Unix timestamp

The method byte is two flags, not four codecs
---------------------------------------------
This is the thing worth knowing, and it is not visible from the outside. The
loader tests **individual bits** of that byte in two different places:

    0x8210E0FC   rlwinm. r10, r10, 0, 30, 30     bit 1 -- the range coder
    0x8210E284   clrlwi. r11, r11, 31            bit 0 -- the LZSS layer

So the four values are a two-bit field, and method 3 is not a third codec but
**method 1 running on top of method 2**:

| Method | Bit 1 | Bit 0 | | Files |
| --- | --- | --- | --- | ---: |
| 0 | | | stored | 136 |
| 1 | | LZSS | LZSS over raw bytes | 8 |
| 2 | coder | | range coder alone | 13 |
| 3 | coder | LZSS | LZSS over the range coder | 948 |

The two layers meet at one function, `0x8210E0F8`, which returns the next byte
of the stream: raw from the input buffer when bit 1 is clear, and a decoded
symbol when it is set. Everything above it is written once and works either
way. That is why the disassembly is short and why the file counts look the way
they do -- 948 files use both layers because both layers are free.

Which method a file gets is decided per file rather than per type: the 13 that
use the coder alone are neither the largest files nor a single extension. The
one rule that does hold is that **all 136 stored files are audio** -- 62
`.cxs`, 60 `.csf`, 14 `.wav` -- so already-compressed data is left alone.

Layer 1: Okumura's LZSS, unmodified
-----------------------------------
Not a variant of tri-Ace's: the reference implementation. `0x8210E0C0`
memsets a **4 096-byte ring buffer** and sets the write position to **0xFEE**,
which is `N - F` for `N = 4096, F = 18` -- the initialiser in Haruhiko
Okumura's `lzss.c`, the routine LHA descends from. `THRESHOLD` is 2, giving
the same 3..18 lengths. The one departure is the fill: Okumura primes the
window with spaces and this primes it with zeroes, which is what most of the
routine's descendants do.

    flag byte    eight tokens, least significant bit first
    1            a literal byte
    0            two bytes, `a` then `b`:
                     ring position = a | ((b >> 4) << 8)    -- absolute, 12-bit
                     length        = (b & 0x0F) + 3         -- 3 .. 18

Every byte written, literal or copied, also goes into the ring buffer.

**The position is absolute, not a distance**, and that is the correction this
file exists to record. Session 16 decoded these files with tri-Ace's
sliding-window reader and two nibbles swapped, and reported 8 of 8 successes --
but both of its tests, output size and input consumed, are blind to *where* a
match copies from. Content is not: under the ring reading `op.bmd` resolves to
16-byte records with ascending offsets, and under the window reading the same
bytes interleave into nothing. See
[aska-across-titles.md](../docs/aska-across-titles.md).

The distinction cuts the other way too, and was checked in both directions.
tri-Ace's method 1 really is a sliding window: over 40 Star Ocean 3 blocks the
window reading produces `Bip01` **1 356** times and the ring reading 63, and
only the window reading reconstructs the header word at `+0x0C`.

Layer 2: Subbotin's carryless range coder, order-0 and static
-------------------------------------------------------------
Also a stock routine -- Dmitry Subbotin's carryless range coder, with
`TOP = 1 << 24` and `BOT = 0x2000`. The renormalisation at `0x8210E18C` is the
published loop step for step -- identified by its structure, not by comparing
against compiled reference code -- including the underflow case that rebuilds
the range out of `-low`:

    while ((low ^ (low + range)) < TOP)       { code = code<<8 | *in++; low <<= 8; range <<= 8; }
    while (range < BOT)                       { code = code<<8 | *in++; range = (-low & (BOT-1)) << 8; low <<= 8; }

The model is **static, and shipped in the stream**: the first **256 bytes** of
a method-2 or method-3 file are one frequency per symbol. The decoder builds a
cumulative table from them, then an inverse table mapping a scaled value back
to a symbol -- which is why the buffer for it is `0x2000` bytes and why `BOT`
is `0x2000`: the frequencies are normalised so they sum to no more than that.
Four bytes prime the code register and decoding begins.

    freq[s]        the 256 header bytes
    cum[s]         running sum, u16
    total          cum[256]
    inv[v]         the symbol whose cumulative interval contains v

    range /= total
    value  = (code - low) / range
    symbol = inv[value]
    low   += cum[symbol] * range
    range *= freq[symbol]

Nothing is adaptive. A file is one static model and one arithmetic stream.

What that says about the studio
-------------------------------
Both layers are famous public-domain routines. Session 16 argued from the
codec that "the oldest layer travelled with the people" who left tri-Ace, on
the strength of tri-Crescendo's LZSS being tri-Ace's with two nibbles swapped.
It is the other way around: **tri-Crescendo's is the textbook routine and
tri-Ace's is the one that deviates** -- a true sliding window, and the nibbles
the other way from Okumura. Two teams reaching for the same well-known LZSS is
an ordinary event. What still needs explaining is the *convention* around it --
a method code of 0 to 3 with 0 meaning stored, and four-character space-padded
big-endian magics with the size behind them -- and that is a weaker but still
real resemblance.

    python tools/vmtoc.py list    "iso/Eternal Sonata ....iso"
    python tools/vmtoc.py verify  "iso/Eternal Sonata ....iso" --limit 1048576
    python tools/vmtoc.py extract "iso/Eternal Sonata ....iso" extract/es --only btldata/
"""

import argparse
import collections
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xdvdfs import XdvdfsImage, SECTOR

MASK = 0xFFFFFFFF
RECORD_SIZE = 0x30

METHOD_LZSS = 1
METHOD_CODER = 2

RING_SIZE = 0x1000
RING_START = 0xFEE          # N - F, straight out of Okumura's lzss.c
MIN_MATCH = 3


class VmtocError(Exception):
    pass


class RangeDecoder:
    """Subbotin's carryless range coder over a static order-0 model.

    The model is the first 256 bytes of the stream, one frequency per symbol.
    """

    TOP = 1 << 24
    BOT = 0x2000

    def __init__(self, src):
        self.src = src
        self.at = 0
        self.freq = [0] * 256
        self.cum = [0] * 257
        for symbol in range(256):
            self.freq[symbol] = self._byte()
            self.cum[symbol + 1] = (self.cum[symbol] + self.freq[symbol]) & 0xFFFF
        self.total = self.cum[256]
        if self.total == 0:
            raise VmtocError("the model's frequencies are all zero")
        self.inv = bytearray(self.total)
        at = 0
        for symbol in range(256):
            while at < self.cum[symbol + 1]:
                self.inv[at] = symbol
                at += 1
        self.low = 0
        self.code = 0
        self.range = MASK
        for _ in range(4):
            self.code = ((self.code << 8) | self._byte()) & MASK

    def _byte(self):
        if self.at >= len(self.src):
            raise EOFError
        value = self.src[self.at]
        self.at += 1
        return value

    def get(self):
        low, rng, code = self.low, self.range, self.code
        # Renormalise: first while the top bytes of low and low+range agree,
        # then while the range has collapsed below BOT.
        while ((((low + rng) & MASK) ^ low) & MASK) < self.TOP:
            code = ((code << 8) | self._byte()) & MASK
            low = (low << 8) & MASK
            rng = (rng << 8) & MASK
        while rng < self.BOT:
            code = ((code << 8) | self._byte()) & MASK
            rng = ((((-low) & MASK) & (self.BOT - 1)) << 8) & MASK
            low = (low << 8) & MASK
        rng //= self.total
        value = ((code - low) & MASK) // rng
        if value >= self.total:                     # a truncated stream
            raise EOFError
        symbol = self.inv[value]
        self.low = (low + self.cum[symbol] * rng) & MASK
        self.range = (rng * self.freq[symbol]) & MASK
        self.code = code
        return symbol

    @property
    def consumed(self):
        return self.at


class RawReader:
    """The other half of the same interface: bytes straight off the input."""

    def __init__(self, src):
        self.src = src
        self.at = 0

    def get(self):
        if self.at >= len(self.src):
            raise EOFError
        value = self.src[self.at]
        self.at += 1
        return value

    @property
    def consumed(self):
        return self.at


def unpack(src, size, method):
    """Decode one shipped file. Returns (output, input bytes consumed)."""
    reader = RangeDecoder(src) if method & METHOD_CODER else RawReader(src)
    out = bytearray()

    if not method & METHOD_LZSS:
        try:
            while len(out) < size:
                out.append(reader.get())
        except EOFError:
            pass
        return bytes(out[:size]), reader.consumed

    ring = bytearray(RING_SIZE)
    write = RING_START
    left = size
    flags = 0
    mask = 1
    state = 0
    first = 0
    try:
        while left > 0:
            token = reader.get()
            if state == 0:
                flags = token
                mask = 1
                state = 1 if token & 1 else 2
                continue
            if state == 1:
                out.append(token)
                left -= 1
                ring[write] = token
                write = (write + 1) & (RING_SIZE - 1)
            elif state == 2:
                first = token
                state = 3
                continue
            else:
                length = (token & 0x0F) + MIN_MATCH
                read = (((token >> 4) << 8) | first) & (RING_SIZE - 1)
                left -= length
                for _ in range(length):
                    value = ring[read]
                    read = (read + 1) & (RING_SIZE - 1)
                    out.append(value)
                    ring[write] = value
                    write = (write + 1) & (RING_SIZE - 1)
            mask = (mask << 1) & 0xFF
            state = (1 if flags & mask else 2) if mask else 0
    except EOFError:
        pass
    return bytes(out[:size]), reader.consumed


class Archive:
    """An Eternal Sonata disc, read through its index."""

    def __init__(self, path):
        self.image = XdvdfsImage(path)
        self.files = {}
        for entry in self.image.entries():
            if entry.attributes & 0x10:
                continue
            key = entry.path.replace(chr(92), "/").lstrip("/").lower()
            self.files[key] = entry
        if "index.vmtoc" not in self.files:
            raise VmtocError("%s has no index.vmtoc" % path)
        toc = self.read("index.vmtoc")
        if len(toc) % RECORD_SIZE:
            raise VmtocError("index.vmtoc is not a whole number of records")
        self.records = []
        for at in range(0, len(toc), RECORD_SIZE):
            path_ = toc[at:at + 0x20].rstrip(b"\0").decode("latin-1")
            size, method, spare, stamp = struct.unpack_from(">4I", toc, at + 0x20)
            self.records.append((path_.replace(chr(92), "/").lower(),
                                 size, method >> 24, stamp))

    def read(self, key):
        entry = self.files[key]
        self.image.fh.seek(self.image.base + entry.sector * SECTOR)
        return self.image.fh.read(entry.size)

    def on_disc(self, key):
        entry = self.files.get(key)
        return entry.size if entry else None


def cmd_list(args):
    archive = Archive(args.image)
    methods = collections.Counter()
    for path, size, method, stamp in archive.records:
        methods[method] += 1
        if args.verbose:
            print("%-34s %9d  method %d  %s"
                  % (path, size, method,
                     time.strftime("%Y-%m-%d", time.gmtime(stamp))))
    print("%d records" % len(archive.records))
    for method in sorted(methods):
        print("  method %d : %5d  (%s)"
              % (method, methods[method], describe(method)))
    return 0


def describe(method):
    if not method:
        return "stored"
    parts = []
    if method & METHOD_CODER:
        parts.append("range coder")
    if method & METHOD_LZSS:
        parts.append("LZSS")
    return " + ".join(reversed(parts))


def cmd_verify(args):
    """Decode every file small enough and check it on both sides.

    Two tests, and only the first is obvious: the output is exactly the size
    the index states, and the input is consumed to within the four bytes the
    encoder pads with. A third is free where the payload carries its own
    length at +0x04, which most of them do.
    """
    archive = Archive(args.image)
    tried = collections.Counter()
    good = collections.Counter()
    over = collections.Counter()
    slack = collections.Counter()
    magics = collections.Counter()
    raw = collections.Counter()
    out = collections.Counter()
    failures = []
    declared_ok = declared_seen = 0
    declared_by_tag = collections.defaultdict(collections.Counter)
    start = time.time()
    for path, size, method, _ in archive.records:
        disc = archive.on_disc(path)
        if disc is None:
            continue
        if args.limit and disc > args.limit:
            over[method] += 1
            continue
        tried[method] += 1
        try:
            blob, used = unpack(archive.read(path), size, method)
        except Exception as exc:                     # noqa: BLE001
            failures.append((path, method, "%s" % exc))
            continue
        if len(blob) != size:
            failures.append((path, method,
                             "produced %d of %d" % (len(blob), size)))
            continue
        if not 0 <= disc - used <= 4:
            failures.append((path, method,
                             "consumed %d of %d" % (used, disc)))
            continue
        good[method] += 1
        slack[disc - used] += 1
        raw[method] += disc
        out[method] += len(blob)
        tag = bytes(blob[:4])
        magics[tag] += 1
        if len(blob) >= 8 and tag[:3].isalnum():
            declared_seen += 1
            agrees = struct.unpack_from(">I", blob, 4)[0] == size
            declared_ok += agrees
            declared_by_tag[tag][agrees] += 1
    print("%s" % os.path.basename(args.image))
    print("records %d, decoded in %.0f s" % (len(archive.records),
                                             time.time() - start))
    for method in sorted(set(list(tried) + list(over))):
        ratio = (out[method] / raw[method]) if raw[method] else 0.0
        print("  method %d %-22s %5d of %5d, %5d over the size limit, ratio %.2f"
              % (method, "(%s)" % describe(method), good[method],
                 tried[method], over[method], ratio))
    print("  total            : %d of %d, %d failures"
          % (sum(good.values()), sum(tried.values()), len(failures)))
    print("  trailing input bytes : %s" % dict(sorted(slack.items())))
    # Per tag, because the bare ratio is misleading: some of these formats do
    # not put a length at +0x04 at all, and lumping them in reads as a failure.
    print("  payload states its own size, and it agrees : %d of %d"
          % (declared_ok, declared_seen))
    for tag, counts in sorted(declared_by_tag.items(),
                              key=lambda kv: -sum(kv[1].values())):
        print("      %-8r %4d of %4d%s"
              % (tag, counts[True], sum(counts.values()),
                 "" if counts[False] == 0 else
                 "   <- +0x04 is not a length in this format"))
    print("  magics : %s"
          % ", ".join("%r x%d" % (m, n) for m, n in magics.most_common(10)))
    for path, method, why in failures[:20]:
        print("  FAIL %-34s method %d: %s" % (path, method, why))
    return 1 if failures else 0


def cmd_extract(args):
    archive = Archive(args.image)
    written = 0
    for path, size, method, _ in archive.records:
        if args.only and not path.startswith(args.only.lower()):
            continue
        if archive.on_disc(path) is None:
            continue
        blob, _ = unpack(archive.read(path), size, method)
        dest = os.path.join(args.output, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fo:
            fo.write(blob)
        written += 1
        if args.verbose:
            print("%-34s %9d  method %d" % (path, len(blob), method))
    print("wrote %d files to %s" % (written, args.output))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Eternal Sonata's index.vmtoc and its two compression "
                    "layers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="read the index and count the methods")
    p.add_argument("image")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("verify", help="decode and self-check in bulk")
    p.add_argument("image")
    p.add_argument("--limit", type=lambda v: int(v, 0), default=1 << 20,
                   help="skip files larger than this on disc (0 for no limit)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("extract", help="decode files out of the image")
    p.add_argument("image")
    p.add_argument("output")
    p.add_argument("--only", help="path prefix, lower case, forward slashes")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_extract)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
