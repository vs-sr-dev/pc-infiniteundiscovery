# Session 13 — the engine in eight other games

**Date:** 2026-08-25
**Goal:** the second front named at the end of [TODO.md](../../TODO.md) — does
the ASKA engine appear in tri-Ace's other titles, and does enough of it survive
to be readable with the tools here? Three specimens to start with — *Star
Ocean: The Last Hope* (2009, Xbox 360), *Resonance of Fate* (2010, Xbox 360)
and *Star Ocean: Integrity and Faithlessness* (2016, PlayStation 3, Japanese)
— and five more arrived while those were being measured: *Star Ocean:
Anamnesis* on Android, *Beyond the Labyrinth* on the 3DS, *Phantasy Star Nova*
on the Vita, and two PlayStation 2 discs three years older than this one,
*Radiata Stories* and *Valkyrie Profile 2: Silmeria*.

## Outcome

**Yes for six of the eight.** The full argument, with every measurement, is in
[aska-across-titles.md](../aska-across-titles.md); this log is what happened
and what it cost.

The specimens turned out to be eight different situations rather than eight
answers to one question, and the per-title summary is the table in
[§1 of the cross-title document](../aska-across-titles.md#1-the-short-version).
The one-line version: **Star Ocean 4 is the only title whose data this
repository can read end to end**, Beyond the Labyrinth is the only one that
says no, and Phantasy Star Nova is the only one that cannot be asked.

## What was worth the day

**Every reader in this repository parses Star Ocean 4.** Not the magics — the
files. 60 scenes through `asf.py check` with the bone pool inside the node tree
on 164 of 164 objects; 27 collision files through `acf.py check`, all clean,
with the shape code agreeing with the artist's Maya name on 1 515 of 1 515
primitives; 117 of 120 animations clean; six scene scripts clean, on a payload
whose version string `-CNS00.3` is *identical* to Infinite Undiscovery's.

**Six AIF images are byte-identical between the two Xbox 360 Star Oceans**,
compiled into both executables. Same SHA-1, 192 KB, same PNG out of `aif.py`
from either binary.

**The opening table of the first container is shared.** 40 rows of 64 words at
the top of `ud1.bin` and `soz0.bin`; the top half of each word is the same in
both games on 99.5 % of 2 560 words, the bottom half is per-title and per-disc.
That is [question 13](../../TODO.md) seen from a second angle, and it says the
table is not per-disc — only its low halves are.

**SLZ survived to 2016 and to PowerPC.** Star Ocean 5's PlayStation 3 build
puts `SLZ` blocks inside CRI `CPK` archives on a 2 048-byte grid, and the walk
closes exactly on 2 845 of 2 845 consecutive blocks.

## The thing that did not work, which is worth as much

Star Ocean 4's scene scripts parse, and the obvious next thought — a second
corpus for the 246 unnamed opcodes of question 1 — is **wrong**, and it was
tested rather than assumed.

Of the 77 opcode numbers appearing in both titles, only 15 use an operand
signature that Infinite Undiscovery also produces. The other 62 differ in
operand *count*, which no amount of sampling error can explain: a 13 306-
instruction corpus can miss signatures that a 420 532-instruction one has, but
it cannot invent them. Three consecutive opcodes with three different shapes in
one game and one shared shape in the other is a renumbered table.

So the instruction encoding is shared and the opcode table is not. **Question 1
has to be answered inside Infinite Undiscovery**, and knowing that cost an hour
rather than a session.

## The oldest thing in the engine

The two PlayStation 2 discs were the last to arrive and gave the best result.
Radiata Stories (2005) carries **26 254 sound `SLZ` blocks** and Valkyrie
Profile 2 (2006) **25 431**, and their executables carry the `SLZ`/`SLE`
constant pair that all three Xbox 360 executables also carry — five titles,
three CPUs, 2005 to 2010.

Their header is one word shorter than the one
[slz.md](../formats/slz.md) described, and that is what makes them worth
having. **The byte at `+0x03` is a compression method, and it always was.**
Infinite Undiscovery writes a constant 4 there, so from this disc alone it
reads like a version; Star Ocean 5 showed it selecting a codec and Star Ocean
4's stored blocks agreed, and Radiata settles it — of 661 blocks sampled from
three widely separated regions, the 68 that say 0 have their two sizes equal
and their payload in the clear, one of them opening with `SEQW`. The zero word
at `+0x0C` and the ordered size pair hold on 661 of 661.

Between 2005 and 2008 exactly one word was inserted at `+0x04`. Nothing else
moved.

## Tooling

Five tools changed and one is new.

**`tools/pkg.py`, new** — the PlayStation 3 package. Star Ocean 5 was never
pressed on a disc, so there was no filesystem to walk; the reader opens the
AES-128-CTR run, walks the item table and extracts, with seven self-checks
because a wrong key produces a table of garbage that still prints. Documented
in [formats/pkg.md](../formats/pkg.md).

**`tools/xex.py` — "normal" compression implemented.** Both Xbox 360 titles use
LZX where Infinite Undiscovery used the basic scheme, so neither executable
could be decrypted at all. The chain of hash-linked blocks is now unpacked and
handed to `lzx.py`. The self-checks are strong: exact stated image size, and
every block's SHA-1 matching the one its predecessor declared — **85 of 85**
for Star Ocean 4, **69 of 69** for Resonance of Fate. That same hash now picks
the decryption key, because under this scheme the plaintext does not start with
`MZ` and the old test could not work.

**`tools/lzx.py` — `decode_stream`.** XCompress delimits its frames; the LZX
inside an XEX does not. Decoding one frame at a time from successive slices,
each starting on a 16-bit boundary, reproduces exactly what an undelimited
stream does.

**`tools/slz.py` — the frame walk stops on the output count.** Star Ocean 4
leaves zero padding behind the last frame where Infinite Undiscovery lands
exactly on the end. The padding is still checked, so a walk that goes wrong
still fails.

**`tools/aska.py` — six changes.**

* A **chunk-boundary double count** is fixed. The 64-byte overlap between
  chunks meant any signature landing in it was counted twice, and the fix is a
  frontier: a match beginning in the last 64 bytes is left to the next chunk,
  where its validator has the bytes it wants as well. The baseline moved by one
  hit — `R:M:` from 877 638 to 877 637 — which is the size of the error and
  also proof it was real.
* The **SLZ validator knows both revisions**: `0x20` at `+0x04`, where
  Infinite Undiscovery puts it, or at `+0x14`, where Star Ocean 5 does.
* **`AHSL`** joins the signature list. It is the shader toolchain's name, in
  both Xbox 360 executables and on 30 shipped files in the PlayStation 3 build,
  and it is so far the only name seen to survive a change of platform.
* **The payload magics are looked for reversed as well**, along with `SLZ`,
  after Anamnesis showed that a FourCC stored as a word does not survive a
  change of byte order the way an ASCII name does.
* **The SLZ validator knows all three revisions**, the PlayStation 2 one
  included, each tested on its own terms.
* **`AAC ` has a validator at last**, which is the fix for the mistake below.

**`tools/aaf.py` — a second known version.** Star Ocean 4 writes `0x190000`
where Infinite Undiscovery writes `0x16`, and nothing else about the format
moved. Both are accepted so a self-check reports what is actually wrong.
Infinite Undiscovery's own corpus still reads 900 of 900 clean.

## The mistake worth recording

Resonance of Fate was written up as showing nothing at all on its disc, on the
grounds that every signature with a structural test scored zero sound. That was
true and the conclusion was wrong: `AAC ` had **no** test, and its raw count was
185 on 7.3 GiB where chance produces about two. A hundred times chance was
filed as noise.

Checked properly, 26 of 26 `AAC ` magics in a 256 MiB window have the same
version word `0x00020100`, a plausible total size, and land **exactly on a
2048-byte boundary** — one in 2048 by chance. They are audio containers, with a
header revised from Infinite Undiscovery's `0x00010003`.

`aska.py` now validates `AAC ` on a size that makes sense over two words that
are zero in both revisions, and the sweeps were run again. The lesson is the
one the sound column exists to enforce, and it failed here because the column
was empty rather than because it was wrong.

## The baseline was re-measured

The tool changed three times during the session — the double-count fix, then
`AHSL` and the reversed magics, then the `AAC ` and three-revision `SLZ`
validators — and each time every sweep was run again from scratch, six of them
at the end, so that no column is measured differently from its neighbours. The
table in
[aska-across-titles.md](../aska-across-titles.md#5-what-the-sweep-found)
replaces the one that used to be in TODO.md. Comparing counts across titles is
the whole point of it, and three re-runs is a cheap price for that.

## The Android specimen, and the assumption it broke

Star Ocean: Anamnesis is 58 MB of Android APK, and it needed no ladder at all:
`lib/arm64-v8a/libSOA.so` carries **46 507** hits of `4Aska` in Itanium
mangling and the asset file is called `assets/aska0000.bin`. Those symbols
resolve to **5 960 distinct two-level names** — against the 1 740 class names
session 1 recovered from Infinite Undiscovery's RTTI — and they are methods and
members, not only classes. `Aska::TAafRotateQuaternionController` and
`Aska::TAafControllerCompressionLayer` name, in the engine's own words, the
machinery [aaf.md](../formats/aaf.md) has been decoding from the outside.

It also proved one line of `aska.py`'s docstring wrong. It claimed every
signature but one was ASCII and so survived a change of byte order. **A FourCC
written out as a 32-bit word does not**: this build stores `AIF ` as ` FIA`.
The payload magics, `SLZ` and the node-field constant are now looked for both
ways round, with validators that read the length in the matching order — which
matters for every remaining candidate, since all of them are little-endian.

## What the later specimens added

**Beyond the Labyrinth (3DS, 2012) is the first no.** Every signature at chance
in both byte orders, Nintendo's `CTPK`, `CGFX` and `DVLB` for its assets, and a
`.code` — decompressed through the console's backward LZ77 — that names no
engine. What it does share is the layer above the formats: a `P@CK` container
one bit from Star Ocean 4's `PACK`, a RomFS of 1 313 `f0000.bin` files, and the
same material naming as Infinite Undiscovery and Star Ocean 4.

**Phantasy Star Nova (Vita, 2014) cannot be asked.** `pkg.py` grew a Vita path
— the key encrypts the package's own RIV, and the right one is found by trying
each candidate until the item table holds together — and every check passes on
all 85 items. Underneath is PFS, whose key is sealed by the licence. The test
that tells a second layer from a wrong key is a file whose first bytes are known
in advance: `sce_sys/pic0.png` is not a PNG under any candidate, while the same
key reads all 85 filenames. Its listing carries `disc1/f00000.bin` and CRI
`CPK` archives, which is the naming convention and the middleware, and nothing
more can honestly be claimed.

**Star Ocean 4's container is `PACK`.** Absent from Infinite Undiscovery, 32
archives in `soz1.bin` with the first at offset 0, a table of (id, flags, size,
offset) whose header ends exactly where the first entry points, and every entry
holding an `SLZ` block whose uncompressed size matches the table's on 13 of 14.

## Left open

1. **Star Ocean 5's payload envelope.** 1 886 sound `ASF ` headers and 3 740
   sound `AIF ` ones, and not one of them opens: the magic and the self-stated
   length are right, and there is no `ao__` at `0x20` or `imgX` at `0x10`
   behind them. Something sits between the header and the chunks, and 58 of
   613 sampled headers carry the tag `PS3 ` in their first 64 bytes.
2. **The compressed methods in Star Ocean 5's SLZ.** Byte `0x03` selects one of
   1, 2 or 3; the stored method 0 is readable and the other three are not. It
   is not XCompress and not plain LZSS — 480 combinations of offset width,
   length width, byte order, minimum match, flag polarity and bit order were
   tried against 60 blocks and none decoded one.
3. **Resonance of Fate's container.** Its executable proves the engine, its
   disc shows nothing: every signature with a structural test scores zero
   sound, and both containers are entropy 8.00 everywhere sampled. Where the
   entry tables are, and what wraps them, is unknown.
4. **Star Ocean 4's container.** Not one versioned tag on the disc, yet the
   payloads are there in their thousands behind `SLZ`. Something indexes them;
   whatever it is, it does not announce itself the way `MRON` does.
5. **`EXD\0`, `mcd `, `MMD `** — three resource magics in Star Ocean 4's data
   that this repository has no reading for. `EXD\0` is the commonest payload in
   the sample, ahead of `AAF`.
6. **The four columns** of the shared opening table whose top halves are *not*
   constant down the rows — and which vary identically in both games.
7. **Animation tangents differ between the titles.** Over the same measurement,
   Star Ocean 4's translation tangents sit within 5° of the line through their
   neighbouring keys on 93.5 % of 4 588 keys; Infinite Undiscovery's manage
   51.2 % of 57 279. Whether that is a different exporter or a different
   authoring convention is not known, and it bears on
   [question 5](../../TODO.md).
