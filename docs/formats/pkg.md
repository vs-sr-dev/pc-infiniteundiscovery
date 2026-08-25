# PKG — the PlayStation package

Every other format in this directory is tri-Ace's. This one is Sony's, and it
is here for a single reason: two specimens in the [cross-title
test](../aska-across-titles.md) were never pressed on a disc — *Star Ocean:
Integrity and Faithlessness* on the Japanese PlayStation 3, and *Phantasy Star
Nova* on the PlayStation Vita. Both existed only as downloads, so there is no
ISO to walk and no filesystem to list — there is one `.pkg` file and, for the
PlayStation 3 one, a 16-byte `.rap` licence beside it. Until the package is
opened there is nothing for `aska.py` to sweep.

**Status:** solved on the PlayStation 3 — all 82 items listed, every self-check
passing, bodies extracting — and half-solved on the Vita, where the container
opens and reads its 85 filenames but the bodies sit behind a second layer this
reader deliberately does not go after. The same is true of the PlayStation 3
package's NPDRM SELF executables. See [§4a](#4a-the-vita-variant) and
[§5](#5-what-stays-shut).

Everything below describes the PlayStation 3 package unless it says otherwise;
the type word at `0x06` is `1` there and `2` on the Vita.

## 1. Layout

Big-endian, which is convenient: the same byte order as everything else here.

**Header**, `0xC0` bytes:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | `\x7fPKG` |
| `0x04` | 2 | Revision — `0x8000` retail |
| `0x06` | 2 | Package type — 1 PS3, 2 PSP/Vita |
| `0x08` | 4 | Offset of the metadata block |
| `0x0C` | 4 | Number of metadata records |
| `0x10` | 4 | Header size (`0xC0`) |
| `0x14` | 4 | Item count |
| `0x18` | 8 | Total size — must equal the file's |
| `0x20` | 8 | Offset of the encrypted run |
| `0x28` | 8 | Length of the encrypted run |
| `0x30` | 0x24 | Content id, ASCII |
| `0x60` | 0x10 | QA digest |
| `0x70` | 0x10 | Package RIV — the counter the encryption starts from |

**Metadata**, from the offset at `+0x08`: `(u32 id, u32 size, body)` records,
laid end to end. The ones this specimen carries are the DRM type, the content
type, the package size, the `make_package_npdrm` revision, a second QA digest
and a software version.

**The encrypted run** holds everything else, and offsets inside it are relative
to its own start:

* the item table, `0x20` bytes per item, right at offset 0;
* the filenames, in one run just past the table;
* the file bodies.

**Item record**, `0x20` bytes:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | Filename offset |
| `0x04` | 4 | Filename length |
| `0x08` | 8 | Body offset |
| `0x10` | 8 | Body length |
| `0x18` | 4 | Flags — the low byte is the kind |
| `0x1C` | 4 | Zero |

Kinds seen here: 1 NPDRM SELF, 2 NPDRM EDAT, 3 file, 4 directory.

## 2. The encryption

AES-128 in **counter mode**, with a key that is the same in every retail
PlayStation 3 package and has been documented for many years, and a counter
that starts at the 16-byte RIV in the header and advances once per 16 bytes.

Counter mode is the reason this reader can be cheap. Any offset decrypts on its
own, without touching a byte in front of it, once the counter has been advanced
by the number of blocks that precede it:

```python
counter = int.from_bytes(riv, "big") + (offset // 16)
```

So pulling one 34 MB file out of an 11.2 GiB package costs 34 MB of work, and
the item table — 2 624 bytes at offset 0 — costs nothing at all.

## 3. The checks, and why they matter more here

A wrong key does not fail loudly. It produces a table of plausible-looking
numbers that prints without complaint, and the only thing separating that from
a real table is whether the numbers agree with each other. `pkg.py` therefore
refuses to list or extract until all of these pass:

| Check | On this package |
| --- | --- |
| Total size matches the file | 12 025 027 536, exactly |
| Encrypted run inside the file | `0x180 + 0x2CCBF59F0` |
| Item table inside the run | 82 items, `0xA40` bytes |
| Every body inside the run | 0 outside |
| Every filename printable ASCII | 82 of 82 |
| Names between the table and the first body | table ends `0xA40`, names end `0x156F`, first body `0x1570` |

The filename check is the one that settles it: 82 consecutive runs of printable
ASCII, each exactly where a `u32` said it would be, is not something a wrong
key produces.

That is also the evidence for reading revision `0x8000` as *retail* rather than
debug. The published tables disagree with each other; the retail key is the one
that turns this file into 82 printable filenames, and that is the reading.

## 4. What is in this one

82 items, 11.2 GiB, and nearly all of it in nine CRI **CPK** archives:

| | |
| --- | --- |
| `USRDIR/FAI_main_ps3.cpk` | 4.53 GB |
| `USRDIR/FAI_main_ps3_RgA.cpk` | 7.04 GB |
| `USRDIR/FAI_main_ps3_VoJPN.cpk` | 306 MB, voice |
| `USRDIR/FAI_main_ps3_LgJPN.cpk` | 34.7 MB, text |
| `USRDIR/shader/AHSLDiskCachePs3_*` | 30 files, 84 MB |
| `USRDIR/sprx/*.sprx` | 7 modules, 1.4 MB |
| `USRDIR/EBOOT.BIN` | 5.4 MB |

`USRDIR/Version.txt` dates the build: **2016-03-31 15:56:46**, program revision
12072, asset revision 48989.

The shader caches and the module names are discussed in
[aska-across-titles.md](../aska-across-titles.md) — they are the part of this
listing that is evidence rather than inventory.

## 4a. The Vita variant

A PlayStation Vita package is the same container with a different key, and the
key is not used directly. The published constant encrypts the package's **own
RIV**, and the 16 bytes that come out are what drives the counter. Which
constant applies is supposed to follow from the content type, and the published
tables of that mapping disagree with each other.

So `pkg.py` does not use a table. It **tries** each candidate and keeps the one
whose item table passes the checks — which is not a shortcut, because those
checks are the same evidence the PS3 path relies on: 85 consecutive runs of
printable ASCII, each exactly where a `u32` said it would be, is not something
a wrong key produces. On Phantasy Star Nova the winner is the second Vita
constant, and every check passes.

The item flag byte means more on Vita than on PS3: alongside 3 for a plain file
this package uses 0x0E, 0x10, 0x11, 0x12, 0x13, 0x15, 0x16 and 0x18, and those
are printed by number rather than guessed at.

**The bodies stay shut, and not because of the key.** Under the package layer a
Vita title has a second one, PFS, whose key is sealed by the licence — the
package even carries its metadata, in `sce_pfs/files.db` and `sce_pfs/unicv.db`.
Every candidate key was tried against the body of `sce_sys/pic0.png`, a file
whose first four bytes are known in advance, and none of them produces a PNG
while the same key reads all 85 filenames correctly. That is the signature of a
second layer rather than a wrong key, and opening it means obtaining a title's
licence key, which is a different activity from reading a format and is not
what this repository does.

## 5. What stays shut

The eight NPDRM SELF items — `EBOOT.BIN` and the seven `.sprx` modules —
carry a second layer of encryption keyed by the licence in the `.rap`, and
`pkg.py` does not touch it. Extracted, they yield their SCE header and the
content id string and nothing else.

That closes the third rung of the [test ladder](../../TODO.md) on this
specimen. There is no executable to hand to `rtti.py`, so the evidence has to
come from the data files — which, as it turns out, is where it came from
anyway on the two Xbox 360 titles, both of which shipped with RTTI stripped.

## 6. Reproducing

```
python tools/pkg.py info    <pkg>
python tools/pkg.py list    <pkg> [--only SUBSTRING] [--type N]
python tools/pkg.py extract <pkg> <outdir> [--only SUBSTRING] [--max-size N]
python tools/pkg.py decrypt <pkg> <out.bin>
```

`decrypt` writes the whole encrypted run out as one plaintext file with its
offsets preserved, which is what `aska.py identify` wants: a stream to sweep in
which an offset means the same thing it means inside the package.
