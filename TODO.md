# Open questions

What is not yet known, roughly in order of how much it would unlock. Each
session's log carries its own "Left open" list; this file is the consolidated
view, kept current at the end of every session.

Solved work lives in [docs/formats/](docs/formats/) and is not repeated here.

**Start here next time: question 1.** `AAF ` animation is the largest format
left that nobody has opened, and after session 8 a model is complete apart from
moving: geometry, skinning weights, bone indices, materials and textures all
decode. The bone pool the weights index into (`bnpl` / `bnpi`, question 3) is
part of the same problem and worth reading first — it is two small chunks, and
an animation has to address bones the same way a vertex does.

## Now the main line of work

**1. `AAF ` animation and `ACF ` collision.** Both are plain readable files.
The engine's RTTI already names the collision primitives — capsule, cube and
sphere, via `Aska::AcfPrimitiveData_capsule` / `_cube` / `_sphere` — so ACF has
a head start.

**2. `-CNS` / `SNC-` scene data**, from `SCE-` resources. Only four blocks, but
scene scripting is likely to explain a lot of the rest.

**3. The ASF chunks nobody has opened:** `bnpl`/`bnpi` (bone pools — the vertex
bone indices decode, but what they index into has not been read),
`ptcl`/`pprn`/`pani` (particles), and `modf`, `extl`, `PAIF`, `AAIF`, `ACHF`,
`glbl`, `mdfr`, `anim`.

**4. The material leftovers**, small and self-contained after session 8: the
two fields in a texture reference at `+0x08` and `+0x0C`, neither of which
separates a colour map from a normal map; the shader program block between a
material's header and its binding table; the 48-byte records counted at
`mats +0x19`, which look like a UV transform; and the four-byte entries in an
`rnel`, presumably how the shading nodes connect.

**5. The 59 ASF objects in 3 855 whose geometry misses their stated bounding
box** by more than 10 %. They are mostly treasure chests and morph targets —
things whose geometry moves — which suggests the box describes a pose the
stored vertices are not in.

## Smaller and self-contained

6. **AIF mip chains.** The base level decodes. The Xbox 360 packs the small mip
   levels into a shared tile, and working that out would complete the texture
   format.

7. **The AIF flags at `0x34`** (`0x500`, `0x200`, `0x40400`, zero). The word at
   `0x24` is no longer open: session 8 showed it is the asset number, and that
   `0x20` and `0x24` together are the key a material references a texture by.

8. **`NODE` payloads**, which carry no magic at all, and **`TTD-`**, whose
   payload begins `DTT\0`.

9. **The 30 488 bytes at the start of each `ud1.bin`.** Session 7 identified
   the rest of that `0x16000` header as the compiled shader library, 70 of the
   160 shaders in the container. What is left is a per-disc table with a
   `0x100`-byte period, holding no pointers, 51 % of whose blocks are shared
   between the two discs.

10. **The ASF/WMV video runs** in the container gaps — they need splitting into
   individual movies.

11. **`AOF`**, named three times in the engine's RTTI (`Aska::AofHandler`,
   `Aska::AofObject`, `Aska::DirectAofHandler`) but never seen as a payload
   magic on disc. One lead turned up while reading ASF: the chunk holding a
   single object is tagged `ao__`, and `Aska::AofObject` is what the engine
   calls an object. That is a resemblance between two names and nothing more,
   but it is the first place to look.

12. **Disc 2.** Everything established so far was measured on disc 1. Disc 2 has
    been walked but its containers have not been put through the same checks.
    Its audio has: the same banks as disc 1, plus one track disc 1 lacks.

13. **The `AAC ` leftovers**, small and self-contained after session 5: the
    eight-byte field at `WAVE +0x08`, constant `0x995A7C80_00000015` in 2404
    sounds and zero elsewhere; what the sample count at `+0x24` counts exactly;
    and the `PLBK` playback record, whose shape is known but whose 23 values
    have never been checked against what the engine does with them.

14. **Five missing music tracks** — the numbers 35, 45, 46, 55 and 74 appear on
    neither disc. Cut, or somewhere not yet walked.

15. **The other 90 shaders**, which session 7 did not locate: 160 are counted
    in disc 1's `ud1.bin` and 70 sit in the header block, so the rest are
    presumably inside archives. Related: a shader blob's constant table has a
    structure, and parsing it rather than scanning for strings would give each
    shader its full signature.

16. **The ASF vertex leftovers**, small after session 6: the descriptor nibble
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
* ASF scenes: container, geometry and materials — [docs/formats/asf.md](docs/formats/asf.md)
* AAC audio, and where the music lives — [docs/formats/aac.md](docs/formats/aac.md)
