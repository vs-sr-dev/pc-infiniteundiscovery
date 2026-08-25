# NODE — the AI node field

Every scene archive that carries a [`SCE-` script](snc.md) carries a `NODE`
resource beside it, one for one: 44 pairs on disc 1, 17 more in disc 2's
`ud1.bin`. The payload has no ASCII magic — it opens with the constant
`0x0131F119` — which is why the
[resource-payload census](resource-payloads.md) could only ever call it "no
magic, raw data", and why it stayed open from session 3 to session 11.

It is a **navigation mesh**: the walkable floor of a map, cut into convex
polygons, with the doorways between them and the cost of crossing each one
worked out in advance.

**Status: solved.** All 61 payloads parse; every reference in every record
resolves; and the two numbers the format states redundantly — where a link's
edge lies, and what a route costs — are reproduced exactly from the geometry
in every one of the 277 518 cases where they can be checked.

```
files                       61 parsed, 0 failed
self-check clean            61 / 61
nodes / links / partitions  53987 / 55140 / 32854
index == position           109127 / 109127  100.0000%
link edge on the polygon    110202 / 110202  100.0000%
route cost == midpoint gap  167316 / 167316  100.0000%
route names the far node    167316 / 167316  100.0000%
links listed from 2 sides   55062 / 55140  99.8585%
partition box is XZ bound   32804 / 32854  99.8478%
polygon convex in XZ        51930 / 53185  97.6403%
polygon wound one way       53180 / 53185  99.9906%
gated route costs nothing   1512 / 1512  100.0000%
partitions cover nodes once 61 / 61
```

## 1. The engine names every part of it

The RTTI recovered in [session 1](../sessions/session-01.md) describes this
file almost field by field:

```
CAINodeField          CAINodeFieldManager
CAIPartition          Aska::TArray<const CAIPartition *>
CAINodeLink           Aska::TArray<const CAINodeLink *>
CAIRoutePoint         Aska::TArray<CAIRoutePoint>
CAISearchAStar        CAIAStarPoint    CAStarAlgorithm<CAIAStarPoint>
CPartitionOptionDoor  CPartitionOptionToggle
CPartitionOptionTroopPlayer            CPartitionOptionTroopEnemy
AIFsm_NoMesh
```

A node field made of partitions, links and route points, searched with A* over
`CAIAStarPoint`, with partitions that can carry a door or a toggle — and
`AIFsm_NoMesh`, the state machine for an agent that has no navigation mesh,
which is what tells you the rest of the AI assumes one.

## 2. References are shifted by eight

Nodes, links and partitions refer to one another with a 32-bit word that is
**`index << 8`, plus a low byte to be masked off**. Getting that wrong is the
one thing that stops the file making sense, and it is easy to miss: in a small
map the low byte is zero everywhere and the shift looks like a stride.

The index is exact — `word >> 8` equals the record's own position for every
node and every link in all 61 payloads, 109 127 of them.

What the low byte carries is not known. On a node's own reference it is 0 on
35 002 of 53 987, 1 to 7 on most of the rest, and `0xFF` on 2 143. Every
reference *to* a node carries 0 instead, so it belongs to the record rather
than to the identity.

## 3. The header

0x2C bytes, big-endian. The offsets are plain byte offsets from the start of
the file — unlike SNC, nothing here counts words.

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | `0x0131F119` |
| `+0x04` | 4 | Zero in all 61 |
| `+0x08` | 4 | Node count |
| `+0x0C` | 4 | Link count |
| `+0x10` | 4 | Partition count |
| `+0x14` | 4 | Offset to the nodes |
| `+0x18` | 4 | Offset to the links |
| `+0x1C` | 4 | Offset to the partitions |
| `+0x20` | 4 | Zero in all 61 |
| `+0x24` | 4 | Offset to the gate table, or zero |
| `+0x28` | 4 | Offset to a trailing table, or zero |

## 4. Nodes — the walkable polygons

0x18 bytes each:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | Its own reference |
| `+0x04` | 4 | Zero in all 53 987 nodes |
| `+0x08` | 4 | Link count |
| `+0x0C` | 4 | Offset to that many link references, four bytes each |
| `+0x10` | 4 | Offset to that many `(edge, neighbour)` pairs, eight bytes each |
| `+0x14` | 4 | Offset to the polygon |

The polygon is a count followed by that many `(x, y, z)` floats. The vertices
are full 3D points, so the mesh follows the terrain rather than sitting on a
plane — only 60 % of polygons are flat to within one unit.

Two properties hold across the corpus and neither is something a wrong stride
would produce: the polygons are **convex in XZ** (51 930 of 53 185) and
**wound the same way** (53 180 of 53 185 have positive XZ area). Most are
small — 19 827 triangles and 15 555 quadrilaterals, and the largest runs
to 48 sides.

The two per-node arrays run in step. Entry *k* of the first names a link;
entry *k* of the second says which of this polygon's edges that link crosses
and which node lies beyond it. **Edge *k* runs from vertex *k* to vertex
*k+1*.**

## 5. Links — the shared edges

The link array holds `(reference, offset)` pairs; the record itself is 0x28
bytes:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | Route entry count |
| `+0x04` | 4 | Offset to the route entries |
| `+0x08` | 4 | One of the two nodes it joins |
| `+0x0C` | 4 | The other |
| `+0x10` | 12 | One end of the shared edge |
| `+0x1C` | 12 | The other end |

**The two stored points are exactly the polygon edge — in both of the polygons
that share it, on 110 202 of 110 202 sides.** That is the measurement that
settles the whole reading: the edge index in the node, the vertex order in the
polygon, the reference shift and the node array stride all have to be right at
once for it to come out, and it comes out every time.

78 links of 55 140 are listed by only one of the two nodes they join. They are
one-way connections — a drop the AI can take downwards but not back up.

## 6. Route entries — the cost table

0x10 bytes each:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | The node on the far side of the neighbouring link |
| `+0x04` | 4 | A neighbouring link |
| `+0x08` | 4 | Offset to one float: the cost of getting there |
| `+0x0C` | 4 | Gate reference, or zero |

Two things are exact over all 167 316 entries:

* the two links **always share exactly one node**, and the far-side field
  names the *other* node of the neighbouring link — so a search that arrives
  through one portal knows where the next one lets it out;
* **the cost is the distance between the two links' edge midpoints**, in 3D,
  to within 0.05.

So the A* graph is not over polygons but over **portal midpoints**, with the
edge weights baked into the file. `CAIRoutePoint` is the name the engine gives
them.

## 7. Partitions — a spatial index

0x18 bytes each: a node count, an offset to that many node references, and
four floats that are **`minX, maxZ, maxX, minZ`** of the nodes listed — an
unusual order, and it holds to 0.01 on 32 804 of 32 854 partitions.

The partitions cover every node exactly once in all 61 files. They are not
connectivity groups: 34 005 of 55 140 links join nodes in two *different*
partitions. They are a broad-phase index, which is what you would use to find
which polygon a character is standing on without testing all 3 649 of them.

## 8. Gates — doors and toggles

Where a route entry's last word is not zero it reads `(slot << 16) | group`.
The group is a record in the table at header `+0x24` — a count and an offset,
then records of `(group id, slot count, offset to that many values)`.

Three things line up:

* **every slot is claimed exactly once**, in all 61 files — 1 512 slots
  against 1 512 gated route entries;
* **every gated route costs zero**, all 1 512 of them;
* the two links involved always meet at a node that joins two otherwise
  separate areas.

That is a switchable connection whose cost the engine has to supply at
runtime, which is exactly what `CPartitionOptionDoor` and
`CPartitionOptionToggle` are, and what the scene script of the same archive
binds by name as `DOOR_01_BOTH`, `DOOR_18_BOTH` and `CTRL_elevator`.

## 9. The check from outside

Everything above is internal to the format. The check that owes it nothing
comes from its neighbour in the archive.

An [SNC script](snc.md) spawns objects at world positions with opcodes `0149`
and `0032`. Those positions are decoded by a different reader, from a
different file, in a different encoding — and **5 673 of 5 705 of them fall
inside the XZ footprint of the nav mesh belonging to the same archive**, over
42 scenes. 99.44 %.

Two formats decoded independently agree on where the world is.

## 10. Reproducing

```
python tools/mron.py extract <image> --offset N --length N \
    --tag NODE --decompress out/
python tools/node.py info       out/xxx_NODE.bin
python tools/node.py links      out/xxx_NODE.bin --limit 5
python tools/node.py partitions out/xxx_NODE.bin
python tools/node.py obj        out/xxx_NODE.bin navmesh.obj --portals
python tools/node.py check      out/*.bin
```

`obj` writes the walkable polygons as an n-gon mesh, one group per node, and
with `--portals` adds every shared edge as a line — so the floor plan of a map
can be opened in any modelling tool and looked at.

## 11. What is left

* **The low byte of a node's own reference**, described in
  [§2](#2-references-are-shifted-by-eight).
* **The values in a gate group's slot list.** They are small integers, 2 and 9
  in the files examined, and they are the one part of the door mechanism that
  is not accounted for.
* **The trailing table at header `+0x28`**, present in 47 files of 61, whose
  records begin `0x00440000` or `0x00440004`.
* **802 nodes have a two-vertex polygon** — a segment, not an area. They sit
  in the graph like any other node and are presumably a connector across
  something with no floor of its own, such as a stair or a ledge.
