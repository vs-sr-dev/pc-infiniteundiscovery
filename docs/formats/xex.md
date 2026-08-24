# XEX2 — the Xbox 360 executable format

An `.xex` is a wrapper around an ordinary PE image. The wrapper holds the
metadata the console needs before it can load anything, and the PE image
follows it, compressed and encrypted.

This document specifies the format and then records what Infinite
Undiscovery's own headers say, because the two are more useful together.

## 1. Header

Big-endian throughout.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | Magic `XEX2` |
| `0x04` | 4 | Module flags |
| `0x08` | 4 | Offset of the PE data within the file |
| `0x0C` | 4 | Reserved |
| `0x10` | 4 | Offset of the security info block |
| `0x14` | 4 | Optional header count |
| `0x18` | .. | Optional headers, 8 bytes each: `(key, value)` |

The **low byte of an optional header's key** says how to read `value`:

* `0x00` or `0x01` — the value *is* the datum, stored inline.
* `0xFF` — the value is a file offset to a block whose first dword is its size.
* anything else *n* — the value is a file offset to *n* × 4 bytes.

That one rule makes the whole optional header table walkable even when you do
not recognise a key, which matters because the set of keys grew over the
console's life.

## 2. Security info

Located at the offset in the main header, and everything below is relative to
it.

| Offset | Size | Field |
| --- | --- | --- |
| `0x000` | 4 | Header size |
| `0x004` | 4 | Image size |
| `0x008` | 256 | RSA signature |
| `0x10C` | 4 | Image flags |
| `0x110` | 4 | Load address |
| `0x140` | 16 | Media id |
| `0x150` | 16 | Encrypted AES session key |
| `0x178` | 4 | Region code |
| `0x17C` | 4 | Allowed media types |
| `0x180` | 4 | Page descriptor count |

## 3. Getting to the PE

Three steps, in this order.

**Recover the session key.** The 16 bytes at `0x150` are an AES-128 key which
is itself encrypted, AES-128-ECB, under a fixed key-encryption key. Retail
discs use the retail key; development builds use an all-zero key.

```
retail: 20 B1 85 A5 9D 28 FD C3 40 58 3F BB 08 96 BF 91
devkit: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Neither is a secret. The retail key is public in every Xbox 360 emulator and
homebrew toolchain, and has to be, since the console itself must hold it to
load a game at all.

**Decrypt.** AES-128-CBC with a zero IV, using the session key, over
everything from `pe_data_offset` to the end of the file.

**Decompress.** The scheme is named in `FILE_FORMAT_INFO`:

| Value | Scheme |
| --- | --- |
| 0 | none |
| 1 | basic |
| 2 | normal (LZX) |
| 3 | delta |

"Basic" is a run-length description of the address space: a list of
`(data length, zero length)` pairs, where the data is copied from the stream
and the zeros are gaps that were never stored. It is trivial to implement and
it is what most retail titles use. "Normal" is LZX and is not implemented in
this repository's tooling.

A correct result starts with `MZ`. That check is worth making, because the
wrong key produces plausible-looking noise rather than an error.

## 4. Infinite Undiscovery's headers

From disc 1 of the European release. Disc 2 differs only in its media id, its
disc number, its LAN key and its session key.

```
image size       : 0xAE0000
load address     : 0x82000000
entry point      : 0x821CBA90
region           : 0x00FF0000  PAL (Europe and Australia)
encryption       : normal (AES-128-CBC)
compression      : basic, 2 blocks
                     [0] data 0x00A58000  zero 0x00050000
                     [1] data 0x00030000  zero 0x00000000
original PE name : default.exe
```

**Execution info.** Title id `0x535107DB` — the high half is ASCII `SQ`, for
Square Enix. Version 2, base version 2, disc 1 of 2, no savegame id.

**Static libraries.** Every one of them from the same SDK:

```
XAPILIB    2.0.6534.16385      D3D9       2.0.6534.16385
XBOXKRNL   2.0.6534.16385      D3DX9      2.0.6534.16385
LIBCPMT    2.0.6534.16385      XGRAPHC    2.0.6534.16385
XMEDIA     2.0.6534.16388      XAUD       2.0.6534.16385
XMP        2.0.6534.16385      MDISC      2.0.6534.8193
XONLINE    2.0.6534.16385
```

XDK build **6534** is the November 2007 release — confirmed independently by
the Microsoft source paths left in the binary, which all read
`e:\xenon\nov07\core\private\...`.

`MDISC` is the multi-disc support library, which is what a two-disc game
needs and most titles do not link.

**Import libraries.** Only two: `xam.xex` and `xboxkrnl.exe`.

**Game ratings.** ESRB is `0xFF`, unrated — as expected on a PAL disc. The
boards that are set: PEGI `0x0D`, PEGI-FI `0x0C`, PEGI-PT `0x0D`, PEGI-UK
`0x0D`, OFLC-NZ `0x04`, KMRB `0x02`, Brazil `0x02`.

**Multi-disc media ids.** Both discs' ids are listed in each executable:

```
disc 1  52a8c8a4ec74457d3af12b4e7a1c58f8
disc 2  55e2ecb103e56e400174fded20854892
```

That is how the game recognises the correct disc when it asks you to swap.

**Checksum and timestamp.** Checksum `0x00AE6EBB`, timestamp `0x48744044`.
Read as UTC that is 2008-07-09 04:36:20, which falls *after* the disc masters
were written (2008-07-08 20:52 and 21:19 UTC). Read as Japan time it lands
about an hour before them, which is the reading that makes chronological
sense — but XEX timestamps are not reliably documented as to zone, so treat
this as an inference rather than a fact.

## 5. Implementation

[`tools/xex.py`](../../tools/xex.py) — `info` prints every header field with
structured decoding for the ones that have known layouts; `extract` performs
the three-step recovery and writes the PE image.

The tool uses pycryptodome when it is installed and otherwise falls back to a
pure-Python AES-128 implementation included in the file, so it has no hard
dependencies. The fallback verifies itself against the FIPS-197 test vector
before use, and has been cross-checked block-for-block against pycryptodome.
