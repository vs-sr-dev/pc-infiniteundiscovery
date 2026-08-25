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

Frames, and why they are the whole story
----------------------------------------
LZX does not decode a bitstream straight through. Output is cut into **frames**
of exactly 32 768 bytes, and the input is cut with it: each frame's compressed
bytes are a separate run, and the bit reader restarts, byte-aligned, at the
start of every one. Whoever wraps LZX decides how the frame boundaries are
found -- CAB, WIM, XNB and XCompress all differ there, and none of it is part
of LZX itself. See `slz.py` for how XCompress marks them.

What matters here is that **everything except the bit reader survives a frame
boundary**: the Huffman tables, R0/R1/R2, and above all the current block and
how much of it is left. Blocks routinely span several frames, so a decoder that
expects a block header at the start of each frame is reading Huffman tables out
of the middle of coded data. It will resynchronise often enough to look like it
almost works, which is the worst possible failure mode.

State is therefore held on the decoder, not in a local, and `reset()` marks the
points where the encoder genuinely started over.

Usage
-----
    dec = LzxDecoder(window_bits=17)
    out = bytearray()
    for data, length in frames:          # 32 KB each, the last one shorter
        dec.decode_frame(data, length, out)
    dec.reset()                          # only where the stream restarts

or, where the frames are not delimited and simply follow one another:

    out = LzxDecoder(window_bits=15).decode_stream(data, uncompressed_size)
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

FRAME_SIZE = 0x8000

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
    """A stateful LZX stream. Feed it one frame at a time.

    The decoder holds everything that outlives a frame -- Huffman tables, the
    repeated offsets, and the block currently being decoded -- because in LZX
    only the bit reader restarts at a frame boundary.
    """

    def __init__(self, window_bits=17):
        if window_bits not in POSITION_SLOTS:
            raise LzxError("unsupported window size: %d bits" % window_bits)
        self.window_bits = window_bits
        self.window_size = 1 << window_bits
        self.num_position_slots = POSITION_SLOTS[window_bits]
        self.main_elements = NUM_CHARS + (self.num_position_slots << 3)
        self.reset()

    def reset(self):
        """Start a fresh stream: new tables, new offsets, header unread."""
        self.main_lengths = [0] * self.main_elements
        self.length_lengths = [0] * (NUM_SECONDARY_LENGTHS + 1)
        self.main_table = None
        self.length_table = None
        self.aligned_table = None
        self.block_type = 0
        self.block_remaining = 0
        self.r0 = self.r1 = self.r2 = 1
        self.header_read = False
        self.intel_filesize = 0
        self._raw = None          # byte cursor inside an uncompressed block

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

    # -- block headers -----------------------------------------------------

    def _read_block_header(self, reader, data):
        self.block_type = reader.read(3)
        self.block_remaining = ((reader.read(8) << 16) | (reader.read(8) << 8)
                                | reader.read(8))
        if self.block_remaining == 0:
            raise LzxError("zero-length block")

        if self.block_type == BLOCKTYPE_ALIGNED:
            self.aligned_table = HuffmanTable(
                [reader.read(3) for _ in range(ALIGNED_ELEMENTS)], table_bits=7)

        if self.block_type in (BLOCKTYPE_VERBATIM, BLOCKTYPE_ALIGNED):
            self._read_lengths(reader, self.main_lengths, 0, NUM_CHARS)
            self._read_lengths(reader, self.main_lengths, NUM_CHARS,
                               self.main_elements)
            self.main_table = HuffmanTable(self.main_lengths, table_bits=11)
            self._read_lengths(reader, self.length_lengths, 0,
                               NUM_SECONDARY_LENGTHS)
            self.length_table = HuffmanTable(self.length_lengths, table_bits=11)
        elif self.block_type == BLOCKTYPE_UNCOMPRESSED:
            # Raw bytes, preceded by the three repeated offsets. Note these are
            # stored little-endian, unlike everything else on this console.
            reader.align_to_word()
            position = reader.byte_position()
            self.r0 = int.from_bytes(data[position:position + 4], "little")
            self.r1 = int.from_bytes(data[position + 4:position + 8], "little")
            self.r2 = int.from_bytes(data[position + 8:position + 12], "little")
            self._raw = position + 12
        else:
            raise LzxError("unknown block type %d" % self.block_type)

    # -- main loop ---------------------------------------------------------

    def decode_frame(self, data, out_length, out):
        """Decode one frame of `out_length` bytes, appending to `out`.

        `data` is just this frame's compressed bytes. The bit reader is local
        to the call -- that is the entire meaning of a frame boundary -- while
        every other piece of state lives on the decoder and carries over.
        """
        target = len(out) + out_length
        reader = BitReader(data)

        if not self.header_read:
            if reader.read(1):
                self.intel_filesize = (reader.read(16) << 16) | reader.read(16)
            self.header_read = True
        if self._raw is not None:
            # An uncompressed block that ran off the end of the previous frame
            # simply continues with this frame's first byte.
            self._raw = 0

        while len(out) < target:
            if self.block_remaining == 0:
                self._raw = None
                self._read_block_header(reader, data)
                continue

            want = min(self.block_remaining, target - len(out))

            if self.block_type == BLOCKTYPE_UNCOMPRESSED:
                take = min(want, len(data) - self._raw)
                out += data[self._raw:self._raw + take]
                self._raw += take
                self.block_remaining -= take
                if self.block_remaining == 0:
                    end = self._raw + (self._raw & 1)
                    reader.pos, reader.buf, reader.count = end, 0, 0
                    self._raw = None
                if take < want:
                    break
                continue

            produced = 0
            while produced < want:
                symbol = self.main_table.decode(reader)
                if symbol < NUM_CHARS:
                    out.append(symbol)
                    produced += 1
                    continue

                symbol -= NUM_CHARS
                match_length = symbol & NUM_PRIMARY_LENGTHS
                if match_length == NUM_PRIMARY_LENGTHS:
                    match_length += self.length_table.decode(reader)
                match_length += MIN_MATCH

                slot = symbol >> 3
                if slot == 0:
                    offset = self.r0
                elif slot == 1:
                    offset = self.r1
                    self.r1 = self.r0
                    self.r0 = offset
                elif slot == 2:
                    offset = self.r2
                    self.r2 = self.r0
                    self.r0 = offset
                else:
                    extra = EXTRA_BITS[slot]
                    if self.block_type == BLOCKTYPE_ALIGNED and extra >= 3:
                        verbatim = reader.read(extra - 3) << 3 if extra > 3 else 0
                        offset = POSITION_BASE[slot] - 2 + verbatim
                        offset += self.aligned_table.decode(reader)
                    else:
                        offset = POSITION_BASE[slot] - 2 + reader.read(extra)
                    self.r2, self.r1, self.r0 = self.r1, self.r0, offset

                # A match may run past the end of the frame -- frames are an
                # output-side division, invisible to the encoder -- but never
                # past the end of the block. Clip it there.
                if produced + match_length > self.block_remaining:
                    match_length = self.block_remaining - produced
                self._copy_match(out, offset, match_length)
                produced += match_length

            self.block_remaining -= produced

        # How much of `data` this frame consumed. A caller whose frames are
        # separately delimited does not need it; `decode_stream` does, because
        # there the frames are laid end to end and only this says where the
        # next one starts.
        if self._raw is not None:
            self.frame_input_used = self._raw
        else:
            reader.align_to_word()
            self.frame_input_used = reader.byte_position()
        return out

    def decode_stream(self, data, total_length, out=None):
        """Decode frames laid end to end in one buffer.

        XCompress delimits each frame, so `slz.py` can hand them over one at a
        time. The LZX inside an XEX is not delimited at all: the frames simply
        follow one another, and the only thing marking the boundary is that the
        bit reader restarts on a 16-bit boundary once 32 768 bytes have come
        out. Decoding one frame at a time from successive slices reproduces
        exactly that, because a fresh reader on an aligned position and a
        realigned reader are the same thing.
        """
        if out is None:
            out = bytearray()
        view = memoryview(data)
        target = len(out) + total_length
        at = 0
        while len(out) < target:
            want = min(FRAME_SIZE, target - len(out))
            before = len(out)
            self.decode_frame(view[at:], want, out)
            if len(out) == before:
                raise LzxError("frame at input 0x%X produced nothing" % at)
            at += self.frame_input_used
            if at > len(view):
                raise LzxError("ran off the end of the compressed stream")
        return out


def decompress_frames(frames, window_bits=17, out=None):
    """Decode a whole stream: `frames` yields (compressed bytes, length)."""
    decoder = LzxDecoder(window_bits)
    if out is None:
        out = bytearray()
    for data, length in frames:
        decoder.decode_frame(data, length, out)
    return out
