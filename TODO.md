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
`modf`, `extl`, `PAIF`, `AAIF`, `ACHF`, `glbl`, `mdfr`, `anim`.

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
    on the disc with no reading at all.

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

**Yes: the engine is in all four of the titles that were tested**, and the
argument, the measurements and the ladder as it actually played out are in
[docs/aska-across-titles.md](docs/aska-across-titles.md). Star Ocean 4 is
settled by `Aska::` in its executable and then by every reader here parsing its
payloads; Resonance of Fate by AIF headers and the `SLZ` token in its
executable; Star Ocean 5 by `SLZ` blocks whose walk closes exactly, inside the
CPK archives of its PSN package; Star Ocean: Anamnesis on Android by 46 507
mangled `Aska` symbols in its native library and an asset file named
`aska0000.bin`.

The questions that came out of it, none of which is about this disc:

21. **Star Ocean 5's payload envelope.** 1 886 sound `ASF ` headers and 3 740
    sound `AIF ` ones in the decrypted package, and not one opens: no `ao__` at
    `0x20`, no `imgX` at `0x10`. Something sits between the magic and the
    chunks, and 58 of 613 sampled headers carry the tag `PS3 `.

22. **The compressed methods in Star Ocean 5's `SLZ`.** Byte `0x03` selects
    one of three; method 0, stored, is readable and the rest are not. Not
    XCompress and not plain LZSS.

23. **Resonance of Fate's container.** The executable proves the engine and the
    disc shows nothing at all — every signature with a structural test scores
    zero sound, and both containers are entropy 8.00 everywhere sampled.

24. **Star Ocean 4's container.** Not one versioned tag on the whole disc, and
    yet thousands of payloads behind `SLZ`. Something indexes them without
    announcing itself the way `MRON` does.

25. **`EXD\0`, `mcd `, `MMD `** — three resource magics in Star Ocean 4's data
    with no reading here. `EXD\0` is the commonest payload in the sample.

Two notes for anyone extending this to a fourth title. The **tests are
asymmetric**: a hit on a versioned magic or on the engine namespace is
conclusive, while a miss proves very little — Resonance of Fate is the worked
example of a title that is certainly ASKA and shows nothing on its disc. And
the **RTTI rung is closed**, more thoroughly than expected: neither Xbox 360
title ships RTTI at all, and a PlayStation executable is encrypted behind
NPDRM. What replaced it was plain strings in the binary.

26. **The mobile class inventory.** `libSOA.so` carries 26 378 mangled `Aska`
    symbols resolving to 5 960 distinct two-level names — methods and members,
    not only classes, against the 1 740 class names session 1 recovered here.
    The `Aska::TAaf…Controller` family alone names the animation machinery
    [docs/formats/aaf.md](docs/formats/aaf.md) decoded from the outside.
    Reading it properly needs an Itanium demangler, which `tools/rtti.py` is
    not.

The remaining candidates all sit on little-endian hardware — Star Ocean 6 on
x86, a PlayStation Vita title, anything else on mobile. `aska.py` now looks for
the payload magics and `SLZ` both ways round, because Anamnesis showed that a
FourCC stored as a 32-bit word *does* flip while the ASCII names do not. Every
`struct` format string in the readers still assumes big-endian, so opening a
little-endian title's payloads is a separate piece of work.

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
