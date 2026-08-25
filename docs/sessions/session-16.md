# Session 16 — the offshoot studio, and one swapped nibble

**Date:** 2026-08-25
**Goal:** a different question from the twelve before it. *Eternal Sonata*
(Xbox 360, 2007) is not a tri-Ace game: it is **tri-Crescendo**, the studio
founded by people who left tri-Ace, and best known there as the sound team. The
title was chosen deliberately — same console, same generation, same shape of
project as Infinite Undiscovery and Star Ocean 4, developed entirely in-house
with no co-developer. So the question is not "is this ASKA" but **which layer,
if any, did the people carry with them.**

Three layers with known birthdays after session 15: the **compression**, from
1998; the **payload formats**, between 1999 and 2003; the **container and the
engine name**, later still. A hit dated to one of them says when.

> **Corrected by [session 18](session-18.md).** Two things below did not
> survive being checked against the executable. The method-1 decode is wrong
> in its match target — tri-Crescendo's 12-bit field is an absolute ring
> position, not a back-distance — and the tests in §4 could not have caught
> that, because output size and input consumption are blind to where a match
> copies from and both content checks sit in the literal prefix. And the
> codec turns out to be **Okumura's `lzss.c`** over **Subbotin's range
> coder**, both stock, so the headline below — that the oldest layer
> travelled with the people — does not follow. What travelled is the
> convention. The rest of this log stands, including the index, the method
> byte, the magic style and the timestamp check.

## Outcome

**The compression, and the conventions around it. Not the engine.**

* No `Aska`, no `AHSL`, no RTTI, no `SLZ`, and not one payload magic of
  tri-Ace's anywhere in the executable.
* But every shipped file is compressed with **a byte-for-byte relative of
  tri-Ace's method 1** — same framing, same bias, **one swapped nibble** — and
  the table that indexes them carries a **method byte with tri-Ace's exact
  semantics**: values 0–3, where 0 means stored.
* And the file magics are the same house style: `CXS `, `CSF `, `BMD ` — four
  ASCII characters padded with a space, big-endian, with the size behind them,
  exactly as `ASF `, `AIF `, `AAF `, `ACF ` and `AAC ` are.

So: the *oldest* layer travelled, along with the habits of mind around it. The
engine did not.

## 1. The disc, which is nothing like the other two Xbox 360 ones

| | |
| --- | --- |
| image | XGD2, 7.297 GiB, partition base `0x0FD90000` |
| volume timestamp | 2007-09-05 |
| contents | 15 directories, **1 108 files**, 6.695 GiB |
| executable | `default.xex`, 4 399 104 bytes, original PE name `P1_EU.pe` |

Infinite Undiscovery's whole filesystem is four files and one directory, two
of those files being the monolithic containers; Star Ocean 4 ships the same
idea with `PACK` inside it. Eternal Sonata ships **an ordinary
filesystem with an ordinary directory tree** — `btldata/enemy/ep001.bop`,
`cfdata/maptex/ADG.x3tex`, `sound/cxs/MP101.cxs` — and no container at all.
That is the first thing that is different and it is visible before anything is
decoded.

The extensions: 678 `.e`, 123 `.csf`, 122 `.bop`, 90 `.x3tex`, 62 `.cxs`, 14
`.wav`, 12 `.bmd`, 2 `.tex`, 2 `.fnt`, and `index.vmtoc`.

## 2. The executable says nothing, and says it cleanly

`xex.py` reads it with no changes. The compression is **basic**, as Infinite
Undiscovery's is — Star Ocean 4 and Resonance of Fate both needed the LZX path
that session 13 wrote — and the retail key decrypts it to a 5 767 168-byte
image that matches its stated size exactly.

Then nothing:

| Searched for | Hits |
| --- | ---: |
| `Aska`, `ASKA`, `aska`, `AHSL` | 0 |
| `SLZ` | 0 |
| `R:M:`, `pCol`, `Tri_ace` | 0 |
| `ASF `, `AIF `, `AAF `, `ACF `, `AAC `, `MRON`, `PACK` | 0 |
| `.?AV` (MSVC RTTI) | 0 |
| `tri-Crescendo` | **5** |

The one `SLE` hit is `SLEP`, inside a table of four-character task names —
`TextMgr Task`, `SLEP`, `ACTV`. Checked, and false.

What the strings *do* show is a different kind of studio: **libpng, zlib and
libjpeg are linked in**, with their version-mismatch messages intact, beside
`D3DX`. tri-Ace wrote its own texture format; tri-Crescendo used the ones
everybody uses.

## 3. `index.vmtoc`, the only readable file on the disc

Every other file is compressed from its first byte, with no header of any
kind. Measured over the first 64 KB of a 219-file sample, the 948 method-3
files — 86 % of the disc — sit at a median entropy of **7.997**, so a signature
sweep is blind on almost all of it. The one file that is not compressed is
`index.vmtoc`, 53 040 bytes, and it is **1 105 records of 48 bytes**:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 32 | path, lower case, backslash-separated, NUL-padded |
| `0x20` | 4 | **uncompressed size**, big-endian |
| `0x24` | 4 | **method** in the top byte; the rest zero |
| `0x28` | 4 | zero |
| `0x2C` | 4 | Unix timestamp |

Four measurements say that reading is right:

| | |
| --- | --- |
| records whose path exists in the filesystem | **1 105 of 1 105** |
| field at `0x20` ≥ the size on disc | **1 105 of 1 105** |
| method 0 with the two sizes **equal** | **136 of 136** |
| timestamps | 2006-07-24 to 2007-08-27, one per file |

The 1 105 records against 1 108 files is exact: the three that are not listed
are `index.vmtoc` itself, `default.xex` and the system update blob.

### The method byte is tri-Ace's idea, in a different place

| Method | Files | |
| --- | ---: | --- |
| 0 | 136 | stored — and stated size equals on-disc size on all 136 |
| 1 | 8 | LZ77 — **opens**, see below |
| 2 | 13 | not decoded |
| 3 | 948 | not decoded, and it is the default |

That is `SLZ`'s method byte exactly: a small code, **0 through 3, where 0 means
stored**, selecting one of three compressors. tri-Ace puts it at `+0x03` of
every block; tri-Crescendo puts it in a per-file table and keeps the meaning.

## 4. Method 1 is tri-Ace's codec with two nibbles swapped

The stored files give the game away before any decoding. A compressed stream
begins with a flag byte, and `0xFF` means eight literals — so a file whose
first flag is `0xFF` shows its own magic in the clear, one byte in. **All eight
method-1 files begin with `0xFF`**, and behind it sits `BMD ` on one of them
and a consistent 16-byte header on the other seven.

Running tri-Ace's method 1 against them produces the right *header* and the
wrong *length*, which is the signature of a shared framing and a different
match encoding. So the same search session 14 used was run again, over twelve ways
of splitting the two bytes into a distance and a length, four length biases,
both bit orders, both polarities, and a sliding window against a ring buffer at
three start positions — 768 candidates, with the oracle that the output must
land on exactly the size the table of contents states **and** consume the input
to its last byte, on every file at once.

One candidate does it, and it is one bit-field away from tri-Ace's:

| | tri-Ace, 1998–2006 | tri-Crescendo, 2007 |
| --- | --- | --- |
| flag byte | 8 tokens, bit 0 first, literal on 1 | **identical** |
| back-reference | two bytes, `a` then `b` | **identical** |
| distance | `a \| ((b & 0x0F) << 8)` | `a \| ((b >> 4) << 8)` |
| length | `(b >> 4) + 3` | `(b & 0x0F) + 3` |
| window / range | 4 095 / 3–18 | **identical** |

**The two nibbles of the second byte are swapped. Nothing else differs** — not
the flag direction, not the polarity, not the bias of three, not the window.

| | |
| --- | --- |
| files decoding to exactly the stated size | **8 of 8** |
| input consumed to the last byte | **8 of 8** |
| decompressed files that restate their own size at `+0x0C` | 7 of 8 |

The eighth is `op.bmd`, which has a magic instead: it comes out as `BMD `
with `0x1DCF` = 7 631 at `+0x04`, exactly its own length, and it holds the
game's staff credits.

### The check that settles it

Output length is a weak test on its own — a wrong length field can still land
on the right total. This one is not. Five of the seven `.e` files put a **Unix
timestamp at `+0x04` of their decompressed data**, and it is the same timestamp
`index.vmtoc` records for that file, **to the second**:

```
btldata/script/ai/default.e     index 2007-02-15T09:19:15   inside 2007-02-15T09:19:15
btldata/script/ai/bos03_v1.e    index 2007-02-15T09:19:17   inside 2007-02-15T09:19:17
btldata/script/ai/bos07_v1.e    index 2007-02-15T09:19:19   inside 2007-02-15T09:19:19
btldata/script/ai/bos03_v2.e    index 2007-02-15T09:19:22   inside 2007-02-15T09:19:22
btldata/script/ai/bos07_v2.e    index 2007-02-15T09:19:24   inside 2007-02-15T09:19:24
```

The other two agree except for a constant offset of **exactly 80 seconds** in
both, which reads as a later build step stamping the index rather than a decode
error. A wrong decompression does not produce a 32-bit value that matches an
independent table to the second, five times.

That is not a coincidence and it is not independent invention. Two studios do
not arrive separately at the same flag direction, the same polarity, the same
two-byte reference, the same 12/4 split and the same bias of three, and then
differ only in which nibble is which.

## 5. Methods 2 and 3 are not that family at all

The same negative as tri-Ace's methods 2 and 3, and here it can be proved
rather than merely reported.

`btldata/voice/bos01.csf` is a method-3 file, and its stored siblings in
`sound/mapse/` are all `CSF `. So its first decompressed byte is `C`. Its first
byte on disc is `0x28` — bit 0 clear — so under the framing that method 1 uses
the first token is a back-reference, which cannot exist at output position
zero. **Method 3 does not use that framing.** Only 33 of 948 method-3 files
begin with `0xFF` at all, and none of the four bytes behind those is a magic.

A wider search was run anyway — 14 byte splits, four length biases, both bit
orders, both polarities and four header skips, 896 candidates — against five
method-3 `.e` files and one method-2 one, with 16 bytes of known plaintext each — word 0 is `0x181` and
word 3 is the size the table of contents states. **Nothing reproduces it.**

Method 2 gets the same treatment and the same answer: all 13 of its files begin
with `0xFF`, and the four bytes behind are small values rather than a magic —
including on `bosWLZ.csf`, whose decompressed form must begin `CSF `.

## 6. The magic convention travelled too

The 136 stored files show their headers on disc with nothing in the way, and
the convention behind them is the one this repository has been describing since
session 2 — a four-character tag, then a **total size counted from byte zero**:

| Tag | Files | States its own file length at `+0x04` |
| --- | ---: | --- |
| `CSF ` — sound-effect banks | 60 | **60 of 60** |
| `CXS ` — streamed audio | 62 | 0 — `+0x04` is the header size, then 48 000 Hz and a channel count |
| `RIFF` | 14 | **14 of 14** |

plus `BMD ` out of the one method-1 file that carries a magic, whose `0x1DCF`
at `+0x04` is exactly its own 7 631 bytes.

**`CSF ` is a chunk list.** All 60 carry `BOOK` at `+0x10` and `SONG` at
`+0x20`, each a four-character tag followed by its own size — the shape of
`ASF `'s chunk tree, with different tags.

And the `RIFF` row is not what it looks like. Those fourteen files write the
RIFF size **big-endian**, and set it to the whole file length rather than
`length − 8` as the format specifies; their `fmt ` fields are big-endian too.
So even the one standard format on the disc was written to the house
convention rather than the standard's.

Four ASCII characters, padded to four with a space, big-endian, with a size
field right behind them, and chunks behind that. That is the `A?F` house style
with different letters, and `aska.py`'s own length validator would accept it.

## 7. The sweep, and the tool bug it exposed

`aska.py identify` over the whole 7.30 GiB finds **nothing sound**. Every
signature with a structural test scores zero; the three without one score 1, 1
and 3, against the ~1.8 that chance produces on that much data. Which is
exactly what the entropy census predicts — 86 % of the disc is method 3 at
entropy 7.997, and a signature sweep cannot see through it.

The tool did not say that, though. It printed **"probably ASKA, on payload
magics alone"**, because the verdict rule counted any signature with no
structural test at its raw hit count, and one `ACF ` hit on 7.3 GiB was enough.
That is the mirror image of the Resonance of Fate mistake session 13 recorded:
there a real finding was dismissed as noise, here noise was reported as a
finding.

`aska.py` now judges an untested signature against chance — `max(4, 8 × size ÷
2³²)` hits — and prints the bar it used. Replayed against every specimen
already measured, the fix changes two printed verdicts and no measurement:
Eternal Sonata and **Beyond the Labyrinth** both drop to "nothing found", which
is what [aska-across-titles.md §9](../aska-across-titles.md#9-beyond-the-labyrinth--the-first-specimen-that-says-no)
has been claiming in prose all along. All nine positive titles stay
positive.

## 8. What this says, stated carefully

Three layers, three answers:

| Layer | Born | In Eternal Sonata? |
| --- | --- | --- |
| the compression algorithm and its method byte | 1998 | **yes**, with one nibble swapped |
| the four-character space-padded magic convention | by 2003 | **yes**, different letters |
| the payload formats — `S?F`, `A?F` | 1999–2003 | no |
| the container — `MRON`, `PACK` | 2005–2009 | no, there is no container |
| the engine namespace and shader toolchain | — | no |

The reading that fits is the ordinary one: **people carried the oldest and most
portable piece of code they had, and the habits that go with it, and built
everything above it new.** A compression routine is exactly the kind of thing
that travels in someone's head or in someone's personal library; a renderer is
not. That the swap is a *swap* rather than a copy is itself informative — it
reads like a reimplementation from memory or from a description, not a copied
file.

This is a resemblance argued from measurements, and it is worth saying what
would overturn it: a third studio, unconnected to either, shipping the same
byte-flag LZ77 with a 12/4 split and a bias of three. That scheme is not exotic.
What is hard to explain away is the **method byte** — 0 to 3 with 0 meaning
stored — sitting beside it in both.

## Left open

1. **Eternal Sonata's methods 2 and 3.** 961 of the 1 105 shipped files, which
   is the whole game. Not the method-1 family. `default.xex` decrypts cleanly
   and is 5.7 MB of PowerPC, so unlike tri-Ace's PlayStation 2 case the
   decompressor is right there in a readable image.
2. **`.bop`, `.x3tex`, `.e` and `.bmd`.** Only `BMD ` has a magic; the rest are
   headerless and all four are behind methods 2 and 3.
3. **What `CSF `'s `BOOK` block is.** The word is what ADPCM coefficient tables
   are called on several consoles, and 60 stored files carry it.
4. **Whether tri-Ace's method 2 and tri-Crescendo's are the same thing.**
   Both are the second slot in the same numbering, both resist the same search,
   and neither is byte-flag framed. If one falls the other may follow.
