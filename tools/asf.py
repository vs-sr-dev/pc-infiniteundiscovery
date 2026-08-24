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

A vertex begins with its position, stored one of two ways, and which one is
given by the low nibble of the descriptor at vlas +0x04: 8 means three half
floats, 1 and 4 mean three 32-bit floats. That mapping is not read off a
hardware format enum. Each `ao__` states an oriented bounding box -- a centre,
three axis directions and a half-extent along each -- in full 32-bit floats,
written by whatever exported the model from geometry this reader never sees.
Reproducing that box from the decoded vertices is therefore a check against a
number from outside the decode, and the nibble is simply which reading passes
it: 98.4% of 3855 objects agree to within one percent.

The rest of the vertex -- normals, texture coordinates, skinning -- has not
been worked out; `obj` exports positions and triangles only.

Usage
-----
    python tools/asf.py tree     <file.asf>
    python tools/asf.py info     <file.asf>
    python tools/asf.py obj      <file.asf> <out.obj>
    python tools/asf.py textures <file.asf> <outdir>
"""

from __future__ import annotations

import argparse
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


# Low nibble of the vlas descriptor, against how the position is stored. Only
# these three values occur. The mapping was not read off a format enum: each
# was decided by which reading reproduces the object's stated bounding box.
POSITION_FORMAT = {0x8: "half4", 0x1: "float3", 0x4: "float3"}


class Mesh:
    def __init__(self, chunk):
        self.chunk = chunk
        self.vertex_count = chunk.u16(0)
        self.index_count = chunk.u16(2)
        self.vertices = []
        self.indices = []
        self.stride = 0
        self.descriptor = 0
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

        self.position_format = POSITION_FORMAT.get(self.descriptor & 0xF)
        base = chunk.offset + offset
        for i in range(self.vertex_count):
            at = base + i * self.stride
            if self.position_format == "float3":
                self.vertices.append(struct.unpack_from(">3f", blob, at))
            else:
                self.vertices.append(tuple(
                    half_float(struct.unpack_from(">H", blob, at + a * 2)[0])
                    for a in range(3)))

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
    written = base = 0
    with open(args.output, "w", encoding="utf-8") as fo:
        fo.write("# %s\n# positions and triangles only; the rest of the vertex\n"
                 "# format is not yet understood\n" % os.path.basename(args.file))
        for index, obj in enumerate(asf.objects):
            for number, mesh in enumerate(obj.meshes):
                if not mesh.vertices:
                    continue
                fo.write("o %s_%d_%d\n" % (obj.name or "object", index, number))
                for x, y, z in mesh.vertices:
                    fo.write("v %.6f %.6f %.6f\n" % (x, y, z))
                for a, b, c in mesh.triangles:
                    if max(a, b, c) < len(mesh.vertices):
                        fo.write("f %d %d %d\n" % (base + a + 1, base + b + 1,
                                                   base + c + 1))
                        written += 1
                base += len(mesh.vertices)
    print("wrote %s: %d vertices, %d triangles" % (args.output, base, written))
    return 0


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

    s = sub.add_parser("textures", help="write out the embedded AIF textures")
    s.add_argument("file")
    s.add_argument("outdir")
    s.set_defaults(func=cmd_textures)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
