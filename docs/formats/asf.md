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
count. `asf.py` treats a disagreement as an error, and across the 4 398 meshes
of the 400-payload sample it never fired: the two always agree. The stride is
not fixed, though — 12, 16, 20, 24, 28, 32, 36, 40 and 44 all occur.

Both data offsets land the bulk data on a 4096-byte boundary of the file.

### Position

The low nibble of the descriptor at `+0x04` says how the position is stored:

| Nibble | Position |
| --- | --- |
| `0x8` | Three 16-bit half floats (in a four-component slot) |
| `0x1` | Three 32-bit floats |
| `0x4` | Three 32-bit floats |

No other value occurs. The mapping was not read off a hardware format enum; it
was decided by which reading reproduces each object's stated bounding box, and
the split is clean — every mesh in the sample falls into one of the three.

The rest of the vertex — normals, texture coordinates, skinning weights — is
**not understood**. Several readings of the remaining fields were tried against
the mesh's own texture, and none produced UV islands that trace what is drawn
there, so they are recorded as unknown rather than guessed at. `asf.py obj`
exports positions and triangles only.

## 5. What was verified

Over the first 400 `MESH` resources of disc 1's `ud1.bin`:

| | |
| --- | ---: |
| Payloads parsed | 400 |
| Walks closing on `eof_` | **400** |
| Parse errors | **0** |
| Objects | 3 855 |
| Meshes | 4 398, all carrying vertex data |
| Vertices | 1 025 173 |
| Triangles | 1 304 004 |
| Embedded textures | 1 253 |
| Meshes with an out-of-range index | 2 |
| Position format recognised | 4 398 of 4 398 -- 3 162 half, 1 236 float |
| Vertex strides seen | 12, 16, 20, 24, 28, 32, 36, 40, 44 |

And the bounding-box check, per object:

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
python tools/asf.py obj      <file.asf> out.obj  # positions and triangles
python tools/asf.py textures <file.asf> outdir/  # the embedded AIF textures
```

Getting a file to point it at:

```
python tools/mron.py extract <image> --offset N --length N \
    --tag MESH --decompress out/
```

An extracted texture needs the offset it had inside the ASF, because AIF pixel
data begins at the next 4096-byte boundary of the containing file — `textures`
puts that in the filename and prints the command.
