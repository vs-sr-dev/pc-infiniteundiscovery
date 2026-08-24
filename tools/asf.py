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
        ml__ / mats          materials
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

Usage
-----
    python tools/asf.py tree     <file.asf>
    python tools/asf.py info     <file.asf>
    python tools/asf.py obj      <file.asf> <out.obj>
    python tools/asf.py textures <file.asf> <outdir>
    python tools/asf.py check    <file.asf> [...]
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
    "rl__": "render list",
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
        if start is None:
            return []
        return list(walk(self.blob, start, self.end))

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
        self.stride = 0
        self.descriptor = 0
        self.format = None
        self.position_format = None
        for child in chunk.children():
            if child.tag == "vlas" and self.vertex_count:
                self._read_vertices(child)
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


class Object3D:
    """One `ao__`: an oriented bounding box, meshes, and embedded textures."""

    def __init__(self, chunk):
        self.chunk = chunk
        self.sphere = chunk.floats(0x00, 4)        # centre xyz, radius
        self.centre = chunk.floats(0x10, 3)
        self.axes = [chunk.floats(0x20 + i * 0x10, 3) for i in range(3)]
        self.extents = chunk.floats(0x50, 3)
        self.name = chunk.name(0x80)
        self.meshes = []
        self.textures = []
        for child in chunk.children():
            if child.tag == "mess":
                self.meshes.append(Mesh(child))
            elif child.tag == "AIF ":
                self.textures.append(child)

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


def cmd_obj(args):
    asf = load(args.file)
    written = base = uv_base = normal_base = 0
    with open(args.output, "w", encoding="utf-8") as fo:
        fo.write("# %s\n# positions, texture coordinates, normals and triangles.\n"
                 "# Faces are written a-c-b: the game winds its front faces the\n"
                 "# other way round, which is how the normals come out pointing\n"
                 "# outwards.\n" % os.path.basename(args.file))
        for index, obj in enumerate(asf.objects):
            for number, mesh in enumerate(obj.meshes):
                if not mesh.vertices:
                    continue
                fo.write("o %s_%d_%d\n" % (obj.name or "object", index, number))
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
    return 0


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


def cmd_check(args):
    """Measure the vertex decode over as many files as are given."""
    totals = {"unit": [], "normal": [], "perpendicular": [], "binormal": []}
    meshes = weights = weights_ok = 0
    unknown = {}
    padded = failed = 0
    for path in args.files:
        try:
            asf = load(path)
        except AsfError:
            failed += 1
            continue
        for obj in asf.objects:
            for mesh in obj.meshes:
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
    return 0


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
    s.set_defaults(func=cmd_obj)

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
