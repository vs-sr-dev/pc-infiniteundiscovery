# Session 8 — which texture a triangle uses

**Date:** 2026-08-24
**Goal:** open question 1, `ml__` and `mats` — the last thing standing between
a decoded mesh and a textured one. Geometry decoded, textures decoded, nothing
tying them together.

## Outcome

Solved, and the link was smaller than expected: **a signed 32-bit displacement
at `mess +0x14`, counted from the start of the mesh chunk, pointing at the
`mats` that shades it**. It lands on a `mats` for all 4 176 meshes in the
corpus. From there a material names its textures by an eight-byte key, and that
key is the eight bytes at `AIF +0x20` — the asset name AIF already read, plus
the word beside it that had been listed as unidentified since session 3.

So the chain closes: mesh → material → texture. `asf.py obj --textures` now
writes an OBJ with `usemtl` groups, a companion MTL carrying the material's own
diffuse, ambient and specular constants, and each material's texture decoded to
a PNG next to it.

## How it went

**The tree walker had been hiding it.** `ml__` looked childless, because
`asf.py` finds a child region by requiring chunk headers to tile it exactly and
`mats` states a step that stops short of its own last section — the same trick
`vlas` plays. Scanning for the tag on 16-byte boundaries instead showed
`ml__` full of materials all along.

**One object gave up the whole format.** Miruce's weapon is a spellbook: three
textures, two meshes, two materials. Its first material's float constants read
0.8/0.8/0.8, 0.2/0.2/0.2 and 1/1/1 with 20 in the fourth slot — diffuse,
ambient, specular, specular power — and the two 8-byte keys at the end of it
were byte-for-byte two of the three AIF headers sitting above it in the same
object. Its second material carried the third.

**`mess +0x14` was a negative number that looked like nothing.** `0xFFFFF9F0`
on the first mesh, `0xFFFFC770` on the second. Read as signed and added to the
chunk's own offset they give `0x2B010` and `0x2B330`, which are exactly where
the two materials sit.

**Then the corpus.** 4 176 of 4 176 meshes resolve. 57 % of them point into
*another object's* `ml__`, which is why 2 205 objects have an empty material
list and every one of their meshes is still shaded.

## What makes it more than a coincidence

Two facts the pointer cannot have produced:

* meshes sharing a material almost always share a vertex format — 1 755 of the
  1 794 materials are used only by meshes of one single descriptor. A shader
  needs the attributes it was compiled against.
* a mesh has texture coordinates exactly when its material has textures, on
  4 172 of the 4 176 meshes.

And the material layout, worked out from section offsets and counts rather than
from the stated step, **lands on the start of the next material on 1 793 of
1 794**.

## `rl__` names the shading network

The render list turned out to be the shading graph the artists built, one
`rnel` per node, each with its name and a type byte:

```
R:M:Material_Book   R:M:Blinn_Book   R:M:Tex_Book   R:M:Tex_Normal
```

Fourteen type codes appear. The readings come from the names — every type-3
node is a variation of `phong`, every type-0x1B node a variation of
`marschner` — but four are corroborated from outside the artists' naming
entirely: `MarschnerShader`, `AshikhminShader`, `NormalMap` and `DoubleSided`
are strings in the retail executable, next to `KajiyaKayShader` and a shader
register vocabulary (`avUVSet[0..15]`, `avWorkReg[0..31]`,
`eamUVShiftMatrix[0..3]`, `vFinalColor`) belonging to the same system.

A 2008 console title shipping Marschner and Ashikhmin–Shirley BRDFs — hair and
anisotropic metal — is worth recording about the engine, not just the format.

## A measurement redone

Session 6 could only test the binormal-or-tangent question on meshes whose
object carried a single non-square texture, because nothing said which texture
a mesh used. Redone per mesh against its own material's texture: median texel
anisotropy **1.89** over 251 914 triangles for the plain `(u, v)` reading,
**5.03** for the rotated one.

Honesty about what that does not show: mis-assigning every mesh to the next
texture in its file gives 1.69, because the textures of one file tend to share
an aspect ratio. The measurement supports the binormal reading and says nothing
about the link. The evidence for the link is the four checks above.

## Left open

1. The two fields in a texture reference, at `+0x08` (`0x0001`, `0x0002`,
   `0x0080`, `0x0081`, `0x0082`) and `+0x0C` (`0x100`, `0x200`, `0x400`,
   `0x800`, `0xA00`). Neither separates a colour map from a normal map:
   classifying 625 decoded textures by whether their average pixel is the flat
   lavender of a tangent-space normal map splits every value of both in the
   same proportion. The only signal is positional and weak — first in the list
   is a colour map 91 % of the time, second is a normal map 58 %.
2. The shader program block, the `0x120`-odd bytes between a material's header
   and its binding table. It is structured — repeating `00 XX 8Y 00 00 00 00
   XX` groups — and unread.
3. The 48-byte records counted by the byte at `mats +0x19`, present on 685 of
   1 794 materials. They hold pairs of 1.0 and read like a UV transform, which
   `UVSetTransform` and `eamUVShiftMatrix` in the executable would fit.
4. The four-byte entries in an `rnel`, which are presumably how the nodes
   connect to each other.
5. The word in each constant binding, which runs `0x60`, `0x68`, `0x70` … in
   step with the entry number on every material seen and so carries nothing
   this reader can use.
