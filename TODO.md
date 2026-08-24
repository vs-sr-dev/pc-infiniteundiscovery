# Open questions

What is not yet known, roughly in order of how much it would unlock. Each
session's log carries its own "Left open" list; this file is the consolidated
view, kept current at the end of every session.

Solved work lives in [docs/formats/](docs/formats/) and is not repeated here.

**Start here next time: question 1.** Everything a textured model needs is now
readable except the one link between the two — geometry decodes, textures
decode, and nothing yet says which texture a given triangle uses. The material
chunks sit inside the same `ao__` as both, so the corpus and the tools for it
already exist: `python tools/asf.py tree <file.asf>` shows `ml__` and `mats`
side by side with the `AIF ` chunks they presumably reference, and an object
with three textures and two meshes is a small enough puzzle to brute-force the
indices against.

## Now the main line of work

**1. `ml__` / `mats`, the materials.** With the vertex format solved in session
6, this is what is left between a decoded mesh and a textured one: the chunks
that tie geometry to the `AIF ` textures sitting beside it in the same object.
A material index would also settle the binormal-or-tangent question in
question 16, by making a textured render possible.

**2. `AAF ` animation and `ACF ` collision.** Both are plain readable files now.
The engine's RTTI already names the collision primitives — capsule, cube and
sphere, via `Aska::AcfPrimitiveData_capsule` / `_cube` / `_sphere` — so ACF has
a head start.

**3. `-CNS` / `SNC-` scene data**, from `SCE-` resources. Only four blocks, but
scene scripting is likely to explain a lot of the rest.

**4. The ASF chunks nobody has opened:** `rl__` (render list), `bnpl`/`bnpi`
(bone pools — the vertex bone indices decode, but what they index into has
not been read), `ptcl`/`pprn`/`pani` (particles), and `modf`, `extl`, `PAIF`,
`AAIF`, `ACHF`, `rnel`, `glbl`, `mdfr`, `anim`.

**5. The 59 ASF objects in 3 855 whose geometry misses their stated bounding
box** by more than 10 %. They are mostly treasure chests and morph targets —
things whose geometry moves — which suggests the box describes a pose the
stored vertices are not in.

## Smaller and self-contained

6. **AIF mip chains.** The base level decodes. The Xbox 360 packs the small mip
   levels into a shared tile, and working that out would complete the texture
   format.

7. **The unidentified AIF fields**: the `u32` at `0x24`, which varies per asset,
   and the flags at `0x34` (`0x500`, `0x200`, `0x40400`, zero).

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
    in slot 3 that two meshes set, the 24 meshes whose stride is rounded up
    rather than exact, and whether slot 4 holds a binormal or a tangent with
    the texture coordinates rotated — which only rendering a mesh against its
    own texture will settle.

## Verified, needs no further work

* Disc layout and XDVDFS — [docs/formats/xdvdfs.md](docs/formats/xdvdfs.md)
* NORM/MRON containers — [docs/formats/norm-mron.md](docs/formats/norm-mron.md)
* XEX2 and the decrypted executable — [docs/formats/xex.md](docs/formats/xex.md)
* XDBF title metadata — [docs/formats/xdbf.md](docs/formats/xdbf.md)
* SLZ / XCompress — [docs/formats/slz.md](docs/formats/slz.md)
* AIF textures — [docs/formats/aif.md](docs/formats/aif.md)
* ASF scenes, container and geometry — [docs/formats/asf.md](docs/formats/asf.md)
* AAC audio, and where the music lives — [docs/formats/aac.md](docs/formats/aac.md)
