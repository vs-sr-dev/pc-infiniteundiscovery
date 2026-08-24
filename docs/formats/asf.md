# ASF — the Aska Scene File

`ASF ` is what every `MESH` resource decompresses to: 916 of the 1 812
compressed blocks in disc 1's `ud1.bin`, and the largest single format in the
game.

Despite the tag it is not one mesh. It is a small scene — geometry, the
materials that geometry uses, the textures those materials reference, and a
named node tree tying them together. A `MESH` resource is self-contained: the
textures travel inside it.

Nothing here is shared with Microsoft's ASF container. tri-Ace's three letters
stand for Aska Scene File, and the collision is only in the name.

## 1. A tree of chunks

Every chunk has the same 16-byte header, big-endian:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | Tag, four printable ASCII characters |
| `+0x04` | 4 | Content size, header included |
| `+0x08` | 4 | Zero in everything seen so far |
| `+0x0C` | 4 | Step to the next sibling; zero means "same as the content size" |

The two sizes differ when the content is not a multiple of 16 — `bnpl` holds
`0x14` bytes of content in a `0x20`-byte slot. Following the step lands exactly
on the end of the parent, and the file closes with a 16-byte `eof_`.

There is one wrinkle. `vlas` states an *unrounded* step, so a chunk containing
one finishes a few zero bytes short of its parent's end. A walk is therefore
accepted when it stops less than one header short with only zeros left over —
not when it stops anywhere.

The root is `ASF ` at offset 0, with the payload's total length at `+0x04`, and
the first child at `0x20`.

### Where the children start

Children do not necessarily begin right after the header. Several chunks carry
a fixed payload first:

| Tag | Payload before the children |
| --- | ---: |
| `ao__` | `0xA0` |
| `tree` | `0xB0` |
| `mess` | `0x10` |

`tools/asf.py` does not rely on that table. It finds the child region by trying
each 16-byte offset and keeping the one from which chunk headers tile the rest
of the body. A wrong offset fails within a chunk or two, so the search is safe
rather than a guess — and the table above is simply what it converges on.

### The tags

```
ASF                    the file
  ao__                 one object: its bounds, then everything it needs
    AIF                an embedded texture, in the AIF format
    ml__ / mats        materials
    bnpl               bone pool
    mess               one mesh
      bnpi             bone pool indices
      idxl             triangle indices
      vlas             vertices
    rl__               render list
    ptcl / pprn / pani particles
  tree                 the node graph
    attr               one named node
  modf / extl          small, unexamined
  eof_                 end marker
```

`PAIF`, `AAIF`, `ACHF`, `rnel`, `glbl`, `mdfr` and `anim` also occur, and have
not been looked at.

## 2. The node tree

`tree` holds one `attr` per node, and each `attr` opens with a 16-byte
NUL-padded ASCII name. These are the names from whatever the artists modelled
in — they survived into the shipped disc untouched:

```
ROOT   R:M:SK_WEP01 .. R:M:SK_WEP09   R:M:CAPEL_WEAPON
ROOT   camera1_group  camera1  camera1_aim  POS_ROOT  POS_Pad1  POS_Pad2
       SQ  TM  R  MS  Tri_ace
```

The second is the opening logo sequence, camera included. `Capell` is the
game's protagonist, so the first is his weapon set. Others carry Maya's default
names — `pPlaneShape6`, `polySurfaceShape` — and one is `R:M:MORPH_BLINKS`.

## 3. Objects and their bounding boxes

An `ao__` body opens with 0xA0 bytes of fixed fields. The first six 16-byte
rows are geometry, all 32-bit floats:

| Body offset | Field |
| --- | --- |
| `+0x00` | Bounding sphere: centre xyz, then radius |
| `+0x10` | Bounding box centre, then 1.0 |
| `+0x20` | Box axis 0, then 1.0 |
| `+0x30` | Box axis 1, then 1.0 |
| `+0x40` | Box axis 2, then 1.0 |
| `+0x50` | Half-extent along each axis |
| `+0x80` | 16-byte object name |

The three axes are unit vectors and usually the coordinate axes, but not
always: one object measured has axis 0 = `(0, 0, -1)` and axis 2 = `(-1, 0, 0)`,
with the extents given in that rotated order. So it is an **oriented** box, not
an axis-aligned one — an important distinction, because reading it as
axis-aligned makes the extents look scrambled on exactly those objects.

This box is the single most useful thing in the format for anyone reverse
engineering it. It was written in full 32-bit floats by whatever exported the
model, computed from source geometry, and it describes the same vertices the
file stores in a much lossier form. Reproducing it from the decoded vertices is
therefore a check against a number that did not come from the decode.

## 4. Geometry

`mess` opens with two 16-bit counts: vertices, then indices.

**`idxl`** holds the triangle indices. The offset to the data is at `+0x10` of
the body, counted from the start of the chunk. Indices are 16-bit, and the
count is always a multiple of three, so these are triangle lists rather than
strips.

**`vlas`** holds the vertices:

| Body offset | Field |
| --- | --- |
| `+0x00` | Zero, or 0x10 |
| `+0x04` | Vertex format descriptor |
| `+0x08` | Vertex stride in the top 16 bits |
| `+0x0C` | Offset to the vertex data, from the start of the chunk |

The stride is stated *and* derivable — divide the data region by the vertex
count. `asf.py` treats a disagreement as an error, and across all 14 618 meshes
of disc 1's `ud1.bin` it never fired: the two always agree. The stride is not
fixed, though — 12, 16, 20, 24, 28, 32, 36, 40 and 44 all occur.

Both data offsets land the bulk data on a 4096-byte boundary of the file.

### The vertex descriptor

The word at `+0x04` is a set of four-bit fields. **Which field a nibble sits in
says which attribute it describes; its value says how that attribute is
stored.** Only slots 0, 1, 2, 4 and 7 are ever used.

| Slot | Bits | Attribute | Values |
| --- | --- | --- | --- |
| 0 | `0..3` | Position | `1` three floats (12 B), `4` four floats (16 B), `8` four halfs (8 B) |
| 1 | `4..7` | Normal | `4` a packed unit vector (4 B) |
| 2 | `8..11` | Texture coordinates | `9` two shorts (4 B), `A` four shorts (8 B, two sets), `1` two floats (8 B), `2` four floats (16 B, two sets) |
| 4 | `16..19` | Binormal | `4` a packed unit vector (4 B) |
| 7 | `28..31` | A bitmask | `1` a colour (4 B), `4` four blend weights (8 B), `8` four bone indices (4 B) |

The order in memory is **not** the order of the nibbles. It is: position,
normal, colour, texture coordinates, binormal, blend weights, bone indices — so
the colour sits between the normal and the texture coordinates, and the two
skinning fields go at the end.

Adding those sizes reproduces the stride the file states, exactly, on **14 594
of the 14 618 meshes** in disc 1's `ud1.bin`. The other 24 leave four bytes
over, which is the layout rounded up to the next multiple of 16. Two meshes set
a nibble in slot 3 that nothing here explains.

The position readings are the ones session 4 settled against the stated
bounding boxes; what is new is that `4` occupies a fourth component as well,
which is what makes the stride add up.

### The packed unit vectors

Slots 1 and 4 hold one four-byte vector each: **three signed 10-bit components
in a big-endian word, lowest component first**, each divided by 511.

That reading was not taken from a hardware enum. It is the one under which the
vector comes out a unit vector, and it does so to within 0.2 %: the median
`|length - 1|` is **0.0014 over 6 935 532 packed vectors**, which is the
quantisation error of ten bits per axis and nothing more.

The packing leaves two bits over. They are always `1` on a normal, and `1` or
`3` on a binormal, which is where the handedness of the tangent frame sits.

### Texture coordinates

Two components, either 16-bit normalised by 32767 or full floats, in the order
`(u, v)`. About half of each is negative: the coordinates are centred on zero
rather than laid out in the unit square, and the shorts saturate at ±1 on 1.1 %
of components.

### Skinning

Four blend weights as unsigned 16-bit values, then four bone indices as single
bytes. **The weights sum to 65535 on 100.0 % of 2 919 607 skinned vertices** —
which is the cleanest single confirmation in this document, because a wrong
offset or a wrong width breaks it immediately.

### The colour

Four bytes, and the values give it away: `FFFFFFFF`, `FF7F7F7F`, `00FFFFFF`,
`FF999999`. White, mid grey, white with no alpha. A `D3DCOLOR`.

## 5. What was verified

Over all 1 505 `MESH` resources of disc 1's `ud1.bin`, of which 1 438
decompress to an `ASF ` and 67 to a nested NORM archive:

| | |
| --- | ---: |
| Payloads parsed | 1 438 |
| Parse errors | **0** |
| Meshes | 14 618 |
| Descriptor nibbles not accounted for | **2 meshes, slot 3** |
| Meshes whose layout adds up to the stated stride | 14 594 of 14 618 |

### The decode against geometry it did not produce

Every measurement below compares a decoded attribute with something computed
from a different part of the file. A wrong reading of any packed field moves
all of them at once, which is why they are worth stating together.

| Check | Median | Under 15° |
| --- | ---: | ---: |
| Stored normal against the normal of the triangles sharing the vertex | 2.3° | 79.8 % |
| Stored binormal against the stored normal, off square by | 1.1° | 85.7 % |
| Stored binormal against the direction the texture coordinates imply | 8.9° | 67.1 % |

and the blend weights sum to one on **100.0 % of 2 919 607 skinned vertices**.

Two conventions fall out of those numbers rather than being assumed:

* **The triangles are wound the other way round.** Taking the geometric normal
  as `(b-a) × (c-a)` puts it at 179.9° from the stored normal; the other
  winding puts it at 0.4°. `asf.py obj` writes its faces `a-c-b` accordingly.
* **The texture v axis points downwards**, as in Direct3D: the stored vector in
  slot 4 runs *against* increasing v.

### Binormal or tangent?

The vertex data alone cannot tell a binormal apart from a tangent whose texture
coordinates are rotated by ninety degrees: both readings fit every measurement
above equally well.

What separates them is texel density. On meshes whose object carries a single
non-square texture, taking the pair as `(u, v)` and the stored vector as the
binormal gives a median anisotropy of **2.0**; reading the coordinates rotated
gives **7.0**. Artists match texel density, so the first is the reading, and it
is recorded here as a reading rather than a certainty. Rendering a mesh against
its own texture would settle it outright.

### The bounding-box check, from session 4

Per object, over the first 400 payloads:

| Agreement | Objects | |
| --- | ---: | ---: |
| better than 0.1 % | 3 549 | 92.1 % |
| 0.1 to 1 % | 244 | 6.3 % |
| 1 to 10 % | 3 | 0.1 % |
| worse than 10 % | 59 | 1.5 % |

So **98.4 % of objects reproduce their stated bounding box to within one
percent**, and 92 % to within a tenth of one.

The 59 objects that miss by more than 10 % are not scattered at random. The
commonest names among them are `R:M:TRE_BOX_WOOD`, `R:M:TREASURE_BOX` and
`R:M:TRE_BOX_IRON`, followed by morph targets — `R:M:MORPH_BLINKS`,
`R:M:MORPH_ASh`. Both groups are things whose geometry moves: a chest with a
lid that opens, and a blend shape. The likely reading is that the box covers a
pose the stored vertices are not in. That is a reading, not a finding, and it
is the obvious place for the next person to start.

One earlier version of this check divided the error by each axis in turn, which
made every flat object — billboards, decal planes, with one extent of exactly
zero — report an infinite error on a perfect decode. The error is now scaled by
the object's largest extent.

## 6. Implementation

[`tools/asf.py`](../../tools/asf.py):

```
python tools/asf.py tree     <file.asf>          # the chunk tree
python tools/asf.py info     <file.asf>          # summary and bounding-box check
python tools/asf.py obj      <file.asf> out.obj  # positions, UVs, normals
python tools/asf.py textures <file.asf> outdir/  # the embedded AIF textures
python tools/asf.py check    <file.asf> [...]    # measure the vertex decode
```

Getting a file to point it at:

```
python tools/mron.py extract <image> --offset N --length N \
    --tag MESH --decompress out/
```

An extracted texture needs the offset it had inside the ASF, because AIF pixel
data begins at the next 4096-byte boundary of the containing file — `textures`
puts that in the filename and prints the command.
