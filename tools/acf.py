#!/usr/bin/env python3
"""
acf.py -- reader for ACF, the Aska Collision File.

Every `COLL` resource is an `ACF ` payload: 972 of them in disc 1's `ud1.bin`,
2.7 MB in all. It is the smallest of the Aska formats and the most completely
readable -- a sphere tree over three primitive shapes, with the artists' Maya
names left in.

The engine names the shapes before the disc does. Its RTTI carries
`Aska::AcfPrimitiveData_capsule`, `_cube` and `_sphere`, and the shape code in
a primitive record is 0, 1 or 2 in exactly that order -- confirmed by the name
the artist gave the node. 8 119 primitives are called some variation of
`pColSphere`, `pColCube` or `pColCapsule`, and the code agrees with the name on
**all 8 119**.

The header
----------
0x30 bytes, big-endian:

    +0x00  4  'ACF '
    +0x04  4  total length -- matches the file on all 972
    +0x10  2  version, 5 everywhere
    +0x12  2  branch group count
    +0x14  2  leaf group count
    +0x16  2  primitive count
    +0x18  4  1.0 in every file
    +0x1C  4  offset to the groups (the branches come first)
    +0x20  4  offset to the leaf groups
    +0x24  4  offset to the primitive records
    +0x28  4  the highest point the collision reaches in Y
    +0x2C  4  the whole thing's radius measured from the origin

Then three arrays, each tiling exactly into the next: 0x40-byte group records,
0x30-byte primitive records, and the primitive data itself on a 0x20 grid.

Groups
------
A group is a bounding sphere with a name and either children or primitives:

    +0x00 16  bounding sphere: centre xyz, then radius
    +0x10 32  name, NUL-padded ASCII
    +0x30  2  kind: 0 a branch, 0x0100 a leaf
    +0x32  2  this group's index within its own array
    +0x34  2  collision mask
    +0x36 10  five slots: children if a branch, (first, count) if a leaf

A branch's five slots are child references terminated by 0xFFFF. **Bit 0x8000
means the child is a leaf**, indexed into the leaf array; without it the child
is another branch, indexed into the branch array. Following them from group 0
reaches every group in the file exactly once, on all 522 files that have
branches -- so the slots are a spanning tree, not a loose list.

A leaf instead names a run of primitives: the first and how many. Those runs
partition the primitive array exactly, on all 972 files.

The names are bones. `R:M:SK_HipR`, `R:M:SK_LtArmR`, `R:M:SK_RtLegL` -- the
same names the ASF node tree and the AAF animation records carry, so the sphere
tree is the skeleton, and each node's sphere is in its own bone's space.

Primitives
----------
    +0x00 32  name, NUL-padded ASCII
    +0x20  2  shape: 0 sphere, 1 cube, 2 capsule
    +0x22  2  this primitive's index
    +0x24  4  offset to its data
    +0x28  2  unidentified
    +0x2A  2  0xFFFF, or zero
    +0x2C  2  collision mask
    +0x2E  2  zero

The data is a centre, a bounding radius, and then the shape's own parameters:

    sphere   cx cy cz  r     r
    cube     cx cy cz  r     hx hy hz 1.0
    capsule  cx cy cz  r     half-length  radius

The bounding radius is redundant, and that is what makes the reading checkable:
it is the sphere's radius, the cube's half-diagonal, and the capsule's
half-length plus radius, and it comes out right on **all 8 302** primitives
that state one -- median error exactly zero. The file's own length is another
check: it ends exactly after the last primitive's data, which is only true if
the shape code picks the right number of floats.

The mask
--------
A 16-bit field on every primitive, and a group carries the OR of everything
under it -- on 7 252 of 7 252 leaves and 2 281 of 2 281 branches. The values
are single bits and small combinations (0x0001, 0x0010, 0x0100, 0x0200,
0x1000), so it reads as a layer or category: what this volume collides with.
"""

import argparse
import collections
import glob
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAGIC = b"ACF "
GROUP = 0x40
PRIMITIVE = 0x30
LEAF = 0x0100

SHAPES = {0: "sphere", 1: "cube", 2: "capsule"}
# floats stored for each shape: centre, bounding radius, then its parameters
SHAPE_FLOATS = {0: 5, 1: 8, 2: 6}


class AcfError(Exception):
    pass


def _u32(blob, at):
    return struct.unpack_from(">I", blob, at)[0]


def _u16(blob, at):
    return struct.unpack_from(">H", blob, at)[0]


def _name(blob, at, size=0x20):
    return blob[at:at + size].split(b"\0")[0].decode("latin-1", "replace")


class Primitive:
    __slots__ = ("offset", "name", "shape", "index", "data", "unknown",
                 "terminator", "mask", "values")

    def __init__(self, blob, at):
        self.offset = at
        self.name = _name(blob, at)
        self.shape = _u16(blob, at + 0x20)
        self.index = _u16(blob, at + 0x22)
        self.data = _u32(blob, at + 0x24)
        self.unknown = _u16(blob, at + 0x28)
        self.terminator = _u16(blob, at + 0x2A)
        self.mask = _u16(blob, at + 0x2C)
        count = SHAPE_FLOATS.get(self.shape)
        if count is None:
            raise AcfError("primitive %r states shape %d" % (self.name, self.shape))
        if self.data + count * 4 > len(blob):
            raise AcfError("primitive %r points past the file" % self.name)
        self.values = struct.unpack_from(">%df" % count, blob, self.data)

    @property
    def shape_name(self):
        return SHAPES.get(self.shape, "shape %d" % self.shape)

    @property
    def centre(self):
        return self.values[:3]

    @property
    def radius(self):
        """The stated bounding radius."""
        return self.values[3]

    @property
    def measured_radius(self):
        """The bounding radius the shape's own parameters imply."""
        v = self.values
        if self.shape == 0:
            return v[4]
        if self.shape == 1:
            return math.sqrt(v[4] ** 2 + v[5] ** 2 + v[6] ** 2)
        return v[4] + v[5]

    def describe(self):
        v = self.values
        if self.shape == 0:
            return "r %.2f" % v[4]
        if self.shape == 1:
            return "half %.2f %.2f %.2f" % (v[4], v[5], v[6])
        return "length %.2f r %.2f" % (v[4] * 2, v[5])


class Group:
    __slots__ = ("offset", "centre", "radius", "name", "kind", "index",
                 "mask", "slots")

    def __init__(self, blob, at):
        self.offset = at
        sphere = struct.unpack_from(">4f", blob, at)
        self.centre = sphere[:3]
        self.radius = sphere[3]
        self.name = _name(blob, at + 0x10)
        self.kind = _u16(blob, at + 0x30)
        self.index = _u16(blob, at + 0x32)
        self.mask = _u16(blob, at + 0x34)
        self.slots = struct.unpack_from(">5H", blob, at + 0x36)

    @property
    def leaf(self):
        return self.kind == LEAF

    @property
    def first(self):
        return self.slots[0]

    @property
    def count(self):
        return self.slots[1]


class AcfFile:
    def __init__(self, data):
        if data[:4] != MAGIC:
            raise AcfError("not an ACF payload")
        self.data = data
        self.total_size = _u32(data, 0x04)
        self.version = _u16(data, 0x10)
        self.branch_count = _u16(data, 0x12)
        self.leaf_count = _u16(data, 0x14)
        self.group_offset = _u32(data, 0x1C)
        self.leaf_offset = _u32(data, 0x20)
        self.primitive_offset = _u32(data, 0x24)
        self.highest = struct.unpack_from(">f", data, 0x28)[0]
        self.reach = struct.unpack_from(">f", data, 0x2C)[0]

        count = self.branch_count + self.leaf_count
        self.groups = [Group(data, self.group_offset + i * GROUP)
                       for i in range(count)]
        self.primitives = [Primitive(data, self.primitive_offset + i * PRIMITIVE)
                           for i in range(_u16(data, 0x16))]

    def children(self, group):
        """The groups a branch points at, resolved through the 0x8000 flag."""
        if group.leaf:
            return []
        out = []
        for slot in group.slots:
            if slot == 0xFFFF:
                break
            index = ((self.branch_count + (slot & 0x7FFF)) if slot & 0x8000
                     else slot)
            if index < len(self.groups):
                out.append(self.groups[index])
        return out

    def members(self, group):
        """The primitives a leaf covers."""
        if not group.leaf:
            return []
        return self.primitives[group.first:group.first + group.count]

    def problems(self):
        bad = []
        if self.version != 5:
            bad.append("version %d" % self.version)
        if self.total_size != len(self.data):
            bad.append("states %d bytes, the file has %d"
                       % (self.total_size, len(self.data)))
        count = self.branch_count + self.leaf_count
        if self.group_offset + count * GROUP != self.primitive_offset:
            bad.append("the group array does not reach the primitives")
        if self.leaf_offset != self.group_offset + self.branch_count * GROUP:
            bad.append("the leaf offset does not follow the branches")
        blobs = self.primitive_offset + len(self.primitives) * PRIMITIVE
        for i, primitive in enumerate(self.primitives):
            if primitive.data != blobs + i * 0x20:
                bad.append("primitive data is not on the 0x20 grid")
                break
        if self.primitives:
            last = self.primitives[-1]
            end = last.data + SHAPE_FLOATS[last.shape] * 4
            if end != len(self.data):
                bad.append("the file ends %d bytes after the last primitive"
                           % (len(self.data) - end))
        for primitive in self.primitives:
            if primitive.radius > 1e-6 and abs(
                    primitive.measured_radius - primitive.radius) > 1e-3 * primitive.radius:
                bad.append("%r states a radius its shape does not give"
                           % primitive.name)
                break
        seen = collections.Counter()
        for group in self.groups:
            if group.leaf:
                for i in range(group.first, group.first + group.count):
                    seen[i] += 1
                mask = 0
                for primitive in self.members(group):
                    mask |= primitive.mask
            else:
                mask = 0
                for child in self.children(group):
                    mask |= child.mask
            if mask != group.mask:
                bad.append("%r states a mask its members do not give" % group.name)
                break
        if len(seen) != len(self.primitives) or (seen and max(seen.values()) > 1):
            bad.append("the leaf ranges do not partition the primitives")
        if self.branch_count:
            reached = collections.Counter()
            stack = [self.groups[0]]
            while stack:
                group = stack.pop()
                reached[group.offset] += 1
                if reached[group.offset] > 1:
                    continue
                stack.extend(self.children(group))
            if len(reached) != len(self.groups) or max(reached.values()) > 1:
                bad.append("the branch tree does not reach every group once")
        return bad


def load(path):
    with open(path, "rb") as fh:
        return AcfFile(fh.read())


# -- commands --------------------------------------------------------------

def cmd_tree(args):
    acf = load(args.file)
    print("ACF version %d, %d branches, %d leaves, %d primitives"
          % (acf.version, acf.branch_count, acf.leaf_count, len(acf.primitives)))
    printed = [0]

    def walk(group, depth):
        if printed[0] >= args.limit:
            return
        printed[0] += 1
        print("%s%-28s r %8.2f at (%8.2f %8.2f %8.2f)  mask %04x"
              % ("  " * depth, repr(group.name), group.radius,
                 group.centre[0], group.centre[1], group.centre[2], group.mask))
        for primitive in acf.members(group):
            print("%s  %-10s %-24s %s  mask %04x"
                  % ("  " * depth, primitive.shape_name, repr(primitive.name),
                     primitive.describe(), primitive.mask))
        for child in acf.children(group):
            walk(child, depth + 1)

    if acf.groups:
        walk(acf.groups[0], 0)
        if acf.branch_count == 0:
            for group in acf.groups[1:]:
                walk(group, 0)
    return 0


def cmd_info(args):
    acf = load(args.file)
    shapes = collections.Counter(p.shape_name for p in acf.primitives)
    masks = collections.Counter(p.mask for p in acf.primitives)
    print("%s" % args.file)
    print("  version      %d" % acf.version)
    print("  groups       %d branch, %d leaf" % (acf.branch_count, acf.leaf_count))
    print("  primitives   %d: %s"
          % (len(acf.primitives),
             ", ".join("%d %s" % (v, k) for k, v in shapes.most_common())))
    print("  masks        %s"
          % ", ".join("%04x x%d" % (k, v) for k, v in masks.most_common(6)))
    if acf.groups:
        root = acf.groups[0]
        print("  root         %r, r %.2f at (%.2f %.2f %.2f)"
              % (root.name, root.radius, *root.centre))
    print("  highest in Y %.2f, reach from the origin %.2f"
          % (acf.highest, acf.reach))
    bad = acf.problems()
    print("  self-check   %s" % ("clean" if not bad else "; ".join(bad)))
    return 0


def _sphere(centre, radius, rings, segments, offset=(0.0, 0.0, 0.0)):
    """Vertices and faces of a UV sphere, faces as 1-based local indices."""
    vertices, faces = [], []
    for i in range(rings + 1):
        theta = math.pi * i / rings
        y = math.cos(theta) * radius
        r = math.sin(theta) * radius
        # a capsule is a sphere cut in half and pulled apart
        shift = offset[1] if y >= 0 else -offset[1]
        for j in range(segments):
            phi = 2 * math.pi * j / segments
            vertices.append((centre[0] + r * math.cos(phi),
                             centre[1] + y + shift,
                             centre[2] + r * math.sin(phi)))
    for i in range(rings):
        for j in range(segments):
            a = i * segments + j + 1
            b = i * segments + (j + 1) % segments + 1
            faces.append((a, b, b + segments, a + segments))
    return vertices, faces


def _box(centre, half):
    x, y, z = half
    vertices = [(centre[0] + sx * x, centre[1] + sy * y, centre[2] + sz * z)
                for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [(1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2),
             (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)]
    return vertices, faces


def cmd_obj(args):
    """Write the collision volumes out as a Wavefront OBJ.

    Every group's primitives become one OBJ group named after the bone the
    collision hangs off, so a viewer shows the shape of the skeleton.
    """
    acf = load(args.file)
    written = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("# %s -- %d collision primitives\n"
                 % (os.path.basename(args.file), len(acf.primitives)))
        base = 0
        for group in acf.groups:
            if not group.leaf:
                continue
            fh.write("g %s\n" % (group.name or "unnamed"))
            for primitive in acf.members(group):
                v = primitive.values
                if primitive.shape == 0:
                    vertices, faces = _sphere(primitive.centre, v[4],
                                              args.rings, args.segments)
                elif primitive.shape == 1:
                    vertices, faces = _box(primitive.centre, v[4:7])
                else:
                    vertices, faces = _sphere(primitive.centre, v[5],
                                              args.rings, args.segments,
                                              (0.0, v[4], 0.0))
                fh.write("o %s\n" % (primitive.name or primitive.shape_name))
                for x, y, z in vertices:
                    fh.write("v %.4f %.4f %.4f\n" % (x, y, z))
                for face in faces:
                    fh.write("f %s\n" % " ".join(str(base + i) for i in face))
                base += len(vertices)
                written += 1
    print("wrote %d primitives to %s" % (written, args.out))
    return 0


def _expand(patterns):
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern) if any(c in pattern for c in "*?")
                     else [pattern])
    return sorted(files)


def cmd_check(args):
    files = _expand(args.files)
    clean = 0
    faults = collections.Counter()
    unreadable = []
    shapes = collections.Counter()
    named = [0, 0]
    radius = []
    masks = collections.Counter()
    for path in files:
        try:
            acf = load(path)
        except (AcfError, struct.error) as exc:
            unreadable.append((path, exc))
            continue
        bad = acf.problems()
        if bad:
            for line in bad:
                faults[line[:64]] += 1
            if args.verbose:
                print("%s: %s" % (path, "; ".join(bad[:2])))
            continue
        clean += 1
        for primitive in acf.primitives:
            shapes[primitive.shape_name] += 1
            masks[primitive.mask] += 1
            if primitive.radius > 1e-6:
                radius.append(abs(primitive.measured_radius - primitive.radius)
                              / primitive.radius)
            # The artist's own name says which shape it is, and owes nothing
            # to the shape code.
            spelt = primitive.name.lower()
            for code, word in ((0, "sphere"), (1, "cube"), (2, "capsule")):
                if word in spelt:
                    named[1] += 1
                    named[0] += primitive.shape == code
                    break
    print("%d files: %d parse and self-check clean, %d unreadable, %d with faults"
          % (len(files), clean, len(unreadable), len(files) - clean - len(unreadable)))
    for path, exc in unreadable[:args.limit]:
        print("  unreadable  %s: %s" % (path, exc))
    for line, count in faults.most_common(args.limit):
        print("  %5d x %s" % (count, line))
    print("primitives   %s"
          % ", ".join("%d %s" % (v, k) for k, v in shapes.most_common()))
    if radius:
        radius.sort()
        print("stated bounding radius against the shape's own parameters:")
        print("  median %.2e, within one part in a million on %.1f%% of %d"
              % (radius[len(radius) // 2],
                 100.0 * sum(1 for x in radius if x < 1e-6) / len(radius),
                 len(radius)))
    if named[1]:
        print("shape code against the name the artist gave: %d of %d (%.1f%%)"
              % (named[0], named[1], 100.0 * named[0] / named[1]))
    print("masks        %s"
          % ", ".join("%04x x%d" % (k, v) for k, v in masks.most_common(8)))
    if args.models:
        _against_scenes(files, args.models)
    return 0


def _against_scenes(files, patterns):
    """Group names against the node tree of the scene they belong to.

    A collision group is named after a bone, so its name should be in the
    matching ASF's `tree`. That is a check on the group record from outside
    this reader, and it is what says the sphere tree is the skeleton.
    """
    import asf as asf_module

    scenes = collections.defaultdict(list)
    for path in _expand(patterns):
        scenes[os.path.basename(path).split("_")[0]].append(path)
    hit = total = 0
    whole = collections.Counter()
    for path in files:
        group = os.path.basename(path).split("_")[0]
        if group not in scenes:
            continue
        names = set()
        for scene in scenes[group]:
            try:
                names |= set(asf_module.load(scene).nodes())
            except Exception:
                continue
        if not names:
            continue
        try:
            acf = load(path)
        except (AcfError, struct.error):
            continue
        mine = [g.name for g in acf.groups if g.name]
        if not mine:
            continue
        found = sum(1 for n in mine if n in names)
        hit += found
        total += len(mine)
        whole[found == len(mine)] += 1
    if total:
        print("group names found in the matching scene's node tree: %d of %d (%.1f%%)"
              % (hit, total, 100.0 * hit / total))
        print("  files where every group name is found: %d of %d"
              % (whole[True], whole[True] + whole[False]))


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Reader for ACF, the Aska Collision File.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("tree", help="print the sphere tree and its primitives")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=60)
    s.set_defaults(func=cmd_tree)

    s = sub.add_parser("info", help="summarise one file and self-check it")
    s.add_argument("file")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("obj", help="write the collision volumes to an OBJ")
    s.add_argument("file")
    s.add_argument("out")
    s.add_argument("--rings", type=int, default=8)
    s.add_argument("--segments", type=int, default=12)
    s.set_defaults(func=cmd_obj)

    s = sub.add_parser("check", help="parse a corpus and measure the decode")
    s.add_argument("files", nargs="+")
    s.add_argument("--models", nargs="+",
                   help="ASF payloads, to check the group names against the "
                        "node tree of the scene they belong to")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
