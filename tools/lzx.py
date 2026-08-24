#!/usr/bin/env python3
"""
lzx.py -- LZX decompressor, the variant used by Microsoft's XCompress.

LZX is the LZ77 + Huffman codec Microsoft shipped in the Cabinet SDK and later
reused, largely unchanged, as the Xbox 360 XDK's `XMemCompress`. This is a
decoder for it, written from the published algorithm.

Shape of the format
-------------------
The bitstream is read as **little-endian 16-bit words**, with bits consumed
most-significant-first within each word. That mismatch -- little-endian words,
big-endian bits -- is the single most common thing to get wrong.

The stream opens with one bit saying whether Intel E8 call translation is in
effect, followed by a 32-bit size if it is. After that come blocks, each with:

* a 3-bit type: 1 verbatim, 2 aligned-offset, 3 uncompressed,
* a 24-bit uncompressed length,
* for compressed types, the Huffman code lengths, then the coded data.

Code lengths are themselves compressed, against the previous block's lengths,
using a 20-symbol "pretree" whose own lengths are stored as 20 raw 4-bit
values. Symbols 17, 18 and 19 in that pretree encode runs of zeros and runs of
repeats rather than lengths.

Matches use three **repeated offsets** (R0, R1, R2). Position slots 0, 1 and 2
mean "reuse R0/R1/R2" rather than encoding a distance, which is what makes LZX
compress structured binary data as well as it does.

Aligned-offset blocks add a fourth Huffman tree carrying the low 3 bits of each
distance, which pays off when distances cluster on a stride -- exactly the case
for arrays of fixed-size records.

Usage
-----
    from lzx import LzxDecoder
    LzxDecoder(window_bits=17).decompress(data, expected_length)
"""

from __future__ import annotations

MIN_MATCH = 2
NUM_CHARS = 256

BLOCKTYPE_VERBATIM = 1
BLOCKTYPE_ALIGNED = 2
BLOCKTYPE_UNCOMPRESSED = 3

PRETREE_ELEMENTS = 20
ALIGNED_ELEMENTS = 8
NUM_PRIMARY_LENGTHS = 7
NUM_SECONDARY_LENGTHS = 249

# Position slots available for each window size, indexed by window bits.
POSITION_SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}


def _build_position_tables():
    extra = []
    j = 0
    for i in range(0, 52, 2):
        extra.append(j)
        extra.append(j)
        if i != 0 and j < 17:
            j += 1
    base = []
    total = 0
    for i in range(51):
        base.append(total)
        total += 1 << extra[i]
    return extra[:51], base


EXTRA_BITS, POSITION_BASE = _build_position_tables()


class LzxError(Exception):
    pass


class BitReader:
    """LZX bit order: little-endian 16-bit words, MSB-first within the word."""

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.buf = 0
        self.count = 0

    def _fill(self, need):
        while self.count < need:
            if self.pos + 1 < len(self.data):
                word = self.data[self.pos] | (self.data[self.pos + 1] << 8)
            elif self.pos < len(self.data):
                word = self.data[self.pos]
            else:
                word = 0
            self.pos += 2
            self.buf = (self.buf << 16) | word
            self.count += 16

    def read(self, n):
        if n == 0:
            return 0
        self._fill(n)
        self.count -= n
        value = self.buf >> self.count
        self.buf &= (1 << self.count) - 1
        return value

    def peek(self, n):
        self._fill(n)
        return self.buf >> (self.count - n)

    def skip(self, n):
        self.count -= n
        self.buf &= (1 << self.count) - 1

    def align_to_word(self):
        """Drop to the next 16-bit boundary, as uncompressed blocks require."""
        drop = self.count % 16
        if drop:
            self.skip(drop)

    def byte_position(self):
        """Input offset, once the buffer has been aligned and drained."""
        return self.pos - self.count // 8


class HuffmanTable:
    """Canonical Huffman decoder with a lookup table for the short codes."""

    __slots__ = ("table", "table_bits", "long_codes", "max_length")

    def __init__(self, lengths, table_bits=11):
        self.table_bits = table_bits
        self.max_length = max(lengths) if lengths else 0
        self.table = [None] * (1 << table_bits)
        self.long_codes = []

        if self.max_length == 0:
            return

        counts = [0] * (self.max_length + 1)
        for length in lengths:
            if length:
                counts[length] += 1

        code = 0
        next_code = [0] * (self.max_length + 2)
        for length in range(1, self.max_length + 1):
            code = (code + counts[length - 1]) << 1 if length > 1 else 0
            next_code[length] = code

        for symbol, length in enumerate(lengths):
            if length == 0:
                continue
            value = next_code[length]
            next_code[length] += 1
            if length <= table_bits:
                shift = table_bits - length
                start = value << shift
                entry = (symbol, length)
                for i in range(start, start + (1 << shift)):
                    self.table[i] = entry
            else:
                self.long_codes.append((value, length, symbol))

    def decode(self, reader):
        entry = self.table[reader.peek(self.table_bits)]
        if entry is not None:
            reader.skip(entry[1])
            return entry[0]
        # Fall back to a linear walk for codes longer than the table covers.
        for length in range(self.table_bits + 1, self.max_length + 1):
            value = reader.peek(length)
            for code, code_length, symbol in self.long_codes:
                if code_length == length and code == value:
                    reader.skip(length)
                    return symbol
        raise LzxError("no Huffman code matches the bitstream")


class LzxDecoder:
    def __init__(self, window_bits=17):
        if window_bits not in POSITION_SLOTS:
            raise LzxError("unsupported window size: %d bits" % window_bits)
        self.window_bits = window_bits
        self.window_size = 1 << window_bits
        self.num_position_slots = POSITION_SLOTS[window_bits]
        self.main_elements = NUM_CHARS + (self.num_position_slots << 3)

    # -- match copying -----------------------------------------------------

    def _copy_match(self, out, offset, length):
        """Copy `length` bytes from `offset` back, through the circular window.

        The window is a fixed ring of `window_size` bytes that starts zeroed,
        and LZX lets a match point into the part of it that has not been
        written yet. That is not corruption: encoders use a far-back match into
        the zeroed region as a cheap way to emit a run of zeros, which shows up
        constantly in game data full of padding. Treating it as an error --
        the obvious reading of "offset larger than the output so far" -- breaks
        on real streams.
        """
        if offset > self.window_size:
            raise LzxError("match offset %d exceeds the %d-byte window"
                           % (offset, self.window_size))

        produced = len(out)
        if offset <= produced:
            start = produced - offset
            if offset >= length:
                out += out[start:start + length]
            else:
                for i in range(length):
                    out.append(out[start + i])
            return

        # The window has not filled yet, so window position i is output
        # position i, and anything at or past `produced` is still zero.
        source = produced - offset + self.window_size
        for i in range(length):
            position = source + i
            if position >= self.window_size:
                out.append(out[position - self.window_size])
            else:
                out.append(0)

    # -- code length decoding ---------------------------------------------

    def _read_lengths(self, reader, lengths, first, last):
        """Decode code lengths for [first, last) against their current values."""
        pretree_lengths = [reader.read(4) for _ in range(PRETREE_ELEMENTS)]
        pretree = HuffmanTable(pretree_lengths, table_bits=6)

        i = first
        while i < last:
            symbol = pretree.decode(reader)
            if symbol == 17:
                run = reader.read(4) + 4
                for _ in range(run):
                    if i >= last:
                        break
                    lengths[i] = 0
                    i += 1
            elif symbol == 18:
                run = reader.read(5) + 20
                for _ in range(run):
                    if i >= last:
                        break
                    lengths[i] = 0
                    i += 1
            elif symbol == 19:
                run = reader.read(1) + 4
                value = pretree.decode(reader)
                value = (lengths[i] - value) % 17
                for _ in range(run):
                    if i >= last:
                        break
                    lengths[i] = value
                    i += 1
            else:
                lengths[i] = (lengths[i] - symbol) % 17
                i += 1

    # -- main loop ---------------------------------------------------------

    def _resync(self, reader, remaining):
        """Find the next block header after an inter-block gap.

        Returns True with the reader positioned on the header, False if no
        candidate was found. Candidates are ranked: a header whose declared
        length is exactly the chunk's remaining output is taken immediately,
        since that is what a final block looks like; otherwise the first
        syntactically valid one is used.

        This is a workaround, not a specification. Whatever occupies the gap
        between blocks has not been identified, so the decoder locates the
        header empirically rather than pretending to know the rule.
        """
        saved = (reader.pos, reader.buf, reader.count)
        fallback = None
        for skip in range(0, 97):
            reader.pos, reader.buf, reader.count = saved
            try:
                if skip:
                    reader.read(skip)
                block_type = reader.read(3)
                block_length = ((reader.read(8) << 16) | (reader.read(8) << 8)
                                | reader.read(8))
            except (IndexError, ValueError):
                continue
            if block_type not in (BLOCKTYPE_VERBATIM, BLOCKTYPE_ALIGNED):
                continue
            if not 0 < block_length <= remaining:
                continue
            if block_length == remaining:
                reader.pos, reader.buf, reader.count = saved
                if skip:
                    reader.read(skip)
                return True
            if fallback is None:
                fallback = skip
        reader.pos, reader.buf, reader.count = saved
        if fallback is None:
            return False
        if fallback:
            reader.read(fallback)
        return True

    def decode_chunk(self, data, out_length, out=None, skip_bytes=0):
        """Decode one chunk, appending to `out` so the window carries over.

        XCompress splits a stream into chunks. Each chunk restarts the
        bitstream -- fresh E8 flag, fresh Huffman tables -- but the LZX
        *window* is shared, so a match late in the stream may reach back into
        an earlier chunk. Passing the same `out` buffer through every chunk is
        what gives that continuity; decoding chunks independently produces
        plausible-looking garbage a few chunks in.

        `skip_bytes` drops the chunk's leading prefix, whose length varies.
        """
        if out is None:
            out = bytearray()
        target = len(out) + out_length

        reader = BitReader(data[skip_bytes:])
        if reader.read(1):
            reader.read(16)
            reader.read(16)

        main_lengths = [0] * self.main_elements
        length_lengths = [0] * (NUM_SECONDARY_LENGTHS + 1)
        r0 = r1 = r2 = 1
        block_index = 0

        while len(out) < target:
            remaining = target - len(out)
            if block_index:
                # Blocks inside one chunk are not bit-contiguous: something
                # sits between them. In the cases measured it works out to
                # "pad to a byte boundary, then 32 bits", but that rule does
                # not hold everywhere, so resynchronise by looking for the
                # next header instead of assuming a fixed gap.
                if not self._resync(reader, remaining):
                    break

            block_type = reader.read(3)
            block_length = (reader.read(8) << 16) | (reader.read(8) << 8) | reader.read(8)
            if block_length == 0:
                break

            if block_type == BLOCKTYPE_UNCOMPRESSED:
                reader.align_to_word()
                start = reader.byte_position()
                r0 = int.from_bytes(data[start:start + 4], "little")
                r1 = int.from_bytes(data[start + 4:start + 8], "little")
                r2 = int.from_bytes(data[start + 8:start + 12], "little")
                start += 12
                out += data[start:start + block_length]
                consumed = start + block_length
                if consumed & 1:
                    consumed += 1
                reader.pos = consumed
                reader.buf = 0
                reader.count = 0
                block_index += 1
                continue

            if block_type not in (BLOCKTYPE_VERBATIM, BLOCKTYPE_ALIGNED):
                raise LzxError("unknown block type %d" % block_type)

            aligned_table = None
            if block_type == BLOCKTYPE_ALIGNED:
                aligned_table = HuffmanTable(
                    [reader.read(3) for _ in range(ALIGNED_ELEMENTS)], table_bits=7)

            self._read_lengths(reader, main_lengths, 0, NUM_CHARS)
            self._read_lengths(reader, main_lengths, NUM_CHARS, self.main_elements)
            main_table = HuffmanTable(main_lengths, table_bits=11)

            self._read_lengths(reader, length_lengths, 0, NUM_SECONDARY_LENGTHS)
            length_table = HuffmanTable(length_lengths, table_bits=11)

            produced = 0
            while produced < block_length:
                symbol = main_table.decode(reader)
                if symbol < NUM_CHARS:
                    out.append(symbol)
                    produced += 1
                    continue

                symbol -= NUM_CHARS
                match_length = symbol & NUM_PRIMARY_LENGTHS
                if match_length == NUM_PRIMARY_LENGTHS:
                    match_length += length_table.decode(reader)
                match_length += MIN_MATCH

                slot = symbol >> 3
                if slot == 0:
                    offset = r0
                elif slot == 1:
                    offset = r1
                    r1 = r0
                    r0 = offset
                elif slot == 2:
                    offset = r2
                    r2 = r0
                    r0 = offset
                else:
                    extra = EXTRA_BITS[slot]
                    if block_type == BLOCKTYPE_ALIGNED and extra >= 3:
                        verbatim = reader.read(extra - 3) << 3 if extra > 3 else 0
                        offset = POSITION_BASE[slot] - 2 + verbatim
                        offset += aligned_table.decode(reader)
                    else:
                        offset = POSITION_BASE[slot] - 2 + reader.read(extra)
                    r2, r1, r0 = r1, r0, offset

                # A block produces exactly its declared length. A match that
                # would overrun is clipped: letting it through shifts every
                # later byte and silently corrupts the rest of the stream.
                if produced + match_length > block_length:
                    match_length = block_length - produced
                self._copy_match(out, offset, match_length)
                produced += match_length

            block_index += 1

        return out

    def decompress(self, data, out_length):
        """Decode a single self-contained chunk."""
        return bytes(self.decode_chunk(data, out_length)[:out_length])


def decompress(data, out_length, window_bits=17):
    return LzxDecoder(window_bits).decompress(data, out_length)
