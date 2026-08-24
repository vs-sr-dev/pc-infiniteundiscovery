# NORM ("MRON") — the ASKA resource archive

This is the container that holds essentially all of Infinite Undiscovery's
content. `ud1.bin` and `ud2.bin` are each a plain sequence of these archives,
written end to end on 2048-byte boundaries, with no global index anywhere on
the disc.

Everything here was derived from the retail European discs and verified
arithmetically against both of them. Where something is still a guess, it says
so.

## 1. The name, and a byte-order trap

Every archive opens with the eight ASCII bytes `MRON00.2`. Read those four-byte
groups reversed and they say `NORM` version `2.00`. The same reversal applies
to every type tag inside the archive, so the raw bytes `HSEM` mean `MESH`,
`MINA` mean `ANIM`, `XETM` mean `MTEX`, `AERA` mean `AREA`.

This matters because the payload data is otherwise big-endian, as you would
expect from a PowerPC target. The tags are the exception. A separate family of
lowercase tags found inside mesh payloads — `poly`, `mate`, `idxl`, `attr`,
`strm`, `vlas`, `modf`, `extl`, `eof_` — reads correctly **without** reversal,
which suggests the two came from different parts of the toolchain.

`tools/mron.py` reverses tags for you; every tag it prints is readable.

## 2. Archive header

Big-endian, 32 bytes.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 8 | Magic `MRON00.2` |
| `0x08` | 4 | Entry count |
| `0x0C` | 4 | Alignment applied to the start of the data region |
| `0x10` | 4 | Group id |
| `0x14` | 12 | Reserved, zero |

The **group id** ties archives together. Archives that serve one game area
share it, and they appear consecutively in the container: typically one archive
holding the area's meshes, textures and scene data, immediately followed by a
second holding that area's `APAC`/`EPAC` blocks at a coarser alignment.

Observed alignments are `0x10`, `0x40` and `0x800`. The `0x800` archives are
always the packed-data ones, which is consistent with those payloads being read
straight off the disc a sector at a time.

## 3. Entry table

Immediately after the header, at `0x20`. Big-endian, 32 bytes per entry.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | Type tag, byte-reversed FourCC |
| `0x04` | 2 | Sub-index within the group |
| `0x06` | 2 | Group id |
| `0x08` | 4 | Size in bytes |
| `0x0C` | 4 | Offset, relative to the start of the archive header |
| `0x10` | 16 | Reserved, zero |

An entry's group id normally repeats the archive's own. When it does not, the
entry is presumably referring to a resource owned by another group — that
reading has not been confirmed.

## 4. Deriving the layout

The data region begins at

```
data_start = align_up(0x20 + count * 32, alignment)
```

and entries are stored contiguously from there in offset order, so the total
length of an archive is

```
total = align_up(max(entry.offset + entry.size), 2048)
```

That is the whole trick: because `total` is computable from the header alone,
the container can be walked from front to back without an index. Four worked
examples from disc 1, each confirming the formula:

| Archive | count | align | table ends | data starts | first entry offset |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ud1.bin` `0x16000` | 2 | `0x40` | `0x60` | `0x80` | `0x80` ✔ |
| `ud1.bin` `0x1F800` | 3 | `0x40` | `0x80` | `0x80` | `0x80` ✔ |
| `ud1.bin` `0xA4000` | 24 | `0x10` | `0x320` | `0x320` | `0x320` ✔ |
| `ud2.bin` `0x1749A000` | 49 | `0x800` | `0x640` | `0x800` | `0x800` ✔ |

Contiguity holds too: in the first archive, entry 0 (`IMG-`) sits at `0x80` with
size `0x9000`, and entry 1 (`TTD-`) starts at exactly `0x9080`.

## 5. Resource types

Counts below are from the four retail containers. Meanings marked *unconfirmed*
are inferred from the tag and from what the resource travels with, not from
having parsed the payload.

| Tag | Reading | Confidence |
| --- | --- | --- |
| `MESH` | Geometry | confirmed by payload chunk tags |
| `ANIM` | Animation | confirmed by bone-name strings |
| `MTEX` | Texture, material-bound | unconfirmed |
| `TTEX` | Texture | unconfirmed |
| `IMG-` | Image | unconfirmed |
| `SOND` | Sound | unconfirmed |
| `AREA` | Area / level | unconfirmed |
| `NODE` | Scene node | unconfirmed |
| `SCE-` | Scene | unconfirmed |
| `COLL` | Collision | unconfirmed |
| `SIG-` | Signal / trigger | unconfirmed |
| `WEAP` | Weapon | unconfirmed |
| `EPAC`, `APAC` | Packed data, two flavours | unconfirmed |
| `SKAC` | Travels with skeletons | unknown |
| `SEEK` | Small, numerous | unknown |
| `MINI` | ~16 bytes each | unknown |
| `MAIF`, `TTD-`, `RMD-`, `LNS-` | — | unknown |

The largest single category by volume is `EPAC` at 1.19 GB in disc 1's
`ud2.bin` alone.

Bone names recovered from `ANIM`/`MESH` payloads follow a consistent
convention: `R:M:SK_Hip`, `R:M:POS_ROOT`, `R:M:SK_MARK_01`, `R:M:MARK_OBJ_01`,
`R:M:JUMPMARKER`, `R:M:DIVIDE`, `R:M:DummyPos`. The `R:M:` prefix is almost
certainly a DCC-tool namespace carried through the exporter.

## 6. Gaps

Not all of a container is archives. Two kinds of blob sit between them:

**ASF video.** Identified by the GUID `75B22630-668E-11CF-A6D9-00AA0062CE6C`.
Disc 1's `ud2.bin` begins with one at offset 0.

**SLZ compressed blocks.** 357 sector-aligned occurrences in disc 1's
`ud1.bin`. The header is 32 bytes:

```
0x00  4  "SLZ" + version byte (0x04 observed)
0x04  4  header size (0x20)
0x08  4  0x002E9969   \  the two sizes, in some order --
0x0C  4  0x005786B0   /  which is which is not yet established
0x10  4  zero
0x14  4  0x00000001
0x18  4  checksum?
0x1C  4  0x01020000
```

The compression itself has not been decoded. The 1.88× ratio between the two
size fields is consistent with an LZ variant over game data.

## 7. Open questions

* The first `0x16000` bytes of disc 1's `ud1.bin` precede the first archive and
  are not SLZ, ASF or NORM. High entropy (6.74 bits/byte) with strong
  self-correlation at a 128-byte period — many byte pairs differ by exactly
  `0x80`. Not identified.
* `tools/mron.py` reports each contiguous non-archive run as a single gap, so
  the reported ASF sizes are runs of concatenated streams. They need splitting.
* The SLZ algorithm.
* Payload structure for every tag except the broad strokes of `MESH`.

## 8. Implementation

[`tools/mron.py`](../../tools/mron.py) — walks a container in place inside a
disc image (`--offset` / `--length`), lists archives and gaps (`scan`), emits a
per-entry CSV (`scan --csv`), or summarises by type (`census`).
