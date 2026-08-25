#!/usr/bin/env python3
"""
asf.py -- reader for ASF, the Aska Scene File.

`ASF ` is what every `MESH` resource decompresses to -- 916 of the 1 812
compressed blocks in disc 1's `ud1.bin`, and the largest single format in the
game. Despite the tag it is not one mesh but a small scene: geometry, the
materials it uses, the textures those materials reference, and a named node
tree tying them together.

Nothing here is shared with Microsoft's ASF container. tri-Ace got there first
by fifteen years, and the collision is only in the three letters.

The chunk tree
--------------
An ASF is a tree of chunks with a uniform 16-byte header, big-endian:

    +0x00  4  tag, four printable ASCII characters
    +0x04  4  content size, header included
    +0x08  4  zero in everything seen so far
    +0x0C  4  step to the next sibling; zero means "same as content size"

The two size fields differ only when a chunk's content is not a multiple of 16
-- `bnpl` is 0x14 bytes of content in a 0x20-byte slot -- so the step is the
content size rounded up. Walking with the step lands exactly on the end of the
parent, every time, and the file ends with a 0x10-byte `eof_`. That exactness
is what makes the format safe to parse: there is no need to guess.

A chunk's children do not necessarily start right after the header. Several
tags carry a fixed payload first -- `ao__` 0xA0 bytes of it, `tree` 0xB0,
`mess` 0x10 -- so this reader finds the child region by looking for the offset
from which chunk headers tile the rest of the body exactly. A wrong offset
fails almost immediately, which is why searching for it is safe.

An embedded `AIF ` chunk is an AIF payload exactly as `aif.py` reads one, with
one catch: AIF pixel data starts at the next 4096-byte boundary of the file it
sits in, so a texture extracted out of an ASF needs the offset it came from.
`textures` puts that in the filename and prints the command.

    ASF                      the file
      ao__                   one object: bounds, then everything it needs
        AIF                  an embedded texture, in the AIF format
        ml__ / mats          materials (see below)
        bnpl                 bone pool
        mess                 one mesh
          bnpi               bone pool indices
          idxl               triangle indices
          vlas               vertices
        rl__                 render list
      tree                   the node graph
        attr                 one named node
      modf / extl            small, unexamined
      eof_                   end marker

Skinning and the bone pool
--------------------------
A skinned vertex carries four blend weights and four one-byte bone indices,
and those indices are not node numbers. They index the mesh's own `bnpi`, a
list of 16-bit numbers; those index the object's `bnpl`; and `bnpl` holds node
numbers into the file's `tree`. Three levels, so that a mesh can address at
most 256 bones with a single byte each while the file as a whole carries
hundreds.

Both chunks are bare arrays of 16-bit numbers with no count of their own -- the
chunk size gives it, rounded up to a multiple of four, so a pool with an odd
number of entries has a trailing zero that is padding rather than node 0.

The chain closes on the whole corpus: every `bnpl` entry lands inside its own
file's node tree (261 of 261 objects), every `bnpi` entry lands inside its
object's pool (642 of 642 meshes) and every vertex bone index lands inside its
mesh's `bnpi` (642 of 642). There is no shared skeleton resource -- session 9
thought there was, because 44 objects appeared to overshoot a tree that the
reader was refusing to walk. See `Chunk._counted_children`.

Geometry
--------
`mess` opens with two 16-bit counts: vertices, then indices. Both `idxl` and
`vlas` state where their bulk data sits as an offset from the start of their
own chunk -- at +0x10 for `idxl`, +0x1C for `vlas` -- and those offsets always
land the data on a 4096-byte boundary in the file.

Indices are 16-bit, and the count is always a multiple of three: triangle
lists, not strips. The vertex stride is stated in the top half of the word at
vlas +0x08 and also falls out of dividing the data region by the vertex count;
the two agree everywhere. It is not fixed -- 12 through 44 bytes all occur.

A vertex is a position followed by whatever the descriptor at vlas +0x04 says.
That descriptor is a set of four-bit fields: which field a nibble sits in says
which attribute, and the value says how it is stored.

    slot 0   position   1 = three floats, 4 = four floats, 8 = four halfs
    slot 1   normal     4 = a packed unit vector, four bytes
    slot 2   texcoord   9 = two shorts, A = four shorts (two sets),
                        1 = two floats, 2 = four floats (two sets)
    slot 4   binormal   4 = a packed unit vector, four bytes
    slot 7   a bitmask: 1 = a four-byte colour, 4 = four 16-bit blend weights,
                        8 = four one-byte bone indices

The order in memory is not the order of the nibbles: the colour goes between
the normal and the texture coordinates, and the two skinning fields go last.
Adding the sizes reproduces the stated stride exactly on 14 594 of the 14 618
meshes in disc 1's `ud1.bin`; the other 24 round up to the next multiple of 16.
Two meshes set a nibble in slot 3 that nothing here explains.

A packed unit vector is three signed 10-bit components in a big-endian word,
lowest component first, each divided by 511. Nothing was read off a hardware
enum -- the reading is the one that makes the vector a unit vector, and it is
one to within 0.2%: median |length - 1| is 0.0014 over 6 935 532 of them.

Which is only worth anything because the same numbers then agree with geometry
this reader did not produce. Measured over all 14 618 meshes:

  * the stored normal against the normal of the triangles sharing the vertex:
    median 2.3 degrees;
  * the stored binormal against the stored normal: 1.1 degrees off square;
  * the stored binormal against the direction the texture coordinates imply:
    median 8.9 degrees;
  * the four blend weights sum to one on 100.0% of 2 919 607 skinned vertices.

Two conventions fall out of those measurements. The triangles are wound the
other way round -- the geometric normal comes out opposite to the stored one,
so `obj` writes its faces a-c-b. And the stored vector in slot 4 runs *against*
the direction of increasing v, which is what a texture v axis pointing
downwards gives, as in Direct3D.

That slot 4 holds the binormal rather than the tangent is a reading rather than
a certainty: the vertex data alone cannot tell a binormal apart from a tangent
with the texture coordinates rotated by ninety degrees. What settles it is that
the plain reading keeps texel density isotropic on meshes whose texture is not
square, and the rotated one stretches it by a factor of about 3.5.

Materials
---------
`ml__` is a list of `mats` chunks and a `mats` is one material. What ties a
mesh to one is a signed 32-bit displacement at mess +0x14, counted from the
start of the mesh chunk. It lands on a `mats` for every one of the 4 176 meshes
in the corpus, and 57% of the time it lands in a *different* object's `ml__`,
which is how one file shares a material between several objects.

Two things the pointer did not produce agree with it. The meshes that share a
material almost always share a vertex format -- 1 755 of 1 794 materials are
used by meshes of one single descriptor -- and a mesh has texture coordinates
exactly when its material has textures, on 4 172 of the 4 176 meshes. Neither
would hold if the displacement were being read wrongly.

A material's own layout is four sections after a 0xB0-byte header: a shader
program block, a table of constant bindings 8 bytes an entry, the float
constants themselves 16 bytes a row, and a table of texture references 24 bytes
an entry. Only the first, second and fourth have stated offsets; the constants
simply follow the bindings, rounded up to 16. Laying it out that way and adding
the lengths reproduces the start of the next material exactly on 1 793 of the
1 794 materials, which is the check that the reading is right.

The first eight bytes of a texture reference are the same eight bytes that sit
at AIF +0x20: the four-character asset name, and the word beside it that had
never been identified. 90.3% of references resolve to a texture embedded in the
same file; the rest name one that lives in another resource.

The constants read as an ordinary shader. The first three rows of the first
material read here are 0.8/0.8/0.8, 0.2/0.2/0.2 and 1/1/1 with 20 in the fourth
component -- diffuse, ambient, specular and a specular power -- and the render
list beside them names the node a "blinn".

`rl__` holds the shading network the artists built, one `rnel` per node, each
with its name and a type byte. The type byte is corroborated from outside the
artists' naming: types 0x1B, 0x06, 0x0A and 0x07 are marschner, ashikhmin,
normal map and double sided, and `MarschnerShader`, `AshikhminShader`,
`NormalMap` and `DoubleSided` are all strings in the retail executable.

Usage
-----
    python tools/asf.py tree      <file.asf>
    python tools/asf.py info      <file.asf>
    python tools/asf.py materials <file.asf>
    python tools/asf.py obj       <file.asf> <out.obj> [--textures]
    python tools/asf.py textures  <file.asf> <outdir>
    python tools/asf.py check     <file.asf> [...]
"""

from __future__ import annotations

import argparse
import math
import os
import struct
import sys

MAGIC = b"ASF "
HEADER = 16
EOF_TAG = "eof_"

# Bytes that may appear in a chunk tag.
TAG_BYTES = set(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_ ")

# Fixed payload sizes observed before a chunk's children begin. The reader does
# not rely on these -- it finds the child region by tiling -- but they are what
# the search converges on.
KNOWN_PAYLOADS = {"ao__": 0xA0, "tree": 0xB0, "mess": 0x10}

TAG_MEANINGS = {
    "ao__": "object",
    "AIF ": "embedded texture",
    "ml__": "material list",
    "mats": "materials",
    "bnpl": "bone pool",
    "bnpi": "bone pool indices",
    "mess": "mesh",
    "idxl": "triangle indices",
    "vlas": "vertices",
    "rl__": "shading network",
    "rnel": "shading node",
    "tree": "node graph",
    "attr": "node",
    "modf": "unexamined",
    "extl": "unexamined",
    "eof_": "end marker",
}


class AsfError(Exception):
    pass


def half_float(bits):
    sign = -1.0 if bits >> 15 else 1.0
    exponent = (bits >> 10) & 0x1F
    mantissa = bits & 0x3FF
    if exponent == 0:
        return sign * mantissa * 2.0 ** -24
    if exponent == 31:
        return sign * float("inf")
    return sign * (1.0 + mantissa / 1024.0) * 2.0 ** (exponent - 15)


def is_tag(raw):
    return len(raw) == 4 and all(b in TAG_BYTES for b in raw) and not raw.isspace()


class Chunk:
    __slots__ = ("tag", "offset", "size", "step", "blob")

    def __init__(self, blob, tag, offset, size, step):
        self.blob = blob
        self.tag = tag
        self.offset = offset
        self.size = size
        self.step = step

    @property
    def body(self):
        return self.offset + HEADER

    @property
    def end(self):
        return self.offset + self.step

    def name(self, at=0):
        """A NUL-terminated ASCII name inside the body, if there is one."""
        raw = self.blob[self.body + at:self.body + at + 16].split(b"\0")[0]
        if raw and all(32 <= b < 127 for b in raw):
            return raw.decode("latin-1")
        return None

    def u32(self, at):
        return struct.unpack_from(">I", self.blob, self.body + at)[0]

    def u16(self, at):
        return struct.unpack_from(">H", self.blob, self.body + at)[0]

    def floats(self, at, count):
        return struct.unpack_from(">%df" % count, self.blob, self.body + at)

    def raw(self):
        return bytes(self.blob[self.offset:self.offset + self.size])

    def children(self):
        start = self._child_start()
        if start is not None:
            return list(walk(self.blob, start, self.end))
        return self._counted_children()

    def _child_start(self):
        """Offset where this chunk's children begin, or None if it has no tree.

        Found by requiring an exact tiling of the rest of the body, which a
        wrong offset almost never produces.
        """
        limit = min(0x200, self.end - self.body)
        for payload in range(0, limit + 1, 16):
            if _tiles(self.blob, self.body + payload, self.end):
                return self.body + payload
        return None

    def _counted_children(self):
        """Children of a `tree` that states its own count and has a tail.

        A node graph puts its `attr` chunks at body+0xB0 and may follow them
        with a block that is not chunks at all -- 86 of the 369 files in the
        model corpus do, from 192 bytes to 3 600. That block makes the exact
        tiling above fail, and reading it as "this file has no node tree" is
        what hid ten character skeletons until session 12.

        The count at body+0x00 is the number of nodes, and it agrees with the
        run of `attr` chunks on all 369 trees, so the count is what to trust.
        """
        if self.tag != "tree" or self.end - self.body < TREE_NODES + 4:
            return []
        stated = struct.unpack_from(">I", self.blob, self.body + TREE_NODES)[0]
        out, pos = [], self.body + TREE_CHILDREN
        while len(out) < stated and self.end - pos >= HEADER:
            if self.blob[pos:pos + 4] != b"attr":
                break
            size, _reserved, step = struct.unpack_from(">III", self.blob, pos + 4)
            step = step or size
            if step < HEADER or pos + step > self.end:
                break
            out.append(Chunk(self.blob, "attr", pos, size, step))
            pos += step
        return out if len(out) == stated else []

    def tail(self):
        """The bytes after this chunk's children, which are not themselves
        chunks. Empty unless the children were found by count."""
        kids = self.children()
        if not kids:
            return b""
        after = kids[-1].offset + kids[-1].step
        return bytes(self.blob[after:self.end])


# A `tree` states its node count at body+0x00 and puts its `attr` chunks at
# body+0xB0, on all 369 trees in the model corpus.
TREE_NODES = 0x00
TREE_CHILDREN = 0xB0


def _tiles(blob, start, end):
    """Do chunk headers cover [start, end), give or take trailing padding?

    A chunk's step is usually its content size rounded up to 16, but not
    always: `vlas` states an unrounded one, which leaves a few zero bytes
    before the parent ends. So a run is accepted if it stops less than one
    header short and everything left is zero.
    """
    pos = start
    count = 0
    while end - pos >= HEADER:
        if not is_tag(blob[pos:pos + 4]):
            return False
        size, _reserved, step = struct.unpack_from(">III", blob, pos + 4)
        step = step or size
        if step < HEADER or pos + step > end:
            return False
        pos += step
        count += 1
    return count > 0 and not any(blob[pos:end])


def walk(blob, start, end):
    """Yield the chunks laid end to end in [start, end).

    Stops on a residue smaller than one header, which is padding.
    """
    pos = start
    while end - pos >= HEADER:
        raw = blob[pos:pos + 4]
        if not is_tag(raw):
            raise AsfError("no chunk tag at 0x%X (found %r)" % (pos, raw))
        size, _reserved, step = struct.unpack_from(">III", blob, pos + 4)
        step = step or size
        if step < HEADER or pos + step > end:
            raise AsfError("chunk %r at 0x%X overruns its parent"
                           % (raw.decode("latin-1"), pos))
        yield Chunk(blob, raw.decode("latin-1"), pos, size, step)
        pos += step


# The vlas descriptor is a set of four-bit fields. Which field a nibble sits in
# says which attribute it describes; its value says how that attribute is
# stored. Sizes are what the stride confirms: adding the sizes below reproduces
# the stated stride on every mesh in the corpus but the handful noted in the
# docs, which round up to a multiple of 16.
SLOT_POSITION, SLOT_NORMAL, SLOT_TEXCOORD, SLOT_BINORMAL, SLOT_EXTRA = 0, 1, 2, 4, 7

# Slot 0. The three readings were settled in session 4 against each object's
# stated bounding box; 0x4 turns out to occupy a fourth component as well.
POSITION_FORMAT = {0x1: ("float3", 12), 0x4: ("float4", 16), 0x8: ("half4", 8)}

# Slots 1 and 4: one packed unit vector each, three signed 10-bit components in
# a big-endian word, lowest component first. Slot 1 is the normal and slot 4 is
# the binormal. The two bits the packing leaves over are always 1 on a normal,
# and 1 or 3 on a binormal, which is where the handedness of the frame sits.
VECTOR_FORMAT = {0x4: ("dec3n", 4)}

# Slot 2, as (reading, total size, number of sets).
TEXCOORD_FORMAT = {0x1: ("float2", 8, 1), 0x2: ("float2", 16, 2),
                   0x9: ("short2", 4, 1), 0xA: ("short2", 8, 2)}

# Slot 7 is a bitmask rather than a format code. The colour sits directly after
# the normal; the two skinning fields sit at the end of the vertex.
EXTRA_COLOUR, EXTRA_WEIGHTS, EXTRA_INDICES = 0x1, 0x4, 0x8


class VertexFormat:
    """What a descriptor says a vertex holds, and where each part sits."""

    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.fields = []          # (name, reading, offset, size)
        self.size = 0
        self.unknown = []
        nibble = lambda slot: (descriptor >> (4 * slot)) & 0xF

        extra = nibble(SLOT_EXTRA)
        texcoord = TEXCOORD_FORMAT.get(nibble(SLOT_TEXCOORD))
        self.texcoord_sets = texcoord[2] if texcoord else 0

        # Memory order, which is not the order of the nibbles: the colour goes
        # between the normal and the texture coordinates, and the two skinning
        # fields go last.
        self._add(SLOT_POSITION, "position", POSITION_FORMAT.get(nibble(SLOT_POSITION)))
        self._add(SLOT_NORMAL, "normal", VECTOR_FORMAT.get(nibble(SLOT_NORMAL)))
        if extra & EXTRA_COLOUR:
            self._add(None, "colour", ("d3dcolor", 4))
        self._add(SLOT_TEXCOORD, "texcoord", texcoord and texcoord[:2])
        self._add(SLOT_BINORMAL, "binormal", VECTOR_FORMAT.get(nibble(SLOT_BINORMAL)))
        if extra & EXTRA_WEIGHTS:
            self._add(None, "weights", ("ushort4n", 8))
        if extra & EXTRA_INDICES:
            self._add(None, "bones", ("ubyte4", 4))

        for slot in (3, 5, 6):
            if nibble(slot):
                self.unknown.append((slot, nibble(slot)))
        if extra & ~(EXTRA_COLOUR | EXTRA_WEIGHTS | EXTRA_INDICES):
            self.unknown.append((SLOT_EXTRA, extra))

    def _add(self, slot, name, spec):
        if spec is None:
            if slot is not None and (self.descriptor >> (4 * slot)) & 0xF:
                self.unknown.append((slot, (self.descriptor >> (4 * slot)) & 0xF))
            return
        reading, size = spec
        self.fields.append((name, reading, self.size, size))
        self.size += size

    def offset(self, name):
        for field, _reading, offset, _size in self.fields:
            if field == name:
                return offset
        return None

    def reading(self, name):
        for field, reading, _offset, _size in self.fields:
            if field == name:
                return reading
        return None

    def __str__(self):
        return ", ".join("%s@%d %s" % (n, o, r) for n, r, o, _s in self.fields) \
            or "nothing recognised"


def _texcoord(blob, where, reading, index):
    """One texture coordinate pair, stored in the order (u, v)."""
    if reading == "float2":
        return struct.unpack_from(">2f", blob, where + index * 8)
    return tuple(v / 32767.0 for v in
                 struct.unpack_from(">2h", blob, where + index * 4))


def dec3n(word):
    """A packed unit vector: three signed 10-bit components, lowest first."""
    def signed(value):
        return value - 1024 if value >= 512 else value
    return tuple(signed((word >> shift) & 0x3FF) / 511.0
                 for shift in (0, 10, 20))


class Mesh:
    def __init__(self, chunk):
        self.chunk = chunk
        self.vertex_count = chunk.u16(0)
        self.index_count = chunk.u16(2)
        self.vertices = []
        self.normals = []
        self.binormals = []
        self.handedness = []
        self.uvs = []
        self.colours = []
        self.weights = []
        self.bones = []
        self.indices = []
        self.bone_indices = []
        self.stride = 0
        self.descriptor = 0
        self.format = None
        self.position_format = None
        # A signed 32-bit displacement from the start of this chunk to the
        # `mats` that shades it. It reaches outside the object: 57% of meshes
        # point into another object's material list, which is how one ASF
        # shares a material between several objects.
        self.material_offset = chunk.offset + struct.unpack_from(
            ">i", chunk.blob, chunk.offset + 0x14)[0]
        for child in chunk.children():
            if child.tag == "vlas" and self.vertex_count:
                self._read_vertices(child)
            elif child.tag == "bnpi":
                # A vertex's bone byte indexes this list, and this list indexes
                # the object's `bnpl`, which indexes the file's node tree.
                count = (child.size - HEADER) // 2
                self.bone_indices = list(struct.unpack_from(
                    ">%dH" % count, chunk.blob, child.offset + HEADER))
            elif child.tag == "idxl" and self.index_count:
                offset = child.u32(0x00)
                self.indices = list(struct.unpack_from(
                    ">%dH" % self.index_count, chunk.blob, child.offset + offset))

    def _read_vertices(self, chunk):
        blob = chunk.blob
        self.descriptor = chunk.u32(0x04)
        # The stride is stated in the top half of the word at +0x08, and it
        # also falls out of dividing the data region by the vertex count. The
        # two agreed on every mesh measured, so disagreement means a misparse.
        declared = chunk.u16(0x08)
        offset = chunk.u32(0x0C)
        computed = (chunk.step - offset) // self.vertex_count
        if declared and declared != computed:
            raise AsfError("vlas states a stride of %d but the data gives %d"
                           % (declared, computed))
        self.stride = declared or computed
        if self.stride < 6:
            raise AsfError("vertex stride %d is too small" % self.stride)

        self.format = VertexFormat(self.descriptor)
        self.position_format = self.format.reading("position")
        if self.format.size > self.stride:
            raise AsfError("descriptor 0x%08X needs %d bytes but the stride is %d"
                           % (self.descriptor, self.format.size, self.stride))
        base = chunk.offset + offset
        for i in range(self.vertex_count):
            self._read_vertex(blob, base + i * self.stride)

    def _read_vertex(self, blob, at):
        fmt = self.format
        for name, reading, offset, _size in fmt.fields:
            where = at + offset
            if name == "position":
                if reading == "half4":
                    self.vertices.append(tuple(
                        half_float(struct.unpack_from(">H", blob, where + a * 2)[0])
                        for a in range(3)))
                else:
                    self.vertices.append(struct.unpack_from(">3f", blob, where))
            elif name in ("normal", "binormal"):
                word = struct.unpack_from(">I", blob, where)[0]
                (self.normals if name == "normal" else self.binormals).append(dec3n(word))
                if name == "binormal":
                    self.handedness.append(1 if word >> 30 == 1 else -1)
            elif name == "texcoord":
                self.uvs.append([_texcoord(blob, where, reading, s)
                                 for s in range(fmt.texcoord_sets)])
            elif name == "colour":
                self.colours.append(struct.unpack_from(">I", blob, where)[0])
            elif name == "weights":
                self.weights.append(tuple(
                    v / 65535.0 for v in struct.unpack_from(">4H", blob, where)))
            elif name == "bones":
                self.bones.append(struct.unpack_from(">4B", blob, where))

    @property
    def triangles(self):
        for i in range(0, len(self.indices) - 2, 3):
            yield self.indices[i], self.indices[i + 1], self.indices[i + 2]


# The type byte at rnel +0x30. The names are self-identifying: every node of
# type 3 is called some variation of "phong", every node of type 0x1B some
# variation of "marschner". Four of them are corroborated by strings in the
# retail executable -- `MarschnerShader`, `AshikhminShader`, `NormalMap`,
# `DoubleSided` -- which is a source that owes nothing to the artists' naming.
RENDER_NODE_TYPES = {
    0x01: "shading group",
    0x03: "phong",
    0x04: "blinn",
    0x05: "anisotropic phong",
    0x06: "ashikhmin",
    0x07: "double sided",
    0x09: "texture",
    0x0A: "normal map",
    0x0C: "blend colours",
    0x0D: "calc vectors",
    0x0E: "fresnel",
    0x0F: "sampling offset",
    0x12: "lambert",
    0x1B: "marschner",
}

MATERIAL_HEADER = 0xB0


def _align_up(value, to):
    return (value + to - 1) // to * to


class TextureRef:
    """One 24-byte entry in a material's texture list.

    The first eight bytes are the key, and they are the same eight bytes that
    sit at +0x20 of an AIF header -- the four-character asset name that
    `aif.py` already reads, followed by the word next to it that had never been
    identified. Together they name a texture. 90.3% of the references in the
    corpus resolve to an AIF embedded in the same file; the rest name one that
    lives in another resource.
    """

    __slots__ = ("key", "usage", "channel", "index")

    def __init__(self, blob, at, index):
        self.key = bytes(blob[at:at + 8])
        self.usage = struct.unpack_from(">H", blob, at + 8)[0]
        self.channel = struct.unpack_from(">I", blob, at + 12)[0]
        self.index = index

    @property
    def name(self):
        raw = self.key[:4]
        if all(32 <= b < 127 for b in raw):
            return raw.decode("latin-1")
        return raw.hex()

    @property
    def asset(self):
        return struct.unpack_from(">I", self.key, 4)[0]

    def __str__(self):
        return "%s:%08X" % (self.name, self.asset)


class Material:
    """One `mats`: what a mesh is shaded with.

    The 0xB0-byte header states, in order, how many shader constants the
    material carries, how many textures it references, and where each of its
    three tables begins:

        +0x16  1  constant count
        +0x18  1  texture reference count
        +0x19  1  count of a fourth table, 48 bytes an entry
        +0x1C  4  offset of the shader program block; always 0xB0, so the
                  block begins the moment the header ends
        +0x20  4  offset of the constant binding table, 8 bytes an entry
        +0x2C  4  offset of the texture reference table, 24 bytes an entry

    The float constants are not given an offset of their own: they follow the
    binding table, rounded up to 16, one 16-byte row per binding. That is not
    an assumption -- laying the sections out this way and adding up their
    lengths reproduces the start of the next material exactly on 1 793 of the
    1 794 materials in the corpus.

    One wrinkle, the same one `vlas` has: the step in the chunk header stops
    short of the texture reference table on 1 377 materials, so a walk that
    trusts it lands in the middle of the data. This reader computes the extent
    instead.
    """

    def __init__(self, blob, offset):
        self.blob = blob
        self.offset = offset
        size = struct.unpack_from(">I", blob, offset + 4)[0]
        if size != MATERIAL_HEADER:
            raise AsfError("mats at 0x%X states a header of %d bytes"
                           % (offset, size))
        self.constant_count = blob[offset + 0x16]
        self.texture_count = blob[offset + 0x18]
        self.transform_count = blob[offset + 0x19]
        self.program_offset = struct.unpack_from(">I", blob, offset + 0x1C)[0]
        self.binding_offset = struct.unpack_from(">I", blob, offset + 0x20)[0]
        self.texture_offset = struct.unpack_from(">I", blob, offset + 0x2C)[0]

        # Each binding is (group, index, width) and a word that runs 0x60,
        # 0x68, 0x70 ... in step with the entry number on every material seen,
        # so it carries no information this reader can use yet.
        self.bindings = []
        for i in range(self.constant_count):
            at = offset + self.binding_offset + i * 8
            self.bindings.append((blob[at + 1], blob[at + 2], blob[at + 3],
                                  struct.unpack_from(">I", blob, at + 4)[0]))

        self.constants_offset = _align_up(
            self.binding_offset + 8 * self.constant_count, 16)
        self.constants = [
            struct.unpack_from(">4f", blob, offset + self.constants_offset + i * 16)
            for i in range(self.constant_count)]

        self.textures = []
        if self.texture_offset:
            for i in range(self.texture_count):
                self.textures.append(
                    TextureRef(blob, offset + self.texture_offset + i * 24, i))

    @property
    def end(self):
        """Where this material stops, computed rather than taken from the step."""
        last = self.constants_offset + 16 * self.constant_count
        if self.texture_offset:
            last = max(last, self.texture_offset + 24 * self.texture_count)
        return self.offset + _align_up(last, 16) + 48 * self.transform_count


class RenderNode:
    """One `rnel`: a named node of the shading network the artists built.

    The name survived export untouched, the same way the node names in `tree`
    did, so the list reads as a Maya shading graph: a shading group, the
    shader hanging off it, and the file textures hanging off that.

        R:M:Material_Book  R:M:Blinn_Book  R:M:Tex_Book  R:M:Tex_Normal

    The byte at +0x30 types the node and the byte at +0x32 counts the four-byte
    entries that follow at +0x34, which have not been read.
    """

    __slots__ = ("chunk", "name", "kind", "entries")

    def __init__(self, chunk):
        self.chunk = chunk
        self.name = chunk.name(0) or "<unnamed>"
        self.kind = chunk.blob[chunk.offset + 0x30]
        count = chunk.blob[chunk.offset + 0x32]
        self.entries = [struct.unpack_from(">I", chunk.blob,
                                           chunk.offset + 0x34 + i * 4)[0]
                        for i in range(count)]

    @property
    def type_name(self):
        return RENDER_NODE_TYPES.get(self.kind, "type 0x%02X" % self.kind)


class Object3D:
    """One `ao__`: an oriented bounding box, meshes, and embedded textures."""

    def __init__(self, chunk):
        self.chunk = chunk
        self.sphere = chunk.floats(0x00, 4)        # centre xyz, radius
        self.centre = chunk.floats(0x10, 3)
        self.axes = [chunk.floats(0x20 + i * 0x10, 3) for i in range(3)]
        self.extents = chunk.floats(0x50, 3)
        self.name = chunk.name(0x80)
        self.bone_pool = []
        self.meshes = []
        self.textures = []
        self.material_lists = []
        self.render_nodes = []
        for child in chunk.children():
            if child.tag == "bnpl":
                count = (child.size - HEADER) // 2
                self.bone_pool = list(struct.unpack_from(
                    ">%dH" % count, chunk.blob, child.offset + HEADER))
            elif child.tag == "mess":
                self.meshes.append(Mesh(child))
            elif child.tag == "AIF ":
                self.textures.append(child)
            elif child.tag == "ml__":
                self.material_lists.append(child)
            elif child.tag == "rl__":
                self.render_nodes.extend(RenderNode(c) for c in child.children()
                                         if c.tag == "rnel")

    def extent_error(self):
        """Largest disagreement between stated and measured extents.

        The bounding box was written in 32-bit floats by whatever exported the
        model, from geometry this reader never sees except as the vertex data.
        So reproducing it is a check against numbers from outside the decode.

        The error is scaled by the object's *largest* extent rather than by
        each axis in turn. Plenty of objects here are flat -- billboards, decal
        planes -- with one extent of exactly zero, and dividing by that turns a
        perfect decode into an infinite error.
        """
        points = [v for mesh in self.meshes for v in mesh.vertices]
        if not points:
            return None
        scale = max(abs(e) for e in self.extents) or 1.0
        worst = 0.0
        for axis, extent in zip(self.axes, self.extents):
            try:
                measured = max(abs(sum(axis[k] * (p[k] - self.centre[k])
                                       for k in range(3))) for p in points)
            except (OverflowError, ValueError):
                return float("inf")
            worst = max(worst, abs(measured - extent) / scale)
        return worst


class AsfFile:
    def __init__(self, data):
        if data[:4] != MAGIC:
            raise AsfError("not an ASF payload")
        self.data = data
        self.total_size = struct.unpack_from(">I", data, 4)[0]
        if self.total_size > len(data):
            raise AsfError("header claims %d bytes, file has %d"
                           % (self.total_size, len(data)))
        self.chunks = list(walk(data, 0x20, self.total_size))
        self.objects = [Object3D(c) for c in self.chunks if c.tag == "ao__"]
        self.materials = self._read_materials()
        self.texture_index = {}
        for obj in self.objects:
            for chunk in obj.textures:
                key = bytes(data[chunk.offset + 0x20:chunk.offset + 0x28])
                self.texture_index.setdefault(key, chunk)

    def _read_materials(self):
        """Every `mats` in the file, keyed by offset.

        Materials are read from every `ml__` in the file rather than per
        object, because a mesh's material pointer reaches across objects. A
        `mats` is found by its tag on a 16-byte boundary and then measured; the
        measured extents tile each `ml__` exactly, which is the check that the
        layout in `Material` is right.
        """
        found = {}
        for obj in self.objects:
            for chunk in obj.material_lists:
                at = chunk.offset + HEADER
                while at <= chunk.end - HEADER:
                    if self.data[at:at + 4] == b"mats":
                        material = Material(self.data, at)
                        found[at] = material
                        at = max(material.end, at + 16)
                    else:
                        at += 16
        return found

    def material_of(self, mesh):
        return self.materials.get(mesh.material_offset)

    def texture_of(self, ref):
        """The embedded AIF a texture reference names, if it is in this file."""
        return self.texture_index.get(ref.key)

    @property
    def closed(self):
        """True if the top-level walk ended on an `eof_`, as it should."""
        return bool(self.chunks) and self.chunks[-1].tag == EOF_TAG

    def nodes(self):
        for chunk in self.chunks:
            if chunk.tag != "tree":
                continue
            for child in chunk.children():
                if child.tag == "attr":
                    yield child.name() or "<unnamed>"


def load(path):
    with open(path, "rb") as fh:
        return AsfFile(fh.read())


# -- commands --------------------------------------------------------------

def _print_tree(chunks, depth, limit, printed):
    for chunk in chunks:
        if printed[0] >= limit:
            return
        printed[0] += 1
        name = chunk.name()
        meaning = TAG_MEANINGS.get(chunk.tag, "")
        print("%s%-5s 0x%-8X %-18s %s"
              % ("  " * depth, chunk.tag, chunk.size, meaning,
                 "%r" % name if name else ""))
        _print_tree(chunk.children(), depth + 1, limit, printed)


def cmd_tree(args):
    asf = load(args.file)
    print("ASF   0x%-8X %s" % (asf.total_size,
                               "exact" if asf.total_size == os.path.getsize(args.file)
                               else "file is padded"))
    _print_tree(asf.chunks, 1, args.limit, [0])
    print("walk %s" % ("closed on eof_" if asf.closed else "did NOT reach an eof_"))
    return 0


def cmd_info(args):
    asf = load(args.file)
    meshes = [m for o in asf.objects for m in o.meshes]
    vertices = sum(m.vertex_count for m in meshes)
    triangles = sum(m.index_count // 3 for m in meshes)
    textures = sum(len(o.textures) for o in asf.objects)
    strides = sorted({m.stride for m in meshes if m.stride})
    print("size      : %d bytes, walk %s"
          % (asf.total_size, "closed on eof_" if asf.closed else "DID NOT CLOSE"))
    print("objects   : %d" % len(asf.objects))
    print("meshes    : %d, %d vertices, %d triangles" % (len(meshes), vertices, triangles))
    print("stride    : %s" % (", ".join("%d bytes" % s for s in strides) or "n/a"))
    layouts = {}
    for mesh in meshes:
        if mesh.format is not None:
            layouts.setdefault(str(mesh.format), 0)
            layouts[str(mesh.format)] += 1
    for layout, count in sorted(layouts.items(), key=lambda kv: -kv[1])[:4]:
        print("vertex    : %s  (%d meshes)" % (layout, count))
    print("textures  : %d embedded AIF" % textures)
    resolved = sum(1 for m in meshes if asf.material_of(m) is not None)
    refs = [r for mat in asf.materials.values() for r in mat.textures]
    print("materials : %d, %d of %d meshes point at one, %d texture references, "
          "%d of them in this file"
          % (len(asf.materials), resolved, len(meshes), len(refs),
             sum(1 for r in refs if asf.texture_of(r) is not None)))
    nodes = [n for o in asf.objects for n in o.render_nodes]
    if nodes:
        print("shading   : %d render-list nodes  %s"
              % (len(nodes), ", ".join("%s (%s)" % (n.name, n.type_name)
                                       for n in nodes[:4])
                 + (" ..." if len(nodes) > 4 else "")))
    names = list(asf.nodes())
    print("nodes     : %d  %s" % (len(names), ", ".join(names[:8])
                                  + (" ..." if len(names) > 8 else "")))
    worst = [o.extent_error() for o in asf.objects]
    worst = [w for w in worst if w is not None]
    if worst:
        print("bbox check: worst %.4f%% against the stated bounding boxes"
              % (max(worst) * 100))
    for obj in asf.objects[:args.limit]:
        print("  %-20s centre (%.2f, %.2f, %.2f) extents (%.2f, %.2f, %.2f) "
              "%d mesh, %d tex"
              % (obj.name or "<unnamed>", obj.centre[0], obj.centre[1], obj.centre[2],
                 obj.extents[0], obj.extents[1], obj.extents[2],
                 len(obj.meshes), len(obj.textures)))
    return 0


def cmd_materials(args):
    """What shades what: every mesh, its material, and that material's textures."""
    asf = load(args.file)
    print("%d material%s in the file" % (len(asf.materials),
                                         "" if len(asf.materials) == 1 else "s"))
    order = {offset: i for i, offset in enumerate(sorted(asf.materials))}
    for index, obj in enumerate(asf.objects):
        print("")
        print("object %d  %s" % (index, obj.name or "<unnamed>"))
        for node in obj.render_nodes:
            print("   node   %-18s %s" % (node.type_name, node.name))
        for number, mesh in enumerate(obj.meshes):
            material = asf.material_of(mesh)
            if material is None:
                print("   mesh %d -> 0x%X, which is not a material"
                      % (number, mesh.material_offset))
                continue
            inside = obj.chunk.offset < mesh.material_offset < obj.chunk.end
            print("   mesh %d  %5d vertices -> material %d at 0x%X%s"
                  % (number, mesh.vertex_count, order[mesh.material_offset],
                     mesh.material_offset, "" if inside else "  (shared)"))
            for ref in material.textures:
                chunk = asf.texture_of(ref)
                if chunk is None:
                    detail = "not in this file"
                else:
                    w, h = struct.unpack_from(">HH", asf.data, chunk.offset + 0x38)
                    detail = "embedded at 0x%X, %dx%d" % (chunk.offset, w, h)
                print("      texture %d  %-16s usage 0x%04X  %s"
                      % (ref.index, str(ref), ref.usage, detail))
            for (group, slot, width, _word), value in zip(material.bindings,
                                                          material.constants):
                print("      constant %d.%d  %s"
                      % (group, slot, " ".join("%g" % v for v in value[:width])))
    return 0


def cmd_obj(args):
    asf = load(args.file)
    written = base = uv_base = normal_base = 0
    order = {offset: i for i, offset in enumerate(sorted(asf.materials))}
    mtl_path = os.path.splitext(args.output)[0] + ".mtl"
    pngs = _write_mtl(asf, mtl_path, order, args.textures)
    with open(args.output, "w", encoding="utf-8") as fo:
        fo.write("# %s\n# positions, texture coordinates, normals and triangles.\n"
                 "# Faces are written a-c-b: the game winds its front faces the\n"
                 "# other way round, which is how the normals come out pointing\n"
                 "# outwards.\n" % os.path.basename(args.file))
        fo.write("mtllib %s\n" % os.path.basename(mtl_path))
        for index, obj in enumerate(asf.objects):
            for number, mesh in enumerate(obj.meshes):
                if not mesh.vertices:
                    continue
                fo.write("o %s_%d_%d\n" % (obj.name or "object", index, number))
                if mesh.material_offset in order:
                    fo.write("usemtl material_%d\n" % order[mesh.material_offset])
                for x, y, z in mesh.vertices:
                    fo.write("v %.6f %.6f %.6f\n" % (x, y, z))
                for uv in mesh.uvs:
                    fo.write("vt %.6f %.6f\n" % uv[0])
                for x, y, z in mesh.normals:
                    fo.write("vn %.6f %.6f %.6f\n" % (x, y, z))
                # Each list gets its own running count, so a mesh missing one
                # attribute does not shift the next mesh's indices.
                have_uv = len(mesh.uvs) == len(mesh.vertices)
                have_n = len(mesh.normals) == len(mesh.vertices)
                for a, b, c in mesh.triangles:
                    if max(a, b, c) >= len(mesh.vertices):
                        continue
                    fo.write("f %s\n" % " ".join(
                        _obj_vertex(base + k + 1, uv_base + k + 1,
                                    normal_base + k + 1, have_uv, have_n)
                        for k in (a, c, b)))
                    written += 1
                base += len(mesh.vertices)
                uv_base += len(mesh.uvs)
                normal_base += len(mesh.normals)
    print("wrote %s: %d vertices, %d triangles" % (args.output, base, written))
    print("wrote %s: %d materials, %d textures" % (mtl_path, len(order), pngs))
    return 0


def _write_mtl(asf, path, order, want_textures):
    """The companion .mtl: one material per `mats`, with its first texture.

    The colours are the material's own float constants. The first three rows
    read as diffuse, ambient and specular with the specular power in the fourth
    component -- 0.8/0.8/0.8, 0.2/0.2/0.2, 1/1/1 and 20 on the first object
    this was read on, which is an ordinary Maya shader and exactly what the
    node the render list calls a "blinn" would want.
    """
    written = 0
    directory = os.path.dirname(os.path.abspath(path))
    with open(path, "w", encoding="utf-8") as fo:
        fo.write("# materials, one per mats chunk\n")
        for offset, index in sorted(order.items(), key=lambda kv: kv[1]):
            material = asf.materials[offset]
            fo.write("\nnewmtl material_%d\n" % index)
            for name, row in zip(("Kd", "Ka", "Ks"), material.constants):
                fo.write("%s %.4f %.4f %.4f\n" % (name, row[0], row[1], row[2]))
            if len(material.constants) > 2:
                fo.write("Ns %.2f\n" % material.constants[2][3])
            for ref in material.textures[:1]:
                chunk = asf.texture_of(ref)
                if chunk is None:
                    fo.write("# %s is not in this file\n" % ref)
                    continue
                # Not str(ref): the colon in a texture's printed name is not
                # a filename character on every platform.
                png = "%s_%08X.png" % (ref.name, ref.asset)
                if want_textures and _write_png(asf, chunk,
                                                os.path.join(directory, png)):
                    fo.write("map_Kd %s\n" % png)
                    written += 1
                else:
                    fo.write("# %s is embedded at 0x%X\n" % (ref, chunk.offset))
    return written


def _write_png(asf, chunk, path):
    """Decode one embedded texture straight to a PNG beside the OBJ.

    AIF pixel data begins at the next 4096-byte boundary of the file it sits
    in, so the chunk goes to `aif.py` together with the offset it came from.
    """
    try:
        import aif
    except ImportError:
        return False
    try:
        image = aif.AifImage(asf.data[chunk.offset:chunk.offset + chunk.size],
                             base=chunk.offset)
        aif.write_png(path, image.width, image.height, image.to_rgba())
    except Exception as error:          # a format aif.py declines to decode
        print("   %s: %s" % (os.path.basename(path), error))
        return False
    return True


def _obj_vertex(position, texture, normal, have_uv, have_normal):
    if have_uv and have_normal:
        return "%d/%d/%d" % (position, texture, normal)
    if have_normal:
        return "%d//%d" % (position, normal)
    if have_uv:
        return "%d/%d" % (position, texture)
    return "%d" % position


def cmd_textures(args):
    asf = load(args.file)
    if not os.path.isdir(args.outdir):
        os.makedirs(args.outdir)
    count = 0
    stem = os.path.splitext(os.path.basename(args.file))[0]
    for index, obj in enumerate(asf.objects):
        for number, texture in enumerate(obj.textures):
            name = "%s_%02d_%02d_at%X.aif" % (stem, index, number, texture.offset)
            path = os.path.join(args.outdir, name)
            with open(path, "wb") as fo:
                fo.write(texture.raw())
            count += 1
            if count <= 3:
                print("   python tools/aif.py png %s out.png --base 0x%X"
                      % (name, texture.offset))
    print("wrote %d embedded textures to %s" % (count, args.outdir))
    print("--base is the offset the texture had inside the ASF: AIF pixel data")
    print("begins at the next 4096-byte boundary of the containing file.")
    return 0


def _unit(v):
    length = math.sqrt(sum(c * c for c in v))
    return None if length < 1e-12 else [c / length for c in v]


def _angle(a, b):
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def mesh_agreement(mesh):
    """How well the decoded vertex attributes agree with the geometry.

    Three measurements, none of which uses a number this reader produced:

    * the stored normal against the normal of the triangles around it,
    * the angle between the stored normal and the stored binormal,
    * the stored binormal against the one the texture coordinates imply.

    A wrong reading of any of the packed fields moves all three off at once,
    which is what makes them worth measuring together.
    """
    out = {"unit": [], "normal": [], "perpendicular": [], "binormal": []}
    if not mesh.vertices or not mesh.indices:
        return out
    count = len(mesh.vertices)
    geometric = [[0.0, 0.0, 0.0] for _ in range(count)]
    for a, b, c in mesh.triangles:
        if max(a, b, c) >= count:
            continue
        pa, pb, pc = mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]
        u = [pb[k] - pa[k] for k in range(3)]
        v = [pc[k] - pa[k] for k in range(3)]
        # Wound the other way round: the front face is clockwise.
        face = [v[1] * u[2] - v[2] * u[1],
                v[2] * u[0] - v[0] * u[2],
                v[0] * u[1] - v[1] * u[0]]
        for k in (a, b, c):
            for j in range(3):
                geometric[k][j] += face[j]
        if mesh.binormals and mesh.uvs:
            ua, ub, uc = mesh.uvs[a][0], mesh.uvs[b][0], mesh.uvs[c][0]
            du1, dv1 = ub[0] - ua[0], ub[1] - ua[1]
            du2, dv2 = uc[0] - ua[0], uc[1] - ua[1]
            det = du1 * dv2 - du2 * dv1
            if abs(det) > 1e-9:
                # The direction of increasing v, negated: the stored vector
                # runs against it, which is a v axis that points downwards.
                implied = _unit([-(du1 * v[k] - du2 * u[k]) / det for k in range(3)])
                stored = _unit(mesh.binormals[a])
                if implied and stored:
                    out["binormal"].append(_angle(implied, stored))
    for vector in (mesh.normals, mesh.binormals):
        for v in vector:
            out["unit"].append(abs(math.sqrt(sum(c * c for c in v)) - 1.0))
    for i in range(count):
        g = _unit(geometric[i])
        n = _unit(mesh.normals[i]) if i < len(mesh.normals) else None
        if g and n:
            out["normal"].append(_angle(n, g))
        t = _unit(mesh.binormals[i]) if i < len(mesh.binormals) else None
        if n and t:
            out["perpendicular"].append(abs(90.0 - _angle(n, t)))
    return out


def cmd_skeleton(args):
    """The bone chain: a vertex names a palette slot, which names a node."""
    asf = load(args.file)
    names = list(asf.nodes())
    print("%d nodes in the tree" % len(names))
    for obj in asf.objects:
        if not obj.bone_pool and not any(m.bone_indices for m in obj.meshes):
            continue
        print("object %r: pool of %d" % (obj.name, len(obj.bone_pool)))
        for i, node in enumerate(obj.bone_pool[:args.limit]):
            label = names[node] if node < len(names) else "<outside this file>"
            print("   pool[%3d] -> node %3d  %s" % (i, node, label))
        for j, mesh in enumerate(obj.meshes):
            if not mesh.bone_indices:
                continue
            shown = ", ".join(str(v) for v in mesh.bone_indices[:12])
            print("   mesh %d palette of %d: %s%s"
                  % (j, len(mesh.bone_indices), shown,
                     " ..." if len(mesh.bone_indices) > 12 else ""))
    return 0


def cmd_check(args):
    """Measure the vertex decode over as many files as are given."""
    totals = {"unit": [], "normal": [], "perpendicular": [], "binormal": []}
    meshes = weights = weights_ok = 0
    unknown = {}
    padded = failed = 0
    materials = tiled = linked = agreed = refs = refs_here = 0
    pools = pools_ok = palettes = palettes_ok = skinned = skinned_ok = 0
    pools_elsewhere = 0
    for path in args.files:
        try:
            asf = load(path)
        except AsfError:
            failed += 1
            continue
        materials += len(asf.materials)
        refs += sum(len(m.textures) for m in asf.materials.values())
        refs_here += sum(1 for m in asf.materials.values() for r in m.textures
                         if asf.texture_of(r) is not None)
        tiled += _materials_tile(asf)
        node_count = len(list(asf.nodes()))
        for obj in asf.objects:
            if obj.bone_pool and node_count:
                pools += 1
                pools_ok += max(obj.bone_pool) < node_count
            elif obj.bone_pool:
                pools_elsewhere += 1
            for mesh in obj.meshes:
                if mesh.bone_indices and obj.bone_pool:
                    palettes += 1
                    palettes_ok += max(mesh.bone_indices) < len(obj.bone_pool)
                if mesh.bones and mesh.bone_indices:
                    used = max(b for bones, w in zip(mesh.bones, mesh.weights)
                               for b, weight in zip(bones, w) if weight > 0)
                    skinned += 1
                    skinned_ok += used < len(mesh.bone_indices)
                material = asf.material_of(mesh)
                if material is not None:
                    linked += 1
                    # A mesh should carry texture coordinates exactly when the
                    # material it points at has textures. Nothing in the
                    # pointer knows that, so agreement is a check on it.
                    agreed += bool(mesh.uvs) == bool(material.textures)
                if mesh.format is None:
                    continue
                meshes += 1
                for slot, value in mesh.format.unknown:
                    unknown[(slot, value)] = unknown.get((slot, value), 0) + 1
                if mesh.stride != mesh.format.size:
                    padded += 1
                for w in mesh.weights:
                    weights += 1
                    weights_ok += abs(sum(w) - 1.0) < 1e-3
                for key, values in mesh_agreement(mesh).items():
                    totals[key] += values
    print("files    : %d read, %d not ASF" % (len(args.files) - failed, failed))
    print("meshes   : %d, %d with padding after the attributes" % (meshes, padded))
    print("descriptor nibbles not accounted for: %s"
          % (", ".join("slot %d = 0x%X (%d meshes)" % (s, v, n)
                       for (s, v), n in sorted(unknown.items())) or "none"))
    values = sorted(totals.pop("unit"))
    if values:
        print("%-42s median %.4f          (n = %d)"
              % ("packed vectors, |length - 1|", values[len(values) // 2], len(values)))
    for key, label in (("normal", "stored normal vs the geometry"),
                       ("perpendicular", "normal against binormal, off 90 deg by"),
                       ("binormal", "stored binormal vs the one the UVs imply")):
        values = sorted(totals[key])
        if not values:
            continue
        print("%-42s median %6.2f deg   under 15 deg %5.1f%%   (n = %d)"
              % (label, values[len(values) // 2],
                 100.0 * sum(1 for x in values if x < 15) / len(values), len(values)))
    if weights:
        print("%-42s %.1f%% of %d vertices"
              % ("blend weights summing to one", 100.0 * weights_ok / weights, weights))
    if pools or palettes or skinned:
        print("%-42s %d of %d objects%s"
              % ("bone pool inside the node tree", pools_ok, pools,
                 "" if not pools_elsewhere
                 else " (%d more in files with no readable tree)"
                 % pools_elsewhere))
        print("%-42s %d of %d meshes" % ("mesh palette inside the bone pool",
                                         palettes_ok, palettes))
        print("%-42s %d of %d meshes" % ("vertex bone index inside the palette",
                                         skinned_ok, skinned))
    if materials:
        print("%-42s %d, %d laid out end to end" % ("materials", materials, tiled))
        print("%-42s %d meshes, %d agree on texture coordinates"
              % ("meshes linked to a material", linked, agreed))
        print("%-42s %d, %d embedded in the same file"
              % ("texture references", refs, refs_here))
    return 0


def _materials_tile(asf):
    """How many materials end exactly where the next one begins.

    The extent of a `mats` is computed from its section offsets and counts,
    because the step in its chunk header stops short of the texture reference
    table. Landing on the next material is therefore a test of the computation.
    """
    exact = 0
    for obj in asf.objects:
        for chunk in obj.material_lists:
            found = sorted(o for o in asf.materials
                           if chunk.offset < o < chunk.end)
            for i, offset in enumerate(found):
                after = found[i + 1] if i + 1 < len(found) else chunk.end
                exact += asf.materials[offset].end == after
    return exact


def main(argv=None):
    p = argparse.ArgumentParser(description="Reader for ASF, the Aska Scene File.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("tree", help="print the chunk tree")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=80, help="maximum lines")
    s.set_defaults(func=cmd_tree)

    s = sub.add_parser("info", help="summarise the scene and self-check the geometry")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=10, help="objects to list")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("obj", help="export positions and triangles to Wavefront OBJ")
    s.add_argument("file")
    s.add_argument("output")
    s.add_argument("--textures", action="store_true",
                   help="also decode each material's texture to a PNG beside it")
    s.set_defaults(func=cmd_obj)

    s = sub.add_parser("materials",
                       help="what shades what: meshes, materials and textures")
    s.add_argument("file")
    s.set_defaults(func=cmd_materials)

    s = sub.add_parser("skeleton",
                       help="print the bone pool and each mesh's bone palette")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=24)
    s.set_defaults(func=cmd_skeleton)

    s = sub.add_parser("check", help="measure the vertex decode against the geometry")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("textures", help="write out the embedded AIF textures")
    s.add_argument("file")
    s.add_argument("outdir")
    s.set_defaults(func=cmd_textures)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
