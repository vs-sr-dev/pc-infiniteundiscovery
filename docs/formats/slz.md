# SLZ — the compressed resource wrapper

Most of Infinite Undiscovery's bulk is compressed. Every `MESH`, `MTEX`,
`SCE-`, `SKAC` and `APAC` resource sits behind a header whose first three bytes
are `SLZ` — 1 812 blocks in disc 1's `ud1.bin` alone, holding 1.88 GB of
uncompressed data. Nothing much can be read out of the game without going
through it.

The name is tri-Ace's. The compression is not.

**Status: solved.** All 1 812 blocks in disc 1's `ud1.bin` decompress without
error, and every payload that states a usable length agrees with the decode.
See [§6](#6-status) for the exact numbers.

## 1. It is XCompress underneath

The constant `0x0FF512EE` at offset `0x18` is Microsoft **XCompress**'s stream
magic, and it is byte-identical in all 1 812 blocks along with the version field
that follows it — so it is a signature, not a checksum. XCompress is the Xbox
360 XDK's `XMemCompress`, which is LZX with a configurable window.

So SLZ is a 24-byte tri-Ace wrapper in front of a stock SDK stream. Given that
the same executable links `XGRAPHC` and `D3DX9` from the same SDK, that is
exactly the pragmatic choice one would expect.

## 2. Layout

All big-endian.

**tri-Ace wrapper**, 24 bytes:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 3 | `SLZ` |
| `0x03` | 1 | Version — 4 everywhere |
| `0x04` | 4 | Header size (`0x20`) |
| `0x08` | 4 | Compressed size, counted from `0x18` |
| `0x0C` | 4 | Uncompressed size |
| `0x10` | 4 | Zero |
| `0x14` | 4 | One |

**XCompress stream header**, 48 bytes, starting at `0x18`:

| Offset | Size | Field |
| --- | --- | --- |
| `0x18` | 4 | Magic `0x0FF512EE` |
| `0x1C` | 4 | Version `0x01020000` |
| `0x20` | 4 | Context flags |
| `0x24` | 4 | Flags |
| `0x28` | 4 | Window size — `0x20000`, 128 KB |
| `0x2C` | 4 | Compression partition size — `0x80000` |
| `0x30` | 8 | Uncompressed size |
| `0x38` | 8 | Compressed size |
| `0x40` | 4 | Uncompressed chunk size — `0x20000` |
| `0x44` | 4 | Largest compressed chunk in this stream |

**Chunk table**, from `0x48`:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | Compressed size of this chunk, counted from `+0x04` |
| `+0x04` | .. | Chunk payload, that many bytes |

The next chunk header follows at `+0x04 + size`.

Two independent checks say the chunk table is right: walking it lands
**exactly** on the end of the compressed region in every block tested, and the
largest size encountered always equals the field at `0x44`.

Entries holding an SLZ block are padded, with
`entry size == align_up(compressed size, 4) + 24` — the 24 being the wrapper
that sits before the counted region.

## 3. Frames

A chunk is not one LZX bitstream, and this is the part that decides whether a
decoder works.

A chunk decodes to `0x20000` bytes. LZX produces output in **frames** of
`0x8000`, so an ordinary chunk holds four of them, laid end to end, each
introduced by a short header giving its compressed length:

```
hh ll               ordinary: 16-bit compressed length; output is 0x8000
ff  hh ll  hh ll    extended: 16-bit output length, then 16-bit compressed length
```

The extended form is what a short frame needs, so it appears as the last frame
of the last chunk — and, because the marker is `0xFF`, also whenever an
ordinary frame's compressed length would reach `0xFF00`.

This is the same framing XNB files use for LZX. It belongs to XCompress, not to
LZX: the codec has frames, but says nothing about how a container marks them.

Walking it is exact, not probabilistic. In every chunk of every block tested,
each frame header lands precisely where the previous frame's length says it
should, the walk finishes on the final byte of the chunk payload, and the frame
output lengths sum to the chunk's uncompressed size. `slz.py` treats any
departure from that as an error rather than a hint.

### What crosses a frame boundary

Only the bit reader restarts at a frame boundary. Everything else survives:
the Huffman tables, the repeated offsets R0/R1/R2, and — the one that matters —
**the current block and how much of it is left**.

Blocks are routinely longer than a frame. Instrumenting the decoder over 500
SLZ blocks — 3 636 chunks, 13 994 frames, 5 405 LZX blocks — **81 % of blocks
span more than one frame**, and a chunk averages 1.5 blocks across its roughly
four. A decoder that expects a block header at the start of each frame is
therefore reading Huffman code lengths out of the middle of coded data four
times out of five. It will resynchronise often enough to look like it nearly
works, which is the worst way for this to fail.

Of those 5 405 blocks, 5 089 are aligned-offset, 308 verbatim and 8
uncompressed, so all three block types occur and all three are exercised.

### What a chunk restarts

A chunk *is* an independent LZX stream: fresh Huffman tables, fresh repeated
offsets, and the E8 header bit read again. `LzxDecoder.reset()` marks it.

That independence is real and not merely assumed. Across those same 3 636
chunks, **no match ever referenced output from before the start of its own
chunk** — not once. Chunks can therefore be decompressed independently and in
any order, which is presumably the point of chunking the stream at all.

## 4. Window size

`window_bits = 17`, and this is not taken on trust from the header. Every other
size was tried: 15, 16, 18, 19, 20 and 21 all fail, because the window size
determines the number of position slots and therefore the size of the main
Huffman tree, so a wrong guess misparses immediately.

## 5. Two things session 3 believed that turned out not to be true

Both were artefacts of the missing frame model, and both are worth recording,
because each is a plausible reading that survives testing for a while.

**"The window is shared across chunks."** It is not — see above, no match ever
reaches back that far. The symptom that suggested it (decode chunks
independently and the third turns to noise) came from the block state being
lost, not the window.

The reason the mistake was invisible: the chunk size and the window size are
both `0x20000`. A ring buffer that wraps every `0x20000` bytes and a buffer
reset every `0x20000` bytes hold identical contents, so the two models cannot
be told apart by their output at all — only by instrumenting how far back the
matches actually reach.

**"Matches may point into the unwritten window."** Legal in LZX, and worth
supporting, but it never happens here: since no match reaches past the start of
its chunk, the zero-filled region is never read. `lzx.py` still implements it,
as the specification requires, but it is dead code on this game's data and is
no longer offered as an observation about it.

The third of session 3's findings does hold: **a block produces exactly its
declared length**, and a match that would overrun it is clipped. What changed is
the boundary that does the clipping — the block's end, not the frame's. Frames
are an output-side division the encoder cannot see, and matches cross them
freely.

## 6. Status

Over disc 1's `ud1.bin`, all 1 812 SLZ blocks:

| | Blocks |
| --- | ---: |
| Decompressed without error | **1 812** |
| Confirmed by the payload's own length | 1 066 |
| Payload declares less, and the extra bytes are real data | 6 |
| Payload has a length field but leaves it zero | 62 |
| Payload has no length field | 678 |
| Failures | **0** |

1 134 payloads carry a length field. 62 of those leave it zero, saying nothing.
Of the 1 072 that state a length, 1 066 match the decode exactly and 6 come out
short — and no payload anywhere claims to be *longer* than what was decoded,
which is the only outcome that would mean output had gone missing.

The confirmation is worth something: `ASF `, `AIF ` and `AAF ` payloads store
their own total length at offset 4, a value the compressor never touches, so
each match is a check against a number that came from somewhere else entirely.

The six "plus trailing data" cases are not failures. The stream carries more
than the one payload, and the extra bytes are coherent: three of them continue
with the ASCII string `MessageConvertLib_1.0.0.0`, a build-tool version left in
the shipped data, and the rest with arrays of plausible floats. Decoded
payloads by magic: `ASF ` 916, `AAC ` 349, `MRON` 324, `AIF ` 156, `AAF ` 62,
`-CNS` 4.

## 7. Implementation

* [`tools/lzx.py`](../../tools/lzx.py) — the LZX decoder, written from the
  published algorithm. No dependencies. Stateful, and fed one frame at a time.
* [`tools/slz.py`](../../tools/slz.py) — the SLZ/XCompress container:
  `info`, `decompress`, and `verify` for bulk self-checking.

```
python tools/slz.py info       <file> --offset N
python tools/slz.py decompress <file> --offset N out.bin
python tools/slz.py verify     <image> --csv entries.csv --base N
```
