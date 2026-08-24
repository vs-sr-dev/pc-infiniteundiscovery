# XDBF — Xbox 360 title metadata

Every Xbox 360 title embeds an XDBF database in its executable's resource
section. It is what the dashboard reads to show a game's name, its icon and its
achievement list, so it carries the achievement names, both descriptions, the
gamerscore values and the PNG icons, in every language the title shipped with.

## 1. Finding it

The XEX `RESOURCE_INFO` optional header gives a virtual address and a size.
Subtract the image base to get an offset into the decrypted PE.

For Infinite Undiscovery: resource `535107DB` at `0x82AB0000`, 159 023 bytes,
image base `0x82000000`, so the blob sits at `0xAB0000` in `default.exe`.

The resource is named after the title id, which is `0x535107DB` — the high half
being ASCII `SQ`.

## 2. Container

Big-endian throughout.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | Magic `XDBF` |
| `0x04` | 4 | Version (`0x00010000`) |
| `0x08` | 4 | Entry table capacity, in entries |
| `0x0C` | 4 | Entries used |
| `0x10` | 4 | Free table capacity |
| `0x14` | 4 | Free entries used |
| `0x18` | .. | Entry table, 18 bytes per slot |
| .. | .. | Free table, 8 bytes per slot |
| .. | .. | Data |

The data region begins at `0x18 + entry_capacity * 18 + free_capacity * 8`, and
every entry's offset is relative to **that** point rather than to the file.
Getting this wrong is the usual reason a parser reads garbage.

### Entry

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 2 | Namespace |
| `0x02` | 8 | Id |
| `0x0A` | 4 | Offset into the data region |
| `0x0E` | 4 | Length |

| Namespace | Contents | Id means |
| --- | --- | --- |
| 1 | Metadata tables | a FourCC in the low 32 bits |
| 2 | Images, raw PNG | image id; `0x8000` is the title icon |
| 3 | String tables | language id |

## 3. String table (`XSTR`)

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | Magic `XSTR` |
| `0x04` | 4 | Version |
| `0x08` | 4 | Size |
| `0x0C` | 2 | String count |
| `0x0E` | .. | Repeated: `u16` id, `u16` byte length, UTF-8 bytes |

The strings are UTF-8, not UTF-16, which is worth noting for a Microsoft format
of this era.

## 4. Achievement table (`XACH`)

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | Magic `XACH` |
| `0x04` | 4 | Version |
| `0x08` | 4 | Size |
| `0x0C` | 2 | Achievement count |
| `0x0E` | .. | Entries, 36 bytes each |

Each entry:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 2 | Achievement id |
| `0x02` | 2 | String id — name |
| `0x04` | 2 | String id — description once unlocked |
| `0x06` | 2 | String id — description while locked |
| `0x08` | 4 | Image id |
| `0x0C` | 2 | Gamerscore |
| `0x0E` | 2 | Reserved |
| `0x10` | 4 | Flags |
| `0x14` | 16 | Reserved |

**Gamerscore is 16-bit, not 32.** That was settled by arithmetic rather than by
assumption: read as `u16`, the fifty values sum to exactly 1000, which is the
title's advertised total. Read as `u32` they do not.

## 5. What Infinite Undiscovery's copy holds

25 entries: 11 metadata tables, 12 PNGs, and 2 string tables.

Only **two languages** ship — id 1 (English) and id 2 (Japanese) — with 317
strings each. This is a PAL disc, so its dashboard-facing text is English while
the game itself is localised elsewhere.

Metadata tables present: `XACH`, `XCXT`, `XITB`, `XMAT`, `XPBM`, `XPRP`,
`XRPT`, `XSRC`, `XSTC`, `XTHD`, `XVC2`. The largest by far is `XSRC` at 23 008
bytes.

The achievement table has 50 entries totalling 1000 gamerscore, ranging from
1G (`Seraphic Gatekeeper`) to 50G (`Compulsive`). Both descriptions are stored,
so the locked text is recoverable too — achievement 1 reads "Launched your
first surprise attack." once unlocked and "Attack the enemy without being
detected." before that.

## 6. Implementation

[`tools/xdbf.py`](../../tools/xdbf.py) — `info` dumps the entry table,
`achievements` prints the list in any shipped language, `strings` dumps a
string table, `images` writes the embedded PNGs out.
