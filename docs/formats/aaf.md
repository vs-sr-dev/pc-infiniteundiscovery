# AAF — the Aska Animation File

`AAF ` is what every `ANIM` resource holds, and there are more `ANIM`
resources on the disc than of anything else: **5 718 in disc 1's `ud1.bin`,
278 MB in all**, against 1 505 `MESH`. It is the largest format by count and
the second largest by volume.

An AAF does not stand alone. It animates the node tree of an
[ASF scene](asf.md): its records are named after `attr` nodes, and the values
they hold are the same translation, rotation and scale those nodes carry as a
rest pose. That link is what identifies the channels, and it is a check on the
decode that owes nothing to this reader — see
[section 6](#6-what-was-verified).

Everything below was measured on the 900 payloads in `extract/anim/`. All 900
parse and pass every internal consistency check.

## 1. The header

0x24 bytes, big-endian, like everything else in the engine.

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | `AAF ` |
| `+0x04` | 4 | Total length — **zero in every file seen**, unlike ASF and AIF |
| `+0x10` | 4 | Version, `0x16` in all 900 |
| `+0x14` | 2 | Record count |
| `+0x16` | 2 | Duration, in the units a keyframe time uses |
| `+0x1A` | 2 | Animated track count |
| `+0x1C` | 2 | Constant track count |
| `+0x1E` | 2 | Keyframe block count |
| `+0x20` | 4 | Unidentified — larger than the file, so probably a buffer size |

Counts and sizes sit in the **low half of a 32-bit slot**. Most files leave the
high half zero, which makes reading the whole word look right until a file does
not: enough of them set `0x0001` or `0x0200` up there that a 32-bit read walks
off the end of a record. Every count and size in this document is 16-bit.

Then four regions, laid end to end with nothing between them:

```
records          one per animated node
block table      one (offset, time) pair per keyframe block
constant curves  the value of every track that never changes
keyframe blocks  one per entry in the block table
```

## 2. Records and tracks

A **record** is one node. Its header is 0x28 bytes — a track count at `+0x02`,
the record's own size at `+0x04`, and a 0x20-byte NUL-padded name — and its
tracks tile the rest of it exactly.

The names are the artists' own, the same ones that survived into the ASF node
tree:

```
R:WEP_POS  R:WEP_TOPPOS  R:M:SK_WEP01 .. R:M:SK_WEP09  R:M:SdgP
e_Emitter3_chuchu_0  LOGO_Light1  ambientLight2  TITLE  camera1_aim
```

A **track** is one channel of that node. 0x14 bytes, plus 0x10 more when it is
animated:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 2 | Zero, or `0x0200` on a handful of tracks |
| `+0x02` | 2 | Track size |
| `+0x04` | 2 | Flags — see below |
| `+0x06` | 2 | `0x000C` in every track in the corpus |
| `+0x08` | 4 | Target: `0x40` a scalar slot, `0x70` a three-float slot, `0x80` a quaternion slot |
| `+0x0C` | 2 | Channel: **5 translation, 6 rotation, 7 scale** |
| `+0x0E` | 2 | Usually zero |
| `+0x10` | 4 | Key format, four bytes: `[animated, layout, semantic, 0]` |
| `+0x14` | 16 | Animated only: three floats, then a count |

The flags decide where the track's values live:

* `0x20` — the keys are in the keyframe blocks.
* `0x80` — the track never changes; its single value is in the constant region.
* `0x400` — the value is a packed quaternion with no tangent.

`0x20` agrees with the header's animated count on **all 900 files**, which is
what makes it the reliable test rather than "the track is longer than 0x14". A
few tracks carry neither `0x20` nor `0x80`; those are self-contained, with
their payload inline, and they are what makes the two counts in the header not
add up to the number of tracks.

The **target** follows the storage form rather than the channel: a rotation
stored as three Euler floats targets `0x70`, the same slot a translation does,
while a packed quaternion targets `0x80`. So `+0x0C` is the field that says
what a track means.

The last word of an animated track is **the number of keyframe blocks the
track appears in**. It is, for all 4 931 animated tracks in the corpus — an
exact structural check that the block walk and the track walk agree.

## 3. The block table and the constant curves

The block table is `keyframe block count` pairs of `(u32 offset, f32 time)`.
The times ascend, start at zero, and end at or before the header's duration.

The constant region opens with **its own total size as a `u16`**, then one
`u16` offset per constant track in the order the tracks appear, then the data.
The offsets are counted from two bytes into the region — from just past that
size word — and the first of them lands exactly where the offset array ends.
Region start plus the stated size lands exactly on the first keyframe block.

## 4. Keyframe blocks

A block is **one instant**. Its header is a count, then that many
`(u16 track, u16 offset)` pairs; the track number indexes the file's animated
tracks in the order they appear, and the offset is from the start of the block.
A key runs to the next offset, or to the end of the block for the last one — so
the last key in a block also carries whatever padding aligns the next.

A track present in a block has exactly one key there. A track does not have to
appear in every block, which is what the per-track block count is for.

## 5. Key layouts

The byte at track `+0x11` picks the layout, and it fixes the key size. Measured
on every key in the corpus that is not last in its block, so that no padding is
counted:

| `+0x11` | Key | Size |
| ---: | --- | ---: |
| 0 | one float, in-tangent, out-tangent | 12 |
| 1 | one float | 4 |
| 2 | one float | 4 |
| 5 | three floats, in-tangent, out-tangent | 36 |
| 6 | three floats | 12 |
| 7 | three floats | 12 |
| 8 | four floats, in-tangent, out-tangent | 48 |
| 9 | four floats | 16 |
| 10 | four floats | 16 |
| 12 | a packed quaternion | 8 |
| 13 | a packed quaternion and a tangent | 16, or 8 with flag `0x400` |

Where a layout carries tangents the key is **value, in-tangent, out-tangent**,
and the two tangents are equal wherever the curve is smooth.

### The packed quaternion

Eight bytes, of which the top sixteen bits are zero on every one of the 3 736
constant rotations in the corpus. What is left is a 48-bit word holding the
rotation as an **axis and an angle**, and each of its three fields is an angle
quantised the same way — as a fraction of a right angle:

| Bits | Field |
| --- | --- |
| `0..13` | The axis' angle away from the **Y** axis. 16383 = 90° |
| `14..27` | The angle of the axis' xz part away from the **X** axis. 16383 = 90° |
| `28..30` | The signs of z, y, x — one bit each, set means negative |
| `31..47` | The rotation: `w = 1 - (field / 131071)²` |

So

```
|y| = cos(a)            a = (bits 0..13)  / 16383 * 90 degrees
|x| = sin(a) cos(b)     b = (bits 14..27) / 16383 * 90 degrees
|z| = sin(a) sin(b)
q   = (axis * sqrt(1 - w*w), w)
```

Two things about this are worth noticing. The three sign bits mean the two
angles only ever describe the positive octant, which is why fourteen bits each
is enough. And the angle field is squared on the way out, which spends the
precision near `w = 1` — near the identity, where small rotations live and
where a plain fixed-point quaternion is at its worst.

The scheme was not read off a hardware enum. It fell out of pairing constant
rotations against the rest pose of the matching ASF and fitting each field in
turn; the polar angle and the `w` law reproduce their samples exactly, and the
signs explain the rest.

## 6. What was verified

**Every file parses and self-checks.** 900 of 900: records tile the record
table, tracks tile each record, the constant region's stated size lands on the
first block, every key is exactly the size its layout states, every block names
a track that exists, and every animated track appears in exactly the number of
blocks it declares.

**The record names are the scene's node names.** Pairing each ANIM with the
MESH resources of the same archive, 174 of 900 files have every record name in
the node tree — 65.0 % of 146 154 names — and the ones that do not are mostly
particle emitters and lights that live in a resource not extracted here.

**The constants are the rest pose.** This is the check that comes from outside
the decode: an ASF `attr` node stores translation, rotation and scale as full
floats at `+0x50`, `+0x60` and `+0x70`, and a channel that never changes
usually holds exactly those numbers. Over every AAF/ASF pair in the corpus:

| Channel | Reproduces | Of | |
| --- | ---: | ---: | ---: |
| 5, against `attr +0x50` translation | 86 246 | 86 642 | 99.5 % |
| 6, against `attr +0x60` rotation | 52 297 | 56 880 | 91.9 % |
| 7, against `attr +0x70` scale | 14 338 | 14 412 | 99.5 % |

These numbers grew in session 12 without moving. The comparison used to run
over 62 104 translations because 86 model files were reported as having no node
tree at all; they had one, and the ASF reader was refusing to walk it — see
[asf.md §2.1](asf.md#21-a-tree-that-does-not-tile). Fixing that brought 26 346
more channels into the comparison, most of them the game's playable characters,
and **the agreement held**: 99.5 % before and after on translations. A wrong
tree would have collapsed it.

The rotation figure is the weakest of the three, and the residual is not noise
in the decode: sampling it shows the decoded **axis** matching and the angle
differing, which is an animation whose rest pose is genuinely not the scene's.

That table is also what names the channels. Nothing in the file says "this is
a translation"; the numbers do.

**The tangents are tangents.** For a translation curve, the outgoing tangent of
a key should describe where the curve is going. It does, twice over: its length
is the length of the step to the next key — median ratio **0.988** over 60 210
keys — and its direction sits within 5° of the line through the keys either
side on 51 % of them, median 4.7°. That is a Maya smooth tangent scaled to the
segment it opens, which is what the artists' curves would have been exported
as.

## 7. Still open

* The word at `+0x20`, which is larger than the file.
* The three floats at `+0x14` of an animated track. They look like a time
  range — on the opening logo they are `(0, 0, 180)`, `(0, 180, 360)`,
  `(0, 360, 545)` for five nodes that appear one after another — but that is a
  reading of one file.
* The units of time. Durations of 600 and 1 200 with key spacing of 4 suggest
  frames at some rate, but nothing here pins it down.
* The semantic byte at `+0x12` and the channel numbers other than 5, 6 and 7.
  Channels 14, 16, 18, 22, 45 and others occur, on lights, emitters and
  cameras.
* The `0x0200` in the high half of a track's size word.

## 8. Reproducing

```
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 \
       --length 2207584256 --tag ANIM --decompress --limit 900 extract/anim
python tools/aaf.py info     extract/anim/000A4000_008_ANIM.aaf
python tools/aaf.py tree     extract/anim/000A4000_008_ANIM.aaf
python tools/aaf.py pose     extract/anim/000A4000_008_ANIM.aaf --time 40
python tools/aaf.py check    "extract/anim/*.aaf"
python tools/aaf.py rest     "extract/anim/*.aaf" --models "extract/models/*.asf"
```
