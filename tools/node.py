#!/usr/bin/env python3
"""
node.py -- reader for the NODE payload, the ASKA engine's AI node field.

Every scene archive that carries a `SCE-` script carries a `NODE` resource
beside it, one for one: 44 of each on disc 1, 17 more in disc 2's `ud1.bin`.
The payload has no ASCII magic -- it opens with the constant `0x0131F119` --
which is why the resource-payload census could only ever call it "no magic,
raw data".

It is a **navigation mesh**. The engine names the parts: the RTTI in the retail
executable carries `CAINodeField` and `CAINodeFieldManager`, `CAIPartition`
with its `CPartitionOptionDoor` and `CPartitionOptionToggle`, `CAINodeLink`,
`CAIRoutePoint`, `CAINodeColPoint`, and `CAISearchAStar` with `CAIAStarPoint`
and `CAStarAlgorithm<CAIAStarPoint>`. Every one of those has something in this
file.

References
----------
Nodes, links and partitions all refer to one another with a 32-bit word that
is **`index << 8` plus a low byte the reader should mask off**. The index is
exact: `id >> 8 == the record's own position` for every node and every link in
all 61 payloads. What the low byte carries is not known -- see "Left open".

Layout
------
0x2C-byte header, big-endian, then three arrays and the blocks they point at.
Offsets are plain byte offsets from the start of the file.

    +0x00  4  0x0131F119
    +0x04  4  zero in every file
    +0x08  4  node count
    +0x0C  4  link count
    +0x10  4  partition count
    +0x14  4  offset to the nodes
    +0x18  4  offset to the links
    +0x1C  4  offset to the partitions
    +0x20  4  zero in every file
    +0x24  4  offset to the gate table, or zero
    +0x28  4  offset to a trailing table, or zero

A node, 0x18 bytes:

    +0x00  4  its own reference -- index << 8, plus a low byte
    +0x04  4  zero in every node in the corpus
    +0x08  4  link count
    +0x0C  4  offset to that many link references, 4 bytes each
    +0x10  4  offset to that many (edge index, neighbour) pairs, 8 bytes each
    +0x14  4  offset to the polygon

The polygon is a count followed by that many `(x, y, z)` floats. It is convex
in XZ, wound the same way in every node in the corpus, and its vertices are
full 3D points -- the mesh follows the terrain.

The two per-node arrays run in step: entry *k* of the first names a link, and
entry *k* of the second says which of this polygon's edges that link crosses
and which node is on the other side. Edge *k* runs from vertex *k* to vertex
*k+1*.

A link, 0x28 bytes, reached through an (id, offset) pair in the link array:

    +0x00  4  route entry count
    +0x04  4  offset to the route entries
    +0x08  4  one of the two nodes it joins
    +0x0C  4  the other
    +0x10 12  one end of the shared edge
    +0x1C 12  the other end

**The two points are exactly the polygon edge, in both of the polygons that
share it: 110 202 of 110 202 in the corpus.** That is the check that says the
whole reading is right.

A route entry, 0x10 bytes:

    +0x00  4  the node on the far side of the link below
    +0x04  4  a neighbouring link
    +0x08  4  offset to a float: the cost of getting from this link to that one
    +0x0C  4  gate reference, or zero

The cost is **exactly the distance between the two links' edge midpoints, on
all 167 316 route entries** -- so a path search runs over portal midpoints, and
the far-side node is there so the search knows where it comes out.

A partition, 0x18 bytes:

    +0x00  4  node count
    +0x04  4  offset to that many node references
    +0x08 16  minX, maxZ, maxX, minZ of those nodes

The partitions cover every node exactly once in all 61 files, and the rectangle
is the XZ bound of the nodes listed, to 0.01, on 32 804 of 32 854. They are a
spatial index, not a connectivity grouping: 34 005 of 55 140 links join nodes
in two different partitions.

The gate table
--------------
Where a route entry's last word is not zero it reads `(slot << 16) | group`,
and the group is an entry in the table at header `+0x24`: a count and offset,
then records of `(group id, slot count, offset to that many values)`. Every
slot is claimed exactly once, in all 61 files -- 1 512 slots against 1 512
gated routes. Every route entry that names a gate has **cost zero**, and the
links involved meet at a node joining two rooms, which is what
`CPartitionOptionDoor` and `CPartitionOptionToggle` are for and what the scene
script calls `DOOR_01_BOTH` and `CTRL_elevator`.

Left open
---------
* The low byte of a node's own reference: 0 on 35 002 of 53 987, then 1..7, and
  0xFF on 2 143. Every reference *to* a node carries 0 instead, so it is
  attached to the record rather than to the identity.
* The values in a gate group's slot list, and the trailing table at `+0x28`,
  whose records begin `0x00440000` or `0x00440004`.
* 802 nodes have a two-vertex polygon, which is a segment rather than an area.

Reproducing
-----------
    python tools/mron.py extract <image> --offset N --length N \
        --tag NODE --decompress out/
    python tools/node.py info  out/xxx_NODE.bin
    python tools/node.py obj   out/xxx_NODE.bin navmesh.obj --portals
    python tools/node.py check out/*.bin
"""

import argparse
import collections
import math
import os
import struct
import sys

MAGIC = 0x0131F119
HEADER = 0x2C
NODE_SIZE = 0x18
LINK_SIZE = 0x28
PARTITION_SIZE = 0x18
ROUTE_SIZE = 0x10


class NodeError(Exception):
    pass


def ref(word):
    """A node or link reference is index << 8 plus a byte to be masked off."""
    return word >> 8


class Node(object):

    __slots__ = ("index", "word", "spare", "links", "across", "polygon")

    def __init__(self, blob, at, index):
        (self.word, self.spare, count,
         links_at, across_at, polygon_at) = struct.unpack_from(">6I", blob, at)
        self.index = index
        self.links = [ref(struct.unpack_from(">I", blob, links_at + 4 * i)[0])
                      for i in range(count)]
        self.across = []
        for i in range(count):
            edge, other = struct.unpack_from(">2I", blob, across_at + 8 * i)
            self.across.append((edge, ref(other)))
        vertices = struct.unpack_from(">I", blob, polygon_at)[0]
        self.polygon = [struct.unpack_from(">3f", blob, polygon_at + 4 + 12 * i)
                        for i in range(vertices)]

    @property
    def tag(self):
        return self.word & 0xFF

    def edge(self, which):
        """The two endpoints of edge `which`, which runs from vertex to vertex."""
        n = len(self.polygon)
        return self.polygon[which], self.polygon[(which + 1) % n]

    def centre(self):
        n = len(self.polygon)
        return tuple(sum(v[i] for v in self.polygon) / n for i in range(3))

    def area(self):
        """Signed area in XZ. Negative would mean the opposite winding."""
        total = 0.0
        for i in range(len(self.polygon)):
            x1, _, z1 = self.polygon[i]
            x2, _, z2 = self.polygon[(i + 1) % len(self.polygon)]
            total += x1 * z2 - x2 * z1
        return total / 2.0

    def convex(self):
        if len(self.polygon) < 3:
            return None
        signs = set()
        for i in range(len(self.polygon)):
            x1, _, z1 = self.polygon[i]
            x2, _, z2 = self.polygon[(i + 1) % len(self.polygon)]
            x3, _, z3 = self.polygon[(i + 2) % len(self.polygon)]
            cross = (x2 - x1) * (z3 - z2) - (z2 - z1) * (x3 - x2)
            if abs(cross) > 1e-3:
                signs.add(cross > 0)
        return len(signs) <= 1


class Route(object):

    __slots__ = ("far", "link", "cost", "gate")

    def __init__(self, blob, at):
        far, link, cost_at, self.gate = struct.unpack_from(">4I", blob, at)
        self.far, self.link = ref(far), ref(link)
        self.cost = struct.unpack_from(">f", blob, cost_at)[0]

    @property
    def gate_group(self):
        return self.gate & 0xFFFF

    @property
    def gate_slot(self):
        return self.gate >> 16


class Link(object):

    __slots__ = ("index", "word", "a", "b", "first", "second", "routes")

    def __init__(self, blob, at, word, index):
        count, routes_at, a, b = struct.unpack_from(">4I", blob, at)
        self.index, self.word = index, word
        self.a, self.b = ref(a), ref(b)
        self.first = struct.unpack_from(">3f", blob, at + 0x10)
        self.second = struct.unpack_from(">3f", blob, at + 0x1C)
        self.routes = [Route(blob, routes_at + ROUTE_SIZE * i)
                       for i in range(count)]

    @property
    def tag(self):
        return self.word & 0xFF

    def midpoint(self):
        return tuple((self.first[i] + self.second[i]) / 2 for i in range(3))


class Partition(object):

    __slots__ = ("index", "nodes", "box")

    def __init__(self, blob, at, index):
        count, nodes_at = struct.unpack_from(">2I", blob, at)
        self.index = index
        self.nodes = [ref(struct.unpack_from(">I", blob, nodes_at + 4 * i)[0])
                      for i in range(count)]
        self.box = struct.unpack_from(">4f", blob, at + 8)


class NodeField(object):

    def __init__(self, data):
        self.blob = data
        head = struct.unpack_from(">11I", data, 0)
        if head[0] != MAGIC:
            raise NodeError("not a NODE payload: magic 0x%08X" % head[0])
        (_, self.spare, node_count, link_count, partition_count,
         nodes_at, links_at, partitions_at,
         self.spare2, self.gates_at, self.trailer_at) = head
        self.nodes = [Node(data, nodes_at + NODE_SIZE * i, i)
                      for i in range(node_count)]
        self.links = []
        for i in range(link_count):
            word, at = struct.unpack_from(">2I", data, links_at + 8 * i)
            self.links.append(Link(data, at, word, i))
        self.partitions = [Partition(data, partitions_at + PARTITION_SIZE * i, i)
                           for i in range(partition_count)]

    def gates(self):
        """Group id -> the list of values its slots hold."""
        if not self.gates_at:
            return {}
        count, at = struct.unpack_from(">2I", self.blob, self.gates_at)
        out = {}
        for i in range(count):
            which, slots, values_at = struct.unpack_from(">3I", self.blob,
                                                         at + 12 * i)
            out[which] = [struct.unpack_from(">I", self.blob, values_at + 4 * k)[0]
                          for k in range(slots)]
        return out

    def bounds(self):
        points = [v for node in self.nodes for v in node.polygon]
        if not points:
            return None
        return tuple((min(p[i] for p in points), max(p[i] for p in points))
                     for i in range(3))

    def problems(self):
        out = []
        for node in self.nodes:
            if ref(node.word) != node.index:
                out.append("node %d calls itself %d" % (node.index, ref(node.word)))
            for edge, other in node.across:
                if other >= len(self.nodes):
                    out.append("node %d points past the array" % node.index)
                elif edge >= len(node.polygon):
                    out.append("node %d names edge %d of %d"
                               % (node.index, edge, len(node.polygon)))
        for link in self.links:
            if ref(link.word) != link.index:
                out.append("link %d calls itself %d" % (link.index, ref(link.word)))
            for side in (link.a, link.b):
                if side >= len(self.nodes):
                    out.append("link %d points past the node array" % link.index)
                    continue
                node = self.nodes[side]
                edges = [e for l, (e, _) in zip(node.links, node.across)
                         if l == link.index]
                if not edges:
                    continue
                first, second = node.edge(edges[0])
                if (first, second) != (link.first, link.second) and \
                   (second, first) != (link.first, link.second):
                    out.append("link %d does not lie on node %d's edge %d"
                               % (link.index, side, edges[0]))
            for route in link.routes:
                if route.link >= len(self.links):
                    out.append("link %d routes to %d" % (link.index, route.link))
        covered = sorted(i for p in self.partitions for i in p.nodes)
        if covered != list(range(len(self.nodes))):
            out.append("the partitions do not cover every node exactly once")
        return out[:8]


def load(path):
    with open(path, "rb") as fh:
        return NodeField(fh.read())


# -- commands --------------------------------------------------------------

def cmd_info(args):
    field = load(args.file)
    vertices = collections.Counter(len(n.polygon) for n in field.nodes)
    one_way = sum(1 for l in field.links
                  if sum(1 for n in field.nodes if l.index in n.links) == 1)
    gates = field.gates()
    print("%s" % args.file)
    print("  nodes        %d, %d polygon vertices, %s"
          % (len(field.nodes), sum(len(n.polygon) for n in field.nodes),
             ", ".join("%d x%d" % (k, v) for k, v in vertices.most_common(5))))
    print("  links        %d%s"
          % (len(field.links),
             "" if not one_way else ", %d listed from one side only" % one_way))
    print("  routes       %d entries, %d gated"
          % (sum(len(l.routes) for l in field.links),
             sum(1 for l in field.links for r in l.routes if r.gate)))
    print("  partitions   %d, largest holds %d nodes"
          % (len(field.partitions),
             max((len(p.nodes) for p in field.partitions), default=0)))
    if gates:
        print("  gates        %d groups: %s"
              % (len(gates), ", ".join("%d[%d]" % (k, len(v))
                                       for k, v in sorted(gates.items()))))
    box = field.bounds()
    if box:
        print("  extent       x %.0f..%.0f   y %.0f..%.0f   z %.0f..%.0f"
              % (box[0][0], box[0][1], box[1][0], box[1][1], box[2][0], box[2][1]))
    tags = collections.Counter(n.tag for n in field.nodes)
    print("  node tags    %s" % ", ".join("0x%02x x%d" % (k, v)
                                          for k, v in tags.most_common(5)))
    bad = field.problems()
    print("  self-check   %s" % ("clean" if not bad else "; ".join(bad)))
    return 0


def cmd_nodes(args):
    field = load(args.file)
    for node in field.nodes[:args.limit]:
        print("node %-5d tag 0x%02x  %d vertices, centre (%.0f %.0f %.0f)"
              % (node.index, node.tag, len(node.polygon), *node.centre()))
        for link, (edge, other) in zip(node.links, node.across):
            print("    edge %-2d -> node %-5d via link %d" % (edge, other, link))
    return 0


def cmd_links(args):
    field = load(args.file)
    for link in field.links[:args.limit]:
        print("link %-5d joins %d and %d, edge (%.0f %.0f %.0f)-(%.0f %.0f %.0f)"
              % (link.index, link.a, link.b, *(link.first + link.second)))
        for route in link.routes:
            note = ""
            if route.gate:
                note = "   gate group %d slot %d" % (route.gate_group,
                                                     route.gate_slot)
            print("    -> link %-5d cost %9.2f, comes out at node %-5d%s"
                  % (route.link, route.cost, route.far, note))
    return 0


def cmd_partitions(args):
    field = load(args.file)
    for part in field.partitions[:args.limit]:
        print("partition %-4d %3d nodes  x %.0f..%.0f  z %.0f..%.0f"
              % (part.index, len(part.nodes), part.box[0], part.box[2],
                 part.box[3], part.box[1]))
    return 0


def cmd_obj(args):
    """Write the walkable polygons out as a mesh, so they can be looked at."""
    field = load(args.file)
    with open(args.out, "w") as fh:
        fh.write("# navigation mesh from %s\n" % os.path.basename(args.file))
        base = 1
        for node in field.nodes:
            if len(node.polygon) < 3:
                continue
            for x, y, z in node.polygon:
                fh.write("v %.4f %.4f %.4f\n" % (x, y, z))
            fh.write("g node%d\n" % node.index)
            fh.write("f %s\n" % " ".join(str(base + i)
                                         for i in range(len(node.polygon))))
            base += len(node.polygon)
        if args.portals:
            fh.write("g portals\n")
            for link in field.links:
                fh.write("v %.4f %.4f %.4f\n" % link.first)
                fh.write("v %.4f %.4f %.4f\n" % link.second)
                fh.write("l %d %d\n" % (base, base + 1))
                base += 2
    print("wrote %s" % args.out)
    return 0


def cmd_check(args):
    """Parse a corpus and measure everything the format claims about itself."""
    counts = collections.Counter()
    vertices = collections.Counter()
    for path in args.files:
        try:
            field = load(path)
        except (NodeError, struct.error) as exc:
            counts["failed"] += 1
            if args.verbose:
                print("  %s: %s" % (os.path.basename(path), exc))
            continue
        counts["files"] += 1
        bad = field.problems()
        counts["clean"] += not bad
        if bad and args.verbose:
            print("  %s: %s" % (os.path.basename(path), "; ".join(bad)))
        counts["nodes"] += len(field.nodes)
        counts["links"] += len(field.links)
        counts["partitions"] += len(field.partitions)

        counts["index total"] += len(field.nodes) + len(field.links)
        counts["index exact"] += sum(1 for n in field.nodes
                                     if ref(n.word) == n.index)
        counts["index exact"] += sum(1 for l in field.links
                                     if ref(l.word) == l.index)
        for node in field.nodes:
            vertices[len(node.polygon)] += 1
            if len(node.polygon) < 3:
                continue
            counts["polygon total"] += 1
            counts["polygon convex"] += bool(node.convex())
            counts["polygon wound one way"] += node.area() > 0
        for link in field.links:
            for side in (link.a, link.b):
                if side >= len(field.nodes):
                    continue
                node = field.nodes[side]
                edges = [e for l, (e, _) in zip(node.links, node.across)
                         if l == link.index]
                if not edges or edges[0] >= len(node.polygon):
                    continue
                first, second = node.edge(edges[0])
                counts["edge total"] += 1
                counts["edge on the polygon"] += (
                    (first, second) == (link.first, link.second)
                    or (second, first) == (link.first, link.second))
            here = link.midpoint()
            for route in link.routes:
                if route.link >= len(field.links):
                    continue
                counts["route total"] += 1
                there = field.links[route.link].midpoint()
                counts["route cost is the midpoint distance"] += (
                    abs(math.dist(here, there) - route.cost) < 0.05)
                other = field.links[route.link]
                shared = set([link.a, link.b]) & set([other.a, other.b])
                if len(shared) == 1:
                    counts["route names the far node"] += (
                        route.far == (set([other.a, other.b]) - shared).pop())
                    counts["route links share a node"] += 1
        seen = collections.Counter()
        for node in field.nodes:
            for link in node.links:
                seen[link] += 1
        counts["link listing total"] += len(field.links)
        counts["links listed from both sides"] += sum(
            1 for l in field.links if seen[l.index] == 2)
        covered = sorted(i for p in field.partitions for i in p.nodes)
        counts["partitions cover every node once"] += (
            covered == list(range(len(field.nodes))))
        for part in field.partitions:
            points = [v for i in part.nodes for v in field.nodes[i].polygon]
            if not points:
                continue
            counts["box total"] += 1
            want = (min(p[0] for p in points), max(p[2] for p in points),
                    max(p[0] for p in points), min(p[2] for p in points))
            counts["box is the XZ bound"] += all(
                abs(a - b) < 0.01 for a, b in zip(part.box, want))
        for link in field.links:
            for route in link.routes:
                if route.gate:
                    counts["gated route total"] += 1
                    counts["gated route costs nothing"] += route.cost == 0.0

    print("files                       %d parsed, %d failed"
          % (counts["files"], counts["failed"]))
    print("self-check clean            %d / %d" % (counts["clean"], counts["files"]))
    print("nodes / links / partitions  %d / %d / %d"
          % (counts["nodes"], counts["links"], counts["partitions"]))
    for label, hit, total in (
            ("index == position", "index exact", "index total"),
            ("link edge on the polygon", "edge on the polygon", "edge total"),
            ("route cost == midpoint gap", "route cost is the midpoint distance", "route total"),
            ("route names the far node", "route names the far node", "route links share a node"),
            ("links listed from 2 sides", "links listed from both sides", "link listing total"),
            ("partition box is XZ bound", "box is the XZ bound", "box total"),
            ("polygon convex in XZ", "polygon convex", "polygon total"),
            ("polygon wound one way", "polygon wound one way", "polygon total"),
            ("gated route costs nothing", "gated route costs nothing", "gated route total")):
        if counts[total]:
            print("%-27s %d / %d  %.4f%%"
                  % (label, counts[hit], counts[total],
                     100.0 * counts[hit] / counts[total]))
    print("partitions cover nodes once %d / %d"
          % (counts["partitions cover every node once"], counts["files"]))
    print("polygon vertex counts       %s"
          % ", ".join("%d x%d" % (k, v) for k, v in vertices.most_common(8)))
    return 0 if not counts["failed"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Reader for the NODE payload, the ASKA AI node field.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("info", help="summarise one field and self-check it")
    s.add_argument("file")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("nodes", help="print the nodes and what they connect to")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_nodes)

    s = sub.add_parser("links", help="print the links and their route costs")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_links)

    s = sub.add_parser("partitions", help="print the spatial partitions")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_partitions)

    s = sub.add_parser("obj", help="write the walkable polygons to an OBJ")
    s.add_argument("file")
    s.add_argument("out")
    s.add_argument("--portals", action="store_true",
                   help="add the shared edges as lines")
    s.set_defaults(func=cmd_obj)

    s = sub.add_parser("check", help="parse a corpus and measure the decode")
    s.add_argument("files", nargs="+")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
