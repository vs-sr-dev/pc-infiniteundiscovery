# Session 17 — read the decompressor

**Date:** 2026-08-25
**Goal:** method 2. After sixteen sessions it was the most valuable unopened
thing in the repository: the second slot of `SLZ`'s method byte, present on
**every** tri-Ace PlayStation and PlayStation 2 disc from 1998 to 2006, and
resistant to every blind search aimed at it. The TODO's own instruction was to
stop searching and **read the code**, smallest haystack first.

## Outcome

**Methods 2 and 3 are both read, and `SLE` is explained as well.** All three
came out of two dispatchers. The file had been saying for three sessions that
they could not be guessed. They could not — but they never needed to be.

* **Method 2** is method 1 with the top slot of its length field traded for a
  **run**, and with the end-of-stream token removed. **36 598 blocks of
  36 598** across five discs decode to exactly the stated size, and — unlike
  method 1 — consume the input to its **last byte** in every single one.
* **Method 3** is method 1 with every unit widened to a **16-bit halfword**,
  12 000 blocks of 12 000. It is the default on all three PlayStation 2 discs
  and absent from both PlayStation ones, which is what "the codec set grew
  between 1999 and 2003" turns out to mean: it grew by a `u16` variant of what
  was already there.
* **`SLE`**, a string beside `SLZ` in every executable since 2003 and never
  anything more, is **not a codec**. It is an encryption envelope, and the last
  thing its branch does is overwrite its own `E` with a `Z` and fall through to
  the ordinary method switch.

Three codecs, one algorithm. tri-Ace never wrote a second compressor; it wrote
one and parameterised it three ways.

## 1. The way in was the string's own neighbourhood

The TODO named Star Ocean 2's `SCUS_944.21` as the smaller of two haystacks:
128 KB of MIPS, `PS-X EXE` loaded at `0x80010000` from file offset `0x800`,
with `SLZ\0` in an eight-byte slot **twice**, each followed by a table of
`0x8001xxxx` function pointers.

The tables were the finding, before any disassembly. Both are 31 entries, and
both have the *same* sequence of gaps between their targets:

    0x24 0x20 0x24 0x2C 0x34 0x2C 0x34 0x3C 0x48 0x3C 0x44 0x50 0x54 0x4C 0x58
    0x140
    0x24 0x20 0x24 0x2C 0x34 0x2C 0x34 0x3C 0x48 0x3C 0x44 0x50 0x54 0x4C

Sixteen routines of gently growing size, a jump, then fifteen more with the
same growth. That is a **jump table of unrolled copy routines indexed by a
length nibble**, twice — and the reason there are two of it, sharing one table
and one data island with the string, is that two codecs use it. 16 entries for
lengths 3 to 18 and 15 for lengths 3 to 17.

A scan for `lui`/`addiu` pairs that construct the string's address found
exactly one code reference: `0x800121D4`, inside a function at `0x800121A8`.

    move  $a0, $s0                 ; the block header
    lui   $a1, 0x8003
    addiu $a1, $a1, -0x57A0        ; 0x8002A860 -- "SLZ"
    jal   0x80023E80               ; strncmp
    addiu $a2, $zero, 3            ; ... of 3 bytes; non-zero -> return 0
    ...
    lbu   $v1, 3($s0)              ; the method byte
      == 0 -> memcpy(dst, hdr+0x10, hdr[0x08])
      == 1 -> 0x800122B4
      == 2 -> 0x8001275C
      else -> return 0

Three arms, and one of them was already known. That is the free check the TODO
asked for: `0x800122B4` reads its distance as `a | ((b & 0x0F) << 8)`, its
length as `(b >> 4) + 3`, and dispatches on the nibble into entries 0..15 of
the table — method 1, exactly as
[slz.md §2b](../formats/slz.md#2b-the-playstation-codec-method-1) specified it
from the outside two sessions ago. The right function was found.

## 2. Method 2, at `0x8001275C`

The same prologue, the same flag loop, the same token split. Three things
differ, and each is visible in ten instructions.

**It has no terminator.** Method 1's loop tests the distance for zero. Method
2's tests the output pointer:

    addu $a3, $t0, $a3             ; end = dst + uncompressed_size
    sltu $v0, $t0, $a3
    beqz $v0, 0x80012C80           ; out reached end -> return 1

which is why the dispatcher hands this codec **four** arguments and method 1
three. The size in the header is not a check here, it is the stop condition.

**A length nibble of 15 is a run, not a match.** The branch order is the
specification:

    slti $v0, $a1, 0x12            ; len = nib+3 ; len >= 18 ?
    beqz $v0, 0x80012BA4           ;   -> the run path
    slti $v0, $v1, 0x10            ; distance < 16 ?
    bnez $v0, 0x80012B78           ;   -> the byte-safe copy loop

and the run path re-reads the *same two bytes* as either a short form
(`count = (b & 0x0F) + 3`, byte `= a`, two bytes total) or, when that nibble is
zero, a long one (`count = a + 0x13`, byte = a third token byte). Everything
after that in the function — the odd/even address dance, the halfword stores —
is speed, not meaning: it writes `count` copies of one byte.

**The `distance < 16` arm is not a special encoding.** It is a byte-at-a-time
copy for the overlaps that the word-wise unrolled routines, which read four or
more bytes ahead, would get wrong. Semantically it is an ordinary match.

### What it buys, and why it exists

Method 2 is what tri-Ace reached for when the data was sparse, and on these
discs it usually was:

| Disc | method 1 ratio | method 2 ratio |
| --- | ---: | ---: |
| SO2, 1998 | 2.07 | **2.65** |
| Valkyrie Profile, 1999 | 2.27 | 1.65 |
| Star Ocean 3, 2003 | 1.44 | **2.48** |

A run of up to 274 identical bytes costs three bytes where method 1 spends two
bytes for every 18.

## 3. Method 3, at `0x00101520` in `SLES_820.28`

Method 3 is not on either PlayStation disc, so the PlayStation 2 executable was
needed. It has the same data island — `SLZ\0`, then `SLE\0`, then a pointer
table — at `0x0014D6C0`, and the same single code reference, at `0x00102540`.
The dispatcher there is the same function with a fourth arm:

    0 -> memcpy    1 -> 0x00101ED0    2 -> 0x001019C0    default -> 0x00101520

`0x001019C0` is method 2, instruction for instruction the same algorithm as the
1998 one. And `0x00101520` — the default arm, which is method 3 — takes
**three** arguments, no size. So before reading a line of it, it had a
terminator.

It is method 1 in halfwords:

    lhu $a0, ($a1)                 ; 16 flag bits, not 8
    lhu $a3, ($a1)                 ; one u16 token, not two bytes
    andi $t4, $a3, 0xfff           ; distance, in halfwords
    beqz $t4, 0x1019B8             ; zero -> end of stream
    sra  $a3, $a3, 0xc             ; length nibble, +2 halfwords

Literals are halfwords too. Nothing else changed at all.

The one wrinkle is arithmetic rather than structural: a codec that emits
halfwords can only produce an even number of bytes, so a block whose header
states an **odd** size overshoots it by exactly one. Three blocks of 3 000 on
the Radiata Stories disc do this, all three with an odd stated size, and the
extra byte is padding. `slz.py` trims it and treats anything else as an error.

## 4. `SLE` is encryption, and it erases itself

Question 28 asked where `SLE` starts and noted that *what it is* had never been
established either. The PlayStation 2 dispatcher compares it two instructions
after `SLZ` and gives it a branch ahead of the method switch. The branch is:

    plain[j] = (cipher[j] - 3 * (j + 1)) ^ key[j & 15]

over the payload, in place — a 16-byte key XOR with a subtractive counter
starting at 3 and stepping by 3, unrolled eight bytes at a time with a
remainder loop at `0x001027A8`. And then:

    addiu $v0, $zero, 0x5A
    sb    $v0, 2($s1)              ; 'Z' over the 'E' at header +0x02

The block becomes an `SLZ` block and falls through. So `SLE` is not a fourth
compressor, not a variant wrapper, and not a version: it is an **encryption
envelope around the same four methods**, which rewrites its own magic once the
payload is in the clear.

The key is not in the file. It is one `lq` from `0x001CC730`, past the end of
the loaded image, and a scan of every load and store in the executable finds
**two** accesses at that offset — the two copies of this branch. Nothing writes
it.

### And no disc uses it

| | SO2 1998 | VP1 1999 | SO3 2003 | Radiata 2005 | VP2 2006 |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw `SLE` byte sequences | 0 | 0 | 220 | 210 | 312 |
| with a header that could be real | — | — | 3 | 16 | 127 |
| that walk to a neighbouring magic | — | — | 0 | 0 | 0 |
| that decode, encrypted or not | — | — | 0 | 0 | 0 |

Valkyrie Profile 2's 127 candidates are a warning about the test rather than a
finding: "plausible sizes and a zero at `+0x0C`" is passed by 40 % of chance
`SLE` sequences inside compressed data. One of the 127 is sector-aligned, none
continues to another block where its own length says one should be, and none
decodes under any method with or without a zero key. The envelope shipped in
2003; nothing was ever put in it on these five discs.

## 5. The corpus

Run through `tools/slz.py` itself, not through a prototype. Every block found
by walking each image was decoded and checked on both sides: **the output is
exactly the size the header states, and the input is consumed to within the
encoder's four-byte padding.**

| Disc | m0 | m1 | m2 | m3 | blocks | decoded | failed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SO: The Second Story, PS1 1998 | 3 | 995 | 9 376 | — | 10 374 | **10 374** | 0 |
| Valkyrie Profile, PS1 1999 | 127 | 3 880 | 8 388 | — | 12 395 | **12 395** | 0 |
| Star Ocean 3, PS2 2003 | 4 | 4 000 | 8 894 | 4 000 | 16 898 | **16 898** | 0 |
| Radiata Stories, PS2 2005 | 557 | 1 | 5 | 4 000 | 4 563 | **4 563** | 0 |
| Valkyrie Profile 2, PS2 2006 | 2 | 4 000 | 9 935 | 4 000 | 17 937 | **17 937** | 0 |
| | 693 | 12 876 | **36 598** | **12 000** | 62 167 | **62 167** | **0** |

Methods 0 and 2 are complete counts — every block of those methods on each
image. Methods 1 and 3 are capped at 4 000 per disc; the cap, not the disc, is
what stops them.

Two details in that table are findings rather than bookkeeping.

**Method 2's input is consumed exactly.** Method 1 leaves two or three bytes of
four-byte padding at the end of a block, which is why `slz.py` tolerates up to
eight. Method 2 leaves **zero** — on all 36 598 blocks, without exception —
because it has no terminator to stop early on. The stop condition is the output
size, so the encoder has no reason to emit a byte the decoder will not read.
That is a much sharper test than method 1 ever got.

**Radiata Stories writes exactly one method-1 block on its disc.** Session 14
recorded "none, anywhere" from 64 sample windows; walking the whole image finds
one, at ratio 2.28, alongside 4 000+ method 3. The correction does not change
the point — the 2005 title abandoned method 1 — it just makes it a measurement
instead of an absence.

## 6. What method 3 opens, which was the point

[slz.md §2c](../formats/slz.md#2c-what-the-playstation-2-titles-call-their-assets--and-what-the-playstation-ones-do-not)
answered "what do the PlayStation 2 titles call their assets" *for what method
1 holds* — `SAF`, `ATR`, `SPF`, `PTCL`, `MMD`, `CAMR`, `TTD`, `PACK`. Method 3
is the **default** on those discs, so most of each disc was outside that
answer. It is not any more:

Tags are `u32` little-endian on these discs, so they read backwards on disc —
that is how `FAS\0` became `SAF` and `RTA\0` became `ATR` in session 14. The
same inversion applied to what method 3 holds gives a family nobody had seen:

| On disc | Reads | Where | What the first 48 bytes say |
| --- | --- | --- | --- |
| `TGIL` | **`LIGT`** | SO3, 164 blocks | header, then `1.0 1.0 1.0 1.0`, then `43.0 45.0` — a light with an RGBA colour |
| `XBDC` | **`CDBX`** | SO3, 44 | header, a `u32` name hash, then `8.76 16.46 6.73` — a box |
| `PCDC` | **`CDCP`** | SO3, 26 | the same hash, then `7.50 13.78 0.20 0.0` — a capsule |
| `LPDC` | **`CDPL`** | SO3 | the same hash again, and `CDCP` follows it at `+0x20` |

`CD` is the family and `BX`, `CP`, `PL` are the shapes, chained one after
another in a file, each with a four-word header of `tag / size / zero / offset
of the next` — the same shape as `ASF `'s chunk tree, ten years earlier and
little-endian. **That is Star Ocean 3's collision data**, and it sat behind
method 3 the whole time.

Two cautions from the same run, both worth more than the tags:

* **`mcps` is not a tag.** It is the first four bytes of `mcps2lib 2.01`, a
  middleware version string, exactly as `so3m` is the start of `so3mclib
  1.80i`. 575 blocks on the Valkyrie Profile 2 disc lead with it. A tag census
  taken from leading bytes cannot tell a magic from a string, and this is the
  second time that has bitten.
* **Radiata Stories does not invert.** Its commonest method-3 leaders are
  `Kods` (1 163), `RMF1` (549), `RBAD` (256) and `RLF2` (255), and none of
  them reads either forwards or backwards, though `RMF1` and `SEQW` are
  plainly structured — `RMF1` opens with a count and a table of ascending
  offsets, which is question 30's shape. The disc that abandoned method 1 also
  seems to have changed its vocabulary, and that is a question rather than a
  finding.

## 7. A correction worth recording

The TODO carried this, under method 2:

> it is **not byte-flag framed at all**, which is proved rather than inferred.

Method 2 is byte-flag framed. It is method 1's framing exactly.

The claim was not a bad measurement; it was a good measurement generalised past
its data. The 896-candidate search that produced it ran on **Eternal Sonata**
files, and the 480-combination LZSS search before it ran on **Star Ocean 5**
PlayStation 3 blocks. Neither touched a tri-Ace PlayStation or PlayStation 2
method-2 block. Both results still stand where they were taken — session 16's
argument about `bos01.csf` is unaffected, and tri-Crescendo's method 2 was
re-tested here against tri-Ace's, in both nibble orders, and is **not** the
same codec.

What travelled wrongly was a *negative*. Session 13's note that "the tests are
asymmetric" was written about signature hits; it applies to codecs too, and more
sharply. A codec that decodes a corpus in another title tells you the two
titles share it. A codec that fails to decode in another title tells you
nothing about the first one.

## Left open

1. **Eternal Sonata's methods 2 and 3**, 961 files, still shut — and now known
   not to be tri-Ace's. The route is the one that worked here, one console
   over: `default.xex` is 5.7 MB of PowerPC at `0x82000000`, the anchor is
   `index.vmtoc` at `+0x82E92`, and the method byte lives at record `+0x24`.
   The free check is available there too, since method 1 is known.
2. **The PlayStation 3 methods.** Star Ocean 5 uses the same numbering, and its
   method 1 is not this method 1. Whether its method 2 is *this* method 2 is
   now a five-minute test rather than an open question, and worth running
   before anything harder.
3. **`SLE`'s key**, if a disc is ever found that uses the envelope. Nothing in
   the PlayStation 2 executable writes the 16 bytes at `0x001CC730`.
4. **What method 3 opened**: the new payload tags above have no readers.
