# XDVDFS — the Xbox / Xbox 360 on-disc filesystem

XDVDFS is the read-only filesystem Microsoft shipped on both original Xbox and
Xbox 360 game discs. It is deliberately minimal: no allocation bitmap, no
fragmentation, no journal. Every file is a single contiguous run of sectors,
because the disc is written once by a mastering tool and never modified.

Its one interesting design decision is that a directory is not a list. It is a
**balanced binary search tree** serialised into a contiguous byte range, so
resolving one name inside a directory of a thousand entries costs ten
comparisons instead of a thousand. On a 2001-era DVD drive with a seek time
measured in tens of milliseconds, that mattered.

All integers are little-endian.

## 1. Locating the volume

The unit of addressing is a **2048-byte sector**. Sector numbers in the
filesystem are relative to the start of the *game partition*, not to the start
of the image file. On a full retail dump the game partition begins at a fixed
byte offset, past the DVD-Video compatibility area:

| Disc format | Partition base | Notes |
| --- | --- | --- |
| Raw / extracted | `0x00000000` | Filesystem-only image, no video area |
| XGD1 | `0x18300000` | Original Xbox |
| XGD2 | `0x0FD90000` | Xbox 360, 2005–2011 |
| XGD3 | `0x02080000` | Xbox 360, 2011 onward |

The **volume descriptor** occupies exactly one sector at sector 32 relative to
the partition base — that is, `base + 0x10000`.

## 2. Volume descriptor

| Offset | Size | Field |
| --- | --- | --- |
| `0x000` | 20 | Magic `MICROSOFT*XBOX*MEDIA` |
| `0x014` | 4 | Root directory table start sector |
| `0x018` | 4 | Root directory table size, in bytes |
| `0x01C` | 8 | Volume creation time, Windows `FILETIME` |
| `0x024` | 1992 | Unused, filler |
| `0x7EC` | 20 | Magic `MICROSOFT*XBOX*MEDIA` again |

The magic appears twice, at the first and last 20 bytes of the sector. Checking
both is the cheap way to reject a sector that happens to start with the right
bytes — probe both before accepting a partition base.

`FILETIME` counts 100-nanosecond ticks since 1601-01-01 UTC. In practice it
records when the mastering tool built the image, which is a useful (and rarely
tampered with) date stamp for a release.

## 3. Directory tables

A directory's contents live in a contiguous byte range starting at its
`start sector`, `size` bytes long. `size` is always a multiple of 2048; the
tail of the final sector is padded with `0xFF`.

Entries are **4-byte aligned**. Child pointers are expressed in *4-byte units*
measured from the start of the table, so an offset value of `n` means byte
`n * 4`. The root of the tree is always at offset 0.

### Directory entry

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 2 | Left subtree offset, in 4-byte units (`0xFFFF` = none) |
| `0x02` | 2 | Right subtree offset, in 4-byte units (`0xFFFF` = none) |
| `0x04` | 4 | Start sector of the file, or of the subdirectory's own table |
| `0x08` | 4 | Size in bytes |
| `0x0C` | 1 | Attributes |
| `0x0D` | 1 | Filename length, in bytes |
| `0x0E` | *n* | Filename, ASCII, not NUL-terminated |

### Attributes

| Bit | Meaning |
| --- | --- |
| `0x01` | Read-only |
| `0x02` | Hidden |
| `0x04` | System |
| `0x10` | Directory |
| `0x20` | Archive |
| `0x80` | Normal |

Retail discs set `0x20` (archive) on nearly every file and `0x10` on
directories; the other bits are rare and worth noting when they appear.

## 4. Walking the tree

Two details will bite a naive implementation:

**Padding looks like an entry.** The `0xFF` padding at the end of a table
decodes as `left = right = 0xFFFF`, `start sector = 0xFFFFFFFF`. Treat that
combination as a terminator rather than as a real entry.

**Offset 0 is ambiguous.** It is both the valid offset of the tree root and the
value some mastering tools write to mean "no child". Since the root is reached
before any child pointer is followed, treating a child offset of `0` as "none"
is safe, and it prevents an infinite loop back to the root.

A defensive walker should also keep a set of visited offsets, bound the table
size it is willing to allocate, and refuse an entry whose filename would run
past the end of the table. Corrupt or deliberately malformed images exist.

## 5. Ordering

Entries are sorted for a case-insensitive comparison that orders by name
length first and byte value second. This is not the same as an ASCII sort, so
do not assume an in-order traversal will match `sort` output. Extraction tools
should sort by path themselves after the walk, which is what `tools/xdvdfs.py`
does.

## 6. Implementation

See [`tools/xdvdfs.py`](../../tools/xdvdfs.py) for a complete reader:
autodetection of the partition base, volume descriptor parsing, an iterative
tree walk with the guards described above, CSV manifest output, and extraction.
