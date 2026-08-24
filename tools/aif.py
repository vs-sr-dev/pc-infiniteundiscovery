#!/usr/bin/env python3
"""
aif.py -- reader for AIF, the Aska Image File.

Every texture in Infinite Undiscovery is an `AIF ` payload. They arrive under
four different resource tags -- `IMG-`, `MAIF`, `RMD-` plain, and `MTEX` behind
SLZ compression -- but the format is the same in all four, and it is a thin
wrapper around a texture in the Xbox 360 GPU's own memory layout. Reading one
therefore means undoing two things the console did on the way in: the tiled
address swizzle, and a byte order chosen to suit the GPU's fetch unit rather
than any file format.

Layout
------
Big-endian throughout. A 4096-byte header, then pixel data.

    0x00  4  "AIF "
    0x04  4  total payload length, header included
    0x08  8  zero
    0x10  4  "imgX", the image sub-chunk
    0x14  4  sub-chunk header size, 0x70 everywhere
    0x18  4  zero
    0x1C  4  zero, or 0x70
    0x20  4  asset identifier, four ASCII characters
    0x24  4  unidentified, varies per asset
    0x28  4  zero
    0x2C  4  0x0FF0 everywhere
    0x30  4  pixel format
    0x34  4  flags
    0x38  2  width in pixels
    0x3A  2  height in pixels
    0x3C  2  depth, 1 everywhere
    0x3E  2  bits per pixel
    0x40  2  bytes per element -- per 4x4 block if compressed, per pixel if not
    0x42  2  width in elements
    0x44  2  height in elements
    0x46  2  one
    0x48  4  pitch in bytes
    0x4C  4  size of the pixel data
    0x50 ..  zero to the end of the header
    0x1000   pixel data

The identifier at 0x20 is a name, not a magic: the prefixes group the assets by
purpose -- `CH` for characters, `BG` for backgrounds, `EF` for effects, `PG`
for a fourth kind -- and the executable carries its own embedded AIFs tagged
`Dg#1`.

Formats
-------
The value at 0x30 is tri-Ace's own enumeration, but the header states the
element size next to it, so nothing has to be assumed:

| 0x30 | bpp | element | Reading |
| --- | --- | --- | --- |
| 0x46 | 16 | 2 | A4R4G4B4 |
| 0x48 | 32 | 4 | A8R8G8B8 |
| 0x50 | 4 | 8 | DXT1 |
| 0x52 | 8 | 16 | DXT2/3, explicit alpha |
| 0x54 | 8 | 16 | DXT4/5, interpolated alpha |

The split between 0x52 and 0x54 is a decode result, not a guess at the
numbering. 0x54 is settled by smoothness -- its alpha decodes 75x smoother
interpolated than explicit, on 100% of blocks with partial alpha. 0x52 needs a
different test, since those textures are almost all binary alpha and both
decoders agree there: 93% of its alpha-half bytes contain only 0 and F nibbles,
which is only possible if they are sixteen 4-bit values. See docs/formats/aif.md.

Tiling
------
`pitch` is not `elements across x element size`. It is that width **rounded up
to 32 elements**, and the data height is rounded up the same way, because the
GPU addresses texture memory in 32x32-element tiles. That rounding is the
visible edge of the swizzle: element (x, y) does not live at `y * pitch + x`
but at the address `tiled_offset` computes, which interleaves bits of x and y
so that neighbouring texels in both directions stay close in memory.

Byte order
----------
Everything is big-endian, pixel data included, but what that means depends on
the field width. A8R8G8B8 texels are already A, R, G, B in order and need
nothing done to them. A4R4G4B4 and the DXT formats are built out of 16-bit
fields, which a PC decoder expects little-endian, so their bytes swap in pairs.

Swapping A8R8G8B8 too still produces a clean image with permuted channels,
which is easy to miss. The alpha channel is the tell: in a UI atlas half of it
is exactly 0x00 or 0xFF and no colour channel is.

Usage
-----
    python tools/aif.py info <file.aif>
    python tools/aif.py png  <file.aif> <out.png>
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib

MAGIC = b"AIF "
SUBCHUNK = b"imgX"
HEADER_SIZE = 0x1000
TILE = 32

FMT_ARGB4444 = 0x46
FMT_ARGB8888 = 0x48
FMT_DXT1 = 0x50
FMT_DXT3 = 0x52
FMT_DXT5 = 0x54

FORMAT_NAMES = {
    FMT_ARGB4444: "A4R4G4B4",
    FMT_ARGB8888: "A8R8G8B8",
    FMT_DXT1: "DXT1",
    FMT_DXT3: "DXT2/3",
    FMT_DXT5: "DXT4/5",
}

COMPRESSED = (FMT_DXT1, FMT_DXT3, FMT_DXT5)


class AifError(Exception):
    pass


def align_up(value, to):
    return (value + to - 1) // to * to


def tiled_offset(x, y, width_elements, element_bytes):
    """Xbox 360 2D tiled address, in elements.

    Straight from the GPU's addressing rule. `x` and `y` count elements -- 4x4
    blocks for a compressed format, pixels otherwise -- and the result is the
    element index to read from, not a byte offset.
    """
    aligned = align_up(width_elements, TILE)
    log_bpp = element_bytes.bit_length() - 1
    macro = ((x >> 5) + (y >> 5) * (aligned >> 5)) << (log_bpp + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log_bpp
    offset = (macro + ((micro & ~0xF) << 1) + (micro & 0xF)
              + ((y & 8) << (3 + log_bpp)) + ((y & 1) << 4))
    return ((((offset & ~0x1FF) << 3) + ((offset & 0x1C0) << 2) + (offset & 0x3F)
             + ((y & 16) << 7) + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6))
            >> log_bpp)


class AifImage:
    def __init__(self, data):
        if data[:4] != MAGIC:
            raise AifError("not an AIF payload")
        self.data = data
        self.total_size = struct.unpack_from(">I", data, 4)[0]
        if data[0x10:0x14] != SUBCHUNK:
            raise AifError("no imgX sub-chunk at 0x10")
        self.subheader_size = struct.unpack_from(">I", data, 0x14)[0]
        self.identifier = data[0x20:0x24]
        self.unknown_24 = struct.unpack_from(">I", data, 0x24)[0]
        self.format, self.flags = struct.unpack_from(">II", data, 0x30)
        (self.width, self.height, self.depth,
         self.bpp) = struct.unpack_from(">HHHH", data, 0x38)
        (self.element_bytes, self.elements_x, self.elements_y,
         _one) = struct.unpack_from(">HHHH", data, 0x40)
        self.pitch, self.data_size = struct.unpack_from(">II", data, 0x48)

        if self.element_bytes == 0:
            raise AifError("zero element size")
        self.tiled_width = self.pitch // self.element_bytes
        self.tiled_height = align_up(self.elements_y, TILE)

    @property
    def format_name(self):
        return FORMAT_NAMES.get(self.format, "unknown 0x%02X" % self.format)

    @property
    def compressed(self):
        return self.format in COMPRESSED

    def base_level_size(self):
        return self.pitch * self.tiled_height

    def mipmap_bytes(self):
        """Bytes beyond the base level -- the mip chain, if there is one.

        `data_size` counts the base level only, so the mip chain shows up as
        the difference between it and the payload's own total length.
        """
        return max(0, self.total_size - HEADER_SIZE - self.data_size)

    def has_mipmaps(self):
        return self.mipmap_bytes() > 0

    # -- pixel data --------------------------------------------------------

    def untiled(self):
        """Return the base mip level as linear, PC-order element data."""
        raw = self.data[HEADER_SIZE:HEADER_SIZE + self.base_level_size()]
        if len(raw) < self.base_level_size():
            raise AifError("pixel data is %d bytes short"
                           % (self.base_level_size() - len(raw)))

        # Compressed data is stored as big-endian 16-bit words, so every pair
        # of bytes has to be swapped to give the block layout a PC decoder
        # expects. A8R8G8B8 is *not* swapped -- its bytes are already A, R, G,
        # B in that order. Swapping it anyway still decodes to a clean image,
        # just with the channels shuffled, which is the kind of mistake that
        # survives a casual look; the alpha channel gives it away, since in a
        # UI atlas half of it is exactly 0x00 or 0xFF and no colour channel is.
        width = 1 if self.element_bytes == 4 else 2
        if width == 1:
            swapped = raw
        else:
            swapped = bytearray(len(raw))
            swapped[0::2] = raw[1::2]
            swapped[1::2] = raw[0::2]

        size = self.element_bytes
        out = bytearray(self.elements_x * self.elements_y * size)
        for y in range(self.elements_y):
            row = y * self.elements_x * size
            for x in range(self.elements_x):
                source = tiled_offset(x, y, self.tiled_width, size) * size
                out[row + x * size:row + x * size + size] = \
                    swapped[source:source + size]
        return bytes(out)

    def to_rgba(self):
        """Decode the base mip level to 8-bit RGBA."""
        elements = self.untiled()
        if self.format == FMT_DXT1:
            return _decode_dxt(elements, self.width, self.height, self.elements_x,
                               self.elements_y, alpha=None)
        if self.format == FMT_DXT3:
            return _decode_dxt(elements, self.width, self.height, self.elements_x,
                               self.elements_y, alpha="explicit")
        if self.format == FMT_DXT5:
            return _decode_dxt(elements, self.width, self.height, self.elements_x,
                               self.elements_y, alpha="interpolated")
        if self.format == FMT_ARGB8888:
            out = bytearray(self.width * self.height * 4)
            for i in range(self.width * self.height):
                a, r, g, b = elements[i * 4:i * 4 + 4]
                out[i * 4:i * 4 + 4] = bytes((r, g, b, a))
            return bytes(out)
        if self.format == FMT_ARGB4444:
            out = bytearray(self.width * self.height * 4)
            for i in range(self.width * self.height):
                value = elements[i * 2] | (elements[i * 2 + 1] << 8)
                a = (value >> 12) & 0xF
                r = (value >> 8) & 0xF
                g = (value >> 4) & 0xF
                b = value & 0xF
                out[i * 4:i * 4 + 4] = bytes((r * 17, g * 17, b * 17, a * 17))
            return bytes(out)
        raise AifError("no decoder for %s" % self.format_name)


# -- DXT ------------------------------------------------------------------

def _rgb565(value):
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def _decode_dxt(blocks, width, height, blocks_x, blocks_y, alpha):
    """Decode DXT1/3/5 blocks to RGBA. `alpha` picks the DXT flavour."""
    stride = 16 if alpha else 8
    out = bytearray(width * height * 4)
    for by in range(blocks_y):
        for bx in range(blocks_x):
            base = (by * blocks_x + bx) * stride
            block = blocks[base:base + stride]
            if len(block) < stride:
                continue

            alphas = None
            if alpha == "explicit":
                bits = int.from_bytes(block[0:8], "little")
                alphas = [((bits >> (4 * i)) & 0xF) * 17 for i in range(16)]
                colour = block[8:16]
            elif alpha == "interpolated":
                a0, a1 = block[0], block[1]
                table = [a0, a1]
                if a0 > a1:
                    table += [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
                else:
                    table += [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)]
                    table += [0, 255]
                bits = int.from_bytes(block[2:8], "little")
                alphas = [table[(bits >> (3 * i)) & 7] for i in range(16)]
                colour = block[8:16]
            else:
                colour = block

            c0, c1 = struct.unpack_from("<HH", colour, 0)
            r0, g0, b0 = _rgb565(c0)
            r1, g1, b1 = _rgb565(c1)
            palette = [(r0, g0, b0, 255), (r1, g1, b1, 255)]
            if c0 > c1 or alpha:
                palette.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3,
                                (2 * b0 + b1) // 3, 255))
                palette.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3,
                                (b0 + 2 * b1) // 3, 255))
            else:
                # DXT1's one-bit alpha: the fourth entry is transparent black.
                palette.append(((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255))
                palette.append((0, 0, 0, 0))

            indices = int.from_bytes(colour[4:8], "little")
            for i in range(16):
                x = bx * 4 + (i & 3)
                y = by * 4 + (i >> 2)
                if x >= width or y >= height:
                    continue
                r, g, b, a = palette[(indices >> (2 * i)) & 3]
                if alphas is not None:
                    a = alphas[i]
                position = (y * width + x) * 4
                out[position:position + 4] = bytes((r, g, b, a))
    return bytes(out)


# -- PNG ------------------------------------------------------------------

def write_png(path, width, height, rgba):
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)                       # filter type 0, none
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    with open(path, "wb") as fo:
        fo.write(b"\x89PNG\r\n\x1a\n")
        fo.write(chunk(b"IHDR", header))
        fo.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        fo.write(chunk(b"IEND", b""))


# -- commands --------------------------------------------------------------

def load(path):
    with open(path, "rb") as fh:
        return AifImage(fh.read())


def cmd_info(args):
    image = load(args.file)
    print("identifier   : %r" % image.identifier)
    print("total size   : %d" % image.total_size)
    print("format       : 0x%02X  %s" % (image.format, image.format_name))
    print("flags        : 0x%X" % image.flags)
    print("size         : %d x %d, %d bpp" % (image.width, image.height, image.bpp))
    print("elements     : %d x %d of %d bytes"
          % (image.elements_x, image.elements_y, image.element_bytes))
    print("pitch        : %d  (%d elements, padded from %d)"
          % (image.pitch, image.tiled_width, image.elements_x))
    print("data size    : %d" % image.data_size)
    print("base level   : %d bytes" % image.base_level_size())
    print("mipmaps      : %s" % ("%d bytes beyond the base level"
                                 % image.mipmap_bytes()
                                 if image.has_mipmaps() else "none"))
    return 0


def cmd_png(args):
    image = load(args.file)
    rgba = image.to_rgba()
    write_png(args.output, image.width, image.height, rgba)
    print("wrote %s: %d x %d from %s"
          % (args.output, image.width, image.height, image.format_name))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Reader for AIF, the Aska Image File.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="print the header")
    s.add_argument("file")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("png", help="decode the base mip level to a PNG")
    s.add_argument("file")
    s.add_argument("output")
    s.set_defaults(func=cmd_png)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
