# Open questions

What is not yet known, roughly in order of how much it would unlock. Each
session's log carries its own "Left open" list; this file is the consolidated
view, kept current at the end of every session.

Solved work lives in [docs/formats/](docs/formats/) and is not repeated here.

**Start here next time: question 1.** After session 12 a scene is readable as
*structure* from every side — geometry, materials, textures, skeleton,
animation, collision, the script that drives it and the navigation mesh the AI
walks on — and every skinned object indexes its own file's node tree, so there
is no shared skeleton to find. What is thin is *meaning*: 246 of the 253
scene-script opcodes are known only by number.

## Now the main line of work

**1. What the SNC opcodes do.** The scene script parses completely and seven
of its 253 opcodes are identified. The rest are known by number, arity and
operand kinds. Two footholds: the 19 opcodes whose signature ends `@@nn`
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
    160 shaders in the container. What is left is a per-disc table with a
    `0x100`-byte period, holding no pointers, 51 % of whose blocks are shared
    between the two discs.

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

## Verified, needs no further work

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
