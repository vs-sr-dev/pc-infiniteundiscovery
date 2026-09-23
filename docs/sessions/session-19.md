# Session 19 — the shader library was a cache, and the cache is tri-Ace's

**Date:** 2026-09-23
**Goal:** the shader plan in [TODO.md](../../TODO.md), from rung 0. Everything
the repository said about shaders came from session 7 and was reflection
metadata — strings found by scanning. Not one instruction had been decoded.

## Outcome

**All of the plan, and most of it came out differently from how it was
written.**

* The "160 shaders" of session 7 are **a fixed library of 60** and **ten AHSL
  disk caches** of 96 853 records. The "other 90" were never shaders: 100 of
  the 160 counted strings are the ten strings of one **8 KB compression
  dictionary**, repeated at the head of each cache.
* `AHSX`, the cache, is the `AHSLv2DiskCache` the development-kit path names —
  one constructor sets both — and it ships: 116 MB on each retail disc.
* Its records are compressed with **tri-Ace's halfword LZ77**, `SLZ` method 3
  from the PlayStation 2, here big-endian and **with the dictionary preloaded
  as history**. 63 351 of 63 351 decode.
* A **disassembler** for the Xenos microcode, using the opcode names from the
  XDK compiler's own table, which ships in the executable. All **20 517**
  distinct programs pass a check that ties the registers the instructions read
  to the ones the constant table declares.
* **Star Ocean 4** carries two caches with the **same dictionary byte for
  byte**, a year and a cache version later. All 11 679 of its programs pass.

The specification is [shaders.md](../formats/shaders.md); the tool is
[shader.py](../../tools/shader.py).

## 1. The constant table that was short

Rung 1 said to try Direct3D 9's `CTAB` layout first, with four checks. The
first blob looked for it at `0x784C`, just after Microsoft's container magic
`0x102A1100`, and the header was textbook — size `0x1C`, version `0xFFFF0300`,
ten constants, target and creator offsets. The **creator and target offsets
landed**. The **name offsets did not**: the first name sat `0x6C` bytes earlier
than its record said, the last `0x9C` earlier, and the gap opened in steps as
though runs of bytes had been cut out. The container's own sizes were short by
the same `0x9C`.

Two things came next that turned it round. A clean XDK blob in the executable,
at file offset `0x11678`, parsed as a textbook `CTAB` with every offset
landing — so the layout was right and the data was not a shader. And the blob
sat 0x34 bytes into a structure starting `AHSX`, a magic nothing in the
repository had seen.

## 2. `AHSX`

A sector-level scan of `ud1.bin` found ten `AHSX` blocks: one at `0x7800`, nine
between `0x1F947000` and `0x26D8BA66` — inside the run session 5 had filed as
630 MB of ASF video. All ten are **byte-identical for their first `0x2010`
bytes** and diverge after.

The executable builds the magic as an immediate in two places, and those are
the two functions that matter. `0x82217900` builds an empty one — `memset` of
`0x2010` bytes, the magic, two version halfwords from its object, a CRC over
`0x2000` bytes. `0x822190A8` loads one — checks the magic and the two
halfwords, copies the `0x2010` bytes, and walks `u16 @ +0x0C` records from
`+0x2010`, each carrying its own length. The constructor at `0x82219818` sets
the version halfwords to `0x002E` and `0x0003` in the same object that holds
the `e:\AHSLCacheUD4\AHSLv2DiskCache` path.

So a cache is a 16-byte header, 8 KB of something, and records. The records
walked exactly — 26 of them in the first, landing on zero — and they said what
the 8 KB was. Every record carries `0xC2E6` at `+0x08`, and the CRC routine at
`0x82239C28` — CRC-16/X.25 — gives `0xC2E6` over the 8 KB. Every record
carries two sizes, one up to ten times the other. That is **compressed data
declaring the dictionary it was compressed against**.

## 3. The codec, and why the dictionary is 8 KB

Session 17's method 3 has twelve-bit distances counted in halfwords: 8 190
bytes of reach. The dictionary is 8 192. That was worth trying before anything
else, and it worked on the first record tried: big-endian, starting at the
offset in `+0x06`, with the dictionary as history, every one of six test
records ended on a terminator, consumed its input to the last byte and produced
exactly `(+0x04) − (+0x06)` bytes.

Those are exactly the tests sessions 16 and 18 showed to be blind to where a
match copies from. The content test came from the decoded body: an XDK blob
whose `CTAB` offsets land on `cmWVS`, `cmWorld`, `cvWorldEyePos`, `vs_3_0` and
`2.0.6534.1` — strings that came out of **matches into the dictionary**, not
literals — and whose virtual and physical sizes end exactly on the record's
end. Past the first match, and structural.

Then the corpus: 96 853 records in ten caches, 63 351 compressed and every one
clean, 33 502 stored aliases, each pointing at an earlier record's key.
**20 457 distinct programs**, all built by `2.0.6534.1`. Disc 2's ten caches
hash identically to disc 1's.

And the correction session 7 needed falls out of it: the 8 KB dictionary looks
like ten shaders because it is made of shader fragments, which is also why its
constant tables are short — and it is the source of the hundred `2.0.6534.1`
stamps §5 of the engine notes tabulates. The other sixty stamps are the fixed
library at `0xC000`, to the shader.

## 4. The microcode

The cheap question first, as the plan said: is the compiler's mnemonic table
in the executable? It is — `OP_UNKNOWN` at `0x82A55828` heads 103 records of
0x34 bytes, each an index, an opcode and a name. Compared with the public
numbering it agrees everywhere except one row: `MAX_V` is written as 3, like
`MIN_V`, with a flag bit no other vector row has. The microcode decided it —
opcode 2 is 400 438 of the vector ops in the corpus, opcode 3 is 6 871 — and
`MAX_V` is 2.

The disassembler was written from the public encoding and checked three ways:
coverage of every slot, known opcodes, and binding, first on a sample of 4 719
blobs. The first pass failed in instructive places, and each failure was a
fact about the hardware rather than a bug in the reading:

* coverage failed everywhere — every program ends in a slot of zero padding;
* coverage then failed on 4 121 of the 4 719 — control-flow opcodes **13 and
  14**, the predicate-clean conditional execs, are missing from the compiler's
  own table but in 20 101 of the 20 517 programs;
* 1 410 texture fetches in the sample read "undeclared" samplers — in a vertex
  shader, sampler `sN` is fetch constant **16 + N**;
* conditional execs tested "undeclared" bools — pixel-shader bools start at
  **128**.

With those, all 20 517 distinct programs pass all three.

## 5. Reading two of them

**The water** — the fixed library's entry 25 — is a **vertex shader** that
draws nothing: one vertex per grid cell, five height fetches and one from the
previous frame through vertex texture fetch, a wave-equation step, and two
memexport writes, one of the height and one of a packed normal. Session 7 had
it as a pixel shader, from the names alone. It is the only shader of the
20 517 that exports to memory.

**The tone mapper** — cache 0, record `+0x2220` — is the extended Reinhard
operator with a white-point term, then a per-channel `SQRT` as a gamma-2.0
encode, then dither. Its constant table puts three constants at `c0`; the
instructions show them sharing the register's components.

## 6. Star Ocean 4

Rung 4. Its disc has two sector-aligned `AHSX` caches, at version
`0x0033.0x0000`, with **the same dictionary**. The reader needed two things to
open all of it: literal constants read from the definition table rather than
assumed to be `c252..c255` — the newer compiler sometimes uses eight or twelve
— and a vertex magic `0x102A1111` beside `0x102A1101`. After that, 11 679 of
11 679 programs pass. Resonance of Fate, which names `AHSLDiskCacheXe`, shows
no aligned cache, as its entropy-8.00 containers would predict.

## 7. What went wrong on the way

Recorded because each was caught by a test rather than by luck.

* **A misread hexdump.** The first reading of the `CTAB` was four bytes off,
  which made the first comparison look worse than it was. Printing the words
  individually fixed it.
* **A claim in the tool's own docstring**, that a key's third byte is its
  length. It held on the three records it was read from and failed on 73 198
  of 96 853 once `verify` tested it. The byte is the length **modulo 256**, and
  the stored prefix is that length rounded up to four — true of all 96 853.
* **A false alarm about `mron.py`**, which appeared to have skipped an archive
  after the caches. It had not; the gap's end was mis-added by hand.
* **The export rendering.** An exporting ALU instruction sends both halves to
  the vector destination's export register; printing the scalar half at its
  own destination field made the tone mapper look as though it wrote `oC0`
  twice.
* **A slow `verify`**, which recomputed the dictionary's CRC for every record.

## 8. On the side: the video gap

The 630 MB "ASF/WMV stream" at `ud1.bin +0x01442800` now splits exactly: six
ASF movies — 45, 158, 217, 13, 28 and 249 seconds — whose File Properties
sizes tile to the sector, one `AIF ` texture, and the nine caches, back to back
until the next archive. That is question 14 done for one of its runs.

## Left open

1. **What the record key encodes**, and whether it is the shader program block
   an ASF material carries — question 4, and now the obvious next comparison.
2. The record hash at `+0x00`, and the cache header's mask at `+0x04`.
3. Bit 4 of `0x102A1111`.
4. The 30 720-byte table before the first cache, question 13 — now with an
   untested candidate in `AHSLProfileData`, the constructor's other path.
5. The lane selection of two-operand scalar ops.
6. The rest of question 14's video runs, which the same walk will split.
