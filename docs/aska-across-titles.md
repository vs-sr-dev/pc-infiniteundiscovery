# Is ASKA in tri-Ace's other titles?

Everything else in this repository is about one disc. This is the one document
that is not.

The question was posed in [TODO.md](../TODO.md) with a test ladder and two
warnings: that the tests are **asymmetric** — a hit on a versioned magic or on
the engine namespace is conclusive, a miss proves very little — and that the
platform layer is expected to differ on anything that is not an Xbox 360.

Three specimens, chosen to hold the platform constant and vary the year, plus
one that varies the platform while staying big-endian:

| Title | Year | Platform | Build |
| --- | --- | --- | --- |
| Infinite Undiscovery | 2008 | Xbox 360 | the baseline, `UD4` |
| Star Ocean: The Last Hope | 2009 | Xbox 360 | `SOZ.exe`, 2009-03-31 |
| Resonance of Fate | 2010 | Xbox 360 | `CH_Release.exe`, 2010-01-27 |
| Star Ocean: Integrity and Faithlessness | 2016 | PlayStation 3, JP | 2016-03-31, program revision 12072 |
| Star Ocean: Anamnesis | 2016 | Android | `libSOA.so`, arm64 — added after the other three, see [§8](#8-star-ocean-anamnesis-and-what-it-cost-the-tool) |

**The answer is yes, for all four.** What differs between them is not whether
it is the same engine but how much of it is *readable*, and that turns out to
be a different question with a different answer in each case.

## 1. The short version

| Evidence | SO4 | RoF | SO5 | Anamnesis |
| --- | --- | --- | --- | --- |
| `Aska::` in the executable | **yes** | no | encrypted | **yes, 46 507 mangled** |
| Class inventory | RTTI stripped | RTTI stripped | encrypted | **5 960 names** |
| `AHSL` shader toolchain | yes | yes | yes, as shipped files | yes |
| Shader constant names shared with IU | 30 | 0 | 8 | — |
| AIF images embedded in the executable | **6, byte-identical to IU's** | 5 headers, reader-clean | — | — |
| `SLZ` wrapper | named in the executable | named in the executable | **present in the data, revised** | named |
| Container opening table shared with IU | **99.5 % of 2 560 words** | no | — | first word only |
| Payloads the readers open | **all of them** | none found | headers only | byte-reversed |

## 2. What each specimen gave up

### Star Ocean: The Last Hope — settled outright

`SOZ.exe` contains the string

```
Aska::ObjectManagerWorkerThread(%d)
```

a thread name, in clear text. That is the engine namespace in the executable,
which the ladder called conclusive, and it settles the title on its own.

Everything else agrees with it. The executable embeds **six AIF images that are
byte-for-byte identical to six in Infinite Undiscovery's** — same SHA-1, 192 KB
in all, decoded to identical PNGs by `aif.py` from both binaries. Thirty shader
constant names are shared. And the first `0x2800` bytes of the first container
are the same table as Infinite Undiscovery's — see [§4](#4-the-table-at-the-top-of-the-first-container).

### Resonance of Fate — settled by the executable, silent on disc

No `Aska::` string and no RTTI. What `rof.exe` does carry:

* the `SLE` / `SLZ` token pair, in the same relative position as in the other
  two executables;
* `AHSLProfileData`, `AHSLDiskCacheXe`, `ahsl\`;
* **five `AIF ` headers**, which `aif.py` reads field for field with no
  changes — same `imgX` chunk, same `Dg#1` identifier, same `0x10400` flag
  word, 64 × 64 at 8 bits per pixel. They are header-only records, stating a
  total size of `0x80` where Infinite Undiscovery's state the whole image.

Its disc data is another matter, and [§5](#5-what-the-sweep-found) has the
numbers.

### Star Ocean 5 — the same wrapper, eight years later

The PS3 build ships as a PSN package rather than a disc; see
[formats/pkg.md](formats/pkg.md) for how it is opened. Inside, the game data
sits in nine CRI **CPK** archives — the container layer is middleware here, not
tri-Ace's — and inside *those*, on a 2 048-byte grid, are **`SLZ` blocks**.

That is the wrapper from [formats/slz.md](formats/slz.md), with its fields
moved: see [§3](#3-slz-in-2016).

The payloads are there too, in quantity and big-endian: 1 886 sound `ASF `
headers, 3 740 sound `AIF ` ones, 5 553 `AAF ` and 683 `ACF `, and 163 `pCol`
primitive names from Maya. **They do not open, though.** The magic is right and
the length the file states at `+0x04` is right — that is what "sound" means —
but the chunk walk fails immediately: an `ASF ` here has no `ao__` at `0x20`,
and an `AIF ` has no `imgX` at `0x10`. Something sits between the magic and the
chunks that Infinite Undiscovery does not have, and 58 of 613 payload headers
sampled carry the ASCII tag `PS3 ` inside their first 64 bytes.

So Star Ocean 5 is the specimen that answers the *first* question and not the
second: the engine is certainly there, and how much of it is readable is,
today, the header and nothing under it.

## 3. SLZ in 2016

Measured over 2 846 blocks taken from three widely separated regions of
`FAI_main_ps3.cpk`:

| Offset | Infinite Undiscovery | Star Ocean 5 |
| --- | --- | --- |
| `0x00` | `SLZ` | `SLZ` |
| `0x03` | version, 4 everywhere | **method**, 0–3 |
| `0x04` | header size, `0x20` | `0x00010025`, constant |
| `0x08` | compressed size | compressed size |
| `0x0C` | uncompressed size | uncompressed size |
| `0x10` | zero | zero |
| `0x14` | one | **`0x20`**, constant |
| `0x18` | XCompress magic `0x0FF512EE` | `0x00400001`, constant |
| `0x1C` | XCompress version | zero |
| `0x20` | — | payload begins |

Three things are measured rather than assumed:

* **The walk closes.** Every block is followed by the next at
  `align_up(compressed size + 0x20, 2048)` — **2 845 of 2 845** consecutive
  pairs.
* **Byte `0x03` is a method, not a version.** The 175 blocks that carry 0 have
  compressed size *equal* to uncompressed size, and their payload is readable
  text. A version field does not do that.
* **The payload begins at `0x20`.** The words at `0x18` and `0x1C` are constant
  across every block, compressed and stored alike, so they belong to the header
  and not to the data.

The stored blocks are worth reading for their own sake, because of what they
contain:

```
local nEventDB=0
function seq08_ev1650_17_EndOfEvent()
end
End();
```

Infinite Undiscovery's scene scripts are compiled bytecode — 253 opcodes, of
which seven are identified, in [formats/snc.md](formats/snc.md). By 2016 the
scene script is **source text in a Lua-shaped language**, shipped as source.

What the compressed methods 1, 2 and 3 are is open. It is not XCompress, which
is expected — that is an Xbox SDK library and this is a PlayStation. It is also
not plain LZSS: 480 combinations of offset width, length width, byte order,
minimum length, flag polarity and bit order were tried against 60 blocks and
none decoded one.

## 4. The table at the top of the first container

Infinite Undiscovery's `ud1.bin` and Star Ocean 4's `soz0.bin` begin almost
identically. The similarity is exact in extent: it covers the first `0x2800`
bytes and stops dead there.

Laid out on the `0x100` period that [session 7](sessions/session-07.md) found,
it is **40 rows of 64 words**, and the structure of a word is the finding:

| | |
| --- | --- |
| Top 16 bits equal, IU vs SO4 | **2 548 of 2 560 words (99.5 %)** |
| Whole word equal, IU vs SO4 | 690 of 2 560 (27.0 %) |
| Whole word equal, IU disc 1 vs disc 2 | 97.3 % |
| Columns whose top 16 bits are constant down all 40 rows | 56 of 64 |

So each word is a pair: **a 16-bit key that belongs to the engine** — the same
in a different game — and **a 16-bit value that belongs to the title**, and to
the disc. Question 13 in [TODO.md](../TODO.md) asked what this per-disc table
is; it is not per-disc. Only its low halves are.

Resonance of Fate's `ROF0.bin` shares none of it: 0.4 % byte agreement, which
is chance.

## 5. What the sweep found

`aska.py identify` over each whole image, same tool, same run. Where a
signature has a structural test, the **sound** column is the one to read: a
bare four-byte magic turns up by chance about once per four gigabytes, and
every image here is bigger than that.

| Signature | IU disc 1 | Star Ocean 4 | Resonance of Fate | Star Ocean 5 |
| --- | ---: | ---: | ---: | ---: |
| MRON container | **6 873** / 6 261 sound | — | — | — |
| SNC scene script | 7 | — | — | — |
| AREA | 94 | — | — | — |
| MINI | 44 | — | — | — |
| SIG- signal | 2 909 | — | — | — |
| ASF scene | 1 454 / 1 450 | 2 / 1 | 1 / 0 | **1 887** / 1 886 |
| AAF animation | 6 763 | **305** | 2 | **5 553** |
| ACF collision | 1 314 | **769** | 2 | **683** |
| AIF image | 3 321 / 3 320 | **85** / 84 | 3 / 0 | **3 947** / 3 740 |
| AAC audio | 9 080 | **11 681** | 185 | 22 |
| SLZ wrapper | 8 104 / 8 082 | **26 531** / 26 498 | 21 / **0** | **19 583** / 10 155 |
| AI node field | 33 / 33 | 1 / 0 | 1 / 0 | 5 / 0 |
| `R:M:` node prefix | 877 637 | 1 | 1 | 1 |
| pCol primitives | 10 357 | **747** | — | **163** |
| `Tri_ace` node | 1 | — | — | — |
| AHSL | — | — | 4 | 30 |

Star Ocean 5's column is the decrypted package run, 11.2 GiB, not a disc image.
The little-endian rows added to the tool afterwards — see
[§8](#8-star-ocean-anamnesis-and-what-it-cost-the-tool) — are not in this table;
on big-endian data they measure nothing but chance.

Read down the columns and the three specimens are three different situations.

**Infinite Undiscovery** is the baseline: the container announces itself 6 873
times, and everything else follows from the entry tables.

**Star Ocean 4 kept the payloads and threw away the container.** Not one
`MRON`, `AERA`, `INIM`, `-GIS` or `-CNS` tag on the whole disc — the versioned
tags that were called conclusive are simply gone. What is there instead is
**26 498 sound SLZ blocks**, three times Infinite Undiscovery's count, and
uncompressed runs of `ACF` and `AAF` and `AAC` sitting in the open. The 747
`pCol` hits track the 769 `ACF` ones, which is what a stored collision file
looks like: the Maya primitive names are in the payload, and the payload is not
compressed.

The `R:M:` count is the clearest single statement of the difference. Infinite
Undiscovery leaves 877 637 node names in the clear; Star Ocean 4 leaves one.
The models are still there — [§6](#6-the-readers-against-star-ocean-4) opens
them — they are simply all behind `SLZ` now.

**Resonance of Fate shows nothing at all.** Every count is at or below what
chance produces on 7.3 GiB, and every signature with a test scores **zero**
sound. Its two containers are entropy 8.00 everywhere sampled. Whatever wraps
that disc, it is not a format any of these readers can see, and the evidence
for the title rests entirely on its executable.

Two rows are worth a note. `AHSL` scores nothing on any disc, including the
baseline — the shader toolchain names live in the executable, which is
compressed inside its XEX, so a sweep of a disc image cannot see them. And
`Tri_ace` appears once on Infinite Undiscovery and nowhere else: the studio's
own node name is in its opening logo scene, and the other two titles do not put
one on the disc in the clear.

## 6. The readers against Star Ocean 4

The ladder's fourth rung: not "the magic matches" but "the reader parses it and
its self-checks pass". `slz.py` needed one change to get there — see
[§7](#7-what-this-changes-about-the-tooling) — and after that the payloads came
out of the disc and went into the readers untouched.

**797 SLZ blocks** decompressed out of six 32 MiB windows spread through
`soz0.bin`, and what they hold:

| Magic | Count | |
| --- | ---: | --- |
| `AAF ` | 461 | animation |
| `ASF ` | 128 | scenes |
| `EXD\0` | 90 | not a format this repository knows |
| `mcd ` | 45 | likewise |
| `ACF ` | 27 | collision |
| `AIF ` | 13 | textures |
| `MMD ` | 12 | likewise |
| `-CNS` | 6 | scene scripts |

Then the readers, on a corpus carved from those:

**`asf.py check`, 60 scenes** — 60 read, 0 not ASF, 1 094 meshes:

| | |
| --- | --- |
| packed vectors, median &#124;length − 1&#124; | 0.0016 (n = 709 760) |
| bone pool inside the node tree | **164 of 164 objects** |
| mesh palette inside the bone pool | **370 of 370 meshes** |
| vertex bone index inside the palette | 365 of 370 meshes |
| materials laid out end to end | 466 of 467 |
| meshes agreeing with their material on texture coordinates | 1 093 of 1 109 |

**`acf.py check`, 27 collision files** — **27 of 27 parse and self-check
clean**. The shape code agrees with the name the artist typed in Maya on
**1 515 of 1 515** primitives, and every stated bounding radius matches the
shape's own parameters to within one part in a million.

**`aaf.py check`, 120 animations** — 118 parse with exactly one complaint each,
and the complaint is the version number: `0x190000` where Infinite Undiscovery
writes `0x16`. Everything the reader actually walks — records, tracks,
keyframe blocks, channel numbering — comes through. One file uses an 18-byte
key, a size the reader has not seen.

**`snc.py info`, 6 scene scripts** — **self-check clean on all six**, and the
version string on the payload is `-CNS00.3`, *identical* to Infinite
Undiscovery's. The code walk lands exactly on the end of the code section every
time, and the string tables read `camera1`, `pc01_Sheath`, `iron_door01`,
`DoorProg01` — where `pc01_Sheath` is also a node in the skeleton `asf.py` read
out of the same disc.

### The container is `PACK`

The sweep says Star Ocean 4 has no `MRON` anywhere, and that was left as an
open question — something must index those thousands of payloads. It does, and
it is called **`PACK`**:

| | first 128 MiB of each container |
| --- | --- |
| `ud1.bin`, `ud2.bin` | none |
| `soz0.bin` | `PACK` × 7, first at `+0x62800` |
| `soz1.bin` | `PACK` × 32, the first **at offset 0** |
| `ROF0.bin`, `ROF1.bin` | none |

It is new in 2009: Infinite Undiscovery does not have one. The header is four
words and then a table, all big-endian:

| Offset | Field | `soz1.bin` |
| --- | --- | --- |
| `0x00` | `PACK` | |
| `0x04` | version | `0x0706` |
| `0x08` | entry count | 14 |
| `0x0C` | total size | `0x13B10` |
| `0x10` | entries, 16 bytes each: id, flags, **size**, **offset** | |

Two things check it, and both come from numbers the header does not control:

* the table ends at `0x10 + 14 × 16 = 0xF0`, which is **exactly** the offset the
  first entry gives;
* every entry points at an `SLZ` block, and on **13 of the 14** the
  uncompressed size in the SLZ wrapper equals the size the table states. The
  fourteenth states 64 where the wrapper says 54.

Two of the fourteen carry `SLZ` with byte `0x03` set to **0**, and one of those
has packed size equal to plain — the stored method, read here from a second
title after Star Ocean 5's package showed the same byte doing the same job.

### The opcode numbering does not carry over

That last result invites an obvious hope — a second corpus for the 246 unnamed
opcodes of [question 1](../TODO.md) — and the hope is wrong. It was tested.

Of the 77 opcode numbers that appear in both titles, only **15** use a
signature that Infinite Undiscovery also produces. The other 62 use operand
signatures Infinite Undiscovery never writes, and differ in operand *count*,
which is independent of how operand kinds are encoded:

| Opcode | Infinite Undiscovery | Star Ocean 4 |
| --- | --- | --- |
| `0035` | `nn` | `nnn@@nn` |
| `0036` | `e` | `nnn@@nn` |
| `0037` | *(none)* | `nnn@@nn` |
| `0018` | `kn` | `eknn$`, `eknnn` |

Three consecutive opcodes with three different shapes in one game and one
shared shape in the other is a table that was renumbered, not a format that
evolved. A 13 306-instruction sample can miss signatures that a
420 532-instruction one has; it cannot invent them.

So the **instruction encoding is shared and the opcode table is not**: the
number is an index into a per-title function table. Cross-title comparison of
opcode numbers cannot say anything about their meaning, and question 1 has to
be answered inside Infinite Undiscovery after all. That is worth knowing before
spending a session on it.

## 7. What this changes about the tooling

Two gaps were named in the TODO before this started, and both turned out to be
worth closing or correcting.

**XEX "normal" compression is implemented.** Both Xbox 360 titles use LZX where
Infinite Undiscovery used the basic scheme, so neither executable could be
decrypted at all. `xex.py` now unpacks the hash-linked block chain and hands
the stream to `lzx.py`, which gained `decode_stream` for frames that are not
delimited. The self-checks are strong: the image comes out at exactly its
stated size, and every block's SHA-1 matches the one the previous block
declared — **85 of 85** for Star Ocean 4, **69 of 69** for Resonance of Fate.
The same hash is what picks the decryption key, which is a better test than
looking for `MZ`, because under this scheme the plaintext does not start with a
PE header.

**The RTTI gap is wider than described.** The TODO expected to need a different
demangler for a PlayStation build. In fact **neither Xbox 360 title ships RTTI
at all** — no `.?AV` type descriptors in either — and the PlayStation
executable is encrypted behind NPDRM. The class inventory that session 1 built
from Infinite Undiscovery cannot be built for any of the three, and the ladder's
third rung is closed everywhere. What replaced it, on two of the three, was
plain strings in the binary.

## 8. Star Ocean: Anamnesis, and what it cost the tool

A fourth specimen arrived after the other three were measured, and it is not a
console title at all: **Star Ocean: Anamnesis**, the Android build, 58 MB of
APK. tri-Ace has said in public that ASKA runs on mobile as well as console,
and this is what that looks like from the outside.

It is settled before any format is opened, by the executable and by a filename:

| | |
| --- | --- |
| `lib/arm64-v8a/libSOA.so` | **46 507** hits of `4Aska` in Itanium mangling, plus 11 plain `Aska::` strings and 147 `AHSL` |
| `assets/aska0000.bin` | the engine's own name, on the asset file |
| `assets/FilterShader/GLES2/` | 439 files, beside Star Ocean 5's `FilterShader.afsb` |

The mangled symbols are the thing worth having. Session 1 recovered **1 740**
class names from Infinite Undiscovery's MSVC RTTI; this library carries
**26 378** mangled `Aska` symbols resolving to **5 960** distinct two-level
names, and they are methods and members, not only classes. A sample of what is
in there:

```
Aska::TAafRotateQuaternionController      Aska::TAafControllerCompressionLayer
Aska::TAafFrameSortController             Aska::TAafVectorElementController
Aska::TAafTranslate{X,Y,Z,XYZ}Controller  Aska::ParticleEmitter
Aska::Cryption::Ninja::KeyStore::Set      Aska::TaskManager::Add
```

The `TAaf…Controller` family names, in the engine's own words, the machinery
this repository has been decoding from the outside in
[formats/aaf.md](formats/aaf.md) — including a compression layer and a
quaternion controller. That is a lead for the open AAF questions and it is a
different kind of evidence from anything the discs gave up.

### The correction it forced

Anamnesis is little-endian, and it showed that one assumption in `aska.py` was
wrong. The docstring said every signature but one was ASCII and so survived a
change of byte order. It does not: **a FourCC written out as a 32-bit word
comes out reversed**. `assets/disc1/f00003.bin` opens with ` FIA`, which is
`AIF ` seen from the other end, and its inner chunks are reversed with it.

The payload magics, the `SLZ` wrapper and the node-field constant are now all
looked for both ways round, with validators that read the length field in the
matching order. On that one asset file the little-endian rows find three `AIF `
headers, all three sound.

That matters more for what comes next than for what came before. Every
remaining candidate — Star Ocean 6 on x86, a PlayStation Vita title, anything
else on mobile — is little-endian, and the tool would have reported nothing on
all of them.

## 9. Beyond the Labyrinth — the first specimen that says no

Nintendo 3DS, 2012, Japan only, tri-Ace from end to end. 706 MB of RomFS, and
it is the first title tested where the answer is not yes.

**The sweep finds nothing.** Over the whole 0.70 GiB image every count is at or
below what chance produces on that much data, and every signature with a
structural test scores **zero sound** — in both byte orders, the reversed
magics included. Under the `P@CK` entries are blocks tagged `mpak`, which are
not `SLZ`.

**Its assets are Nintendo's formats.** Of the first 400 files in the RomFS,
359 are `P@CK`, 36 are `CTPK` — the 3DS SDK's texture container — two are
`CGFX` and one is `DVLB`, the SDK's shader binary. No `AIF `, no `ASF `, in
either order.

**Its executable does not name the engine.** `.code` is compressed with the
console's backward LZ77; decompressed it holds no `Aska`, no `AHSL`, no `R:M:`.

What *is* familiar is the layer above the formats:

* the RomFS is 1 313 files called `f0000.bin`, `f0001.bin`, … — the same
  convention as Star Ocean: Anamnesis's `assets/disc1/f00000.bin`;
* the container tag is **`P@CK`**, one bit away from the **`PACK`** that
  indexes Star Ocean 4, with the same header shape: tag, a version word, a
  count at `+0x08`, then fixed-size records;
* the material names are the same house style — `c028_01_bodyM`,
  `c032_01_moyouM_bloom`, `etc_Daura01m` beside `AAmbientLight1` and
  `HemiSphereLight1` — as Infinite Undiscovery's `cp001_f01a_hada2` and Star
  Ocean 4's `cp002_Gen`.

So Beyond the Labyrinth is tri-Ace in its art pipeline and in its container
family, and shares **no payload format at all** with the other four. Whether
that is a different engine or ASKA rebuilt on a handheld's SDK is not something
this evidence can decide, and it is worth saying plainly rather than picking
the flattering reading.
