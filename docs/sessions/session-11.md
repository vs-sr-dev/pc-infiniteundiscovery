# Session 11 — the floor the AI walks on

**Date:** 2026-08-25
**Goal:** question 2, the `NODE` payload. It sits beside every `SCE-` script in
the same archive, one for one, and had been on the open list since session 3
under the heading "no magic at all, raw data".

## Outcome

Solved. `NODE` is a **navigation mesh** — the walkable floor of a map cut into
convex polygons, with the doorway between each pair of polygons and the cost of
crossing it worked out in advance. All 61 payloads on both discs parse, and
every redundant number in the format is reproduced exactly from the geometry.

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

The specification is [docs/formats/node.md](../formats/node.md).

## Where the name came from

Before any of the bytes made sense, the RTTI recovered in session 1 said what
to expect. Grepping the class inventory for anything navigational returns a
complete parts list:

```
CAINodeField   CAINodeFieldManager   CAIPartition   CAINodeLink
CAIRoutePoint  CAISearchAStar        CAIAStarPoint  CAStarAlgorithm<CAIAStarPoint>
CPartitionOptionDoor  CPartitionOptionToggle  AIFsm_NoMesh
```

A **node field** made of **partitions**, **links** and **route points**,
searched with A*, with partitions that can carry a **door** or a **toggle**.
The resource tag is `NODE`. Every one of those names turned out to have a
structure in the file, and `AIFsm_NoMesh` — the AI state machine for an agent
with no navigation mesh — is what says the rest of the AI assumes one.

## The thing that had to be got right

Nodes, links and partitions refer to one another with a 32-bit word that is
**`index << 8` plus a low byte**. Nothing resolves until that shift is applied,
and it is easy to miss because in a small map the low byte is zero everywhere
and the shift reads as a stride.

The first pass through the corpus made exactly that mistake and reported
adjacency symmetric in 19 files of 44, with 28 128 references landing nowhere.
With the shift applied it is 42 of 44 — and the two that remain are not errors
but **one-way links**, listed by one node and not by the other, which is a drop
an agent can take downwards and not back up. 78 links of 55 140 are like that.

## The measurement that settles it

A node's polygon comes with a parallel array saying, for each link, which of
its own edges that link crosses. A link record separately stores the two
endpoints of the shared edge.

So the two can be compared, and they have to agree from **both** sides:

> The two points stored in a link are exactly the polygon edge at the stated
> index, in both of the polygons that share it — **110 202 of 110 202**.

The edge index, the vertex order within the polygon, the reference shift and
the node array stride all have to be right simultaneously for that to come out,
and it comes out every time.

Two more properties follow the same pattern: the polygons are convex in XZ
(51 930 of 53 185) and **wound the same way in 53 180 of 53 185**. A wrong
stride does not produce consistently wound convex polygons.

## The cost table, and what the search actually runs on

Each link carries a list of route entries, and each entry is a neighbouring
link, a node, a pointer to one float, and a flag word. Reading the float as a
distance and testing it against the geometry:

> The cost is **exactly the distance between the two links' edge midpoints**,
> in 3D, on all **167 316** route entries.

So the A* graph is not over polygons at all. It is over **portal midpoints**,
with the edge weights precomputed at build time — which is what `CAIRoutePoint`
is. And the node field of each entry names the node on the *far* side of the
neighbouring link, so a search arriving through one portal already knows which
polygon the next one lets it out into. That is exact on all 167 316 too.

## Doors

1 512 route entries of 167 316 have a non-zero flag word, and it reads
`(slot << 16) | group`. The group is a record in a small table the header
points at, which carries a slot count.

Three facts arrive together:

* every slot is claimed **exactly once**, in all 61 files — 1 512 slots
  against 1 512 gated entries;
* every gated route **costs zero**, all 1 512;
* the two links involved always meet at a node joining two otherwise separate
  areas.

A connection whose cost the engine has to supply at runtime, in a place where
one room meets another, is a door. `CPartitionOptionDoor` and
`CPartitionOptionToggle` are in the binary, and the
[SNC script](../formats/snc.md) in the same archive binds `DOOR_01_BOTH`,
`DOOR_18_BOTH` and `CTRL_elevator` by name with opcode `0105`.

## The check from outside

Everything above is internal. The check that owes the reader nothing comes
from the neighbouring resource.

Session 10's SNC reader decodes object spawns — opcodes `0149` and `0032` —
with their world positions. Different file, different reader, different
encoding. Taking each archive that holds both a script and a node field and
asking whether the script's spawn positions land inside the nav mesh's XZ
footprint:

> **5 673 of 5 705 — 99.44 % — across 42 scenes.**

Two formats decoded independently agree on where the world is.

## Two false trails worth recording

**The y that was not a y.** The smallest node field in the corpus has all its
polygons at y ≈ 0, but the bit patterns were not zero: every y was exactly the
z of the same vertex with 52 subtracted from the exponent. That looks like a
packing scheme and it is not one — over the whole corpus y takes ordinary
values up to 38 600, and the relation holds on 125 vertices of 157 618. It is
plane-fitting residue in a flat room, y coming out proportional to z because
the plane is horizontal. A structural conclusion from one file would have been
wrong.

**Partitions are not rooms.** They cover every node exactly once and have a
tidy bounding rectangle, which invites reading them as connected regions. They
are not: 34 005 links of 55 140 join nodes in two *different* partitions. They
are a broad-phase spatial index — what you use to find which polygon a
character is standing on without testing all 3 649 of them.

## Tooling

`tools/node.py` is new: `info`, `nodes`, `links`, `partitions`, `check` over a
corpus, and `obj`, which writes the walkable polygons out as an n-gon mesh with
one group per node and, with `--portals`, every shared edge as a line — so a
map's floor plan can be opened in a modelling tool and looked at.

## Left open

1. **The low byte of a node's own reference.** 0 on 35 002 of 53 987, 1 to 7
   on most of the rest, `0xFF` on 2 143. It is not the partition index, the
   link count, the vertex count, or the number of cross-partition links — all
   tested. Every reference *to* a node carries 0 instead, so it belongs to the
   record and not to the identity.
2. **The values in a gate group's slot list** — small integers, 2 and 9 in the
   files examined. The one part of the door mechanism not accounted for.
3. **The trailing table at header `+0x28`**, in 47 files of 61, whose records
   begin `0x00440000` or `0x00440004`.
4. **802 nodes have a two-vertex polygon** — a segment rather than an area.
   They sit in the graph like any other node, presumably connectors across
   something with no floor of its own.
