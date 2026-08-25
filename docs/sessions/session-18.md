# Session 18 — the method byte was never a codec selector

**Date:** 2026-08-25
**Goal:** Eternal Sonata's methods 2 and 3 — 961 of its 1 105 shipped files,
and the best remaining lead after session 17 closed tri-Ace's. Session 17 had
already established what they are *not*: tri-Ace's method 2 and method 3 were
run against them in both nibble orders and reach the stated size only by
overrunning it on a third of the input. So a different codec, and the same
technique one console over — read the executable.

## Outcome

**Both open, and the interesting part is not either codec.**

* The byte at record `+0x24` is **not a method number**. The loader never
  compares it against 1, 2 or 3; it tests **individual bits**, in two different
  places. Bit 0 turns on an LZSS layer, bit 1 turns on a range coder, and
  **method 3 is method 1 running on top of method 2**.
* The LZSS layer is **Okumura's `lzss.c`**, the routine LHA descends from —
  4 096-byte ring buffer, write position starting at `0xFEE`, `THRESHOLD` of 2.
  Not a variant of tri-Ace's. The reference implementation.
* The coder is **Subbotin's carryless range coder**, `TOP = 1<<24`,
  `BOT = 0x2000`, over a **static order-0 model shipped as the first 256 bytes
  of the file** — one frequency per symbol.

And a correction that runs the other way from session 17's:

* **Session 16's method-1 decode was wrong**, and its two tests could not have
  caught it. tri-Crescendo's LZSS reads its 12-bit field as an **absolute ring
  position**, not as a back-distance. Size and input-consumption tests are
  blind to where a match copies from; content is not.

The full specification is [vmtoc.md](../formats/vmtoc.md).

## 1. The way in, again

`index.vmtoc` sits at `0x82082E92` in the decrypted 5 767 168-byte image, and
a scan for the `lis`/`addi` pairs that build the address of the string it lives
in finds **exactly one** code reference, at `0x8210D2C8`. That is the loader:
it opens `game:\index.vmtoc`, reads it whole, and divides its length by `0x30`.

From there the method byte is followed rather than searched for:

    record +0x24  ->  file context +0x10   (0x8210CB8C)
    context +0x10 ->  decode job   +0x2C   (0x8210DD58)

and the job's `+0x2C` is read twice, in two different functions, **with two
different masks**:

    0x8210E284   clrlwi. r11, r11, 31            bit 0
    0x8210E0FC   rlwinm. r10, r10, 0, 30, 30     bit 1

That is the whole finding, visible in eight instructions. A four-value method
byte tested one bit at a time is a two-bit field, and everything else follows.

## 2. Two layers that meet at one function

`0x8210E0F8` returns the next byte of the stream. If bit 1 is clear it reads
one out of the input buffer; if bit 1 is set it decodes one out of the
arithmetic stream. `0x8210E284` decides, on bit 0, whether the consumer of
those bytes is the LZSS driver at `0x8210E308` or a plain copy loop.

| Method | Bit 1 | Bit 0 | | Files |
| ---: | --- | --- | --- | ---: |
| 0 | — | — | stored | 136 |
| 1 | — | LZSS | LZSS over raw bytes | 8 |
| 2 | coder | — | the coder alone | 13 |
| 3 | coder | LZSS | both | **948** |

948 files use both layers because, with the plumbing built that way, the
second layer is free. The other counts are not a type rule: the 13 that use the
coder alone are 3 voice banks and 10 event scripts and are **not** the largest
of either — 661 other `.e` files use method 3 and run to 53 MB against method
2's 7.9 MB — and the 8 that use LZSS alone are 7 small `.e` and one `.bmd`.
That reads like a build step trying the combinations per file and keeping the
smallest.

One group *is* a rule: **all 136 stored files are audio**, 62 `.cxs`, 60 `.csf`
and 14 `.wav`, and nothing else on the disc. Already-compressed data is left
alone.

## 3. The LZSS layer is somebody else's code

`0x8210E0C0` memsets a 4 096-byte ring buffer and sets the write position to
`0xFEE`. That number is the whole identification: `N - F` for `N = 4096`,
`F = 18`, the initialiser in Okumura's `lzss.c`. `THRESHOLD` is 2, so lengths
run 3 to 18, and the token split is Okumura's exactly —

    ring position = a | ((b >> 4) << 8)
    length        = (b & 0x0F) + 3

The one departure is that the window is primed with zeroes rather than
Okumura's spaces, which is what most descendants of the routine do.

Because the loader is streaming, the decompressor is a state machine rather
than a loop, with the flag byte, the bit mask, the state, the write position
and a pending match byte all in the job struct. That is an implementation
detail and not part of the format.

## 4. The coder

Subbotin's carryless range coder, with the renormalisation at `0x8210E18C`
matching the published loop step for step — identified by structure rather than
by comparison against compiled reference code — underflow case included:

    while ((low ^ (low + range)) < TOP)  { code = code<<8 | *in++; low <<= 8; range <<= 8; }
    while (range < BOT)                  { code = code<<8 | *in++;
                                           range = (-low & (BOT-1)) << 8; low <<= 8; }

`TOP` is `1 << 24` and `BOT` is `0x2000`. The model is static and shipped: the
first 256 bytes are one frequency per symbol, four more prime the code
register, and decoding starts at byte 260. Nothing adapts.

`BOT` and the size of the reverse lookup table are the same number, `0x2000`,
which is the encoder's normalisation target: the 256 frequencies are scaled to
sum to at most 8 192.

## 5. The correction, and why the old tests could not see it

Session 16 reported that all eight method-1 files decoded with tri-Ace's
sliding-window reader once two nibbles were swapped — 8 of 8 landing on the
stated size and consuming the input to its last byte.

The size was right and the bytes were not. Both of those tests are **blind to
where a match copies from**: a match of the right length consumes two input
bytes and produces the right number of output bytes no matter what it points
at. The only thing that distinguishes the two readings is content.

`op.bmd`, decoded both ways, agrees for exactly 22 bytes — every literal before
the first match — and then diverges. Under the ring reading, offset `0x40`
onwards is:

    00 00 02 88 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0
    00 00 02 b8 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0
    00 00 02 e4 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0

Under the window reading the same bytes interleave into nothing.

The check was then run in the **opposite** direction, because a correction that
only goes one way is half a measurement. tri-Ace's method 1 really is a sliding
window: over 40 Star Ocean 3 method-1 blocks, the window reading produces
`Bip01` **1 356 times** and the ring reading 63, and only the window reading
reconstructs the header word at `+0x0C` as a second offset just past the first.

So the two studios genuinely differ, and session 16 had the difference in the
wrong place.

## 6. What that does to session 16's conclusion

Session 16's headline was that **the oldest layer travelled with the people**
who left tri-Ace, argued from tri-Crescendo's LZSS being tri-Ace's with two
nibbles swapped.

The direction is backwards. tri-Crescendo's is the textbook routine; tri-Ace's
is the one that deviates, in two ways at once. Two teams independently reaching
for the most widely copied LZSS in existence carries almost no information
about either, and neither does two teams reaching for Subbotin's range coder.

What survives is about **convention** rather than code, and it is worth
stating at its real strength rather than at session 16's:

| | Still holds? |
| --- | --- |
| a method code of 0..3 with 0 meaning stored | yes — but the meanings differ; tri-Ace's 2 and 3 are alternative LZ77s, tri-Crescendo's are flag bits |
| four-character space-padded big-endian magics with the size behind them | yes — `CSF `, `BMD `, `BOP `, `CAMP`, `FONT`, every one agreeing with the index. `CXS ` keeps the magic style without the size field |
| `CSF `'s internal chunk tree being `ASF `'s shape with different tags | yes, and unchanged |
| the compression itself being carried from tri-Ace | **no** |

Habits of mind rather than a carried file. That is a smaller claim, and it is
the one the measurements support.

It also removes the last reason to think Eternal Sonata tells us anything about
*when* tri-Ace's layers were built. Session 15 dated `SLZ` to 1998 from tri-Ace
discs, and that dating stands on its own.

## 7. The corpus

Through `tools/vmtoc.py`, straight out of the retail image, with both tests on
every file.

| Method | | Decoded | Tried | Over the 4 MiB limit | Ratio |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0 | stored | **117** | 117 | 19 | 1.00 |
| 1 | LZSS | **8** | 8 | — | 2.36 |
| 2 | range coder | **7** | 7 | 6 | 1.05 |
| 3 | LZSS + range coder | **525** | 525 | 423 | 1.60 |
| | | **657** | **657** | 448 | |

**657 of 657, and 0 failures.** Trailing input bytes across the whole set:
`{0: 219, 1: 387, 2: 51}` — the encoder pads to four, and no
walk drifts further than that.

Files over 4 MiB on disc are skipped for time and nothing else: the decoder is
pure Python and the disc is 6.7 GiB. `--limit 0` runs the lot.

A third test is free wherever the payload states its own length at `+0x04` —
a number the compressor never touches, checked against a number that came from
the index. That is **176 of 240** files, and the shortfall is not a decode
failure but two formats that keep something else there:

| Payload | `+0x04` agrees with the index |
| --- | --- |
| `CSF ` | **123 of 123** |
| `BOP ` | **41 of 41** |
| `CAMP` | **6 of 6** |
| `BMD ` | **4 of 4** |
| `FONT` | **2 of 2** |
| `CXS ` | 0 of 57 — `+0x04` is not a length in this format |
| `NTX2` | 0 of 7 — `+0x04` is not a length in this format |

`CXS ` holds `0x800` at `+0x04`, and `NTX2` holds a size for the block that
follows it rather than for the file — its `+0x08` is Microsoft's `XPR2`.

### The checks that are not about size

Sizes and input consumption are what the table above counts, and
[§3](#the-position-is-absolute-not-a-distance) is the reason not to stop there.
Three checks reach past the literals:

**A payload's own length.** `BMD `, `BOP `, `CAMP` and the `.e` scripts state
their length at `+0x04` or `+0x0C`, a number the compressor never touches. It
agrees with the index on every file that has one, including `AppKeep.bmd` —
`0x03802000`, 58 728 448 bytes, out of 34 MB of input through both layers.

**A decoded file against a stored one of the same format.** The index lists
**60 `CSF ` files stored and 60 more behind method 3**. Both put `BOOK` at
`+0x10` with a size behind it, and the method-3 ones continue into a count and
a table of offsets ascending in steps of `0x20`:

    stored   42 4f 4f 4b 00 00 04 90  00 00 00 15 00 00 00 00  53 4f 4e 47 …
    method 3 42 4f 4f 4b 00 00 00 7c  00 00 00 03 00 00 00 01  00 00 00 0c
             00 00 00 2c 00 00 00 4c …

**A format nobody here invented.** `cfdata/maptex/adg.x3tex` decodes to `NTX2`
with Microsoft's **`XPR2`** at `+0x08` — an Xbox 360 texture package, on 21 MB
of output from 16 MB of input. A wrong decode does not produce another
vendor's magic eight bytes in.

## Left open

1. **Eternal Sonata's payload formats**, which is what question 29 was really
   about. `.bop`, `.x3tex`, `.e`, `.tex` and the `.bmd` family are now readable
   and none of them has a reader. Three leads are already visible from the
   first four bytes: `BOP ` and `BMD ` and `CAMP` all state their own length at
   `+0x04`; `.x3tex` decodes to `NTX2` with Microsoft's **`XPR2`** at `+0x08`,
   so its textures are in a documented Xbox 360 container; and `CSF `'s `BOOK`
   chunk lands at `+0x10` exactly where session 16 predicted it from the stored
   files.
2. **`CXS `**, the only format here whose `+0x04` is not a length — it holds
   `0x800` on `sound/cxs/mp118.cxs` against an index size of 452 608. 62 files.
3. **Star Ocean 5's PlayStation 3 codecs**, now the last unread compression in
   this repository. Same method numbering, same stored method 0, and none of
   tri-Ace's or tri-Crescendo's codecs decode it. It is the hardest of the
   three: the executable is inside a PS3 package.
