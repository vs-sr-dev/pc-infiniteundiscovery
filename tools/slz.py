#!/usr/bin/env python3
"""
slz.py -- decompressor for the SLZ blocks in Infinite Undiscovery's containers.

Most of the game's bulk -- every `MESH`, `MTEX`, `SCE-`, `SKAC` and `APAC`
resource, 1812 blocks on disc 1 alone -- is stored compressed behind a header
whose first three bytes are `SLZ`. The name is tri-Ace's; the compression is
not. SLZ is a 24-byte wrapper around a stock Microsoft **XCompress** stream,
which is LZX with a 128 KB window.

The giveaway is the constant at offset 0x18, `0x0FF512EE`, XCompress's own
stream magic. It is byte-identical in all 1812 blocks, as is the version field
after it, so it is a signature rather than a checksum.

Layout
------
tri-Ace wrapper, big-endian, 24 bytes:

    0x00  3  "SLZ"
    0x03  1  version (4 everywhere)
    0x04  4  header size (0x20)
    0x08  4  compressed size, counted from 0x18
    0x0C  4  uncompressed size
    0x10  4  zero
    0x14  4  one

XCompress stream header, big-endian, 48 bytes, from 0x18:

    0x18  4  magic 0x0FF512EE
    0x1C  4  version 0x01020000
    0x20  4  context flags
    0x24  4  flags
    0x28  4  window size (0x20000 -- 128 KB)
    0x2C  4  compression partition size (0x80000)
    0x30  8  uncompressed size
    0x38  8  compressed size
    0x40  4  uncompressed chunk size (0x20000)
    0x44  4  largest compressed chunk in this stream

Then a chunk table from 0x48, each entry:

    +0x00  4  compressed size of this chunk, counted from +0x04
    +0x04  .. chunk payload, that many bytes
              next chunk header follows at +0x04 + size

The chunk table is solid: walking it lands **exactly** on the end of the
compressed region in every block tested, and the largest size seen always
equals the field at 0x44. An entry holding an SLZ block is padded so that
`entry size == align_up(compressed size, 4) + 24`.

Two things make decoding harder than the layout suggests
--------------------------------------------------------
**The window is shared across chunks.** Each chunk restarts the bitstream --
fresh E8 flag, fresh Huffman tables -- but the LZX window carries over, so a
match late in the stream reaches back into an earlier chunk. Decoding chunks
independently yields plausible-looking garbage a few chunks in.

**Each chunk payload opens with a prefix of unknown meaning and varying
length.** Two bytes is the ordinary case; one and five have both been observed,
the latter on a short final chunk. `find_stream_start` locates the bitstream by
trying each offset and keeping the first whose block header decodes sanely.

Status
------
Partial, and worth being precise about. The container is fully mapped and the
LZX decoder is correct: blocks that decode end to end produce payloads whose
own self-reported length matches the wrapper's, a value the compressor never
touches. But only about **12% of blocks (25 of 200 sampled) decode completely**.

Two things remain unexplained, and both are worked around by searching rather
than by knowing the rule:

* what the chunk prefix holds, and what decides its length;
* what sits between two blocks *inside* one chunk. Measured cases come out to
  "pad to a byte boundary, then 32 bits", but that does not hold everywhere.

Where the rule is unknown the decoder locates the next block header by trying
offsets and ranking the candidates. That recovers a good deal, and it fails
loudly rather than quietly, but it is a workaround and the remaining failures
are its cost.

Verification
------------
`ASF `, `AIF ` and `AAF ` payloads all store their own length at offset 4, so a
decode can be checked against something the compressor never wrote.
`slz.py verify` does exactly that and reports the rate honestly.

Usage
-----
    python tools/slz.py info       <file> --offset N
    python tools/slz.py decompress <file> --offset N <out>
    python tools/slz.py verify     <image> --csv entries.csv --base N [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lzx import BitReader, LzxDecoder, LzxError  # noqa: E402

MAGIC = b"SLZ"
XCOMPRESS_MAGIC = 0x0FF512EE

WRAPPER_SIZE = 0x18
STREAM_HEADER_SIZE = 0x30
CHUNK_HEADER_SIZE = 6


class SlzError(Exception):
    pass


class SlzBlock:
    def __init__(self, data):
        if data[:3] != MAGIC:
            raise SlzError("not an SLZ block")
        self.data = data
        self.version = data[3]
        (self.header_size, self.compressed_size,
         self.uncompressed_size) = struct.unpack_from(">III", data, 4)

        magic, self.stream_version = struct.unpack_from(">II", data, 0x18)
        if magic != XCOMPRESS_MAGIC:
            raise SlzError("no XCompress magic at 0x18 (got 0x%08X)" % magic)

        (self.context_flags, self.flags, self.window_size,
         self.partition_size) = struct.unpack_from(">IIII", data, 0x20)
        self.stream_uncompressed, self.stream_compressed = struct.unpack_from(
            ">QQ", data, 0x30)
        self.chunk_size, self.max_chunk_compressed = struct.unpack_from(
            ">II", data, 0x40)

        self.window_bits = self.window_size.bit_length() - 1

    def chunks(self):
        """Yield each chunk's payload and how much output it should produce."""
        pos = WRAPPER_SIZE + STREAM_HEADER_SIZE
        produced = 0
        while produced < self.uncompressed_size:
            if pos + 4 > len(self.data):
                raise SlzError("chunk header runs past the end of the block")
            size = struct.unpack_from(">I", self.data, pos)[0]
            if not 0 < size <= self.max_chunk_compressed:
                raise SlzError("implausible chunk size %d at 0x%X" % (size, pos))
            want = min(self.chunk_size, self.uncompressed_size - produced)
            yield self.data[pos + 4:pos + 4 + size], want
            produced += want
            pos += 4 + size

    def find_stream_start(self, payload, want):
        """Locate the LZX bitstream inside a chunk payload.

        Every chunk payload opens with a short prefix before the bitstream --
        two bytes in the ordinary case, but one and five have both been seen,
        and what the prefix holds has not been worked out. Rather than guess,
        try each plausible offset and read the block header there.

        Candidates are ranked, not just accepted: a chunk is usually one block
        covering the whole chunk, so an offset whose declared block length is
        exactly `want` beats one that merely looks plausible. Taking the first
        syntactically valid offset instead picks the wrong prefix often enough
        to matter.
        """
        candidates = []
        for skip in range(0, 9):
            try:
                reader = BitReader(payload[skip:])
                if reader.read(1):
                    reader.read(16)
                    reader.read(16)
                block_type = reader.read(3)
                block_length = ((reader.read(8) << 16) | (reader.read(8) << 8)
                                | reader.read(8))
            except (IndexError, ValueError):
                continue
            if block_type not in (1, 2) or not 0 < block_length <= want:
                continue
            if block_length == want:
                return skip
            candidates.append(skip)
        if not candidates:
            raise SlzError("no chunk prefix length yields a valid LZX block header")
        # Two bytes is by far the most common prefix, so prefer it when the
        # length test could not decide.
        return 2 if 2 in candidates else candidates[0]

    def decompress(self):
        decoder = LzxDecoder(self.window_bits)
        out = bytearray()
        for payload, want in self.chunks():
            skip = self.find_stream_start(payload, want)
            decoder.decode_chunk(payload, want, out, skip_bytes=skip)
        if len(out) < self.uncompressed_size:
            raise SlzError("stream ended %d bytes short"
                           % (self.uncompressed_size - len(out)))
        return bytes(out[:self.uncompressed_size])


def read_block(path, offset, length=None):
    with open(path, "rb") as fh:
        fh.seek(offset)
        if length is None:
            head = fh.read(0x18)
            if head[:3] != MAGIC:
                raise SlzError("no SLZ magic at offset 0x%X" % offset)
            length = struct.unpack_from(">I", head, 8)[0] + WRAPPER_SIZE
            fh.seek(offset)
        return fh.read(length)


# The payloads that record their own size, and where they keep it.
SELF_SIZED = {b"ASF ": 4, b"AIF ": 4, b"AAF ": 4}


def payload_self_size(blob):
    where = SELF_SIZED.get(blob[:4])
    if where is None:
        return None
    return struct.unpack_from(">I", blob, where)[0]


def cmd_info(args):
    block = SlzBlock(read_block(args.file, args.offset, args.length))
    print("version           : %d" % block.version)
    print("header size       : 0x%X" % block.header_size)
    print("compressed size   : %d (from 0x18)" % block.compressed_size)
    print("uncompressed size : %d" % block.uncompressed_size)
    print("stream version    : 0x%08X" % block.stream_version)
    print("window            : 0x%X (%d bits)" % (block.window_size, block.window_bits))
    print("partition         : 0x%X" % block.partition_size)
    print("stream sizes      : %d -> %d" % (block.stream_compressed,
                                            block.stream_uncompressed))
    print("chunk size        : 0x%X" % block.chunk_size)
    print("largest chunk     : %d" % block.max_chunk_compressed)
    info = [(len(p), block.find_stream_start(p, w)) for p, w in block.chunks()]
    print("chunks            : %d" % len(info))
    print("  (payload bytes, prefix length): %s" % (info[:10],))
    return 0


def cmd_decompress(args):
    block = SlzBlock(read_block(args.file, args.offset, args.length))
    out = block.decompress()
    with open(args.output, "wb") as fo:
        fo.write(out)
    declared = payload_self_size(out)
    print("wrote %d bytes to %s" % (len(out), args.output))
    print("payload magic : %r" % out[:4])
    if declared is not None:
        print("self-reported : %d  %s"
              % (declared, "matches" if declared == len(out) else "MISMATCH"))
    return 0


def cmd_verify(args):
    """Decompress many blocks and check each against its payload's own size."""
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    fh = open(args.image, "rb")
    checked = confirmed = unchecked = 0
    failures = []
    for row in rows:
        if args.limit and checked >= args.limit:
            break
        offset = args.base + int(row["entry_offset"])
        fh.seek(offset)
        if fh.read(3) != MAGIC:
            continue
        fh.seek(offset)
        head = fh.read(0x18)
        total = struct.unpack_from(">I", head, 8)[0] + WRAPPER_SIZE
        fh.seek(offset)
        try:
            block = SlzBlock(fh.read(total))
            out = block.decompress()
        except (SlzError, LzxError, IndexError) as exc:
            failures.append((row["tag"], offset, str(exc)))
            checked += 1
            continue
        checked += 1
        declared = payload_self_size(out)
        if declared is None:
            unchecked += 1
        elif declared == len(out):
            confirmed += 1
        else:
            failures.append((row["tag"], offset,
                             "self-reported %d, got %d" % (declared, len(out))))

    print("decompressed          : %d blocks" % checked)
    print("self-size confirmed   : %d" % confirmed)
    print("no self-size to check : %d" % unchecked)
    print("failures              : %d" % len(failures))
    for tag, offset, reason in failures[:20]:
        print("   %-5s at 0x%X: %s" % (tag, offset, reason))
    return 1 if failures else 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Decompressor for SLZ blocks (an XCompress/LZX wrapper).")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, func, helptext in (
        ("info", cmd_info, "print the wrapper and stream headers"),
        ("decompress", cmd_decompress, "decompress one block to a file"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("file")
        s.add_argument("--offset", type=lambda x: int(x, 0), default=0)
        s.add_argument("--length", type=lambda x: int(x, 0), default=None)
        if name == "decompress":
            s.add_argument("output")
        s.set_defaults(func=func)

    s = sub.add_parser("verify", help="bulk-decompress and self-check")
    s.add_argument("image")
    s.add_argument("--csv", required=True, help="entry manifest from mron.py scan --csv")
    s.add_argument("--base", type=lambda x: int(x, 0), required=True,
                   help="byte offset of the container inside the image")
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
