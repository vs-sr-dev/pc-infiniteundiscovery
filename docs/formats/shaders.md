# Shaders — the AHSL disk caches, the fixed library, and the microcode

Every compiled shader Infinite Undiscovery ships, where it is, how it is
stored, and how to read the Xenos microcode inside it.
[Session 19](../sessions/session-19.md) established all of it;
[tools/shader.py](../../tools/shader.py) implements it.

**Status: solved as storage, and readable as code.** Every shader on the disc
decodes, every compiled blob parses, and every one of them disassembles into a
program that passes three independent checks, the last of which ties the
instructions to the metadata — see [§7](#7-status).

This replaces what [session 7](../sessions/session-07.md) and
[aska-engine.md §5](../aska-engine.md#5-shaders) used to say. "160 shaders, 70
of them located" was a count of the strings `ps_3_0` and `vs_3_0`, and 100 of
those 160 were the same ten strings, inside a compression dictionary, in ten
copies of it. §6 has the correction in full.

## 1. Where the shaders are

Two structures, both in `ud1.bin`, and **byte-identical on the two discs**:

| Where | What | Shaders |
| --- | --- | ---: |
| `ud1.bin +0x7800` | an `AHSX` cache, 26 records | 21 |
| `ud1.bin +0xC000` | the **fixed library**: an index and 60 blobs | 60 |
| `ud1.bin +0x1F947000` .. `+0x26D8BA66` | **nine** `AHSX` caches, back to back | 63 330 |

The nine caches sit inside the run [norm-mron.md §6](norm-mron.md#6-gaps) and
[mron.py](../../tools/mron.py) file as one 630 MB "ASF/WMV stream". That run is
now accounted for exactly: **six ASF movies** — 45, 158, 217, 13, 28 and 249
seconds — each ending on the sector before the next begins, then one `AIF `
texture of 100 KB, then the nine caches, each starting on the sector after the
last one ends, then the next archive. `ud2.bin` carries no cache on either
disc.

On disc 2 the ten caches sit at different offsets (`0x475AE800` onward for the
nine) and hash identically to disc 1's.

## 2. The fixed library

At `ud1.bin +0xC000`, big-endian:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | `0x0000000C` |
| `0x04` | 4 | count — 60 |
| `0x08` | 8 | zero |
| `0x10` | 4 × count | one entry per shader |

An entry is an offset from the start of the header, **with bit 31 set for a
pixel shader** and clear for a vertex shader; the flag agrees with the blob's
own magic in all 60. The blobs follow the table directly and **tile exactly**:
each ends where the next begins, and the last ends at `+0x14800`, where the
zero padding starts.

These are the post-processing and utility shaders — the video YUV conversion,
the depth-of-field family, the sky, the fullscreen filters, and the water
simulation of §8. **54 pixel shaders and 6 vertex shaders, built by nine
different compilers**, from `2.0.4025.0` to `2.0.6534.0`. Not one of them was
built by `2.0.6534.1`, the compiler that built everything in the caches.

## 3. The `AHSX` cache

The AHSL shader cache, as the engine writes and reads it. Big-endian.

### How it is known to be AHSL's

Three functions in the retail executable, read with
[tools/disasm.py](../../tools/disasm.py):

* `0x82219818`, a **constructor**, stores `0x002E` and `0x0003` in its object at
  `+0x78` and `+0x7A`, a pointer to `e:\AHSLCacheUD4\AHSLv2DiskCache` at
  `+0x9C` and one to `e:\AHSLCacheUD4\AHSLProfileData` at `+0xA0`;
* `0x82217900` **builds an empty cache** in the same object: `memset` of
  `0x2010` bytes, `AHSX` built as `lis r11,0x4148` / `ori r9,r11,0x5358`, the
  two halfwords from `+0x78`/`+0x7A` copied to `+0x08`/`+0x0A`;
* `0x822190A8` is the **loader**. For each of 0x20 slots it accepts a buffer
  whose first word is `AHSX` and whose halfwords at `+0x08` and `+0x0A` equal
  the object's `+0x78` and `+0x7A`, copies its first `0x2010` bytes, and walks
  `u16 @ +0x0C` records from `+0x2010`.

So `AHSX` is the thing the `AHSLv2DiskCache` path names, and `0x002E.0x0003`
is the version the engine insists on. Every cache on both discs carries it.

### Header

| Offset | Size | Field |
| --- | --- | --- |
| `0x0000` | 4 | `AHSX` |
| `0x0004` | 4 | a mask: zeroed on creation, different in most caches |
| `0x0008` | 2 | `0x002E` — version, checked by the loader |
| `0x000A` | 2 | `0x0003` — version, checked by the loader |
| `0x000C` | 2 | record count |
| `0x000E` | 2 | zero |
| `0x0010` | `0x2000` | the dictionary — see below |
| `0x2010` | | the records, back to back |

A cache ends where its last record does. The walk is exact: after `+0x0C`
records every cache on the disc lands on zero padding, and whatever follows —
the fixed library, the next cache, the next archive — starts on a sector
boundary after it.

### Records

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 2 | a hash — not a CRC-16 of the key; unexplained |
| `0x02` | 2 | size on disc, this header included |
| `0x04` | 2 | size once decoded, this header included |
| `0x06` | 2 | where the coded part begins; everything before it is stored |
| `0x08` | 2 | CRC-16 of the dictionary the record was coded against |
| `0x0A` | 1 | flags; `0x20` = relocate a pointer, and marks an alias |
| `0x0B` | 1 | zero |
| `0x0C` | | the key |

The key's third byte, at `+0x0E`, is **its own length modulo 256**, and the
stored prefix is that length rounded up to four: `+0x06 − 0x0C` equals
`align4(length)` in all 96 853 records, where 2 579 keys are longer than 255
bytes and the byte has wrapped. What the key encodes — presumably the
permutation, the choice of shading fragments that produced the program — is
not read here.

A record is one of two kinds.

**A shader** — `+0x02` smaller than `+0x04`. The bytes from `+0x06` are coded
with **tri-Ace's halfword LZ77**: `SLZ` method 3 as read off Star Ocean 3's
PlayStation 2 executable in session 17
([slz.md §2b-3](slz.md#2b-3-method-3-the-same-lz77-again-in-halfwords)), here
in **big-endian** halfwords, and **with the dictionary preloaded as its
history**. Decoded, the body begins with a 0x18-byte header whose halfwords at
`+0x12` and `+0x14` are the offset and size of an XDK compiled-shader blob
(§4), and that blob runs exactly to the end of the record.

**An alias** — `+0x02 == +0x04`, stored whole, flag `0x20`, eight bytes long
past the key. Those eight bytes begin with a `u32` pointing at **an earlier
record's key**, `record + 0x0C`, which is the pointer the loader relocates. An
alias's key equals its target's from the ninth byte on: a different
permutation that compiled to the same program, stored once.

### The dictionary

`+0x10 .. +0x2010`: 8 KB, identical in all ten caches. It **looks** like ten
shaders — XDK magics, constant tables, compiler stamps, microcode — and it is
not: its constant tables are short by up to 0x9C bytes against their own
offsets, the first names landing 0x6C early and the last 0x9C early, as though
runs had been cut out. It is a compression dictionary built from shader
fragments, and it is why the records compress as well as they do — a 752-byte
vertex shader in 74 bytes.

Every record states the dictionary's CRC at `+0x08`: CRC-16/X.25 — reflected
polynomial `0x8408`, initial and final value `0xFFFF` — the routine at
`0x82239C28`, which the loader and the builder both call over `+0x10` for
`0x2000` bytes. It is `0xC2E6`, in all 96 853 records.

Why 8 KB: method 3's distance is twelve bits **counted in halfwords**, so it
reaches back 4 095 × 2 = **8 190 bytes** — the dictionary's size, less the two
bytes a distance of zero cannot reach. The window was sized to the codec.

## 4. The compiled blob

Microsoft's XDK container, the same one the executable's own built-in shaders
use (there are several at file offset `0x11678` onward), big-endian:

| Offset | Field |
| --- | --- |
| `0x00` | magic — `0x102A1100` pixel, `0x102A1101` vertex |
| `0x04` | virtual size — everything before the physical part |
| `0x08` | physical size — literals and microcode |
| `0x10` | constant table offset: a `u32` size, then a `CTAB` |
| `0x14` | definition table offset, or 0 |
| `0x18` | shader header offset |

virtual + physical is the blob's length in every one. The **shader header**
begins with the offset of the microcode inside the physical part and its size,
which tile the physical part exactly and are a multiple of 12 bytes in every
blob.

The **`CTAB`** is Direct3D 9's documented constant table unchanged: a 0x1C-byte
header — size, creator, version (`0xFFFF0300` / `0xFFFE0300`), count, record
offset, flags, target — and 20-byte records of name, register set, register
index, register count and type, every offset from the start of the table. The
creator string is the compiler stamp §5 of the engine notes tabulates.

The **definition table** states literal constants. Its word at `+0x14` is
`register << 16 | dwords`, and the physical part begins with that many dwords.
In every blob of this game it is four float4s at **`c252..c255`**, and the
register reads `0x00FC` in a vertex shader and `0x01FC` in a pixel shader: the
pixel shader's constant file is the upper half of 512. Star Ocean 4's newer
compiler sometimes needs more (§9).

## 5. The microcode

Xenos microcode as documented publicly and implemented in Xenia: a
control-flow program of 48-bit instructions packed two per 96-bit slot, then
clauses of 96-bit ALU and fetch instructions that the `EXEC` family runs by
slot address and count, a two-bit-per-instruction sequence field saying which
are fetches. Every program here ends with one slot of zero padding.

### The compiler's own opcode names

The retail executable statically links the XDK microcode compiler (§5 of the
engine notes), and **its opcode table shipped with it**: 103 records of 0x34
bytes at file offset `0xA55828`, `0x82A55828` in memory.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | row index, 0 .. 102 |
| `0x04` | 4 | opcode |
| `0x08` | 36 | name, NUL-padded |
| `0x2C` | 4 | a class — `0x18` control flow, `0x1A`..`0x1C` ALU |
| `0x30` | 4 | unexplained |

Rows 0–4 are pseudo-ops (`OP_UNKNOWN` 255, `GPR`, `PRG`, `VER`, `DEF`), 5–17
control flow, 18–51 vector, 52–102 scalar, with `EXPORT` and `MOV` pseudo-ops
at 176 and above. `shader.py optable` prints it. The disassembler uses these
names, so its output is in Microsoft's vocabulary rather than an invented one.

Against the public numbering the table agrees on **every row but one**:

* **`MAX_V` is written as 3**, the same number as `MIN_V`, and it is the only
  vector row with bit `0x80` set in its class (`0x9A` against `0x1A`). The
  microcode settles which number the hardware uses: across the 20 517
  distinct blobs vector opcode 2 occurs **400 438** times and opcode 3
  **6 871** times, and `max` of a register with itself is how the compiler
  writes a move. `MAX_V` is 2; the
  table row means something other than the encoding.

And it is incomplete in one place: it stops at control-flow opcode 12, while
the compiler emits **13 and 14** — Xenia's `cond_exec_pred_clean` and its
`_end` form — in **20 101 of the 20 517** blobs. The disassembler names those
two from Xenia, and says so.

### Register files

Three bases that the metadata does not state and the microcode does:

| | vertex shader | pixel shader |
| --- | --- | --- |
| float constants | `c0..c255` | `c0..c255`, file offset 256 (definition table) |
| bool constants in a `CEXEC` | `b0..b127` | `b128..b255` |
| sampler `sN` in a `tfetch` | fetch constant **16 + N** | fetch constant N |

The vertex-sampler base is `D3DVERTEXTEXTURESAMPLER0`. Vertex fetches use
fetch constant 95 downward, the XDK's convention for stream 0; their format
and offset fields are zero in every blob, because Direct3D patches them from
the vertex declaration at bind time.

### Exports

An ALU instruction with its export bit set sends **both** halves to the one
export register the vector destination names, each with its own write mask —
the scalar destination field is not used. Export registers: `oPos` 62 and
`oPts` 63 in a vertex shader, `o0..o15` the interpolators; `oC0..oC3` 0–3 and
`oDepth` 61 in a pixel shader; and in either, **`eA` 32 and `eM0..eM4` 33–37,
memexport**.

## 6. What this corrects

* **"160 shaders, 114 pixel and 46 vertex."** Those were string counts, and
  they split exactly: **60** are the fixed library, and **100** are the ten
  target strings of the dictionary — six `ps_3_0`, four `vs_3_0` — counted once
  in each of ten caches. The hundred are **not shaders**. The engine notes'
  table of compiler stamps splits the same way: its nine older compilers, one
  to twenty-nine shaders each, are the library to the shader, and its hundred
  `2.0.6534.1` stamps are the dictionaries. So the reading "a hundred shaders
  rebuilt with the final toolchain, sixty carried forward" was right about the
  sixty and wrong about the hundred. What the caches actually hold is
  **63 351** coded records of 20 457 distinct programs, every one built by
  `2.0.6534.1`.
* **"70 shaders at `0x7718`–`0x14803`."** The range spans three things: the
  last 0xE8 bytes of the 30 KB table (whose true size is therefore `0x7800`,
  30 720 bytes, not 30 488), a 26-record cache at `0x7800`, and the fixed
  library at `0xC000`.
* **"The other 90 shaders … presumably inside archives."** They are the nine
  other dictionaries, and they are between the archives, not inside them.
* **"Water … a wave equation integrated in a pixel shader."** It is a
  **vertex** shader — see §8.
* **The AHSL rung of the TODO's shader plan.** "Does this game's own data
  carry a cache" — it does: 116 MB of it, on the retail disc, in the format
  the development-kit path names.

## 7. Status

`python tools/shader.py verify` on disc 1, and identically on disc 2:

| | |
| ---: | --- |
| 10 | caches, every one at version `0x002E.0x0003` |
| 96 853 | records; every walk lands exactly on the cache's end |
| 96 853 | carry the dictionary's CRC, `0xC2E6` |
| 96 853 | have a stored prefix of exactly their key length, rounded up to four |
| 63 351 | shader records, **every one** decoding to its stated size, consuming its input to the last byte and ending on a terminator |
| 33 502 | aliases, **every one** pointing at an earlier record's key |
| 20 517 | distinct blobs, library included — 20 224 pixel, 293 vertex |
| 20 517 | pass **all three** microcode checks below |

The three checks, applied to every distinct blob:

1. **Coverage.** The control-flow program's clauses cover every slot after it
   exactly once, up to the trailing zero padding, and the program ends in an
   `EXEC_END` form.
2. **Opcodes.** Every control-flow, vector, scalar and fetch opcode is a known
   one.
3. **Binding — the one that ties the reading down.** Every float constant an
   ALU instruction reads lies in a range the `CTAB` declares, or is a literal;
   every texture fetch uses a sampler the `CTAB` declares; every conditional
   exec tests a bool the `CTAB` declares — with the three register-file bases
   of §5 applied. The constant table and the instruction stream are two
   independent readings of one blob, and they agree on all of them.

Checks 1 and 2 are the kind of evidence that can pass while a reading is still
wrong. Check 3 cannot be satisfied by accident at this scale: a misplaced
source-register field or a wrong select bit reads registers no table declares
within a handful of blobs.

What is **not** decoded: the lane selection of two-operand scalar ops (the
disassembly prints the whole operand), the filter fields of a texture fetch,
and the vertex-fetch format, which is not in the blob to decode.

## 8. Two readings

The point of a disassembler is that a shader can now be read for what it
computes rather than for the names in its metadata. Two worked examples.

**The water simulation** — library entry 25, compiled by `2.0.4929.0`, 52
slots. It is a **vertex shader that draws nothing**. It derives a grid cell
from the vertex index (`RECIP_IEEE` of `cvGridSize.x`, `TRUNC`), fetches five
heights around the cell from `tf16` = `heightSampler` and the previous height
from `tf17` = `prevHeightSampler`, combines them with `cvWaveParams` in the
shape of an explicit wave-equation step, and then writes **twice through
memexport**: the new height to `cvExportAddr` + index, and the normal — from
the height gradient, normalised with `DOT2ADD_V` and `RECIPSQRT_IEEE`, packed
with the literal `(127, 254, 0, 1)` — to `cvExportNormal` + index. `oPos` is
set to zero. One vertex per cell, run for its exports alone. It is the only
shader of the 20 517 that allocates memory for export; 126 vertex shaders
sample textures, and this is the only one that writes anything back.

**The tone mapper** — cache 0, record `+0x2220`, 24 slots. It fetches the
scene (`tf0`), the bloom (`tf4`), a dither pattern (`tf2`) and a depth
(`tf1`); blends scene and bloom with the two components of `cvBloomBlend`;
then computes `L·(1 + w·L) / (1 + L)` with `L` the blend scaled by `c0.z` and
`w` built from `c0.x` — the **extended Reinhard operator**, whose white-point
term is `1/Lw²`; encodes with a per-channel **`SQRT`**, which is gamma 2.0;
and adds the dither scaled by `c0.y`. It also copies the fetched depth to
`oDepth`. The constant table places `cvBias`, `cvDitther` and
`cvReinhardWhite` **all at `c0`**: three scalars sharing the components of
one register, which the table alone cannot say and the instructions do.

    python tools/shader.py dis disc1.iso --lib 25
    python tools/shader.py dis disc1.iso --cache 0 --record 0x2220

## 9. Star Ocean 4, the second specimen

The same reader, pointed at *Star Ocean: The Last Hope* (Xbox 360, 2009) — rung
4 of the TODO's shader plan, which asked for a differential rather than a
richer sibling. That disc has no `ud1.bin`, so `shader.py` searches the whole
image, and finds two sector-aligned caches:

| | Infinite Undiscovery, 2008 | Star Ocean 4, 2009 |
| --- | --- | --- |
| caches | 10 | 2, at image `0x16E30000` and `0x26D8E800` |
| version | `0x002E.0x0003` | **`0x0033.0x0000`** |
| dictionary | CRC `0xC2E6` | **the same 8 KB, byte for byte** |
| records | 96 853 | 19 239 |
| shader records / aliases | 63 351 / 33 502 | 13 164 / 6 075 |
| distinct blobs | 20 517 | 11 679 — 11 262 pixel, 417 vertex |
| compiler | `2.0.6534.1` in the caches | `2.0.7645.0` |
| pass all three checks | 20 517 | **11 679** |

So the layout generalises, and what moved is dated: the version the loader
checks went from 46.3 to 51.0 in a year, the compiler moved on by several XDK
releases, and **the dictionary did not change at all** — it belongs to the
engine, not to either game.

Two things the newer compiler does that this game's does not, and which the
reader had to learn:

* **More literals.** 33 blobs define eight float4s from `c248` and 2 define
  twelve from `c244`, against 11 596 with the usual four from `c252`. The
  definition table says so, which is why the reader now takes the range from
  it rather than assuming one.
* **A third magic, `0x102A1111`**, on 13 distinct blobs: a vertex shader, by
  bit 0, with bit 4 also set. Otherwise the container is unchanged. What bit 4
  means is not known.

## 10. Implementation

[tools/shader.py](../../tools/shader.py): `scan` locates the library and the
caches, `verify` makes every check above, `list` prints one line per shader
with its constants, `dis` disassembles one, and `optable` prints the
compiler's table out of the decrypted executable. It takes a disc image or
`ud1.bin` on its own.
