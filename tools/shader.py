#!/usr/bin/env python3
"""
shader.py -- Infinite Undiscovery's compiled shaders: the AHSL disk caches,
the fixed library, and a disassembler for the Xenos microcode inside both.

Session 7 found shader-looking data at the head of `ud1.bin` and counted
`ps_3_0` and `vs_3_0` strings: 160 of them, 70 of which it placed. Session 19
read the thing properly, and the count was wrong in an instructive way -- 100
of the 160 were the same ten strings inside a compression dictionary, repeated
in ten caches. What is really on the disc is below.

Where the shaders are
---------------------
Two structures, both in `ud1.bin`, both byte-identical on the two discs:

* **The fixed library**, at `ud1.bin +0xC000`: a 16-byte header -- `0x0C`,
  the count (60), two zero words -- then one `u32` per shader, an offset from
  the header with **bit 31 set for a pixel shader** and clear for a vertex
  shader, then the 60 compiled blobs back to back with no gap between them.
* **Ten AHSL disk caches**, each beginning `AHSX` on a sector boundary: one at
  `ud1.bin +0x7800` with 26 records, and nine inside the run session 5 filed
  as one 630 MB "ASF/WMV stream", holding 5 054 to 29 443 records each --
  96 853 records and 116 MB in all.

The `AHSX` cache
----------------
Big-endian. The loader is `0x822190A8` and the function that builds an empty
one is `0x82217900`; the constructor at `0x82219818` sets the two version
halfwords and stores the `e:\\AHSLCacheUD4\\AHSLv2DiskCache` path in the same
object, which is how `AHSX` is known to be that cache.

    +0x0000   4   `AHSX`
    +0x0004   4   a mask; varies per cache, zeroed on creation
    +0x0008   2   0x002E  \\  version: the loader rejects a cache whose two
    +0x000A   2   0x0003  /   halfwords differ from the ones the engine sets
    +0x000C   2   record count
    +0x000E   2   zero
    +0x0010  8K   the dictionary -- see below
    +0x2010       the records, back to back

A record:

    +0x00  2  a hash, not the CRC-16 of the key; unexplained
    +0x02  2  size on disc, header included -- the walk to the next record
    +0x04  2  size once decoded, header included
    +0x06  2  where the coded part begins; everything before it is stored
    +0x08  2  CRC-16 of the dictionary this record was coded against
    +0x0A  1  flags: 0x20 means "relocate a pointer", and marks an alias
    +0x0B  1  zero
    +0x0C     the key; its third byte, +0x0E, is its length modulo 256, and
              the stored part is that length rounded up to four -- 2 579 keys
              are longer than 255 bytes, and for those the byte wraps

Records come in two kinds:

* **Shaders**, 63 351 of them: the part from `+0x06` is coded with tri-Ace's
  halfword LZ77 -- `SLZ` method 3, the PlayStation 2 codec of
  [slz.md §2b-3](../docs/formats/slz.md), here in big-endian halfwords --
  **with the dictionary preloaded as history**. Twelve-bit distances in
  halfwords reach exactly 8 190 bytes back, which is why the dictionary is
  8 KB. Decoded, the body has a 0x18-byte header whose halfwords at +0x12 and
  +0x14 give the offset and size of an ordinary XDK compiled-shader blob.
* **Aliases**, 33 502: stored, `+0x02 == +0x04`, flag 0x20, and eight bytes
  past the key a `u32` that points at an earlier record's key (`record +
  0x0C`). The loader relocates it. Their keys match their targets' from the
  ninth byte on: different permutations that compiled to the same program.

The dictionary is 8 KB of shader-shaped bytes -- ten blob fragments, CTABs
included -- and **not** a set of shaders: its constant tables are short by up
to 0x9C bytes against their own offsets. That is what session 7 was reading.
Every record states the dictionary's CRC-16 (X.25: reflected 0x8408, initial
and final 0xFFFF, the routine at `0x82239C28`), and it is 0xC2E6 in every
record of every cache.

The compiled blob
-----------------
Microsoft's XDK container, the same one the executable's own shaders use:

    +0x00  magic 0x102A1100 pixel / 0x102A1101 vertex
    +0x04  virtual size   +0x08 physical size
    +0x10  constant table: a u32 size, then a Direct3D 9 `CTAB`
    +0x14  definition table (0 if none)   +0x18  shader header
    shader header: +0x00 offset into the physical part, +0x04 microcode size

The `CTAB` is the documented Direct3D 9 layout, 20-byte records, offsets from
the start of the table. The physical part holds literal constants first --
`c252..c255`, which the definition table states as register 0xFC, or 0x1FC in
a pixel shader because the pixel constant file starts at 256 -- and then the
microcode, in 96-bit slots.

The microcode
-------------
The encoding is the public one, as implemented in Xenia. The **names** are
Microsoft's: the retail executable carries the XDK microcode compiler, and its
opcode table -- 103 rows of 0x34 bytes, `OP_UNKNOWN` first, at `0x82A55828` --
gives each hardware opcode the compiler's own name. `optable` prints it.

It agrees with the public numbering on every row but one. `MAX_V` is written
there as 3, the same number as `MIN_V`, and is the only vector row with bit
0x80 set in its class field. The microcode settles it: across the 20 517
distinct blobs vector opcode 2 occurs 400 438 times and 3 occurs 6 871 times,
and `max` with equal sources is how the compiler writes a move. So `MAX_V` is 2 in hardware and the
table row means something else. The table also stops at control-flow opcode
12, although the compiler emits 13 and 14 -- the predicate-clean variants of a
conditional exec -- in thousands of shaders.

What a disassembly is checked against
-------------------------------------
`verify` requires three things of every blob, and the third is the one that
binds: the control-flow program's clauses cover every slot after it exactly
once, up to trailing zero padding; every opcode is a known one; and **every
register the microcode reads is one the constant table declares** -- float
constants in a declared range or a literal, texture fetches from a declared
sampler (vertex-shader samplers are fetch constants 16 to 19), conditional
execs on a declared bool (pixel-shader bools start at 128). Two independent
readings of one blob that have to agree.

The same reader opens Star Ocean 4 (2009): two caches at version
0x0033.0x0000, the **same 8 KB dictionary byte for byte**, 11 679 distinct
blobs from compiler 2.0.7645.0, all passing -- once the literal registers are
read from the definition table rather than assumed, and a vertex magic of
0x102A1111 is accepted beside 0x102A1101.

What is not decoded: the lane selection of two-operand scalar ops, the
filtering fields of a texture fetch, and the vertex-fetch format, which is
zero in every blob here because Direct3D patches it at bind time from the
vertex declaration.

Usage
-----
    python tools/shader.py scan    <disc.iso | ud1.bin>
    python tools/shader.py verify  <disc.iso | ud1.bin>
    python tools/shader.py list    <disc.iso | ud1.bin> --cache 0
    python tools/shader.py dis     <disc.iso | ud1.bin> --lib 5
    python tools/shader.py dis     <disc.iso | ud1.bin> --cache 1 --record 0x2010
    python tools/shader.py optable extract/disc1/default.exe
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xdvdfs import XdvdfsImage  # noqa: E402

SECTOR = 0x800
CACHE_MAGIC = b"AHSX"
LIBRARY_OFFSET = 0xC000
DICT_SIZE = 0x2000

# ---------------------------------------------------------------------------
# Opcode names. The numbers are the hardware's; the names are the ones the
# XDK compiler's own table uses (see `optable`), except where noted.

CF_OPS = {
    0: "NOP_CF", 1: "EXEC", 2: "EXEC_END", 3: "CEXEC", 4: "CEXEC_END",
    5: "CEXECP", 6: "CEXECP_END", 7: "CFLOOP", 8: "CFLOOP_END", 9: "CCALL",
    10: "RET", 11: "CJMP", 12: "ALLOC",
    # not in the compiler's table, which stops at 12; Xenia's names
    13: "CEXEC_PRED_CLEAN", 14: "CEXEC_PRED_CLEAN_END", 15: "MARK_VS_FETCH_DONE",
}
EXEC_OPS = {1, 2, 3, 4, 5, 6, 13, 14}
EXEC_END_OPS = {2, 4, 6, 14}
BOOL_EXEC_OPS = {3, 4, 13, 14}

VECTOR_OPS = {
    0: "ADD_V", 1: "MUL_V", 2: "MAX_V", 3: "MIN_V", 4: "SETE_V", 5: "SETGT_V",
    6: "SETGE_V", 7: "SETNE_V", 8: "FRACT_V", 9: "TRUNC_V", 10: "FLOOR_V",
    11: "MULADD_V", 12: "CNDE_V", 13: "CNDGE_V", 14: "CNDGT_V", 15: "DOT4_V",
    16: "DOT3_V", 17: "DOT2ADD_V", 18: "CUBE_V", 19: "MAX4_V",
    20: "PRED_SETE_PUSH_V", 21: "PRED_SETNE_PUSH_V", 22: "PRED_SETGT_PUSH_V",
    23: "PRED_SETGE_PUSH_V", 24: "KILLE_V", 25: "KILLGT_V", 26: "KILLGE_V",
    27: "KILLNE_V", 28: "DST_V", 29: "MOVA_RND_V",
}
# source count per vector op; the rest take two
VECTOR_ARITY = {8: 1, 9: 1, 10: 1, 19: 1, 29: 1, 11: 3, 12: 3, 13: 3, 14: 3, 17: 3}
# vector ops that have an effect with an empty write mask
VECTOR_SIDE_EFFECT = {20, 21, 22, 23, 24, 25, 26, 27}

SCALAR_OPS = {
    0: "ADD", 1: "ADD_PREV", 2: "MUL", 3: "MUL_PREV", 4: "MUL_PREV2", 5: "MAX",
    6: "MIN", 7: "SETE", 8: "SETGT", 9: "SETGE", 10: "SETNE", 11: "FRACT",
    12: "TRUNC", 13: "FLOOR", 14: "EXP", 15: "LOG_CLAMP", 16: "LOG_IEEE",
    17: "RECIP_CLAMP", 18: "RECIP_FF", 19: "RECIP_IEEE", 20: "RECIPSQRT_CLAMP",
    21: "RECIPSQRT_FF", 22: "RECIPSQRT_IEEE", 23: "MOVA_RND", 24: "MOVA_FLOOR",
    25: "SUB", 26: "SUB_PREV", 27: "PRED_SETE", 28: "PRED_SETNE",
    29: "PRED_SETGT", 30: "PRED_SETGE", 31: "PRED_SET_INV", 32: "PRED_SET_POP",
    33: "PRED_SET_CLR", 34: "PRED_SET_RST", 35: "KILLE", 36: "KILLGT",
    37: "KILLGE", 38: "KILLNE", 39: "KILLONE", 40: "SQRT", 42: "MUL_CONST_0",
    43: "MUL_CONST_1", 44: "ADD_CONST_0", 45: "ADD_CONST_1", 46: "SUB_CONST_0",
    47: "SUB_CONST_1", 48: "SIN", 49: "COS",
    # not in the compiler's table; the "no scalar op" filler
    50: "RETAIN_PREV",
}
SCALAR_NONE = 50
SCALAR_SIDE_EFFECT = set(range(27, 40))

FETCH_OPS = {
    0: "vfetch", 1: "tfetch", 16: "getBCF", 17: "getCompTexLOD",
    18: "getGradients", 19: "getWeights", 24: "setTexLOD",
    25: "setGradientH", 26: "setGradientV",
}
TEX_DIM = {0: "1D", 1: "2D", 2: "3D", 3: "Cube"}

REGSET_BOOL, REGSET_INT, REGSET_FLOAT, REGSET_SAMPLER = 0, 1, 2, 3
VS_SAMPLER_BASE = 16   # D3DVERTEXTEXTURESAMPLER0
PS_BOOL_BASE = 128     # pixel-shader bools are the upper half of 256


def bits(v, lo, n):
    return (v >> lo) & ((1 << n) - 1)


def align4(v):
    return (v + 3) & ~3


class ShaderError(Exception):
    pass


# ---------------------------------------------------------------------------
# Reading ud1.bin out of an image, or taking it as given.

class Source:
    """`ud1.bin`, either a file on its own or located inside a disc image."""

    def __init__(self, path):
        self.fh = open(path, "rb")
        self.base = 0
        self.size = os.path.getsize(path)
        self.whole_image = False
        try:
            img = XdvdfsImage(path)
        except (ValueError, OSError):
            return
        for e in img.entries():
            if e.path.lower() == "/ud1.bin":
                self.base = img.base + e.sector * SECTOR
                self.size = e.size
                return
        # another title: no container to narrow the search to, so the caches
        # are looked for across the whole image
        self.whole_image = True

    def read(self, offset, size):
        self.fh.seek(self.base + offset)
        return self.fh.read(size)

    def find_caches(self):
        """Every sector that begins `AHSX`. A linear pass over the file."""
        hits = []
        chunk = 1 << 24
        for pos in range(0, self.size, chunk):
            b = self.read(pos, min(chunk, self.size - pos))
            for i in range(0, len(b), SECTOR):
                if b[i:i + 4] == CACHE_MAGIC:
                    hits.append(pos + i)
        return hits


# ---------------------------------------------------------------------------
# The codec: SLZ method 3, big-endian, with a preloaded window.

def unpack_wide_be(src, history):
    """tri-Ace's halfword LZ77 (slz.md §2b-3) in big-endian halfwords.

    `history` is prepended to the window and not returned: a distance can
    reach back into it. Returns (output, bytes consumed, ended on a token).
    """
    out = bytearray(history)
    skip = len(out)
    i, n, flags, left = 0, len(src), 0, 0
    while i + 1 < n:
        if left == 0:
            flags = (src[i] << 8) | src[i + 1]
            i += 2
            left = 16
            if i + 1 >= n:
                break
        literal = flags & 1
        flags >>= 1
        left -= 1
        if literal:
            out += src[i:i + 2]
            i += 2
            continue
        token = (src[i] << 8) | src[i + 1]
        i += 2
        dist = token & 0x0FFF
        if dist == 0:
            return bytes(out[skip:]), i, True
        start = len(out) - dist * 2
        if start < 0:
            raise ShaderError("distance reaches before the dictionary")
        length = ((token >> 12) + 2) * 2
        if start + length <= len(out):
            out += out[start:start + length]
        else:  # an overlapping copy propagates, as an LZ77 must
            for k in range(length):
                out.append(out[start + k])
    return bytes(out[skip:]), i, False


def crc16_x25(data):
    crc = 0xFFFF
    for v in data:
        crc ^= v
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


# ---------------------------------------------------------------------------
# The two containers.

class Record:
    __slots__ = ("offset", "hash", "size", "full", "coded", "crc", "flags", "raw")

    def __init__(self, offset, raw):
        self.offset = offset
        self.raw = raw
        (self.hash, self.size, self.full, self.coded, self.crc,
         self.flags) = struct.unpack(">6H", raw[:12])

    @property
    def key(self):
        return self.raw[0x0C:self.coded]

    @property
    def is_alias(self):
        return self.size == self.full

    def alias_target(self):
        """The record an alias points at: its u32 names that record's +0x0C."""
        return struct.unpack(">I", self.raw[self.coded:self.coded + 4])[0] - 0x0C


class Cache:
    def __init__(self, data, offset=0):
        if data[:4] != CACHE_MAGIC:
            raise ShaderError("no AHSX at 0x%X" % offset)
        self.offset = offset
        self.mask = struct.unpack(">I", data[4:8])[0]
        self.version = struct.unpack(">HH", data[8:12])
        self.count = struct.unpack(">H", data[12:14])[0]
        self.dictionary = data[0x10:0x10 + DICT_SIZE]
        self.records = []
        o = 0x10 + DICT_SIZE
        for _ in range(self.count):
            size = struct.unpack(">H", data[o + 2:o + 4])[0]
            if size < 12 or o + size > len(data):
                raise ShaderError("record walk left the cache at +0x%X" % o)
            self.records.append(Record(o, data[o:o + size]))
            o += size
        self.end = o

    @classmethod
    def read(cls, src, offset):
        head = src.read(offset, 0x10)
        count = struct.unpack(">H", head[12:14])[0]
        # walk the size fields without reading the whole cache twice
        want, o = 0x10 + DICT_SIZE, 0x10 + DICT_SIZE
        data = bytearray(src.read(offset, want))
        for _ in range(count):
            if len(data) < o + 4:
                data += src.read(offset + len(data), 1 << 20)
            o += struct.unpack(">H", data[o + 2:o + 4])[0]
        if len(data) < o:
            data += src.read(offset + len(data), o - len(data))
        return cls(bytes(data[:o]), offset)

    def decode(self, rec):
        """A shader record's body, header included, and its blob."""
        out, used, ended = unpack_wide_be(rec.raw[rec.coded:], self.dictionary)
        body = rec.raw[:rec.coded] + out
        if not ended or len(body) != rec.full or used != rec.size - rec.coded:
            raise ShaderError("record +0x%X does not decode cleanly" % rec.offset)
        at, size = struct.unpack(">HH", body[rec.coded + 0x12:rec.coded + 0x16])
        if at + size != len(body):
            raise ShaderError("record +0x%X: blob does not end the record" % rec.offset)
        return body, body[at:]


def read_library(src):
    """The fixed library at ud1.bin +0xC000, or [] where there is none."""
    if src.whole_image:
        return []
    head = src.read(LIBRARY_OFFSET, 0x10)
    first, count = struct.unpack(">II", head[:8])
    if first != 0x0C or not 0 < count < 0x1000 or head[8:16] != bytes(8):
        return []
    table = src.read(LIBRARY_OFFSET + 0x10, 4 * count)
    blobs = []
    for i in range(count):
        e = struct.unpack(">I", table[4 * i:4 * i + 4])[0]
        at = LIBRARY_OFFSET + (e & 0x7FFFFFFF)
        magic, vsize, psize = struct.unpack(">III", src.read(at, 12))
        blob = src.read(at, vsize + psize)
        if (magic == 0x102A1100) != bool(e & 0x80000000):
            raise ShaderError("library entry %d: flag bit disagrees with magic" % i)
        blobs.append((at, blob))
    return blobs


# ---------------------------------------------------------------------------
# One compiled blob.

class Blob:
    def __init__(self, x):
        magic, self.vsize, self.psize, _, ctab, self.defs, sh = struct.unpack(">7I", x[:28])
        if magic & 0xFFFFFF00 != 0x102A1100 or magic & 0xEE:
            raise ShaderError("not an XDK shader blob: magic 0x%08X" % magic)
        if self.vsize + self.psize != len(x):
            raise ShaderError("virtual + physical size does not match the blob")
        # bit 0 is the shader type; bit 4 appears on Star Ocean 4's newer XDK
        # vertex shaders and is unexplained
        self.magic = magic
        self.kind = "vs" if magic & 1 else "ps"
        self.x = x
        phys, size = struct.unpack(">II", x[sh:sh + 8])
        if phys + size != self.psize or size % 12:
            raise ShaderError("shader header does not tile the physical part")
        self.code = x[self.vsize + phys:self.vsize + phys + size]
        self.literals = x[self.vsize:self.vsize + phys]
        self._ctab(ctab)

    def _ctab(self, off):
        base = off + 4
        size, creator, version, n, info, _, target = struct.unpack(">7I", self.x[base:base + 28])
        self.version = version
        self.creator = self._cstr(base + creator) if creator else ""
        self.target = self._cstr(base + target) if target else ""
        self.constants = []
        for i in range(n):
            p = base + info + 20 * i
            name, rset, rindex, rcount = struct.unpack(">IHHH", self.x[p:p + 10])
            self.constants.append((self._cstr(base + name), rset, rindex, rcount))

    def _cstr(self, at):
        end = self.x.index(b"\0", at)
        s = self.x[at:end]
        if not re.fullmatch(rb"[A-Za-z_0-9.]+", s):
            raise ShaderError("constant table string at 0x%X is not a name" % at)
        return s.decode()

    def declared(self):
        fl, sm, bo = set(), set(), set()
        for _, rset, rindex, rcount in self.constants:
            r = range(rindex, rindex + rcount)
            if rset == REGSET_FLOAT:
                fl.update(r)
            elif rset == REGSET_SAMPLER:
                sm.update(i + (VS_SAMPLER_BASE if self.kind == "vs" else 0) for i in r)
            elif rset == REGSET_BOOL:
                bo.update(i + (PS_BOOL_BASE if self.kind == "ps" else 0) for i in r)
        fl.update(self.literal_regs())
        return fl, sm, bo

    def literal_regs(self):
        """The float registers the definition table fills with literals.

        Its word at +0x14 is `register << 16 | dwords`, the register counted in
        the full 512-entry file: c252 is 0x0FC in a vertex shader and 0x1FC in
        a pixel shader. Four registers in every blob of this game; in Star Ocean
        4's, eight from c248 in 33 blobs and twelve from c244 in two.
        """
        if not self.defs:
            return range(0)
        word = struct.unpack(">I", self.x[self.defs + 0x14:self.defs + 0x18])[0]
        first = (word >> 16) & 0xFF
        return range(first, first + (word & 0xFFFF) // 4)


# ---------------------------------------------------------------------------
# The microcode.

def decode_cf(v):
    op = bits(v, 44, 4)
    d = {"op": op}
    if op in EXEC_OPS:
        d.update(addr=bits(v, 0, 12), count=bits(v, 12, 3), seq=bits(v, 16, 12))
        if op in BOOL_EXEC_OPS:
            d.update(bool=bits(v, 34, 8), cond=bits(v, 42, 1))
        elif op in (5, 6):
            d.update(cond=bits(v, 42, 1))
    elif op in (7, 8, 9, 11):
        d.update(addr=bits(v, 0, 13), loop=bits(v, 16, 5), bool=bits(v, 34, 8),
                 cond=bits(v, 42, 1))
    elif op == 12:
        d.update(size=bits(v, 0, 3), type=bits(v, 41, 2))
    return d


def decode_alu(a, b, c):
    return dict(
        vdst=bits(a, 0, 6), vrel=bits(a, 6, 1), cabs=bits(a, 7, 1),
        sdst=bits(a, 8, 6), srel=bits(a, 14, 1), export=bits(a, 15, 1),
        vmask=bits(a, 16, 4), smask=bits(a, 20, 4), vsat=bits(a, 24, 1),
        ssat=bits(a, 25, 1), sop=bits(a, 26, 6),
        swz=(bits(b, 16, 8), bits(b, 8, 8), bits(b, 0, 8)),
        neg=(bits(b, 26, 1), bits(b, 25, 1), bits(b, 24, 1)),
        pcond=bits(b, 27, 1), pred=bits(b, 28, 1), crel=(bits(b, 31, 1), bits(b, 30, 1)),
        reg=(bits(c, 16, 8), bits(c, 8, 8), bits(c, 0, 8)), vop=bits(c, 24, 5),
        sel=(bits(c, 31, 1), bits(c, 30, 1), bits(c, 29, 1)))


def decode_fetch(a, b, c):
    op = bits(a, 0, 5)
    d = dict(op=op, src=bits(a, 5, 6), dst=bits(a, 12, 6), const=bits(a, 20, 5),
             dswz=bits(b, 0, 12), pred=bits(b, 31, 1), pcond=bits(c, 31, 1))
    if op == 0:
        d.update(sel=bits(a, 25, 2), sswz=bits(a, 30, 2))
    else:
        d.update(sswz=bits(a, 26, 6), dim=bits(c, 14, 2))
    return d


class Program:
    """The control-flow program and every clause instruction it runs."""

    def __init__(self, code):
        self.code = code
        self.slots = len(code) // 12
        self.cf = []
        first, s = self.slots, 0
        while s < first:
            a, b, c = struct.unpack(">III", code[12 * s:12 * s + 12])
            for v in (a | ((b & 0xFFFF) << 32), (b >> 16) | (c << 16)):
                d = decode_cf(v)
                self.cf.append(d)
                if d["op"] in EXEC_OPS and d["count"]:
                    first = min(first, d["addr"])
            s += 1
        self.first = first
        self.body = []
        for d in self.cf:
            if d["op"] not in EXEC_OPS:
                continue
            for k in range(d["count"]):
                slot = d["addr"] + k
                a, b, c = struct.unpack(">III", code[12 * slot:12 * slot + 12])
                if (d["seq"] >> (2 * k)) & 1:
                    self.body.append(("fetch", slot, decode_fetch(a, b, c)))
                else:
                    self.body.append(("alu", slot, decode_alu(a, b, c)))

    def problems(self, blob):
        """The three checks `verify` makes; an empty list means it passed."""
        out = []
        tail = self.slots
        while tail > self.first and self.code[12 * (tail - 1):12 * tail] == bytes(12):
            tail -= 1
        seen = collections.Counter(s for _, s, _ in self.body)
        if set(seen) != set(range(self.first, tail)) or max(seen.values(), default=1) > 1:
            out.append("coverage")
        if not any(d["op"] in EXEC_END_OPS for d in self.cf):
            out.append("no EXEC_END")
        fl, sm, bo = blob.declared()
        for kind, _, d in self.body:
            if kind == "fetch":
                if d["op"] not in FETCH_OPS:
                    out.append("fetch opcode %d" % d["op"])
                elif d["op"] == 1 and d["const"] not in sm:
                    out.append("tfetch from undeclared tf%d" % d["const"])
                continue
            if d["vop"] not in VECTOR_OPS or d["sop"] not in SCALAR_OPS:
                out.append("alu opcode %d/%d" % (d["vop"], d["sop"]))
                continue
            for sel, reg in used_sources(d):
                if sel == 0 and not any(d["crel"]) and reg not in fl:
                    out.append("reads undeclared c%d" % reg)
        for d in self.cf:
            if d["op"] in BOOL_EXEC_OPS and d["bool"] not in bo:
                out.append("tests undeclared b%d" % d["bool"])
        return out


def used_sources(d):
    vec_live = d["vmask"] or d["vop"] in VECTOR_SIDE_EFFECT
    n = VECTOR_ARITY.get(d["vop"], 2) if vec_live else 0
    used = [(d["sel"][i], d["reg"][i]) for i in range(n)]
    if n < 3 and d["sop"] != SCALAR_NONE:
        used.append((d["sel"][2], d["reg"][2]))
    return used


# ---------------------------------------------------------------------------
# Printing.

def swizzle(s):
    t = "".join("xyzw"[((s >> (2 * i)) + i) & 3] for i in range(4))
    return "" if t == "xyzw" else "." + t


def mask(m):
    return "." + "".join("xyzw"[i] for i in range(4) if m >> i & 1)


def dest(d, reg, rel, kind):
    if d["export"]:
        if reg == 32:
            return "eA"
        if 33 <= reg <= 37:
            return "eM%d" % (reg - 33)
        if kind == "vs":
            names = {62: "oPos", 63: "oPts"}
            return names.get(reg, "o%d" % reg)
        return {0: "oC0", 1: "oC1", 2: "oC2", 3: "oC3", 61: "oDepth"}.get(reg, "export%d" % reg)
    return "r[aL+%d]" % reg if rel else "r%d" % reg


def source(d, i, kind):
    sel, reg, neg = d["sel"][i], d["reg"][i], d["neg"][i]
    if sel:
        s = ("r[aL+%d]" % (reg & 0x3F)) if reg & 0x40 else "r%d" % (reg & 0x3F)
        if reg & 0x80:
            s = "|%s|" % s
    else:
        s = "c%d" % reg
        if any(d["crel"]):
            s = "c[a0+%d]" % reg
        if d["cabs"]:
            s = "|%s|" % s
    return ("-" if neg else "") + s + swizzle(d["swz"][i])


def fetch_swizzle(s):
    return "." + "".join("xyzw01?_"[bits(s, 3 * i, 3)] for i in range(4))


def render(prog, blob):
    lines = []
    for d in prog.cf:
        op, name = d["op"], CF_OPS.get(d["op"], "CF_%d" % d["op"])
        if op in EXEC_OPS:
            if not d["count"] and op not in EXEC_END_OPS:
                continue
            kinds = "".join("F" if (d["seq"] >> (2 * k)) & 1 else "A" for k in range(d["count"]))
            cond = ""
            if "bool" in d:
                cond = " %sb%d" % ("" if d["cond"] else "!", d["bool"])
            elif "cond" in d:
                cond = " %sp0" % ("" if d["cond"] else "!")
            lines.append("    %-22s @%d x%d %s%s" % (name, d["addr"], d["count"], kinds, cond))
        elif op == 12:
            t = {1: "position" if blob.kind == "vs" else "colors",
                 2: "interpolators" if blob.kind == "vs" else "colors", 3: "memory"}
            lines.append("    %-22s %s" % (name, t.get(d["type"], "type%d" % d["type"])))
        elif op:
            lines.append("    %-22s %s" % (name, " ".join("%s=%d" % kv for kv in d.items() if kv[0] != "op")))
    for kind, slot, d in prog.body:
        pred = ""
        if kind == "fetch":
            if d["pred"]:
                pred = "(%sp0) " % ("" if d["pcond"] else "!")
            name = FETCH_OPS.get(d["op"], "fetch%d" % d["op"])
            if d["op"] == 0:
                txt = "%s r%d%s, r%d.%s, vf%d" % (name, d["dst"], fetch_swizzle(d["dswz"]),
                                               d["src"], "xyzw"[d["sswz"]], d["const"] * 3 + d["sel"])
            else:
                ncoord = {0: 1, 1: 2}.get(d["dim"], 3) if d["op"] == 1 else 3
                src = "".join("xyzw"[bits(d["sswz"], 2 * i, 2)] for i in range(ncoord))
                txt = "%s%s r%d%s, r%d.%s, tf%d" % (name, TEX_DIM[d["dim"]] if d["op"] == 1 else "",
                                                   d["dst"], fetch_swizzle(d["dswz"]), d["src"], src,
                                                   d["const"])
            lines.append("%4d  %s%s" % (slot, pred, txt))
            continue
        if d["pred"]:
            pred = "(%sp0) " % ("" if d["pcond"] else "!")
        parts = []
        vec_live = d["vmask"] or d["vop"] in VECTOR_SIDE_EFFECT
        if vec_live:
            n = VECTOR_ARITY.get(d["vop"], 2)
            parts.append("%s%s %s%s, %s" % (
                VECTOR_OPS[d["vop"]], "_sat" if d["vsat"] else "",
                dest(d, d["vdst"], d["vrel"], blob.kind), mask(d["vmask"]) if d["vmask"] else "",
                ", ".join(source(d, i, blob.kind) for i in range(n))))
        if d["sop"] != SCALAR_NONE and (d["smask"] or d["sop"] in SCALAR_SIDE_EFFECT):
            parts.append("%s%s %s%s, %s" % (
                SCALAR_OPS.get(d["sop"], "SOP_%d" % d["sop"]), "_sat" if d["ssat"] else "",
                # an exporting instruction sends both halves to the one export register
                dest(d, d["vdst"] if d["export"] else d["sdst"], d["srel"], blob.kind),
                mask(d["smask"]) if d["smask"] else "",
                source(d, 2, blob.kind)))
        lines.append("%4d  %s%s" % (slot, pred, "  +  ".join(parts) if parts else "NOP"))
    return lines


def describe(blob):
    regs = {REGSET_BOOL: "b", REGSET_INT: "i", REGSET_FLOAT: "c", REGSET_SAMPLER: "s"}
    return ", ".join("%s %s%d%s" % (n, regs.get(s, "?"), i, "..%d" % (i + c - 1) if c > 1 else "")
                     for n, s, i, c in blob.constants)


# ---------------------------------------------------------------------------
# Commands.

def open_all(args):
    src = Source(args.file)
    caches = [Cache.read(src, off) for off in src.find_caches()]
    return src, caches


def cmd_scan(args):
    src, caches = open_all(args)
    lib = read_library(src)
    where = "image" if src.whole_image else "ud1.bin"
    if lib:
        print("fixed library at ud1.bin +0x%X: %d shaders, %d pixel, %d vertex" % (
            LIBRARY_OFFSET, len(lib), sum(Blob(b).kind == "ps" for _, b in lib),
            sum(Blob(b).kind == "vs" for _, b in lib)))
    else:
        print("no fixed library")
    for i, c in enumerate(caches):
        aliases = sum(r.is_alias for r in c.records)
        print("cache %d at %s +0x%08X: %6d records, %6d shaders, %6d aliases, %9d bytes,"
              " version %d.%d, mask %08X" % (i, where, c.offset, c.count, c.count - aliases,
                                             aliases, c.end, c.version[0], c.version[1], c.mask))


def cmd_verify(args):
    src, caches = open_all(args)
    tally = collections.Counter()
    failures = collections.Counter()
    first_failure = {}
    distinct = set()
    ops = collections.Counter()

    def check(tag, x):
        h = hashlib.sha1(x).digest()
        if h in distinct:
            return
        distinct.add(h)
        try:
            blob = Blob(x)
            prog = Program(blob.code)
            bad = prog.problems(blob)
        except ShaderError as e:
            bad = [str(e)]
        if bad:
            for b in set(bad):
                failures[b.split(" c")[0].split(" tf")[0].split(" b")[0]] += 1
                first_failure.setdefault(b, tag)
        else:
            tally["blobs passing all three checks"] += 1
            tally[blob.kind] += 1
            for kind, _, d in prog.body:
                if kind == "alu":
                    ops[d["vop"]] += 1

    for at, blob in read_library(src):
        check("library +0x%X" % at, blob)
    for i, c in enumerate(caches):
        tally["caches at version 0x%04X.%04X" % c.version] += 1
        starts = {r.offset for r in c.records}
        crc = crc16_x25(c.dictionary)
        tally["caches"] += 1
        for r in c.records:
            tally["records"] += 1
            if (r.coded - 0x0C) not in (align4(r.raw[0x0E]), align4(r.raw[0x0E] + 0x100)):
                failures["key length byte"] += 1
            if r.crc != crc:
                failures["dictionary CRC"] += 1
            if r.is_alias:
                if not r.flags & 0x2000 or r.alias_target() not in starts or r.alias_target() >= r.offset:
                    failures["alias target"] += 1
                else:
                    tally["aliases resolving to an earlier record"] += 1
                continue
            try:
                _, blob = c.decode(r)
            except ShaderError as e:
                failures[str(e).split(" +")[0]] += 1
                continue
            tally["records decoding cleanly"] += 1
            check("cache %d +0x%X" % (i, r.offset), blob)
    for k, v in tally.items():
        print("%-42s %8d" % (k, v))
    print("%-42s %8d" % ("distinct blobs", len(distinct)))
    if ops:
        print("vector opcode 2 (MAX_V) %d times, 3 (MIN_V) %d times" % (ops[2], ops[3]))
    for k, v in failures.items():
        print("FAIL %-37s %8d" % (k, v))
    for k, v in list(first_failure.items())[:10]:
        print("  first: %s at %s" % (k, v))
    return 1 if failures else 0


def cmd_list(args):
    src = Source(args.file)
    if args.cache is None:
        for i, (at, x) in enumerate(read_library(src)):
            b = Blob(x)
            print("lib %2d  +0x%05X  %s  %4d slots  %s" % (i, at, b.kind, len(b.code) // 12, describe(b)))
        return
    c = Cache.read(src, src.find_caches()[args.cache])
    for r in c.records:
        if r.is_alias:
            print("+0x%07X  alias of +0x%07X" % (r.offset, r.alias_target()))
            continue
        _, x = c.decode(r)
        b = Blob(x)
        print("+0x%07X  %s  %4d slots  key %s  %s" % (r.offset, b.kind, len(b.code) // 12,
                                                      r.key[:8].hex(), describe(b)))


def cmd_dis(args):
    src = Source(args.file)
    if args.lib is not None:
        at, x = read_library(src)[args.lib]
        where = "library entry %d, ud1.bin +0x%X" % (args.lib, at)
    else:
        c = Cache.read(src, src.find_caches()[args.cache])
        rec = next((r for r in c.records if r.offset == args.record), None)
        if rec is None:
            raise ShaderError("no record starts at +0x%X" % args.record)
        if rec.is_alias:
            print("; alias of +0x%X" % rec.alias_target())
            rec = next(r for r in c.records if r.offset == rec.alias_target())
        _, x = c.decode(rec)
        where = "cache %d record +0x%X" % (args.cache, rec.offset)
    b = Blob(x)
    prog = Program(b.code)
    print("; %s -- %s, compiler %s, %d slots" % (where, b.target, b.creator, prog.slots))
    for name, rset, rindex, rcount in b.constants:
        print(";   %-28s %s%d%s" % (name, "bics"[rset], rindex,
                                     "..%d" % (rindex + rcount - 1) if rcount > 1 else ""))
    if b.literals:
        lit = struct.unpack(">%df" % (len(b.literals) // 4), b.literals)
        for i in range(0, len(lit), 4):
            if any(lit[i:i + 4]):
                print(";   literal c%-24d %s" % (b.literal_regs()[0] + i // 4,
                                              ", ".join("%g" % v for v in lit[i:i + 4])))
    for line in render(prog, b):
        print(line)
    bad = prog.problems(b)
    if bad:
        print("; CHECKS FAILED: " + "; ".join(sorted(set(bad))))


def cmd_optable(args):
    data = open(args.exe, "rb").read()
    at = -1
    for m in re.finditer(re.escape(b"OP_UNKNOWN\0"), data):
        if data[m.start() - 8:m.start()] == struct.pack(">II", 0, 0xFF):
            at = m.start()
            break
    if at < 0:
        raise ShaderError("no compiler opcode table in %s" % args.exe)
    p = at - 8
    rows = []
    while True:
        index, op = struct.unpack(">II", data[p:p + 8])
        name = data[p + 8:p + 0x2C].split(b"\0")[0]
        if not re.fullmatch(rb"[A-Z0-9_]{2,}", name) or index != len(rows):
            break
        cls, extra = struct.unpack(">II", data[p + 0x2C:p + 0x34])
        rows.append((p, index, op, name.decode(), cls, extra))
        p += 0x34
    print("compiler opcode table at file offset 0x%X, %d rows" % (at - 8, len(rows)))
    ours = {}
    for table in (CF_OPS, VECTOR_OPS, SCALAR_OPS):
        for k, v in table.items():
            ours[v] = k
    for p, index, op, name, cls, extra in rows:
        mark = ""
        if name in ours and ours[name] != op:
            mark = "  <- hardware %d" % ours[name]
        print("0x%06X  %3d  op %3d  class 0x%02X  %-18s%s" % (p, index, op, cls, name, mark))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, text in (("scan", cmd_scan, "locate the library and the caches"),
                           ("verify", cmd_verify, "decode and check every shader"),
                           ("list", cmd_list, "one line per shader"),
                           ("dis", cmd_dis, "disassemble one shader")):
        s = sub.add_parser(name, help=text)
        s.add_argument("file", help="a disc image, or ud1.bin on its own")
        s.set_defaults(fn=fn)
        if name in ("list", "dis"):
            s.add_argument("--cache", type=int, help="cache number, as `scan` prints it")
        if name == "dis":
            s.add_argument("--record", type=lambda v: int(v, 0), help="record offset in the cache")
            s.add_argument("--lib", type=int, help="fixed-library entry")
    s = sub.add_parser("optable", help="print the XDK compiler's opcode table")
    s.add_argument("exe", help="the decrypted executable, as xex.py extract writes it")
    s.set_defaults(fn=cmd_optable)
    args = p.parse_args(argv)
    try:
        return args.fn(args) or 0
    except ShaderError as e:
        print("error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
