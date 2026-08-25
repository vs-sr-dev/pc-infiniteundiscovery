# Open questions

What is not yet known, roughly in order of how much it would unlock. Each
session's log carries its own "Left open" list; this file is the consolidated
view, kept current at the end of every session.

Solved work lives in [docs/formats/](docs/formats/) and is not repeated here.
The numbered questions are all about this one disc; the section at the end,
[Beyond this game](#beyond-this-game--is-aska-in-other-titles), is not.

**Start here next time: question 1.** After session 12 a scene is readable as
*structure* from every side — geometry, materials, textures, skeleton,
animation, collision, the script that drives it and the navigation mesh the AI
walks on — and every skinned object indexes its own file's node tree, so there
is no shared skeleton to find. What is thin is *meaning*: 246 of the 253
scene-script opcodes are known only by number.

Session 13 answered the second front — the engine **is** in tri-Ace's other
titles, and [docs/aska-across-titles.md](docs/aska-across-titles.md) is the
result. It also closed off one route to question 1 that looked promising:
Star Ocean 4's scene scripts parse with the same reader, but its opcode
*numbering* is a different table, so a second title cannot name Infinite
Undiscovery's opcodes.

Session 14 added two more titles and, unplanned, **read one of the PlayStation
2 compression codecs**, which turned three discs from a census into a reading.
That moved questions 22 and 24 and gave questions 3, 12 and 25 an older
specimen each.

Session 15 took the same codec back to tri-Ace's first two 32-bit games and it
worked unchanged: **`SLZ` is from 1998, not 2003**, and on those two discs it
wraps MIPS overlays and Sony `TIM` textures rather than any format of the
studio's own. So the wrapper is older than everything it later carries. It also
found that **`SLE` is not there in 1998 or 1999**, which is question 28.

Session 16 asked the last question of a different kind: **Eternal Sonata**, by
tri-Crescendo — the studio founded by people who left tri-Ace — on the same
console and in the same years as this game. It carries no engine, no container
and no payload format, and it appeared to carry **the codec, one swapped
nibble apart, and the method byte beside it** — so, it concluded, the oldest
layer travelled with the people and nothing above it did. *Session 18 read
that codec properly and the conclusion did not survive; see below.*

It also found a bug in `aska.py`: the verdict rule counted signatures with no
structural test at their raw hit count, so one chance match on a seven-gigabyte
image printed "probably ASKA". It now compares them against chance. Two printed
verdicts changed and no measurement did.

Session 17 took the TODO's own advice on question 22 — stop searching, read the
decompressor — and it worked the first time. **Methods 2 and 3 are both read**,
off the dispatchers in Star Ocean 2's and Star Ocean 3's executables, and there
was never more than one codec: methods 1, 2 and 3 are one LZ77 with three
settings. 62 167 blocks of 62 167 decode across all five discs. It also
explained **`SLE`**, which had been a string beside `SLZ` since 2003 and
nothing else: it is an encryption envelope that rewrites its own magic to `SLZ`
and falls through to the method switch.

And it corrected a claim this file was carrying. "Method 2 is not byte-flag
framed at all, which is proved rather than inferred" — it is byte-flag framed,
and always was. The measurement behind that claim was sound; it was taken on
Eternal Sonata and Star Ocean 5 data and applied to a codec on different
hardware. **Negative results do not travel between titles the way positive ones
do**, which is session 13's asymmetry note pointing the other way.

Session 18 did the same to Eternal Sonata, and the answer reframed the title's
whole entry in this repository. Its method byte is **not a codec selector**:
the loader tests two bits of it separately, bit 0 for an LZSS layer and bit 1
for a range coder, so method 3 is method 1 running on top of method 2. Both
layers are famous public routines — **Okumura's `lzss.c`** and **Subbotin's
carryless range coder**, the second over a static order-0 model shipped as the
first 256 bytes of each file. [docs/formats/vmtoc.md](docs/formats/vmtoc.md)
specifies all of it.

That corrected session 16 twice. Its method-1 decode was **wrong in its match
target** — the 12-bit field is an absolute ring position, not a back-distance —
and its tests could not have caught it: output size and input consumption are
blind to where a match copies from, and its two content checks both sit in the
literal prefix, before the byte at which the two readings first disagree. And
with the codec turning out to be stock, session 16's headline that "the oldest
layer travelled with the people" no longer stands. What travelled is
**convention** — a method code of 0..3 with 0 meaning stored, and the magic
style — not code.

Two corrections in two sessions, in opposite directions, from the same cause:
**a test that counts bytes cannot check where bytes came from.** Sizes and
input consumption pin framing and length; only content pins the match target.
Every distance field in this repository that was fixed by a size test alone
should be re-checked against content.

The best remaining lead is now the last open piece of **question 22**: Star
Ocean 5's PlayStation 3 codecs, the only unread compression left in this
repository. Same numbering, same stored method 0, and neither studio's codecs
decode it. Opening them would also unblock **question 21**, its payload
envelope.

## Now the main line of work

**1. What the SNC opcodes do.** This has to be answered inside this game:
session 13 measured Star Ocean 4's scripts, which use the identical container
version `-CNS00.3` and the identical instruction encoding, and found that of
the 77 opcode numbers common to both titles only 15 keep an operand signature
this game also writes. The number is an index into a per-title function table.

The scene script parses completely and seven of its 253 opcodes are
identified. The rest are known by number, arity and operand kinds. Two footholds: the 19 opcodes whose signature ends `@@nn`
demonstrably share a trailing structure — 88 690 instructions of 420 532 — and
`0133`, which puts two quaternions in front of that tail, is a rotation tween.
Related, and smaller: the header word at `+0x08`, which matches no count in the
file; the reference spaces `e`, `c`, `k`, `s`, `i`, `u`, `v`, `r`, `g`; what
`m` is; and the five-digit identifier that ends the spawn commands.

**2. The block after a `tree`'s `attr` chunks**, in 86 model files of 369,
from 144 bytes to 3 600. Most begin with four homogeneous points that read as
two centre-and-extent pairs; the big character skeletons begin instead with
32-byte records naming bone chains — `R:M:SK_A_LtHipFt` and its neighbours —
with floats that read as damping and stiffness, and `R:M:pColCube` names
beside them. Hair and skirt simulation is the obvious reading and `Aska::Dynamics`
is in the binary to run it, but nothing is decoded yet.

**3. The ASF chunks nobody has opened:** `ptcl`/`pprn`/`pani` (particles), and
`modf`, `extl`, `PAIF`, `AAIF`, `ACHF`, `glbl`, `mdfr`, `anim`. Session 14
found `ptcl` outside a scene: on all three PlayStation 2 discs it is a payload
in its own right, written `LCTP`, and on two of them it sits behind a codec
that now decodes.

**4. The material leftovers**, small and self-contained after session 8: the
two fields in a texture reference at `+0x08` and `+0x0C`, neither of which
separates a colour map from a normal map; the shader program block between a
material's header and its binding table; the 48-byte records counted at
`mats +0x19`, which look like a UV transform; and the four-byte entries in an
`rnel`, presumably how the shading nodes connect.

**5. The AAF leftovers**, small and self-contained after session 9: the word
at `+0x20` which is larger than the file; the three floats at `+0x14` of an
animated track, which look like a time window; the units of time; the channel
numbers other than 5, 6 and 7 — 14, 16, 18, 22, 45 and more, on lights,
emitters and cameras — and the semantic byte at track `+0x12`; and the `0x0200`
that some tracks put in the high half of their size word.

**6. The ACF leftovers**, smaller still: the `u16` at primitive `+0x28`, which
is a permutation of `0 .. n-1` in 460 files and something else in 512; which
bit of the 16-bit collision mask means what; and `+0x2C`, which is exactly the
root sphere seen from the origin on 463 of 972 files and at least that on 779.

**7. The 59 ASF objects in 3 855 whose geometry misses their stated bounding
box** by more than 10 %. They are mostly treasure chests and morph targets —
things whose geometry moves — which suggests the box describes a pose the
stored vertices are not in.

## Smaller and self-contained

8. **Where the other 35 % of animation record names live.** Session 12 took
   the AAF-against-ASF name match from 52.4 % to 65.0 %; what is left is
   cameras, lights and effect emitters named in animations that no extracted
   mesh contains.

9. **The NODE leftovers**, small and self-contained after session 11: the low
   byte of a node's own reference, which is not the partition index, the link
   count, the vertex count or the number of cross-partition links; the values
   in a gate group's slot list; the trailing table at header `+0x28`; and the
   802 nodes whose polygon has only two vertices.

10. **AIF mip chains.** The base level decodes. The Xbox 360 packs the small mip
    levels into a shared tile, and working that out would complete the texture
    format.

11. **The AIF flags at `0x34`** (`0x500`, `0x200`, `0x40400`, zero).

12. **`TTD-`**, whose payload begins `DTT\0`. It is the last resource tag
    on the disc with no reading at all — but no longer the only copy of it.
    Valkyrie Profile 2 ships a `DTT\0` payload **stored**, uncompressed, in
    2006, and session 14's `slz.py scan` finds it. An unread format with an
    older specimen in the clear is a much better position than an unread
    format with one.

13. **The 30 488 bytes at the start of each `ud1.bin`.** Session 7 identified
    the rest of that `0x16000` header as the compiled shader library, 70 of the
    160 shaders in the container. What is left is a table with a `0x100`-byte
    period, holding no pointers. Session 13 found its first `0x2800` bytes in
    **Star Ocean 4** as well and read the shape off the comparison: 40 rows of
    64 words, where the **top half of each word is the same in both games** on
    99.5 % of 2 560 words and the bottom half is per-title and per-disc. So it
    is a record of 64 (key, value) pairs and the keys belong to the engine, not
    to the game. What the keys select is open, as are the four columns whose
    top halves vary down the rows — identically in both games.

14. **The ASF/WMV video runs** in the container gaps — they need splitting into
    individual movies.

15. **`AOF`**, named three times in the engine's RTTI (`Aska::AofHandler`,
    `Aska::AofObject`, `Aska::DirectAofHandler`) but never seen as a payload
    magic on disc. One lead turned up while reading ASF: the chunk holding a
    single object is tagged `ao__`, and `Aska::AofObject` is what the engine
    calls an object. That is a resemblance between two names and nothing more,
    but it is the first place to look.

16. **Disc 2.** Its `SCE-` resources went through session 10's checks alongside
    disc 1's and behave identically, and its audio has the same banks as disc 1
    plus one track disc 1 lacks. The rest of its containers have been walked but
    not put through the same checks.

17. **The `AAC ` leftovers**, small and self-contained after session 5: the
    eight-byte field at `WAVE +0x08`, constant `0x995A7C80_00000015` in 2404
    sounds and zero elsewhere; what the sample count at `+0x24` counts exactly;
    and the `PLBK` playback record, whose shape is known but whose 23 values
    have never been checked against what the engine does with them.

18. **Five missing music tracks** — the numbers 35, 45, 46, 55 and 74 appear on
    neither disc. Cut, or somewhere not yet walked.

19. **The other 90 shaders**, which session 7 did not locate: 160 are counted
    in disc 1's `ud1.bin` and 70 sit in the header block, so the rest are
    presumably inside archives. Related: a shader blob's constant table has a
    structure, and parsing it rather than scanning for strings would give each
    shader its full signature.

20. **The ASF vertex leftovers**, small after session 6: the descriptor nibble
    in slot 3 that two meshes set, and the 24 meshes whose stride is rounded up
    rather than exact. The binormal-or-tangent question is now down to one
    measurement rather than open: with each mesh measured against its own
    material's texture, the plain reading gives a median texel anisotropy of
    1.89 against 5.03 rotated, over 251 914 triangles. Only an actual render
    would close it.

## Beyond this game — answered, and what it left open

**Twelve titles were tested and nine of them are the same engine**, with the
argument and every measurement in
[docs/aska-across-titles.md](docs/aska-across-titles.md). A thirteenth,
*Eternal Sonata*, is not a tri-Ace title at all and was measured to ask a
different question — see the row at the end of the table:

| | |
| --- | --- |
| SO: The Second Story, PS1 1998 | `SLZ` in the executable, 10 377 sound blocks, 283 of them decoded — and no tri-Ace format inside any of them |
| Valkyrie Profile, PS1 1999 | `SLZ` in the executable, 12 395 sound blocks, 1 174 decoded, Sony `TIM` inside |
| Star Ocean: Blue Sphere, GBC 2001 | **no** — not one hit of any signature, the only empty table so far |
| Star Ocean 3, PS2 2003 | `SLZ`/`SLE` in the executable, 1 566 sound blocks, and 152 of them decoded |
| Radiata Stories, PS2 2005 | 26 254 sound `SLZ` blocks |
| Valkyrie Profile 2, PS2 2006 | 25 431 sound `SLZ` blocks, 153 of them decoded |
| Star Ocean 4, X360 2009 | `Aska::` in the executable, and every reader here parses its payloads |
| Resonance of Fate, X360 2010 | `SLZ`/`SLE` and AIF headers in the executable, 182 sound `AAC ` containers on the disc |
| Star Ocean 5, PS3 2016 | `SLZ` blocks whose walk closes exactly, inside CRI `CPK` archives |
| Star Ocean: Anamnesis, Android 2016 | 46 507 mangled `Aska` symbols, and an asset called `aska0000.bin` |
| *Eternal Sonata*, X360 2007, **tri-Crescendo** | not the engine, and **not the codec either** — Okumura's LZSS over Subbotin's range coder. What is shared is the method byte and the magic style |
| Beyond the Labyrinth, 3DS 2012 | **no** — nothing above chance, Nintendo's asset formats, no engine name |
| Phantasy Star Nova, Vita 2014 | unanswerable — the naming convention matches, the payloads are behind a second encryption layer |

The single most durable thing found is **`SLZ`**: present from **1998** to
2016 across three CPUs, in three header revisions, the first of which covers
five discs and eight years without a field moving. The 2005 disc is what
identifies the byte at `+0x03` as a compression method rather than a version,
which one specimen alone could not settle; the 1998 disc is what dates the
wrapper, and one of its codecs decodes unchanged across all eight of those
years.

The 1998 disc also settles the **order of the parts**, which no later specimen
could: it carries the wrapper and nothing else of tri-Ace's, so the payload
formats, the container and the name are all younger than the compression.

The questions that came out of it, none of which is about this disc:

21. **Star Ocean 5's payload envelope.** 1 886 sound `ASF ` headers and 3 740
    sound `AIF ` ones, and not one opens: no `ao__` at `0x20`, no `imgX` at
    `0x10`. Something sits between the magic and the chunks, and 58 of 613
    sampled headers carry the tag `PS3 `.

22. **The codecs behind `SLZ`.** *Answered for tri-Ace.* Session 17 stopped
    searching and read the two dispatchers — `SCUS_944.21` at `0x800121A8`,
    `SLES_820.28` at `0x00102540` — and there turned out to be **one codec with
    three settings**, not three codecs:

    * **Method 1**, tri-Ace's LZ77 —
      [slz.md §2b](docs/formats/slz.md#2b-the-playstation-codec-method-1).
    * **Method 2**, the same LZ77 with the top slot of the length nibble spent
      on a **run** instead of a match, and with the end token removed, so the
      stated output size is the stop condition —
      [§2b-2](docs/formats/slz.md#2b-2-method-2-the-same-lz77-with-runs-instead-of-the-longest-match).
    * **Method 3**, the same LZ77 with **every unit widened to a halfword** and
      the end token kept —
      [§2b-3](docs/formats/slz.md#2b-3-method-3-the-same-lz77-again-in-halfwords).

    **62 167 blocks of 62 167 across all five discs, 1998 to 2006, no
    failures.** Method 2's 36 598 also consume their input to the last byte,
    every one, which method 1 never did.

    What is left of this question is elsewhere, and is now three separate
    smaller ones:

    * **Eternal Sonata's methods 2 and 3** — *answered in session 18, by the
      same route*. Not tri-Ace's, and not even a third codec: its method byte
      is two flag bits over Okumura's LZSS and Subbotin's range coder —
      [docs/formats/vmtoc.md](docs/formats/vmtoc.md). What is left of that
      title is its payload formats, which is question 29.
    * **Star Ocean 5's PlayStation 3 methods** — same numbering, same stored
      method 0, and now measured rather than assumed to be different: methods
      1, 2 and 3 were each run against 400 of its blocks and decode none. A
      third disassembly, and the hardest of the three.
    * **What the PlayStation blocks hold**, which is question 30 and no longer
      blocked on anything.

    The **method byte's history** now reads cleanly end to end. One codec in
    1998 with two settings; a third setting, the halfword one, added for the
    PlayStation 2 by 2003 and immediately made the default; the numbering kept
    across the studio change in 2007 and across the move to XCompress on the
    Xbox 360, where the byte goes constant. What travelled was the numbering
    and the habit, not always the code.

23. **Resonance of Fate's container.** The executable proves the engine and its
    audio containers are on the disc, but its scenes, models and animations are
    invisible: every other signature scores zero sound and both containers are
    entropy 8.00 everywhere sampled.

24. **What the PlayStation 2 titles call their assets.** *Answered, and much
    wider than it was.* Session 14 read the vocabulary out of what method 1
    holds —
    [docs/formats/slz.md §2c](docs/formats/slz.md#2c-what-the-playstation-2-titles-call-their-assets--and-what-the-playstation-ones-do-not):
    `SAF`, `ATR`, `SPF`, `PTCL`, `MMD`, `CAMR`, `TTD`, and `PACK` as a tag six
    years before Star Ocean 4. But method 3 is the **default** on those discs,
    so most of each one was outside that answer. With methods 2 and 3 open, the
    whole disc is in it.

    Tags are `u32` little-endian, so they read backwards on disc. Behind
    method 3 specifically, and not seen before: `TGIL` = **`LIGT`** (164
    blocks on Star Ocean 3), `XBDC` = **`CDBX`** (44), `PCDC` = **`CDCP`**
    (26), and on Radiata Stories `Kods` (1 163), `RMF1` (549), `RBAD` (256),
    `RLF2` (255), with `SEQW` on 553 of its 557 **stored** blocks.

    **And the container walks.** These payloads use a 16-byte chunk header of
    tag, size, back-link and step, which tiles 300 of 300 files exactly and is
    `ASF `'s header with two differences — the size excludes the header rather
    than including it, and the word `ASF ` leaves zero at `+0x08` holds the
    previous sibling's step. An `SPF` holds `LIGT`, `MODI`, `PTCL` and a `CD**`
    collision family, which is a **scene**. See
    [docs/aska-across-titles.md §14](docs/aska-across-titles.md#14-the-chunk-container-is-five-years-older-than-aska).

    What is left is a **reader for the chunk contents**. `SAF` and `ATR` are
    still the two commonest payloads on all three discs, both carry a 3ds Max
    biped skeleton and a node name table, and `SAF` contains exactly one other
    chunk, `SAFH`. Nothing here has been put through `asf.py` yet, and that is
    now a cheap experiment rather than a blocked one.

25. **`EXD\0`, `mcd `, `MMD `** — three resource magics in Star Ocean 4's data
    with no reading here. `EXD\0` is the commonest payload in the sample. One
    of the three is older than it looked: `MMD` is on Star Ocean 3's 2003 disc,
    written `DMM\0`.

26. **The mobile class inventory.** `libSOA.so` carries 26 378 mangled `Aska`
    symbols resolving to 5 960 distinct two-level names — methods and members,
    not only classes, against the 1 740 class names session 1 recovered here.
    The `Aska::TAaf…Controller` family alone names the animation machinery
    [docs/formats/aaf.md](docs/formats/aaf.md) decoded from the outside.
    Reading it properly needs an Itanium demangler, which `tools/rtti.py` is
    not.

27. **Beyond the Labyrinth's `P@CK` and `mpak`.** One bit from Star Ocean 4's
    `PACK`, with the same header shape and different records, holding blocks
    that are not `SLZ`.

28. **Where `SLE` starts.** *What it is, answered.* The PlayStation 2
    dispatcher compares `SLE` two instructions after `SLZ` and gives it a
    branch of its own: it decrypts the payload in place with
    `plain[j] = (cipher[j] - 3*(j+1)) ^ key[j & 15]`, stores `0x5A` over the
    `E` at header `+0x02`, and falls through to the ordinary method switch.
    **`SLE` is an encryption envelope around the same four methods, and it
    rewrites its own magic once the payload is in the clear** —
    [slz.md §2b-4](docs/formats/slz.md#2b-4-what-sle-is).

    That reframes the rest of the question. `SLE` is in neither PlayStation
    executable and nowhere on either PlayStation disc, so the *option* arrives
    between 1999 and 2003 and the tri-Ace PlayStation 2 titles in that gap are
    still where to look. But **nothing on the 2003, 2005 or 2006 discs is
    inside it**: 742 raw `SLE` sequences across the three, 146 with a header
    that could be real, and not one that walks to a neighbouring block or
    decodes under any method. So a title that actually uses the envelope has
    not been found yet, and until one is, the 16-byte key cannot be recovered —
    it is a single `lq` from `0x001CC730`, past the end of the loaded image,
    and nothing in the executable writes it.

29. **Eternal Sonata's payload formats.** *Unblocked.* The compression is no
    longer in the way: all four methods read —
    [docs/formats/vmtoc.md](docs/formats/vmtoc.md) — so `.bop`, `.x3tex`,
    `.e`, `.tex` and the `.bmd` family are now ordinary unread formats rather
    than entropy. `tools/vmtoc.py extract` writes them out of the retail
    image.

    Four leads are visible from the first bytes alone, and none has a reader:

    * `BOP `, `BMD ` and `CAMP` all **state their own length at `+0x04`**, so
      each has a size field to walk from.
    * `.x3tex` decodes to `NTX2` with Microsoft's **`XPR2`** at `+0x08` — a
      documented Xbox 360 texture package, so that one is a wrapper around a
      known format rather than a new format.
    * the `.e` scripts open with a 16-byte header whose `+0x04` is a **Unix
      timestamp matching the index to the second** and whose `+0x0C` is the
      file's own length.
    * `CXS `, 62 files, is the one format whose `+0x04` is *not* a length: it
      holds `0x800` against an index size of 452 608 on `sound/cxs/mp118.cxs`.

    And the original sub-question stands, now answerable: **what the `BOOK`
    block inside `CSF ` is.** The word is what ADPCM coefficient tables are
    called on several consoles, 60 stored files carry it, and a decoded
    method-3 `CSF ` puts it at `+0x10` exactly where the stored ones do.

30. **The offset-table archive inside the PlayStation blocks.** A run of `u32`
    offsets whose first entry is the size of the table itself — the same
    self-check `PACK` passes eleven years later. It was seen and not measured.

Two notes for anyone extending this further. The **tests are asymmetric**: a
hit on a versioned magic or the engine namespace is conclusive, a miss proves
very little — Resonance of Fate is the worked example, and its `AAC ` row is
the worked example of the opposite mistake, a real finding dismissed as noise
because the tool had no test for it. And the **RTTI rung is closed** on every
console specimen: neither Xbox 360 title ships RTTI, and both PlayStation
executables are encrypted. What replaced it was plain strings — and, on
Android, 46 507 mangled symbols.

## Verified, needs no further work

* The engine in tri-Ace's other titles — [docs/aska-across-titles.md](docs/aska-across-titles.md)
* PlayStation 3 packages — [docs/formats/pkg.md](docs/formats/pkg.md)
* Disc layout and XDVDFS — [docs/formats/xdvdfs.md](docs/formats/xdvdfs.md)
* NORM/MRON containers — [docs/formats/norm-mron.md](docs/formats/norm-mron.md)
* XEX2 and the decrypted executable — [docs/formats/xex.md](docs/formats/xex.md)
* XDBF title metadata — [docs/formats/xdbf.md](docs/formats/xdbf.md)
* SLZ / XCompress — [docs/formats/slz.md](docs/formats/slz.md)
* AIF textures — [docs/formats/aif.md](docs/formats/aif.md)
* ASF scenes: container, geometry, materials and skinning — [docs/formats/asf.md](docs/formats/asf.md)
* AAF animation — [docs/formats/aaf.md](docs/formats/aaf.md)
* ACF collision — [docs/formats/acf.md](docs/formats/acf.md)
* SNC scene scripts: container and instruction encoding — [docs/formats/snc.md](docs/formats/snc.md)
* NODE, the AI node field — [docs/formats/node.md](docs/formats/node.md)
* AAC audio, and where the music lives — [docs/formats/aac.md](docs/formats/aac.md)
