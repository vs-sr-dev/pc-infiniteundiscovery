# Is ASKA in tri-Ace's other titles?

Everything else in this repository is about one disc. This is the one document
that is not.

The question was posed in [TODO.md](../TODO.md) with a test ladder and two
warnings: that the tests are **asymmetric** — a hit on a versioned magic or on
the engine namespace is conclusive, a miss proves very little — and that the
platform layer is expected to differ on anything that is not an Xbox 360.

Three specimens to begin with, chosen to hold the platform constant and vary
the year, plus one that varies the platform while staying big-endian. Nine more
arrived afterwards, and the list now spans eighteen years and seven consoles,
from tri-Ace's second game to their most recent one measured here:

| Title | Year | Platform | Build |
| --- | --- | --- | --- |
| Star Ocean: The Second Story | 1998 | PlayStation | `SCUS_944.21`, USA, disc 1 |
| Valkyrie Profile | 1999 | PlayStation | `SLUS_011.56`, USA, disc 1 |
| Star Ocean: Blue Sphere | 2001 | Game Boy Color | `STAROCEANGBBO2J`, Japan |
| *Eternal Sonata* † | 2007 | Xbox 360 | `P1_EU.pe`, PAL — **tri-Crescendo, not tri-Ace** |
| Star Ocean: Till the End of Time | 2003 | PlayStation 2 | `SLES_820.28`, PAL, disc 1 |
| Radiata Stories | 2005 | PlayStation 2 | `SLUS_212.62`, USA |
| Valkyrie Profile 2: Silmeria | 2006 | PlayStation 2 | `SLES_546.47`, PAL |
| Infinite Undiscovery | 2008 | Xbox 360 | the baseline, `UD4` |
| Star Ocean: The Last Hope | 2009 | Xbox 360 | `SOZ.exe`, 2009-03-31 |
| Resonance of Fate | 2010 | Xbox 360 | `CH_Release.exe`, 2010-01-27 |
| Star Ocean: Integrity and Faithlessness | 2016 | PlayStation 3, JP | 2016-03-31, program revision 12072 |
| Star Ocean: Anamnesis | 2016 | Android | `libSOA.so`, arm64 |
| Beyond the Labyrinth | 2012 | Nintendo 3DS | `CTR-P-ALVJ`, Japan |
| Phantasy Star Nova | 2014 | PlayStation Vita | `PCSG00351`, Japan, SEGA-published |

† Eternal Sonata is not one of the twelve. It is a different studio and a
different question — see [§13](#13-eternal-sonata--what-an-offshoot-studio-took-with-it).

**The answer is yes for nine of the twelve, no for two, and unanswerable for
one.** What differs between the nine is not whether it is the same engine but
how much of it is *readable*, and that turns out to be a different question
with a different answer every time. The oldest two are a special case worth
naming up front: they carry the wrapper and **nothing** it later wraps, which
is what dates the parts relative to each other.

A thirteenth specimen is in here that does not belong to that count at all.
*Eternal Sonata* is a **tri-Crescendo** game — the studio founded by people who
left tri-Ace — and it was measured to ask a different question: not whether it
is ASKA, but which layer the people took with them.
[§13](#13-eternal-sonata--what-an-offshoot-studio-took-with-it) has the answer,
and it is the oldest layer and only that.

## 1. The short version

One row per specimen, oldest first. "Readers open it" is the only column that
means the tools in this repository actually parsed the title's own data.

| Title | Engine named | Formats shared | Readers open it | Settled by |
| --- | --- | --- | --- | --- |
| SO: The Second Story, PS1 1998 | no | `SLZ` and nothing else | `slz.py`, method 1 | `SLZ` in the executable, 10 377 sound blocks |
| Valkyrie Profile, PS1 1999 | no | `SLZ` and nothing else | `slz.py`, method 1 | `SLZ` in the executable, 12 395 sound blocks |
| Blue Sphere, GBC 2001 | no | none | no | **nothing at all — not one hit** |
| Star Ocean 3, PS2 2003 | no | `SLZ`, and `PACK` as a tag | `slz.py`, method 1 | `SLZ`/`SLE` in the executable, 1 566 sound blocks |
| Radiata Stories, PS2 2005 | no | `SLZ` only | stored blocks only | 26 254 sound `SLZ` blocks |
| Valkyrie Profile 2, PS2 2006 | no | `SLZ`, `DTT\0`, `LCTP` | `slz.py`, method 1 | 25 431 sound `SLZ` blocks |
| Infinite Undiscovery, X360 2008 | `Aska::` + 1 740 RTTI names | *the baseline* | *the baseline* | — |
| Star Ocean 4, X360 2009 | **`Aska::` in `SOZ.exe`** | `SLZ`, `PACK`, ASF, AAF, ACF, AIF, SNC, AAC | **yes, every one** | the namespace, then the readers |
| Resonance of Fate, X360 2010 | no, RTTI stripped | `SLZ`/`SLE` and AIF headers in the executable | headers only | 182 sound `AAC ` containers |
| Beyond the Labyrinth, 3DS 2012 | no | `P@CK` and the art naming | no | **nothing — the one specimen that says no** |
| Phantasy Star Nova, Vita 2014 | not reachable | `disc1/fNNNNN.bin`, CRI `CPK` | no, second layer | the naming, and only that |
| Star Ocean 5, PS3 2016 | not reachable | `SLZ`, ASF/AAF/ACF/AIF magics, `AHSL` | no, envelope changed | `SLZ` walking exactly |
| Star Ocean: Anamnesis, Android 2016 | **46 507 mangled `Aska`** | `aska0000.bin`, `AHSL`, reversed AIF | one texture header | the namespace, overwhelmingly |
| *Eternal Sonata*, X360 2007 — tri-Crescendo | no, and no RTTI | **the method-1 codec, one nibble apart; the method byte; the magic style** | `slz.py`, method 1 | 8 of 8 files decoding exactly |

Three threads run the whole length of it:

* **`SLZ`** is in every title from **1998** to 2016 that this repository could
  look inside, in three header revisions that differ by one inserted word and
  one moved constant — and the first of those three revisions covers five discs
  and eight years without a field moving. Its method-1 codec is readable and
  identical across all of them. See
  [§11](#11-the-five-playstation-discs-1998-to-2006).
  **`SLE`, which always travels beside it from 2003 on, is not there in 1998 or
  1999**, so the pair has two birthdays. And the codec **outlived the studio**:
  tri-Crescendo's 2007 Xbox 360 title uses it with one nibble swapped
  ([§13](#13-eternal-sonata--what-an-offshoot-studio-took-with-it)).
* **`AHSL`**, the shader toolchain, is in both Xbox 360 executables, in 30
  shipped files on the PlayStation 3 and 147 times in the Android library.
* **The art naming** — `cNNN_NN_partM`, `pCol` primitives, Maya light names —
  is recognisable in every title including the one that shares no format at
  all. On the PlayStation 2 it is a *different* tool's naming: `Bip01 Pelvis`
  and its relatives are 3ds Max Character Studio, so the studio moved from 3ds
  Max to Maya between 2006 and 2008.

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

`aska.py identify` over each whole image, one tool, one run, in title order.
Where a signature has a structural test, the second number is the **sound**
count, and it is the only one worth reading: a bare four-byte magic turns up by
chance about once per four gigabytes, and every image here is bigger than that.

| Signature | SO2 1998 | VP1 1999 | Star Ocean 3 2003 | Radiata 2005 | Valkyrie Profile 2 2006 | Infinite Undiscovery 2008 | Star Ocean 4 2009 | Resonance of Fate 2010 | Star Ocean 5 2016 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MRON container | — | — | — | — | — | **6 873** / 6 261 | — | — | — |
| SNC scene script | — | — | — | — | — | 7 | — | — | — |
| AREA | — | — | — | — | — | 94 | — | — | — |
| MINI | — | — | — | — | — | 44 | — | — | — |
| SIG- signal | — | — | — | — | — | 2 909 | — | — | — |
| ASF scene | — | — | 1 / 0 | — | — | 1 454 / **1 450** | 2 / 1 | 1 / 0 | 1 887 / **1 886** |
| AAF animation | — | 8 | 1 | 8 | 12 | **6 763** | 305 | 2 | **5 553** |
| ACF collision | — | — | 1 | — | — | **1 314** | 769 | 2 | 683 |
| AIF image | — | — | 1 / 1 | — | — | 3 321 / **3 320** | 85 / 84 | 3 / 0 | 3 947 / **3 740** |
| AAC audio | 1 / 0 | 1 / 0 | 3 / 0 | — | 3 / 0 | 9 080 / **708** | 11 681 / **6 379** | 185 / **182** | 22 / 0 |
| SLZ wrapper | 15 708 / **10 377** | 13 775 / **12 395** | 55 653 / **53 201** | 26 275 / **26 254** | 25 531 / **25 431** | 8 104 / **8 082** | 26 531 / **26 498** | 21 / 0 | 19 583 / **10 155** |
| AI node field | 1 / 0 | — | — | — | — | 33 / **33** | 1 / 0 | 1 / 0 | 5 / 0 |
| `R:M:` node prefix | — | — | — | 100 † | 37 † | **877 637** | 1 | 1 | 1 |
| pCol primitives | — | — | — | — | — | **10 357** | **747** | — | **163** |
| `Tri_ace` node | — | — | — | — | — | 1 | — | — | — |
| AHSL | — | — | — | 1 † | 7 † | — | — | 4 | 30 |

Dashes are counts at or below chance. Star Ocean 5's column is its decrypted
package run, 11.2 GiB, not a disc image. Beyond the Labyrinth, Star Ocean: Blue
Sphere and Star Ocean: Anamnesis are not in the table: the first two score
nothing anywhere ([§9](#9-beyond-the-labyrinth--the-first-specimen-that-says-no),
[§12](#12-star-ocean-blue-sphere--the-second-specimen-that-says-no)) and the
third is 58 MB of APK whose evidence is in its library
([§8](#8-star-ocean-anamnesis-and-what-it-cost-the-tool)).

**The two PlayStation columns say the whole thing in one line each**: tens of
thousands of sound `SLZ` blocks and not a single other signature above chance,
on discs whose decompressed contents turn out to hold no tri-Ace format at all.

**Star Ocean 3's column is the most extreme in the table**: 53 201 sound `SLZ`
blocks, more than Radiata Stories and Valkyrie Profile 2 put together, and
nothing else above chance anywhere on 4.34 GiB. That is what a disc looks like
when the wrapper is the only thing the sweep can see through — and it is why
reading one of the codecs mattered more than adding another row.

**† Checked, and false.** Two rows looked tempting on the 2005 and 2006 discs
and are not real. Every one of Radiata's 100 `R:M:` hits sits inside the same
self-similar run — `R:M:RAM:m:Y:S:YIS:YIYL|IhIyLh` — and Valkyrie Profile 2's
37 sit inside `R:M:R:M@R3F@W-D3-`; neither is a node name. Their `AHSL` hits
are the same kind of thing, one of them inside `AHSLHLSS4LSH5HSH9*5A**/9`.
Neither PlayStation 2 title leaves a Maya name or a toolchain name on its disc.

Read across the row for `SLZ` and the story of the whole table is there. Read
down the columns and every title is a different situation.

**Infinite Undiscovery** is the baseline: the container announces itself 6 873
times and everything else follows from its entry tables.

**Star Ocean 4 kept the payloads and threw away the container** — not one
`MRON`, `AERA`, `INIM`, `-GIS` or `-CNS` tag on the whole disc, and 26 498
sound `SLZ` blocks instead, with runs of `ACF`, `AAF` and `AAC` in the open.
The 747 `pCol` hits track the 769 `ACF` ones, which is what an uncompressed
collision file looks like. The clearest single number is `R:M:`: Infinite
Undiscovery leaves 877 637 node names in the clear and Star Ocean 4 leaves one.
The models are still there — [§6](#6-the-readers-against-star-ocean-4) opens
them — they are simply all behind `SLZ` now. What indexes them is `PACK`.

**Resonance of Fate** is the quietest disc and not a silent one. Every
signature with a test scores zero sound except one: **182 sound `AAC `
containers**, on a disc where chance would produce about two. That row was read
as noise until it was checked, and checking it is what the `AAC ` validator
exists for now. Its scenes, models and animations remain invisible.

**Star Ocean 5** carries the payload magics in quantity and big-endian, and
they do not open — see [§2](#2-what-each-specimen-gave-up).

**The five PlayStation discs** show `SLZ` and nothing else *to a sweep*. What
is inside those blocks is another matter since session 14 read method 1 —
assets with names on the PlayStation 2, overlay code and Sony `TIM` on the
PlayStation. [§11](#11-the-five-playstation-discs-1998-to-2006) has them.

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
worth closing or correcting. A third was found later, in session 16, and it was
a bug rather than a gap: **the verdict rule counted untested signatures at
their raw hit count**, so one chance match on a seven-gigabyte image was enough
to print "probably ASKA". It now compares them against what chance produces —
see [§13](#13-eternal-sonata--what-an-offshoot-studio-took-with-it).

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
magics included. Until session 16 the tool's own verdict line disagreed with
that sentence, for the reason given in
[§13](#13-eternal-sonata--what-an-offshoot-studio-took-with-it); the numbers
were always right and the summary was not. Under the `P@CK` entries are blocks tagged `mpak`, which are
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

## 10. Phantasy Star Nova — the naming convention, and a locked door

PlayStation Vita, 2014, Japan only. SEGA published it and tri-Ace built it,
which makes it the only specimen here that is not a tri-Ace title in name.

It ships as a Vita package, and [formats/pkg.md](formats/pkg.md#4a-the-vita-variant)
covers how that opens: the same container as Star Ocean 5's, a key derived by
encrypting the package's own RIV, chosen by trying each candidate until the
item table holds together. Every check passes and all 85 filenames read.

The listing is the evidence:

```
disc1/f00000.bin                  81 920
disc1/f00001.bin                 862 208
disc1/f00002.bin                  32 768
NOVA_FileList_Vita.cpk         2.83 GB
NOVA_FileList_Vita_movie.cpk    395 MB
```

**`disc1/fNNNNN.bin`** is the same convention as Star Ocean: Anamnesis's
`assets/disc1/f00000.bin` on Android and Beyond the Labyrinth's `f0000.bin` on
the 3DS — the directory is even called `disc1` on a console that has no discs.
And the bulk sits in CRI `CPK` archives, as it does on Star Ocean 5.

**Nothing inside can be read**, and the reason is worth stating precisely
because it is not the usual one. A Vita title has a second encryption layer,
PFS, under the package layer; its key is sealed by the licence, and the package
carries the layer's own metadata in `sce_pfs/files.db` and `sce_pfs/unicv.db`.
The test that separates "wrong key" from "second layer" is a file whose first
four bytes are known in advance: `sce_sys/pic0.png` does not come out as a PNG
under any candidate key, while the same key that fails on it reads all 85
filenames correctly. Getting past that means obtaining the title's licence key,
which is not reading a format, and this repository stops there.

So Nova is recorded as: **same file-naming convention, same middleware, payloads
not inspectable.**

## 11. The five PlayStation discs, 1998 to 2006

Five titles on two little-endian MIPS consoles, spanning eight years in front
of Infinite Undiscovery:

| | Build | |
| --- | --- | --- |
| *Star Ocean: The Second Story* | `SCUS_944.21`, USA disc 1 | PlayStation, 1998 |
| *Valkyrie Profile* | `SLUS_011.56`, USA disc 1 | PlayStation, 1999 |
| *Star Ocean: Till the End of Time* | `SLES_820.28`, PAL disc 1 | PlayStation 2, 2003 |
| *Radiata Stories* | `SLUS_212.62`, USA | PlayStation 2, 2005 |
| *Valkyrie Profile 2: Silmeria* | `SLES_546.47`, PAL | PlayStation 2, 2006 |

They are the specimens that explain a field the later ones made unreadable,
they are the only ones outside the Xbox 360 whose compressed data this
repository can open, and — the oldest two — they are what dates the parts of
the engine relative to each other.

**The disc layout is one idea, twice.** The PlayStation discs are an ISO 9660
filesystem holding three entries, of which one is everything: an executable,
`SYSTEM.CNF`, and a single `.BIN` of 0.48 or 0.64 GB. The PlayStation 2 discs
are an ISO 9660 filesystem holding three files — the executable, Sony's
`IOPRP*.IMG` and `SYSTEM.CNF` — with four gigabytes in raw sectors *outside*
the filesystem, addressed by LBA. The blob moved out of the filesystem; it did
not otherwise change.

### `SLZ` is theirs from the beginning

| | SO2 1998 | VP1 1999 | Star Ocean 3 | Radiata | Valkyrie Profile 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `SLZ` magics | 15 708 | 13 775 | 1 641 † | 26 275 | 25 531 |
| of those, sound | **10 377** | **12 395** | **1 566** † | **26 254** | **25 431** |
| consecutive blocks landing on the next | 261 / 957 | 410 / 698 | **695 / 727** | — | — |
| everything else | chance | chance | chance | chance | chance |

† Star Ocean 3's figures are a 128 MiB sample; over the whole image it is
55 653 magics and **53 201** sound, the largest count in this document.

The name is in the executables too. Star Ocean 2 puts `SLZ\0`, padded into an
eight-byte slot, at `0x1B060` and `0x1B30C`, each followed by a table of
`0x8001xxxx` function pointers; Valkyrie Profile puts it at `0x1B0D0` and
`0x1B37C`, within `0x70` bytes of the same places, with the same table behind
it — the same library object linked into two games a year apart. From Star
Ocean 3 on it is `SLZ` **and `SLE`** as adjacent eight-byte-aligned constants,
twice per binary, at `0x4DD40` and `0x4DE30`; the three Xbox 360 titles carry
the same pair four-byte-aligned and the other way round, `SLE` then `SLZ`.

**Eight titles, three CPUs, 1998 to 2010.**

### `SLE` is younger than `SLZ`

It is not in either PlayStation executable, and not on either PlayStation disc:
zero occurrences of `SLE\0` across the whole of Star Ocean 2's image, and two
across Valkyrie Profile's — both unaligned, both inside byte-identical copies
of one blob of nibble-packed data. Checked, and false.

So the pair that reads as a unit in every executable from 2003 to 2010 has two
birthdays. `SLZ` is 1998 or earlier; `SLE` arrives between 1999 and 2003, and
the tri-Ace PlayStation 2 titles in that gap are where to look.

### And it explains Infinite Undiscovery's fourth byte

The PlayStation header is shorter than the one [slz.md](formats/slz.md)
describes — and it is the *same* header on all five discs, byte for byte, from
1998 to 2006. Reading it settles a question that a single specimen could not:

| | |
| --- | --- |
| `+0x00` | `SLZ` |
| `+0x03` | **method** — 0 stored, 1–3 compressed |
| `+0x04` | compressed size, little-endian |
| `+0x08` | uncompressed size |
| `+0x0C` | zero |
| `+0x10` | payload |

Measured over 661 blocks taken from three widely separated regions of Radiata's
disc:

| | |
| --- | --- |
| zero word at `+0x0C` | **661 of 661** |
| compressed ≤ uncompressed | **661 of 661** |
| method 0 with the two sizes equal | **68 of 68** |

Between 2006 and 2008 **one word was inserted at `+0x04`**: the size pair moves
to `+0x08` and `+0x0C`, the zero moves with it, and everything else stays where
it was. That is the whole difference.

And the byte at `+0x03` is a **method from the beginning**. Infinite
Undiscovery writes a constant 4 there and it reads like a version number; Star
Ocean 5 was the first specimen to show it selecting a codec, and Star Ocean 4's
stored blocks agreed. The 2005 disc settles it: 68 blocks that say 0 have their
two sizes equal and their payload in the clear, one of them opening with
`SEQW`. Infinite Undiscovery is the exception, not the rule.

The five titles do not use the methods the same way, and the shape of that
table is a finding in itself:

| Method | SO2 1998 | VP1 1999 | Star Ocean 3 | Radiata | Valkyrie Profile 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0, stored | 1 | 4 | — | 14 | 2 |
| 1, LZ77 | 242 | 722 | 152 | **none, anywhere** | 153 |
| 2 | 2 303 | 1 627 | 482 | 2 | 390 |
| 3 | **none** | **none** | 1 505 | 827 | 333 |

**Method 3 does not exist on the PlayStation** and is the default on all three
PlayStation 2 discs, so the codec set grew between 1999 and 2003. **Method 2 is
on every disc from 1998 on** and has never decoded.

### Method 1 is tri-Ace's own LZ77, and it opens

Session 14 read it off the 2003 disc. The specification and the three
independent measurements that fix its three fields are in
[slz.md §2b](formats/slz.md#2b-the-playstation-codec-method-1); the short
version is byte-wide flags read from bit 0 up, literals on 1, and a two-byte
back-reference carrying a 12-bit distance and a 4-bit length biased by 3.

Applied unmodified to the other four discs:

| | SO2 1998 | VP1 1999 | Star Ocean 3 2003 | Valkyrie Profile 2 2006 |
| --- | ---: | ---: | ---: | ---: |
| method 1 blocks sampled | 283 | 1 174 | 152 | 153 |
| decode to exactly the stated size | **283** | **1 174** | **152** | **153** |
| failures | 0 | 0 | 0 | 0 |

**1 762 blocks over eight years and two consoles, and none fails.** Not a field
of the specification changed between 1998 and 2006.

### So the PlayStation 2 discs are not silent after all

What comes out of them is a vocabulary, and it is not Infinite Undiscovery's —
the census is in
[slz.md §2c](formats/slz.md#2c-what-the-playstation-2-titles-call-their-assets--and-what-the-playstation-ones-do-not).
`FAS\0`, `RTA\0` and `FPS\0` are the three commonest payloads on all three
discs. Three of the rarer ones reach back into open questions about the Xbox
360 game: **`DTT\0`**, which is byte for byte the payload of Infinite
Undiscovery's unread `TTD-` resource, shipped *stored* on the 2006 disc;
**`LCTP`**, which is `PTCL` backwards and is one of the ASF chunks nobody has
opened; and **`DMM\0`**, which is `MMD` backwards and is one of Star Ocean 4's
three unread magics.

One row corrects §6 of this document. **`PACK` is not new in 2009.** It is the
leading literal of roughly 190 of the 1 987 blocks sampled on the 2003 disc
that do not yet decode. Whether the header is the same as Star Ocean 4's cannot be
checked until methods 2 and 3 open, so what is established is the tag and not
the container.

### And the PlayStation discs have no vocabulary at all

That is the other half of it, and it is what dates the engine's own formats.
Decompress the 1998 and 1999 blocks and none of those tags is there — not as a
payload head, not as a leading literal of an unopened block, not anywhere
inside the decoded data. What is there instead:

* **MIPS overlay code.** The commonest payload head on both discs is
  `27 bd ff e8` and its relatives — `addiu $sp, $sp, -0x18`, a function
  prologue. tri-Ace compressed its own executable overlays with `SLZ`.
* **Sony `TIM` textures**, 29 of 29 sampled on Valkyrie Profile with a
  self-consistent id word, flag word, CLUT block and image block. The console's
  standard image format, not the studio's.
* **Offset-table archives** — a run of `u32` offsets whose first entry is the
  size of the table itself. That is the same self-check `PACK` passes eleven
  years later.
* Unlabelled binary with no magic at all.

Seven `DTT\0` sequences across the two discs were checked and are false: all
unaligned, all inside nibble-packed image data, three of them inside
byte-identical copies of one blob.

So **the wrapper is older than anything it wraps.** `SLZ` is 1998; the `S?F`
family on the PlayStation 2 and the `A?F` family on the Xbox 360 are both
younger than it, and the studio's own file formats appear somewhere between
1999 and 2003.

### The pipeline was 3ds Max, not Maya

The decoded payloads name their bones, and the names are not the ones the later
discs use:

```
Bip01           Bip01 Pelvis     Bip01 Spine1     Bip01 L Clavicle
Bip01 Neck      Bip01 L Thigh    Bip01 R Finger3  Bip01 Footsteps
DummyBox01      MOVEBOX          CTRL01           RHAND
```

`Bip01` and its children are **3ds Max Character Studio's** biped, exactly as
that tool names them, on both the 2003 and the 2006 disc. Infinite Undiscovery
and Star Ocean 4 leave Maya's naming instead — the `R:M:` prefix, `pCol`
primitives, `AAmbientLight1`. So the row "the art naming is recognisable in
every title" holds, and it hides a change of tool: **tri-Ace moved from 3ds Max
to Maya between Valkyrie Profile 2 and Infinite Undiscovery.**

### What is still not there

No Maya node names, no `Tri_ace`, no `AHSL`, no versioned magic — 56 candidates
for the `XXXXnn.n` pattern in 128 MiB of Star Ocean 3's data, every one of them
a digit run inside compressed data. And methods 2 and 3, which are 1 987 of the
2 139 blocks sampled on that disc, remain closed.

So the lineage the evidence supports is: **the compression wrapper is the
oldest thing in the engine, and older than the engine** — older than the
container, older than the payload formats, older than the name ASKA is attached
to here, and datable to **1998**. Everything else in this document is younger
than it, and on the two oldest discs there is demonstrably nothing else of
tri-Ace's for it to be older *than*: it wraps the console maker's texture
format and the game's own compiled overlays.

## 12. Star Ocean: Blue Sphere — the second specimen that says no

Game Boy Color, 2001, Japan only. tri-Ace developed it and Enix published it,
which makes it the earliest title anyone attributes to the studio's console
lineage and, at 4 MiB on an 8-bit handheld, the least likely specimen here.

**It scores nothing.** `aska.py identify` over the whole ROM returns not one
hit of any signature, in either byte order — the only specimen that manages a
completely empty table, Beyond the Labyrinth included. The targeted checks
agree: no `SLZ`, no `SLE`, no `Aska`, no `AHSL`, no `R:M:`, no `pCol`, no
`Tri_ace`, and zero matches for the general versioned-magic pattern. There is
not one readable string in the image; all 19 350 runs of six or more printable
bytes are tile data.

The cartridge header is the whole of what the ROM says about itself: title
`STAROCEANGBBO2J`, licensee `B4` (Enix), MBC5 with 32 KB of battery-backed RAM,
Super Game Boy support, Japan, version 1.0.

Unlike Beyond the Labyrinth — which shares no format but is unmistakably
tri-Ace in its art naming and its container family — Blue Sphere shares nothing
at any level. That is the expected answer for a 2001 handheld title and it is
recorded so that the ladder has a specimen at the bottom of it: **a real no
looks like an empty table, and an empty table is what one looks like.**

The one deliberate convention the ROM does show is that every non-empty bank
begins with its own bank number — 242 of 255, the thirteen exceptions being
entirely zero-filled. That is common Game Boy practice rather than a tri-Ace
habit, and it is offered as an observation and not as evidence.

## 13. Eternal Sonata — what an offshoot studio took with it

Every other specimen here is a tri-Ace title and the question is always the
same one. This one is not, and the question is different.

*Eternal Sonata* (Xbox 360, 2007) was made by **tri-Crescendo**, founded by
people who left tri-Ace and best known there as its sound team, and developed
in-house with no co-developer. It sits between Infinite Undiscovery and Star
Ocean 4 in time, on the same console, at the same scale. So the useful question
is not "is this ASKA" — it plainly is not — but **which layer the people
carried with them**, given that sessions 14 and 15 dated the layers separately:
the compression to 1998, the payload formats to somewhere between 1999 and
2003, the container later still.

**The answer is the oldest layer, and only that.**

### What is not there

`xex.py` reads the executable with no changes — the compression is `basic`, as
Infinite Undiscovery's is rather than Star Ocean 4's — and the decrypted image
contains none of it:

| Searched for | Hits |
| --- | ---: |
| `Aska`, `ASKA`, `aska`, `AHSL` | 0 |
| `SLZ` | 0 |
| `R:M:`, `pCol`, `Tri_ace` | 0 |
| `ASF `, `AIF `, `AAF `, `ACF `, `AAC `, `MRON`, `PACK` | 0 |
| `.?AV` — MSVC RTTI | 0 |
| `tri-Crescendo` | **5** |

The single `SLE` hit is `SLEP`, in a table of four-character task names beside
`TextMgr Task` and `ACTV`. Checked, and false.

The disc is different in shape too. Infinite Undiscovery ships two monolithic
containers; Star Ocean 4 ships the same idea with `PACK` inside it; Eternal
Sonata ships **an ordinary directory tree of 1 108 named files** — `.bop`,
`.bmd`, `.x3tex`, `.csf`, `.cxs`, `.e` — with no container anywhere. And its
executable links **libpng, zlib and libjpeg**, which tri-Ace's does not: this
is a studio that used the libraries everybody uses.

### The sweep, and the tool bug it exposed

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
is what [§9](#9-beyond-the-labyrinth--the-first-specimen-that-says-no) and this
section have been claiming in prose all along. All nine positive titles stay
positive.

### What is there

**The codec.** Every shipped file is compressed, and the eight files the index
marks method 1 decode with tri-Ace's method 1 — after swapping the two nibbles
of the second byte of a back-reference, and changing nothing else. Same flag
byte, same bit direction, same polarity, same two-byte reference, same 12/4
split, same bias of three, same 4 095-byte window.
[slz.md §2d](formats/slz.md#2d-the-tri-crescendo-variant) has the full
comparison and the 768-candidate search that found it. **8 of 8 files land on
exactly the size the index states and consume the input to its last byte.**

**The method byte.** `index.vmtoc` is 1 105 records of 48 bytes — a path, an
uncompressed size, a Unix timestamp, and a **method** taking 0, 1, 2 or 3,
where 0 means stored on **136 of 136** files. That is `SLZ`'s byte at `+0x03`,
same range and same meaning, moved out of a block header into a per-file table.

**The magic style, and the chunk convention behind it.** The 136 stored files
show their headers with nothing in the way: `CSF ` 60 times, `CXS ` 62, `RIFF`
14, plus `BMD ` out of the one method-1 file that carries one. **All 60 `CSF `
state their own file length at `+0x04`**, counted from byte zero rather than
from the header's end, and all 60 carry `BOOK` at `+0x10` and `SONG` at
`+0x20` — a four-character tag followed by its own size, which is the shape of
`ASF `'s chunk tree with different tags. `aska.py`'s own length validator would
accept every one of them.

Even the standard format is written to the house convention rather than the
standard's: the fourteen `RIFF` files put their size **big-endian** and set it
to the whole file length instead of `length − 8`, and their `fmt ` fields are
big-endian too.

**And the same wall.** Methods 2 and 3 do not open, exactly as tri-Ace's do
not, and here the negative can be proved: a method-3 file whose stored siblings
are all `CSF ` must decompress to a `C`, and its first byte on disc has bit 0
clear, which under this framing puts a back-reference at output position zero.
Two studios, five years apart, with a second and third compressor that resist
the same search.

### The reading, and what would overturn it

Three layers, three answers:

| Layer | Born | In Eternal Sonata? |
| --- | --- | --- |
| the compression algorithm and its method byte | 1998 | **yes**, one nibble apart |
| the four-character space-padded magic convention | by 2003 | **yes**, different letters |
| the payload formats — `S?F`, `A?F` | 1999–2003 | no |
| the container — `MRON`, `PACK` | 2005–2009 | no; there is no container |
| the engine namespace and shader toolchain | — | no |

The ordinary explanation fits: **people carried the oldest and most portable
piece of code they had, and the habits that go with it, and built everything
above it new.** A compression routine travels in a head or a personal library;
a renderer does not. That the difference is a *swap* rather than a copy is
itself informative — it reads like a reimplementation from memory or from a
description rather than a lifted file.

What would overturn it: a third studio, unconnected to either, shipping the
same byte-flag LZ77 with a 12/4 split and a bias of three. That scheme is not
exotic and this document should not pretend otherwise. What is hard to explain
away is the **method byte sitting beside it** — 0 to 3 with 0 meaning stored —
because that is a design decision rather than a common implementation, and it
is in both.
