# `index.vmtoc` — Eternal Sonata's archive index, and the two layers under it

**Not this game's format.** Eternal Sonata is *tri-Crescendo*'s, on the same
console and in the same years as Infinite Undiscovery, and it is in this
repository for one reason: the studio was founded by people who left tri-Ace,
so measuring it says which layer of the engine, if any, travelled with them.
[aska-across-titles.md](../aska-across-titles.md) has that argument;
[session 16](../sessions/session-16.md) opened the index and method 1, and
[session 18](../sessions/session-18.md) read the rest.

**Status: solved.** All four methods decode, off the disassembly rather than by
search — see [§7](#7-status).

The headline is not the codecs. It is that **the method byte is not a codec
selector at all**: it is two independent flag bits, and method 3 is method 1
running on top of method 2. Both layers are well-known public routines.

## 1. The index

Every shipped file sits in an ordinary directory tree with no container and no
header of its own. `index.vmtoc`, 53 040 bytes, is **1 105 records of 48
bytes**, big-endian:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 32 | path, lower case, backslash-separated, NUL-padded |
| `0x20` | 4 | uncompressed size |
| `0x24` | 4 | **method**, in the top byte; the rest zero |
| `0x28` | 4 | zero |
| `0x2C` | 4 | Unix timestamp |

The loader is at `0x8210D2AC` in the decrypted `default.xex`: it opens
`game:\index.vmtoc`, reads it whole, and divides its length by `0x30`. Lookup
is a **binary search** over the records at `0x8210D080`, on the path
lower-cased into a stack buffer first. The record's `+0x20` and `+0x24` are
copied into the open file's context at `+0x18` and `+0x10`, and from there into
the decode job at `+0x24` and `+0x2C`.

## 2. The method byte is two flags

This is the part no amount of looking at the data would have given up. The
loader never compares the method against 1, 2 or 3. It tests **individual
bits**, in two different places:

    0x8210E0FC   rlwinm. r10, r10, 0, 30, 30      bit 1 — the range coder
    0x8210E284   clrlwi. r11, r11, 31             bit 0 — the LZSS layer

So the four values are a two-bit field:

| Method | Bit 1 | Bit 0 | | Files |
| ---: | --- | --- | --- | ---: |
| 0 | — | — | stored | 136 |
| 1 | — | LZSS | LZSS over raw bytes | 8 |
| 2 | coder | — | the range coder alone | 13 |
| 3 | coder | LZSS | **LZSS over the range coder** | 948 |

The two layers meet at exactly one function, `0x8210E0F8`, which returns the
next byte of the stream — read straight out of the input buffer when bit 1 is
clear, and decoded from the arithmetic stream when it is set. Everything above
it is written once and does not know which. That is why the whole decompressor
is four hundred bytes of PowerPC, and it is why the file counts look the way
they do: 948 files use both layers because, once the plumbing is that shape,
both layers are free.

**Which file gets which method is a per-file decision, not a per-type rule.**
The 13 that use the coder without LZSS are 3 voice banks and 10 event scripts,
and they are not the largest of either — 661 other `.e` files use method 3 and
run up to 53 MB against method 2's 7.9 MB. The 8 that use LZSS without the
coder are 7 small `.e` and one `.bmd`. That reads like a build step trying the
combinations and keeping the smallest output rather than a table of rules.

One group is a rule, though, and a sensible one: **all 136 stored files are
audio** — 62 `.cxs`, 60 `.csf` and 14 `.wav`, and nothing else on the disc.
Data that is already compressed is left alone.

## 3. Layer 1 — Okumura's LZSS

Not a variant of tri-Ace's codec. The reference implementation.

`0x8210E0C0` memsets a **4 096-byte ring buffer** and sets the write position
to **`0xFEE`**. That is `N - F` for `N = 4096`, `F = 18` — the initialiser in
Haruhiko Okumura's `lzss.c`, the routine LHA descends from — and `THRESHOLD`
is 2, giving the same 3-to-18 lengths. The single departure is the fill:
Okumura primes the window with spaces, this primes it with zeroes, as most of
the routine's descendants do.

    flag byte    eight tokens, least significant bit first
    1            a literal byte
    0            two bytes, a then b:
                     ring position = a | ((b >> 4) << 8)   — absolute, 12-bit
                     length        = (b & 0x0F) + 3        — 3 .. 18

Every byte written, literal or copied, is also written into the ring buffer at
the write position, which advances and wraps at 4 096.

Because the loader is streaming — it pulls one byte at a time through
`0x8210E0F8` — the decoder is a state machine rather than a loop, with the flag
byte at `+0x3340`, the current bit mask at `+0x3341`, the state at `+0x3342`,
the write position at `+0x333C` and the first byte of a pending match at
`+0x3344`. That structure is an implementation detail; the format above is all
of it.

### The position is absolute, not a distance

This is a correction, and it matters more than it looks.

[Session 16](../sessions/session-16.md) decoded these eight files with tri-Ace's
sliding-window reader and two nibbles swapped, and reported 8 of 8 successes.
The decode was wrong. Both of its tests — **the output is the right size** and
**the input is consumed to the last byte** — are blind to *where* a match copies
from, because a match of the right length consumes and produces the right
number of bytes whatever it points at.

Content is not blind to it. `op.bmd` under the ring reading resolves into
16-byte records with ascending offsets:

    00 00 02 88 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0
    00 00 02 b8 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0
    00 00 02 e4 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0

and under the window reading the same bytes interleave into nothing. The two
decodes agree for the first 22 bytes — every literal — and diverge at the first
match.

**The same test run the other way confirms tri-Ace really is a sliding
window**, so the two studios genuinely differ here. Over 40 Star Ocean 3
method-1 blocks:

| | window | ring |
| --- | ---: | ---: |
| occurrences of `Bip01`, the 3ds Max biped prefix | **1 356** | 63 |

and only the window reading reconstructs the header word at `+0x0C` as a
plausible second offset (`0x0F30`, just past the `0x0F20` at `+0x04`) rather
than as `0x30`.

## 4. Layer 2 — Subbotin's carryless range coder

Also a stock routine: Dmitry Subbotin's carryless range coder, with
`TOP = 1 << 24` and `BOT = 0x2000`. The renormalisation at `0x8210E18C` is the
published loop step for step — an identification by structure, not a comparison
against compiled reference code — including the underflow case that rebuilds
the range out of `-low`:

    while ((low ^ (low + range)) < TOP)  { code = code<<8 | *in++; low <<= 8; range <<= 8; }
    while (range < BOT)                  { code = code<<8 | *in++;
                                           range = (-low & (BOT-1)) << 8; low <<= 8; }

The model is **static, and shipped in the stream**. The first **256 bytes** of a
method-2 or method-3 file are one frequency byte per symbol; four more bytes
prime the code register; decoding starts at byte 260.

    freq[s]     the 256 header bytes
    cum[s]      running sum, u16, with cum[0] = 0
    total       cum[256]
    inv[v]      the symbol whose cumulative interval contains v

and one symbol is:

    range /= total
    value  = (code - low) / range
    symbol = inv[value]
    low   += cum[symbol] * range
    range *= freq[symbol]

Nothing is adaptive and nothing is updated. A file is one static model followed
by one arithmetic stream.

The buffer the engine reserves for `inv` is `0x2000` bytes, which is the same
number as `BOT`, and that is not a coincidence: the encoder normalises the 256
frequencies so they sum to at most 8 192, which is exactly the condition under
which the coder can always separate two symbols before renormalising.

## 5. Reading the whole thing off the executable

The route in was the same as
[SLZ's](slz.md#how-both-were-found-the-string-sits-on-top-of-its-own-jump-table),
one console over:

1. `index.vmtoc` is at `0x82082E92` in the decrypted image. `disasm.py xref`
   finds exactly **one** code reference to the string it sits in, at
   `0x8210D2C8`.
2. That function is the loader. Follow the record fields it copies — `+0x20`
   and `+0x24` — into the file context, and the method to `+0x2C` of the decode
   job.
3. `0x8210E284` tests bit 0 and branches to the LZSS driver at `0x8210E308` or
   to a plain byte loop.
4. Both call `0x8210E0F8`, which tests bit 1 and either reads a byte or decodes
   one.

And the same free check applied: method 1 was already known from the outside,
so one of the four paths had to reproduce it. One did — and reading it is what
showed that what had been "known" about it was half wrong.

## 6. What this says about the two studios

[Session 16](../sessions/session-16.md) argued from the codec that the oldest
layer of tri-Ace's technology travelled with the people who left, on the
strength of tri-Crescendo's LZSS being tri-Ace's with two nibbles swapped.

That reading is now the wrong way round. **tri-Crescendo's is the textbook
routine and tri-Ace's is the one that deviates** — a true sliding window rather
than a ring buffer, and the nibbles the other way from Okumura. Two teams
independently reaching for the most widely copied LZSS in existence is an
ordinary event and carries almost no information about either.

What survives the correction is weaker but is not nothing, and it is about
**convention** rather than code:

* a **method code of 0 to 3 with 0 meaning stored**, in both — though even here
  the meanings diverge, since tri-Ace's 2 and 3 are alternative LZ77s and
  tri-Crescendo's are flag bits;
* **four-character, space-padded, big-endian magics with the size behind
  them** — `CSF `, `BMD `, `BOP `, `CAMP` and `FONT` against `ASF `, `AIF `, `AAF `,
  `ACF `, `AAC `. `CXS ` keeps the magic style without the size field;
* and `CSF `'s internal chunk tree, which is `ASF `'s shape with different
  tags.

Habits of mind, in other words, rather than a carried file. That is a smaller
claim than session 16's and it is the one the measurements support.

## 7. Status

Decoded through [`tools/vmtoc.py`](../../tools/vmtoc.py), straight out of the
retail image, with two tests on every file: **the output is exactly the size
the index states**, and **the input is consumed to within the four bytes the
encoder pads with**.

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

## 8. Implementation

* [`tools/vmtoc.py`](../../tools/vmtoc.py) — the index, both layers, and
  `list`, `verify` and `extract` over a retail image.
* [`tools/disasm.py`](../../tools/disasm.py) — the string-to-code route that
  found all of this. Pass `--base 0x82000000` for a decrypted Xbox 360 image:

```
python tools/disasm.py strings extract/es/default.exe 'game:\index.vmtoc' --base 0x82000000
python tools/disasm.py xref    extract/es/default.exe 0x82082E8C --base 0x82000000
python tools/disasm.py dis     extract/es/default.exe 0x8210E0F8 --base 0x82000000
```

```
python tools/vmtoc.py list    "iso/Eternal Sonata ....iso"
python tools/vmtoc.py verify  "iso/Eternal Sonata ....iso" --limit 0x800000
python tools/vmtoc.py extract "iso/Eternal Sonata ....iso" extract/es --only btldata/
```
