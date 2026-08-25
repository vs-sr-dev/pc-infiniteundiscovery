# ACF — the Aska Collision File

`ACF ` is what every `COLL` resource holds: 972 of them in disc 1's `ud1.bin`,
2.7 MB in all. It is the smallest of the Aska formats and, now, the most
completely read — a sphere tree over three primitive shapes, uncompressed,
with the artists' Maya names left in.

The engine named the shapes before the disc did. Its RTTI carries
`Aska::AcfPrimitiveData_capsule`, `_cube` and `_sphere`, and the shape code in
a primitive record turns out to be 0, 1 and 2 in exactly that order.

**All 972 files parse and pass every check below.**

## 1. The header

0x30 bytes, big-endian.

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | `ACF ` |
| `+0x04` | 4 | Total length — matches the file on all 972 |
| `+0x10` | 2 | Version, 5 everywhere |
| `+0x12` | 2 | Branch group count |
| `+0x14` | 2 | Leaf group count |
| `+0x16` | 2 | Primitive count |
| `+0x18` | 4 | `1.0` in every file |
| `+0x1C` | 4 | Offset to the groups — the branches come first |
| `+0x20` | 4 | Offset to the leaf groups |
| `+0x24` | 4 | Offset to the primitive records |
| `+0x28` | 4 | The highest point the collision reaches in Y |
| `+0x2C` | 4 | The whole thing's radius, measured from the origin |

Then three arrays, each tiling exactly into the next: 0x40-byte group records,
0x30-byte primitive records, and the primitive data on a 0x20 grid.

`+0x28` is worth a note: it is the largest `centre.y + bounding radius` over
every primitive in the file, exactly, on **all 972**. A ceiling height, and a
number the engine would want before touching the tree.

## 2. Groups — the sphere tree

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 16 | Bounding sphere: centre xyz, then radius |
| `+0x10` | 32 | Name, NUL-padded ASCII |
| `+0x30` | 2 | Kind: `0` a branch, `0x0100` a leaf |
| `+0x32` | 2 | This group's index within its own array |
| `+0x34` | 2 | Collision mask |
| `+0x36` | 10 | Five slots — children if a branch, `(first, count)` if a leaf |

A **branch**'s five slots are child references terminated by `0xFFFF`. Bit
`0x8000` means the child is a leaf, indexed into the leaf array; without it the
child is another branch, indexed into the branch array. That distinction is not
a guess: reading it the other way scatters the tree, and reading it this way
means **following the slots from group 0 reaches every group in the file
exactly once, on all 522 files that have branches**. No group is missed and
none is visited twice, so the slots are a spanning tree.

A **leaf** instead names a run of primitives — the first, and how many. Those
runs partition the primitive array exactly, on all 972 files.

The names are bones:

```
R:M:POS_ROOT  R:M:SK_HipR  R:M:SK_Bck3  R:M:SK_LtArmR  R:M:SK_RtLegL
R:M:SK_NckR   R:M:SK_HedR  R:M:SK_WEP01 trColDummy1
```

These are the same names the [ASF](asf.md) node tree and the
[AAF](aaf.md) animation records carry — 947 of 1 269 group names are in the
node tree of the scene from the same archive, and 179 of 196 files have every
one of theirs. So the sphere tree **is** the skeleton, and each group's sphere
is in its own bone's space. That also explains the one thing that does not
check out arithmetically: a leaf's sphere bounds its own primitives (98.4 % of
7 237), but a branch's does not bound its children's, because the bone
transforms between them are in the ASF, not here.

## 3. Primitives

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 32 | Name, NUL-padded ASCII |
| `+0x20` | 2 | Shape: **0 sphere, 1 cube, 2 capsule** |
| `+0x22` | 2 | This primitive's index |
| `+0x24` | 4 | Offset to its data |
| `+0x28` | 2 | Unidentified |
| `+0x2A` | 2 | `0xFFFF`, or zero |
| `+0x2C` | 2 | Collision mask |
| `+0x2E` | 2 | Zero |

The data is a centre, a bounding radius, and then the shape's own parameters:

```
sphere   cx cy cz  r    r
cube     cx cy cz  r    hx hy hz 1.0
capsule  cx cy cz  r    half-length  radius
```

3 767 capsules, 2 625 cubes, 1 925 spheres.

### Why this reading is safe

The bounding radius is redundant with the parameters, and that is what makes it
checkable. It should be the sphere's radius, the cube's half-diagonal
`sqrt(hx² + hy² + hz²)`, and the capsule's half-length plus radius. It is, on
**all 8 302 primitives that state one** — median error exactly zero, every one
within a millionth.

The file's own length is the second check. Each shape stores a different number
of floats — 5, 8 and 6 — so the file only ends exactly after the last
primitive's data if the shape code picks the right count. It does, on all 972.

And the third is the artists. 8 119 primitives are named some variation of
`pColSphere`, `pColCube` or `pColCapsule`, and **the shape code agrees with the
name on all 8 119**. A name an artist typed in Maya owes nothing to a byte in a
header.

## 4. The mask

A 16-bit field on every primitive, and a group carries the OR of everything
beneath it — on **7 252 of 7 252 leaves and 2 281 of 2 281 branches**. The
values are single bits and small combinations:

```
0010 x4521   0100 x1399   0001 x865   0200 x804   0000 x313
1100 x177    0400 x81     1101 x57    0010|0100   ...
```

So it reads as a layer or category — what a volume collides with — rather than
as a shape or a material. Which bit means what is not established here.

## 5. A word the artists left behind

Group names are almost all `R:M:`-prefixed bones, but not all. The largest
file in the corpus, `34C6D000_029_COLL.acf` — 618 primitives fencing off a
whole map region with capsules — calls its root group **`atari`**. 当たり is
the ordinary Japanese word for a hit, and 当たり判定 is what a Japanese studio
calls a collision volume. Someone typed the word in romaji instead of using
the naming convention, and it shipped.

Others in the same vein: `hanes`, `e_raigei`, `MEDICAL_HERB_01`, `NUT`,
`ele_doorL02`, `CTRL_elevator`.

## 6. Still open

* The `u16` at primitive `+0x28`. It is a permutation of `0 .. n-1` in 460
  files and something else in 512, so it is not simply an index.
* Which bit of the mask means what.
* `+0x2C`. It is exactly the root sphere measured from the origin on 463 of
  972 files, at least that on 779, and the median ratio is 1.0000 — so it is
  the reach of the whole thing, but not always computed the same way.
* Whether a capsule has an axis other than Y. Nothing in the record suggests
  one, and the bone the group hangs off would supply the orientation.

## 7. Reproducing

```
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 \
       --length 2207584256 --tag COLL --decompress extract/coll
python tools/acf.py info  extract/coll/49450000_036_COLL.acf
python tools/acf.py tree  extract/coll/49450000_036_COLL.acf
python tools/acf.py obj   extract/coll/49450000_036_COLL.acf collision.obj
python tools/acf.py check "extract/coll/*.acf" --models "extract/models/*.asf"
```
