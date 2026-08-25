# Session 15 — SLZ is from 1998, and SLE is not

**Date:** 2026-08-25
**Goal:** one question, asked of two more specimens. Session 14 found `SLZ` and
`SLE` in Star Ocean 3's PlayStation 2 executable in 2003 and called the wrapper
the oldest thing in the engine. Were they born there, or earlier? The two
titles that can answer it are tri-Ace's first two 32-bit games: *Star Ocean:
The Second Story* (PlayStation, 1998) and *Valkyrie Profile* (PlayStation,
1999), both taken from the USA disc 1.

## Outcome

**Earlier, and by five years.** `SLZ` is on both PlayStation discs, in the same
header, with the same codec. **`SLE` is not on either of them.** So the pair is
not a pair yet in 1999, and the two halves have different birthdays.

And the more useful half of the answer is what is *missing*. The 1998 blocks
decompress, and what comes out is MIPS overlay code and Sony's own `TIM`
textures. There is no `SAF`, no `ATR`, no `FPS`, no `A?F` family — **the
wrapper is older than anything it wraps.**

## 1. The discs

Both are single-track `MODE2/2352` images, and both are laid out the same way:
an ISO 9660 filesystem holding **three entries**, one of which is everything.

| | Star Ocean 2 | Valkyrie Profile |
| --- | --- | --- |
| sectors | 236 531 | 310 565 |
| user data | 0.45 GiB | 0.59 GiB |
| volume id | `STAROCEAN2ND1` | `VALKYRIE` |
| executable | `SCUS_944.21`, 131 072 B | `SLUS_011.56`, 131 072 B |
| the rest | `SO2.BIN`, 483 493 888 B | `VALKYRIE.BIN`, 635 422 720 B |

That is the ancestor of the PlayStation 2 layout session 14 described — a tiny
executable and one enormous opaque blob — with the blob still *inside* the
filesystem rather than in raw sectors outside it. Both executables are stock
`PS-X EXE`, loaded at `0x80010000`, entry `0x80010008`, `0x1F800` bytes of
text. Everything else is an overlay.

## 2. `SLZ` in the executables, and `SLE` nowhere

`SCUS_944.21` carries `SLZ\0` padded into an eight-byte slot, **twice**:

```
0x1B060   "SLZ\0" + 5 zero bytes, then a table of 0x8001xxxx function pointers
0x1B30C   the same
```

`SLUS_011.56` carries it twice as well, at `0x1B0D0` and `0x1B37C` — within
`0x70` bytes of Star Ocean 2's offsets, with the same pointer table behind it.
Two different games, one year apart, linking the same library object.

**`SLE` is absent.** Not in either executable, and not on either disc: a scan
of both whole images finds zero occurrences on Star Ocean 2 and two on Valkyrie
Profile, and both of those are unaligned, inside the same duplicated blob of
nibble-packed data at two different sector addresses. Checked, and false.

So the `SLZ`/`SLE` pair that sits in every executable from 2003 to 2010 is
half as old as it looks. `SLZ` is 1998 or earlier; `SLE` appears somewhere
between 1999 and 2003, and there are two PlayStation 2 titles in the gap that
this repository has not looked at.

## 3. The blocks, and the header that never changed

| | Star Ocean 2 | Valkyrie Profile |
| --- | ---: | ---: |
| `SLZ` magics, whole image | 15 708 | 13 775 |
| of those, sound | **10 377** | **12 395** |
| every other signature | at or below chance | at or below chance |

The header is the sixteen-byte layout that [slz.md](../formats/slz.md) has been
calling the PlayStation 2 revision. It is not: it is the **PlayStation
revision**, unchanged from 1998 to 2006.

```
53 4c 5a 01  59 f1 01 00  d4 53 04 00  00 00 00 00
 S  L  Z  m  compressed   uncompressed  zero
```

Consecutive blocks are packed four-byte aligned where they are packed at all —
261 of 957 pairs on Star Ocean 2 and 410 of 698 on Valkyrie Profile in one
16 MiB window each, with the gap histogram concentrated on 0, 1, 2 and 3 bytes.
That is a lower rate than Star Ocean 3's 695 of 727, and the reason is
structural: on the PlayStation the blocks sit inside archives with their own
padding rather than end to end down the whole data area.

## 4. Method 1 is the same codec, ten years before Infinite Undiscovery

This is the measurement worth having. The LZ77 specified in
[slz.md §2b](../formats/slz.md#2b-the-playstation-codec-method-1) — byte-wide
flags from bit 0 up, literals on 1, a two-byte back-reference with a 12-bit
distance and a 4-bit length biased by 3 — was written from a 2003 disc. Applied
to 1998 and 1999 data, unmodified:

| | Star Ocean 2, 1998 | Valkyrie Profile, 1999 |
| --- | ---: | ---: |
| method 0 blocks | 1 | 4 |
| method 1 blocks | 283 | 1 174 |
| decode to exactly the stated size | **284 of 284** | **1 178 of 1 178** |
| failures | **0** | **0** |

Across the four titles now measured — 1998, 1999, 2003 and 2006 — **1 762
method-1 blocks decode and none fails.** Eight years of one codec with not one
byte of the specification changed.

The method byte is used differently, though, and the pattern is worth writing
down:

| Method | SO2 1998 | VP1 1999 | SO3 2003 | Radiata 2005 | VP2 2006 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0, stored | 1 | 4 | — | 14 | 2 |
| 1, LZ77 | 242 | 722 | 152 | **none** | 153 |
| 2 | 2 303 | 1 627 | 482 | 2 | 390 |
| 3 | **none** | **none** | 1 505 | 827 | 333 |

**Method 3 does not exist on the PlayStation.** It appears with the PlayStation
2 and becomes the default there. Method 2 is on every disc from 1998 on and is
still not decoded.

## 5. What is inside, which is the point

The decoded blocks are not assets in the sense the later discs mean it. They
are:

* **MIPS overlay code** — the commonest payload head on both discs is
  `27 bd ff e8` and its relatives, which is `addiu $sp, $sp, -0x18`, a function
  prologue. tri-Ace compressed its own executable overlays with `SLZ`;
* **Sony `TIM` textures** — 29 of 29 sampled on Valkyrie Profile have a
  self-consistent `TIM` header, id word, flag word, CLUT block and image block.
  The console's standard image format, not the studio's;
* **offset-table archives** — a run of `u32` offsets whose first entry is the
  size of the table itself, ascending, ending on the file length;
* unlabelled binary with no magic at all.

**Not one payload carries a tag from the PlayStation 2 vocabulary.** No `FAS`,
`RTA`, `FPS`, `FIS`, `LCTP`, `DMM`, `RMAC` or `PACK`, as a payload head, as a
leading literal of an unopened block, or anywhere inside 2.5 MB and 8 MB of
decoded data respectively. The four `DTT\0` sequences on Star Ocean 2 and three
on Valkyrie Profile were checked and are false: all unaligned, all inside
nibble-packed image data, three of them inside byte-identical copies of the
same blob.

So the lineage now has an order to it. **The compression wrapper came first, in
1998.** The named payload formats — the `S?F` family on the PlayStation 2, the
`A?F` family on the Xbox 360 — arrive later, on top of a wrapper that already
existed. Whatever ASKA is, `SLZ` predates it by a decade and was carried into
it.

## 6. Neither disc names the engine

No `Aska`, no `ASKA`, no `AHSL`, no `Tri`, no `tri` in either executable. No
Maya names, no 3ds Max biped names, no versioned magic. That is expected for
1998 and it is what the table records: these two titles are settled by `SLZ`
and by nothing else.

## Left open

1. **Where `SLE` starts.** It is absent in 1999 and present in 2003. The gap
   holds at least two tri-Ace PlayStation 2 titles this repository has not
   looked at, and one of them will have it.
2. **Method 2, now on five discs across eight years.** It is 2 303 of 2 546
   blocks on the 1998 disc and it has never decoded. Star Ocean 2's executable
   is 128 KB of MIPS with the `SLZ` string sitting on top of its own function
   table — which is a far smaller haystack for a disassembler than Star Ocean
   3's 751 KB.
3. **Where method 3 came from.** It is not on either PlayStation disc and it is
   the default on all three PlayStation 2 discs. Something replaced or joined
   the codec set between 1999 and 2003.
4. **The archives inside the blocks.** The offset-table shape is visible and
   was not measured properly; it is the obvious ancestor of `PACK`, and both
   are a table whose first entry states where the table ends.
