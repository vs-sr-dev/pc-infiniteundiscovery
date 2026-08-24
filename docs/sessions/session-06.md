# Session 6 — the rest of an ASF vertex

**Date:** 2026-08-24
**Goal:** open question 1, the main line of work since session 4: normals,
texture coordinates and skinning, none of which had come out.

## Outcome

The vertex format is solved. The descriptor at `vlas +0x04` turned out to be a
set of four-bit fields — the slot says which attribute, the value says how it
is stored — and adding the sizes it implies reproduces the stride the file
states on 14 594 of the 14 618 meshes in disc 1's `ud1.bin`, with the other 24
rounded up to the next multiple of 16.

Every attribute now decodes: normals, binormals with their handedness, one or
two sets of texture coordinates, vertex colour, four blend weights and four
bone indices. `asf.py obj` exports normals and texture coordinates along with
the positions, and two conventions of the engine fell out along the way.

## What made it work

Session 4 had tried readings of the leftover bytes against each mesh's own
texture, by eye, and nothing matched. This session did not look at a texture
until the very end. It tested candidate readings against invariants the data
has to satisfy if the reading is right:

* a normal has length one;
* the four blend weights sum to one;
* bone indices are small;
* a normal points the same way as the triangles around it;
* a tangent-frame vector is square to the normal;
* the frame agrees with the direction the texture coordinates run in.

The first probe took the largest descriptor class, `0x00040948` at stride 20,
and asked of each four-byte field whether it was a unit vector under two
candidate packings. The answer was immediate: the fields at +8 and +16 are unit
vectors to a median `|length - 1|` of 0.0013, and the field at +12 is not. One
measurement had found the normal, the binormal and the texture coordinates.

Skinning fell just as fast. The twelve bytes that descriptors starting `0xC`
add are four 16-bit values summing to 65535, then four bytes whose largest
value in the sample was 6. Weights and bone indices, and the sum is exact on
**100.0 % of 2 919 607 skinned vertices**.

## The descriptor

| Slot | Attribute | Values |
| --- | --- | --- |
| 0 | position | `1` three floats, `4` four floats, `8` four halfs |
| 1 | normal | `4` a packed unit vector |
| 2 | texture coordinates | `9` two shorts, `A` four shorts, `1` two floats, `2` four floats |
| 4 | binormal | `4` a packed unit vector |
| 7 | bitmask | `1` colour, `4` blend weights, `8` bone indices |

The order in memory is not the order of the nibbles: the colour sits between
the normal and the texture coordinates, and the skinning goes last. That is not
a guess — it is what makes the float texture coordinates land where they parse
as floats, and it is the only order under which every class adds up.

The packed vectors are three signed 10-bit components in a big-endian word,
lowest first, over 511. The two bits left over are always 1 on a normal, and 1
or 3 on a binormal: the handedness of the frame.

The colour identified itself by its values — `FFFFFFFF`, `FF7F7F7F`,
`00FFFFFF`, `FF999999`.

## Two conventions of the engine

**Triangles are wound the other way round.** Computing the face normal as
`(b-a) × (c-a)` puts it at 179.9° from the stored normal — anti-parallel, which
is a sign error rather than a wrong decode. The other winding puts it at 0.4°.
`obj` now writes faces `a-c-b`, and the exported models light correctly.

**The texture v axis points downwards**, as in Direct3D: the vector in slot 4
runs against increasing v.

## Binormal or tangent, and how it was decided

The vertex data cannot separate "the stored vector is the binormal, and the
coordinates are `(u, v)`" from "it is the tangent, and the coordinates are
rotated ninety degrees". Both fit every angle measured, identically. The first
version of this session's decode picked the second reading and rotated the
coordinates.

What decided it was texel density. Artists match it, so on a mesh whose texture
is not square the correct orientation keeps the mapping close to isotropic and
the rotated one stretches it by the texture's aspect ratio. Measured on the
objects that carry exactly one non-square texture: the plain reading gives a
median anisotropy of 2.0, the rotated one 7.0.

So the plain reading is what `asf.py` emits, and this is recorded as a reading
rather than a certainty. Rendering a mesh against its own texture would settle
it outright, and that has still not been done.

## Verification

`asf.py check`, over all 1 505 `MESH` resources of disc 1's `ud1.bin` — 1 438
of which are `ASF ` payloads and 67 nested NORM archives:

| Check | Result |
| --- | ---: |
| Payloads parsed, errors | 1 438, **0** |
| Meshes | 14 618 |
| Descriptor nibbles not accounted for | 2 meshes, slot 3 |
| Packed vectors, median `\|length - 1\|` | **0.0014** over 6 935 532 |
| Stored normal against the triangles around it | median **2.3°** |
| Binormal against normal, off square by | median **1.1°** |
| Binormal against what the coordinates imply | median **8.9°** |
| Blend weights summing to one | **100.0 %** of 2 919 607 |

None of those comparisons uses a number this reader produced: each puts a
decoded attribute against something computed from a different part of the file.
A wrong reading of any packed field moves all of them at once.

## Tools

* `tools/asf.py` — a `VertexFormat` that turns a descriptor into a layout, full
  attribute decoding, `obj` export with normals and texture coordinates and the
  corrected winding, a vertex-layout line in `info`, and a new `check`
  subcommand that measures the decode against the geometry in bulk.

## Left open

1. `ml__` / `mats`, the materials — now the obvious next step, since they are
   what ties a mesh to the textures sitting beside it in the same object.
2. The nibble in slot 3 that two meshes set, and the 24 meshes whose stride is
   rounded up rather than exact.
3. Whether slot 4 is the binormal or a tangent with rotated coordinates, which
   only a render will settle.
4. `bnpl` / `bnpi`, the bone pools: the indices decode, but what they index
   into has not been read.
