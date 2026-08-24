# Session 3 — payload formats, title metadata, and SLZ

**Date:** 2026-08-24
**Goal:** open question 5 from [session 2](session-02.md) — work out how the
engine's AOF/ASF/ACF vocabulary maps onto the container's resource tags.

## Outcome

The mapping fell out immediately, which then exposed the real obstacle: almost
everything worth reading is behind SLZ compression, and SLZ took the rest of
the session.

### Payload formats

Nearly every payload announces itself. Taking one entry per tag from disc 1's
`ud1.bin` gave the whole table at once, written up in
[formats/resource-payloads.md](../formats/resource-payloads.md).

The `A?F` family is real: `AAF ` animation, `ACF ` collision, `AIF ` image,
`ASF ` scene. Two of those — ACF and ASF — were already named in the
executable's RTTI, so the engine's vocabulary and the on-disc magics line up.
`SOND` payloads are `AAC `, matching the `AAC version problem  BGM ID=%d`
string found last session.

Some distinctions turn out to be about role rather than format: `IMG-`, `MAIF`
and `RMD-` all resolve to `AIF `. And a `MESH` resource decompresses to `ASF `,
so in ASKA's vocabulary a mesh *is* a scene file.

Six tags contain further NORM archives, so the container recurses.

`AOF` remains named in the engine but unseen on disc.

### Title metadata

The XEX resource section (open question 6) is an **XDBF** database — the blob
the dashboard reads. Format written up in
[formats/xdbf.md](../formats/xdbf.md).

It holds all 50 achievements with both descriptions, the gamerscore values, the
PNG icons, and string tables in exactly two languages: English and Japanese,
317 strings each, on a PAL disc.

The gamerscore field being 16-bit rather than 32-bit was settled by arithmetic
rather than assumption — read as `u16` the fifty values sum to exactly 1000,
the title's advertised total. The decoded names and values also match a
screenshot of the owner's own Xbox profile, which is a pleasant end-to-end
check: `Surprise!` 5G, `Blitzkrieg` 10G, `Infinitely Unobservant` 10G.

### SLZ

This is where the session went.

`SLZ` is a 24-byte tri-Ace wrapper around a stock Microsoft **XCompress**
stream — LZX with a 128 KB window. The tell is the constant `0x0FF512EE` at
offset `0x18`, XCompress's own stream magic, byte-identical across all 1 812
blocks on disc 1. Given the executable already links `XGRAPHC` and `D3DX9` from
the same SDK, reaching for `XMemCompress` is exactly the pragmatic choice one
would expect.

Fully mapped: the wrapper, the 48-byte stream header, and the chunk table.
Two independent checks confirm the chunk table — walking it lands *exactly* on
the end of the compressed region in every block tested, and the largest chunk
size always equals the field at `0x44`.

`window_bits = 17` is proven rather than assumed: every other window size
misparses immediately, because the window determines the position-slot count
and therefore the size of the main Huffman tree.

An LZX decoder was written from the published algorithm. Three things had to be
got right, each of which fails far from its cause:

* **The window is shared across chunks.** Each chunk restarts the bitstream but
  the window carries over. Decoding chunks independently gives two perfect
  chunks and then quiet noise.
* **Matches may point into the unwritten window.** The window is a zeroed ring,
  and encoders use a far-back match into it as a cheap way to emit runs of
  zeros. Rejecting "offset larger than output so far" as an error — the obvious
  reading — breaks on valid streams.
* **Blocks produce exactly their declared length.** A match that overruns must
  be clipped; letting it through shifts everything after it.

Write-up: [formats/slz.md](../formats/slz.md).

### Where SLZ stands

**About 12% of blocks decode end to end** — 25 of 200 sampled. That number is
measured, not estimated: `ASF `, `AIF ` and `AAF ` payloads store their own
length at offset 4, a value the compressor never touches, so every completed
decode is checked against it. `slz.py verify` reports the rate rather than
hiding it.

Two things are still unknown, and both are currently worked around by searching
for the next valid block header rather than by knowing the rule:

* what the chunk prefix holds, and what decides its length (2 bytes usually,
  1 and 5 also observed);
* what sits between two blocks *inside* one chunk. Measured cases come out to
  "pad to a byte boundary, then 32 bits", which fixes some blocks and not
  others.

## Tools written

* `tools/lzx.py` — LZX decompressor, no dependencies.
* `tools/slz.py` — the SLZ/XCompress container, with bulk self-verification.
* `tools/xdbf.py` — XDBF reader: entry table, achievements in any shipped
  language, string tables, embedded PNGs.

## Left open

1. **The two SLZ unknowns.** This is now the highest-value problem in the
   repository — 1.88 GB of uncompressed content in `ud1.bin` alone sits behind
   it, and nearly every other question depends on getting through it.
2. The first `0x16000` bytes of disc 1's `ud1.bin`. Unchanged since session 1.
3. Splitting the ASF video runs into individual movies.
4. Internal structure of `AAF `, `ACF `, `AIF `, `ASF ` — reachable for the
   uncompressed tags right now, without waiting on SLZ.
5. `AOF`, named in the engine but not seen on disc.
6. `NODE` payloads, which carry no magic.
