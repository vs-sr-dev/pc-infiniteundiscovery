# AIF — the Aska Image File

Every texture in the game is an `AIF ` payload. They arrive under four resource
tags — `IMG-`, `MAIF` and `RMD-` stored plainly, `MTEX` behind
[SLZ](slz.md) compression — but the format is identical in all four.

AIF is a thin wrapper. What it wraps is a texture already in the Xbox 360 GPU's
own memory layout, ready to be handed to the hardware without processing. So
reading one is mostly a matter of undoing what the console's texture converter
did on the way in: a tiled address swizzle, and a byte order chosen to suit the
GPU's fetch unit rather than a file format.

Everything here was checked by decoding all 220 image resources in disc 1's
`ud1.bin` — 150.9 megapixels, no failures — and by looking at the results.

## 1. Layout

Big-endian throughout, like the rest of the game's data. A 4096-byte header,
then pixel data.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | `AIF ` |
| `0x04` | 4 | Total payload length, header included |
| `0x08` | 8 | Zero |
| `0x10` | 4 | `imgX` — the image sub-chunk |
| `0x14` | 4 | Sub-chunk header size, `0x70` everywhere |
| `0x18` | 4 | Zero |
| `0x1C` | 4 | Zero, or `0x70` |
| `0x20` | 4 | Asset identifier, four ASCII characters |
| `0x24` | 4 | Unidentified, varies per asset |
| `0x28` | 4 | Zero |
| `0x2C` | 4 | `0x0FF0` everywhere |
| `0x30` | 4 | Pixel format |
| `0x34` | 4 | Flags — `0x500`, `0x200`, `0x40400` or zero |
| `0x38` | 2 | Width in pixels |
| `0x3A` | 2 | Height in pixels |
| `0x3C` | 2 | Depth — 1 everywhere |
| `0x3E` | 2 | Bits per pixel |
| `0x40` | 2 | Bytes per element |
| `0x42` | 2 | Width in elements |
| `0x44` | 2 | Height in elements |
| `0x46` | 2 | One |
| `0x48` | 4 | Pitch in bytes |
| `0x4C` | 4 | Size of the base mip level |
| `0x50` | .. | Zero to the end of the header |
| `0x1000` | .. | Pixel data |

An **element** is one 4x4 block for a compressed format and one pixel
otherwise, so `elements = ceil(pixels / 4)` or `= pixels` respectively. The
header states the element size next to the format code, which means no format
has to be guessed at from the file size.

The value at `0x4C` counts the **base level only**. A mip chain, where present,
follows it, and shows up as the difference between the payload's total length
and `0x1000 + base level size`.

## 2. The identifier

The four bytes at `0x20` are a name, not a magic. Across disc 1's images the
prefixes fall into a small set:

| Prefix | Images | Reading |
| --- | ---: | --- |
| `CH` | 106 | Character |
| `BG` | 74 | Background |
| `EF` | 21 | Effect |
| `PG` | 14 | A fourth kind — the title screen and UI atlases are `PG02` |
| `ud`, `YM`, `kn` | 5 | One-offs |

The executable carries its own embedded AIFs — six of them — identified as
`Dg#1`.

## 3. Pixel formats

The code at `0x30` is tri-Ace's own enumeration.

| `0x30` | bpp | Element | Format | Images |
| --- | ---: | ---: | --- | ---: |
| `0x46` | 16 | 2 | A4R4G4B4 | 1 |
| `0x48` | 32 | 4 | A8R8G8B8 | 9 |
| `0x50` | 4 | 8 | DXT1 | 158 |
| `0x52` | 8 | 16 | DXT2/3 — explicit alpha | 17 |
| `0x54` | 8 | 16 | DXT4/5 — interpolated alpha | 35 |

The numbering steps by two from `0x50`, matching D3D's DXT1/DXT3/DXT5 spacing,
but the actual assignment was settled by decoding rather than by that
resemblance:

**`0x54` is interpolated alpha.** Decode a `0x54` texture both ways and measure
how much the alpha channel jumps between neighbouring texels: 1.20 as DXT5
against 90.24 as DXT3, over 3 695 blocks with partial alpha, and the
interpolated reading is smoother in **100 %** of them. There is no ambiguity to
argue about.

**`0x52` is explicit alpha.** This one needs a better test than smoothness,
because these textures are nearly all fully transparent or fully opaque, where
both decoders agree and the comparison is dominated by noise — measured on
partial-alpha blocks alone it actually points the wrong way, on a sample of
nine blocks the explicit decoder itself selected.

The test that settles it does not involve decoding at all. In DXT3 the first
eight bytes of a block are sixteen 4-bit alpha values, so a texture whose alpha
is mostly binary can only contain bytes whose nibbles are `0` or `F` — that is,
`0x00`, `0x0F`, `0xF0`, `0xFF`. In DXT5 those same bytes are two endpoints and
six bytes of 3-bit indices, which have no such restriction.

| Texture | Alpha-half bytes with only 0/F nibbles | Distinct byte values |
| --- | ---: | ---: |
| `0x52` font atlas | 93.1 % | 63 of 256 |
| `0x52` background | 91.7 % | 61 of 256 |
| `0x54` effect (control) | 22.6 % | 256 of 256 |

The control confirms itself from the other direction: the `0x54` texture's most
common alpha-half bytes are `0x24`, `0x49` and `0x92`, which are exactly the
rotating bit pattern a constant 3-bit index packs into consecutive bytes.

## 4. Tiling

`pitch` is **not** `elements_x x element_bytes`. It is that width rounded up to
32 elements, and the data height is rounded up the same way, because the GPU
addresses texture memory in 32x32-element tiles. A 960x540 DXT1 image is 240
by 135 blocks, but is stored 256 by 160.

That rounding is the visible edge of a swizzle. Element `(x, y)` does not sit
at `y * pitch + x`; it sits where the GPU's address function puts it, which
interleaves bits of x and y so that texels close together in both directions
stay close in memory:

```python
def tiled_offset(x, y, width_elements, element_bytes):
    aligned = align_up(width_elements, 32)
    log_bpp = element_bytes.bit_length() - 1
    macro = ((x >> 5) + (y >> 5) * (aligned >> 5)) << (log_bpp + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log_bpp
    offset = (macro + ((micro & ~0xF) << 1) + (micro & 0xF)
              + ((y & 8) << (3 + log_bpp)) + ((y & 1) << 4))
    return ((((offset & ~0x1FF) << 3) + ((offset & 0x1C0) << 2) + (offset & 0x3F)
             + ((y & 16) << 7) + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6))
            >> log_bpp)
```

The result is an element index, not a byte offset.

## 5. Byte order

Everything in an AIF is big-endian, and the pixel data is no exception. What
that means in practice differs by format, and getting it wrong produces a clean
image with wrong colours rather than an obvious mess:

* **A8R8G8B8** — the four bytes of a texel are already A, R, G, B in that
  order. Nothing to do.
* **A4R4G4B4** and the **DXT** formats — these are built out of 16-bit fields,
  and a PC decoder expects them little-endian, so every pair of bytes must be
  swapped before the standard block layout appears.

Swapping A8R8G8B8 as well — the natural thing to do if the swap is treated as a
property of the file rather than of the field width — still decodes to a
perfectly clean image, just with the channels permuted. The tell is the alpha
channel: in a UI atlas roughly half of it is exactly `0x00` or `0xFF` and no
colour channel is, so a histogram of each byte position identifies which one is
alpha in a couple of lines. On the atlas used here that put alpha at byte 0 and
left the other three as a coherent colour, and the resulting image showed the
Xbox button glyphs in their correct green, red, blue and yellow.

## 6. What the textures turn out to be

Worth recording, because several of them answer questions from elsewhere:

* `RMD-` resources are **font atlases** — grids of outlined glyphs covering
  Latin, kana and kanji. That explains the `MessageConvertLib_1.0.0.0` string
  found trailing three RMD- payloads inside the same SLZ stream: an `RMD-`
  entry is a message resource, and the image is only its first half.
* `MTEX` resources are material textures, including normal-map atlases packing
  four ground and wall surfaces into one 1024x1024 sheet.
* 46 `MTEX` entries hold a nested `MRON` archive instead of an image, so the
  container recurses here too.
* `IMG-` covers UI: the title screen logo at 960x540, button and control
  atlases, damage-number sheets.

## 7. Implementation

[`tools/aif.py`](../../tools/aif.py) — header reader, untiler, DXT and
uncompressed decoders, and a dependency-free PNG writer.

```
python tools/mron.py extract <image> --offset N --length N --tag MTEX --decompress out/
python tools/aif.py info out/317BD800_003_MTEX.aif
python tools/aif.py png  out/317BD800_003_MTEX.aif texture.png
```

Only the base mip level is decoded. The mip chain is present in the file and
its size is reported, but the Xbox 360 packs small levels into a shared tile,
so extracting those needs work that has not been done here.
