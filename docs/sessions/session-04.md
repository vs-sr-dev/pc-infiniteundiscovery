# Session 4 — SLZ solved, and the textures come out

**Date:** 2026-08-24
**Goal:** open question 1 from [session 3](session-03.md) — the two unknowns
blocking SLZ decompression, which stood between the repository and 1.88 GB of
content.

## Outcome

Both unknowns turned out to be the same thing, and it was not a tri-Ace
invention at all. With SLZ closed, the session went on to the format sitting
directly behind it, and textures now decode end to end.

## SLZ: there was no chunk prefix and no inter-block gap

Session 3 recorded two mysteries — a short prefix of varying length at the
start of each chunk payload, and something occupying the space between two LZX
blocks inside a chunk. Neither exists.

What exists is **framing**. LZX emits output in frames of `0x8000` bytes, and
XCompress stores each frame's compressed run separately, introduced by its
length:

```
hh ll               ordinary: 16-bit compressed length; output is 0x8000
ff  hh ll  hh ll    extended: 16-bit output length, then 16-bit compressed length
```

So a `0x20000` chunk holds four frames. Session 3's "chunk prefix" was the
first frame's length header, and the "gap between blocks" was the next frame's.
The `0xFF` marker explains the five-byte case seen on a short final chunk, and
the "one-byte prefix" was a misread of the same two bytes.

The check is exact rather than statistical: every frame header lands where the
previous frame's length says it will, the walk ends on the payload's last byte,
and the frame output lengths sum to the chunk's uncompressed size. That held
for every chunk of every block, first try, before a single byte was decoded.

### The part that made it hard to see

Framing alone is not enough. **Only the bit reader restarts at a frame
boundary** — the Huffman tables, the repeated offsets, and above all the
current block and its remaining length all carry across. Measured over 500
blocks: 81 % of LZX blocks span more than one frame. A decoder that expects a
block header per frame is reading Huffman code lengths out of the middle of
coded data four times in five, and session 3's decoder was doing exactly that,
which is why its resynchronising workaround recovered about an eighth of the
data instead of none.

Moving the state out of the decode loop and onto the decoder was the whole fix.

### Result

All **1 812 of 1 812** SLZ blocks in disc 1's `ud1.bin` now decompress with no
errors, against 25 of 200 sampled last session.

| | Blocks |
| --- | ---: |
| Decompressed without error | **1 812** |
| Confirmed by the payload's own length | 1 066 |
| Payload declares less, extra bytes are real data | 6 |
| Length field present but left zero | 62 |
| No length field to check | 678 |
| Failures | **0** |

The six short-declaring cases were checked rather than waved past: the trailing
bytes are coherent data, and three of them begin with the ASCII string
`MessageConvertLib_1.0.0.0` — a build-tool version left in the shipped game.

Write-up: [formats/slz.md](../formats/slz.md).

## Two of last session's findings were wrong

Worth recording plainly, since both were reasonable readings that survived
testing for a while.

**"The window is shared across chunks."** It is not. Instrumented over 3 636
chunks, no match ever reaches back past the start of its own chunk — chunks are
independent, which is presumably why XCompress chunks at all. The mistake was
undetectable by output alone, because the chunk size and the window size are
both `0x20000`: a ring that wraps every `0x20000` bytes and a buffer reset every
`0x20000` bytes hold identical contents. Only instrumenting how far back matches
actually reach can tell them apart.

**"Matches may point into the unwritten window."** Legal in LZX, but it never
happens here, and follows from the above. `lzx.py` still implements it because
the specification calls for it; it is no longer claimed as an observation about
this game.

The third finding — a block produces exactly its declared length, and an
overrunning match is clipped — does hold. What changed is which boundary clips:
the block's end, not the frame's.

## AIF: every texture in the game

With compression out of the way, the natural next target was the format behind
it. `AIF ` is a 4096-byte header in front of a texture already in the Xbox 360
GPU's own memory layout, so reading one means undoing the tiled address swizzle
and a byte order chosen for the fetch unit.

All **220** image resources in disc 1's `ud1.bin` decode — 150.9 megapixels,
no failures — across five pixel formats.

Two points were settled by measurement rather than by assumption:

* **`0x52` is DXT2/3 and `0x54` is DXT4/5.** The numbering resembles D3D's, but
  that is not why. For `0x54`, decoding both ways gives an alpha channel 75x
  smoother as DXT5, on 100 % of 3 695 partial-alpha blocks. For `0x52` the
  smoothness test is useless — those textures are almost entirely binary alpha,
  where both decoders agree — so the deciding test avoids decoding altogether:
  93 % of its alpha-half bytes contain only `0` and `F` nibbles, which is only
  possible if those bytes are sixteen 4-bit alpha values. The `0x54` control
  sits at 23 % and uses all 256 byte values, its most common being `0x24`,
  `0x49` and `0x92` — the rotating pattern of a constant 3-bit index.
* **A8R8G8B8 is not byte-swapped, while the DXT and 16-bit formats are.** Swap
  it anyway and the image still comes out clean, merely with permuted channels
  — a mistake that survives a casual look. A histogram of each byte position
  identifies alpha immediately (half of it is exactly `0x00` or `0xFF`, and no
  colour channel is), and the corrected decode shows the Xbox button glyphs in
  their correct green, red, blue and yellow.

Write-up: [formats/aif.md](../formats/aif.md).

### What the textures are

Decoding them answered two open tag questions:

* **`RMD-` is a message resource.** Its image is a font atlas of outlined
  Latin, kana and kanji glyphs — which is what the trailing
  `MessageConvertLib_1.0.0.0` string in three RMD- streams was about. The
  image is only the first half of the resource.
* **`MTEX` is material texture**, including normal-map atlases packing four
  ground or wall surfaces into one 1024x1024 sheet. 46 `MTEX` entries hold a
  nested `MRON` archive instead of an image, so that tag covers both.

`IMG-` is interface art: the title screen logo at 960x540, button and control
atlases, damage-number sheets. Every AIF also carries a four-character asset
identifier whose prefix groups it — `CH` character (106), `BG` background (74),
`EF` effect (21), `PG` interface (14).

## Tools

* `tools/lzx.py` — rewritten around frames. The decoder is now stateful, and
  the resynchronising workaround is gone.
* `tools/slz.py` — exact frame walking; `verify` classifies its outcomes
  instead of lumping every mismatch together as a failure.
* `tools/aif.py` — new. Header, untiler, DXT1/3/5 and uncompressed decoders,
  PNG writer, no dependencies.
* `tools/mron.py` — new `extract` subcommand, which writes entry payloads out
  as files and optionally decompresses them, closing the last manual step
  between a disc image and a tool's input.

## Left open

1. **Internal structure of `ASF `** — 916 of the compressed blocks, and the
   biggest remaining unknown. `MESH` resources decompress to it.
2. `AAF ` animation and `ACF ` collision, likewise now plain readable files.
3. AIF mip chains. The base level decodes; the Xbox 360 packs small mip levels
   into a shared tile, which has not been worked out.
4. `NODE` payloads, which carry no magic, and `TTD-`.
5. The first `0x16000` bytes of disc 1's `ud1.bin`. Unchanged since session 1.
6. Splitting the ASF video runs into individual movies.
7. `AOF`, named in the engine but not seen on disc.
8. The unidentified `u32` at AIF offset `0x24`, and the flags at `0x34`.
