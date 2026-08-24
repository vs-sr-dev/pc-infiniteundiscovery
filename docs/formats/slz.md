# SLZ — the compressed resource wrapper

Most of Infinite Undiscovery's bulk is compressed. Every `MESH`, `MTEX`,
`SCE-`, `SKAC` and `APAC` resource sits behind a header whose first three bytes
are `SLZ` — 1 812 blocks in disc 1's `ud1.bin` alone, holding 1.88 GB of
uncompressed data. Nothing much can be read out of the game without going
through it.

The name is tri-Ace's. The compression is not.

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

## 3. Window size

`window_bits = 17`, and this is not taken on trust from the header. Every other
size was tried: 15, 16, 18, 19, 20 and 21 all fail, because the window size
determines the number of position slots and therefore the size of the main
Huffman tree, so a wrong guess misparses immediately. Only 17 produces output
whose magic and self-reported length are correct.

## 4. The two things that make this hard

### The window is shared across chunks

Each chunk restarts the bitstream — fresh E8 flag, fresh Huffman tables — but
the LZX window carries over. A match late in the stream reaches back into an
earlier chunk. Decode chunks independently and the first two look perfect while
the third quietly turns to noise, which is a bad failure mode to debug.

### Matches into the unwritten window

An LZX match may point into the part of the window that has not been written
yet. This is not corruption: the window is a ring of `window_size` bytes that
starts zeroed, and encoders use a far-back match into that zeroed region as a
cheap way to emit a run of zeros — which game data, full of padding, is made
of. The obvious check ("offset larger than the output so far must be an error")
is wrong and rejects valid streams.

### Blocks produce exactly their declared length

A match that would overrun the declared block length is clipped. Letting it
through shifts every later byte by a few positions and silently corrupts the
remainder — again, a failure that shows up far from its cause.

## 5. What is still unknown

Two gaps, both currently worked around by searching rather than by knowing the
rule:

**The chunk prefix.** Every chunk payload opens with a short prefix before the
bitstream. Two bytes is the ordinary case; one and five have both been seen,
the five on a short final chunk. Observed prefix values for one file's chunks
were `07 10`, `0a 64`, `0d b0`, `0f ca`, `ff 10` — increasing, then not, which
suggests a running checksum rather than a length. Not established.

**The inter-block gap.** Blocks within one chunk are not bit-contiguous. In the
cases measured the gap comes out to "pad to a byte boundary, then 32 bits" —
which fixes some blocks and not others, so the rule is close but wrong.

`tools/lzx.py` therefore resynchronises: at a gap it scans forward for the next
plausible block header, preferring one whose declared length is exactly the
chunk's remaining output. That is a workaround, and the failures below are its
cost.

## 6. Status

**About 12% of blocks decode end to end** — 25 of 200 sampled. Where a block
does complete, the result is trustworthy: `ASF `, `AIF ` and `AAF ` payloads
all store their own length at offset 4, so every completed decode is checked
against a number the compressor never wrote. `slz.py verify` reports the rate
rather than hiding it.

Closing the remaining 88% means identifying the two unknowns above. That is the
single highest-value open problem in this repository — nearly everything else
about the game's content is behind it.

## 7. Implementation

* [`tools/lzx.py`](../../tools/lzx.py) — the LZX decoder, written from the
  published algorithm. No dependencies.
* [`tools/slz.py`](../../tools/slz.py) — the SLZ/XCompress container:
  `info`, `decompress`, and `verify` for bulk self-checking.
