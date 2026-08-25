# Session 9 — the bones move, and what they bump into

**Date:** 2026-08-25
**Goal:** open question 1, `AAF ` animation — the largest format nobody had
looked at — after first reading `bnpl` and `bnpi`, the two small chunks a
vertex's bone index has to pass through. `ACF ` collision, which was question 1
after that, turned out small enough to finish in the same sitting.

## Outcome

All three solved. A model was complete after session 8 apart from moving; it now
moves, and the chain from a vertex to the node that drives it is closed at
every level.

* **`bnpl` and `bnpi`** are the middle two rungs of a three-level bone
  indirection. Every link lands in range on the whole corpus.
* **`AAF `** parses in full: all 900 payloads sampled pass every internal
  consistency check, and its channels are identified against the rest pose of
  the scene they animate — evidence from outside the decode.
* **`ACF `** parses in full too: all 972 files, with three independent checks
  on the shape reading.

## The bone chain

A skinned vertex's bone byte is not a node number. It indexes the mesh's own
`bnpi`; `bnpi` indexes the object's `bnpl`; `bnpl` holds node numbers into the
file's `tree`. Both chunks are bare arrays of 16-bit numbers with no count —
the chunk size gives it, rounded up to four, so a pool with an odd number of
entries ends in a padding zero.

The point of the middle rung is the byte at the bottom. `53EC3800` has 367
nodes and an object that uses 168 of them; no single mesh in it uses more than
98. The palette is what keeps a vertex's bone reference one byte wide.

Every link closes:

| | |
| --- | --- |
| `bnpl` entry inside the node tree | 217 of 217 objects |
| `bnpi` entry inside its object's pool | 642 of 642 meshes |
| vertex bone index inside its mesh's palette | 642 of 642 meshes |

And the objects that *don't* close are the interesting ones: 44 objects have a
pool overshooting the node tree, and **every one of them is in a file with no
`tree` chunk at all**. Their skeleton is in another resource. That is the first
concrete evidence of a shared skeleton, and `SKAC` — which the census already
described as travelling with skeletons — is where to look.

## AAF, from the outside in

The file opens flat: a 0x24-byte header, then one record per animated node,
then a table of keyframe blocks, then the values of every channel that never
changes, then the blocks themselves. Nothing is compressed and nothing is
indirected except the keys.

**Two false starts, both about field widths.** Reading the record count and the
track size as 32-bit words works on most files and then walks off the end of a
record on the rest — the counts live in the low half of a 32-bit slot and a
minority of files put something in the high half. And "a track is animated if
it is longer than 0x14 bytes" agrees with the header on 221 of 900 files;
"a track is animated if flag 0x20 is set" agrees on 900 of 900. Once both were
fixed every file parsed, and every internal check passed: records tile the
record table, tracks tile each record, the constant region's own stated size
lands exactly on the first keyframe block, every key is exactly the size its
layout declares, and **every animated track appears in exactly the number of
blocks its last word declares** — 4 931 of 4 931.

## What names the channels

Nothing in an AAF says "this is a translation". The ASF does.

An AAF record carries the name of an `attr` node, and an `attr` stores that
node's rest translation, rotation and scale as full floats at `+0x50`, `+0x60`
and `+0x70`. A channel that never changes usually holds exactly those numbers.
Pairing every animation with the scenes in its own archive:

| Channel | Reproduces the ASF rest pose | |
| --- | ---: | ---: |
| 5, against `attr +0x50` | 61 805 of 62 104 | 99.5 % |
| 6, against `attr +0x60` | 37 522 of 40 541 | 92.6 % |
| 7, against `attr +0x70` | 7 871 of 7 903 | 99.6 % |

So channel 5 is translation, 6 rotation, 7 scale — read off numbers this
decoder did not produce. The rotation figure is the weakest, and sampling the
residual shows the decoded *axis* matching while the angle differs: those are
animations whose rest pose is genuinely not the scene's.

## The packed quaternion

This was the session's real work. A rotation key is eight bytes, the top
sixteen bits are always zero, and no reading of the remaining 48 as four signed
shorts gives a unit quaternion — only 78 % have constant length, and those turn
out to be the identity.

What broke it open was counting **bit flips between consecutive keys** of one
long rotation track. Low bits flip on nearly every key, high bits almost never,
and the boundaries between fields show up as a jump back to 50 %. That gave
14 + 17 + 17 bits, and from there each field fell to a fit against the paired
rest poses.

| Bits | Field |
| --- | --- |
| `0..13` | The axis' angle from the **Y** axis, 16383 = 90° |
| `14..27` | The angle of the axis' xz part from the **X** axis, 16383 = 90° |
| `28..30` | The signs of z, y, x |
| `31..47` | The rotation: `w = 1 - (field / 131071)²` |

Three angles, all quantised the same way — as a fraction of a right angle —
with three sign bits so that the two axis angles only ever have to describe the
positive octant. Fourteen bits is plenty for a quarter turn.

The `w` field is the elegant part. Squaring it on the way out concentrates the
precision near `w = 1`, which is where small rotations live and where a plain
fixed-point quaternion is at its worst. It was found by noticing that
`(field/131071)²` came out as `1 - cos(θ/2)` to four decimals on every sample.

## The tangents are tangents

A translation key is a value and two tangents. Checking the outgoing one
against the curve it is supposed to describe, over 60 210 keys:

* its **length** is the length of the step to the next key — median ratio
  **0.988**, independent of how far apart the keys are;
* its **direction** sits within 5° of the line through the keys either side on
  51 % of them, median 4.7°.

That is a Maya smooth tangent scaled to the segment it opens — which is what
an exporter would have written out of the artists' curves.

## `ACF ` — collision, and three ways to check it

The smallest Aska format and the most completely read. A 0x30-byte header, an
array of 0x40-byte groups, an array of 0x30-byte primitive records, and the
primitive data on a 0x20 grid. Nothing compressed, nothing indirect.

**The tree is the skeleton.** A group is a bounding sphere with a name, and the
names are `R:M:SK_HipR`, `R:M:SK_LtArmR`, `R:M:SK_RtLegL` — the same names the
ASF node tree and the AAF records carry. 947 of 1 269 group names are in the
node tree of the scene from the same archive, and 179 of 196 files have every
one of theirs.

Branch groups hold five child slots terminated by `0xFFFF`, and bit `0x8000`
picks which array the child is in — the leaves or the branches. Reading it the
other way scatters the tree; reading it this way means **following the slots
from group 0 reaches every group exactly once, on all 522 files with
branches**. Leaves instead name a run of primitives, and those runs partition
the primitive array exactly, on all 972.

**Three checks on the shapes, none of them circular.** The shape code is 0, 1
or 2 — sphere, cube, capsule, the same order the engine's RTTI lists
`Aska::AcfPrimitiveData_*` in. Each shape stores different parameters, so:

* the redundant bounding radius in every primitive should be the sphere's
  radius, the cube's half-diagonal, or the capsule's half-length plus radius —
  and it is, on **all 8 302** that state one, median error exactly zero;
* each shape stores a different number of floats, 5, 8 and 6, so the file only
  ends exactly after the last primitive's data if the code picks the right
  count — it does, on all 972;
* 8 119 primitives are named some variation of `pColSphere`, `pColCube` or
  `pColCapsule`, and **the code agrees with the artist's name on all 8 119**.

The 16-bit mask on a primitive is carried up the tree as an OR: 7 252 of 7 252
leaves and 2 281 of 2 281 branches. And the header's `+0x28` is exactly the
highest point the collision reaches in Y, on all 972 — a ceiling height the
engine can read without touching the tree.

One thing does *not* check out arithmetically, and it is informative: a leaf's
sphere bounds its own primitives (98.4 %), but a branch's does not bound its
children's. The bone transforms between them live in the ASF, not here.

**`atari`.** The largest file in the corpus fences off a map region with 618
capsules, and its root group is not called `R:M:` anything. It is called
`atari` — 当たり, the ordinary Japanese word for a hit, and the first half of
当たり判定, which is what a Japanese studio calls a collision volume. Someone
typed it in romaji instead of using the naming convention and it shipped.
`hanes`, `e_raigei`, `MEDICAL_HERB_01` and `CTRL_elevator` are in the same
corpus.

## Tooling

`tools/aaf.py` is new: `tree`, `info`, `pose --time`, `check` over a corpus,
and `rest`, which is the cross-check against the ASF rest pose above.
`tools/asf.py` gained `skeleton`, reads `bnpl`/`bnpi` into `Object3D` and
`Mesh`, and its `check` now reports all three rungs of the bone chain.
`tools/acf.py` is new as well: `tree`, `info`, `check` (with `--models`, the
cross-check against the scene's node tree), and `obj`, which writes the
collision volumes out as a mesh so they can be looked at.

## Left open

1. The word at AAF `+0x20`, larger than the file itself.
2. The three floats at `+0x14` of an animated track. On the opening logo they
   read `(0, 0, 180)`, `(0, 180, 360)`, `(0, 360, 545)` across five nodes that
   appear one after another, which looks like a time window — but that is one
   file.
3. The units of time. Durations of 600 and 1 200 with keys every 4 suggest
   frames, and nothing here pins the rate.
4. The channel numbers other than 5, 6 and 7 — 14, 16, 18, 22, 45 and more,
   on lights, emitters and cameras — and the semantic byte at track `+0x12`.
5. The `0x0200` some tracks put in the high half of their size word.
6. Where the skeleton of a `tree`-less ASF lives. `SKAC` is the candidate, and
   it would also say what a collision file's bone names resolve against.
7. In ACF: the `u16` at primitive `+0x28`, a permutation of `0 .. n-1` in 460
   files and something else in 512; which bit of the collision mask means what;
   and `+0x2C`, exactly the root sphere seen from the origin on 463 of 972.
