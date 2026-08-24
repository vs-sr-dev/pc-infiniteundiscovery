# Disc layout

Infinite Undiscovery ships on two Xbox 360 DVDs. Both are XGD2 discs, and both
were mastered on the same evening, about half an hour apart.

Everything below was read from European retail discs. All offsets are byte
offsets into a full (Redump-style) disc image.

## Physical form

| | Disc 1 | Disc 2 |
| --- | --- | --- |
| Image size | 7 835 492 352 bytes | 7 835 492 352 bytes |
| Disc format | XGD2 | XGD2 |
| Game partition base | `0x0FD90000` | `0x0FD90000` |
| Root directory sector | 701 980 | 1 774 503 |
| Volume timestamp (UTC) | 2008-07-08 20:52:54 | 2008-07-08 21:19:37 |

7 835 492 352 bytes is the canonical XGD2 size: the image covers the DVD-Video
compatibility area at the front of the disc as well as the game partition, so
nothing has been trimmed. The European release followed on 5 September 2008,
roughly two months after these masters were built.

## Filesystem contents

The filesystem is startlingly small — four files and one directory per disc.
There is no directory tree of assets at all.

**Disc 1**

| Path | Size | Sector |
| --- | ---: | ---: |
| `/$SystemUpdate/su20076000_00000000` | 7 229 440 | 1 779 904 |
| `/default.xex` | 11 055 104 | 696 582 |
| `/ud1.bin` | 2 207 584 256 | 701 981 |
| `/ud2.bin` | 2 800 330 752 | 1 783 936 |

**Disc 2**

| Path | Size | Sector |
| --- | ---: | ---: |
| `/$SystemUpdate/su20076000_00000000` | 7 229 440 | 1 779 904 |
| `/default.xex` | 11 055 104 | 1 774 504 |
| `/ud1.bin` | 3 217 651 712 | 203 384 |
| `/ud2.bin` | 3 289 788 416 | 1 783 936 |

`$SystemUpdate` is the stock dashboard update Microsoft required every disc to
carry; it is not part of the game. Both discs carry the same 7 229 440-byte
copy.

Note that the two discs place `ud1.bin` very differently — sector 701 981 on
disc 1, sector 203 384 on disc 2 — while `ud2.bin` sits at exactly the same
sector on both. Constant-linear-velocity DVDs read faster toward the outer
edge, so this looks like deliberate placement rather than an accident of the
mastering tool.

## The executable

`default.xex` is a standard XEX2 image, and it is 11 055 104 bytes on both
discs — but the two copies are **not** byte-identical. 99.5 % of the bytes
differ, in four clusters:

| Range | What it is |
| --- | --- |
| `0x0000A0`–`0x00020F` | Security info: encrypted AES session key and signature |
| `0x001374`–`0x001386` | Multi-disc header. Identical except the final byte: `01` on disc 1, `02` on disc 2 |
| `0x0013CC`–`0x0013DB` | 16-byte media ID, unique per disc |
| `0x003000`–`0xA8AFFF` | The encrypted image body |

The multi-disc header reads
`… 00 00 00 02 | 00 00 00 02 | 53 51 07 db | 00 00 0N` on both discs, where
`53 51` is ASCII `SQ` and `N` is the disc number. Since the header fields,
section layout and total size all match, the two copies are almost certainly
the same program encrypted under different per-disc session keys — but that
stays a hypothesis until the images are actually decrypted.

## Where the game data is

`ud1.bin` and `ud2.bin` hold everything else: geometry, animation, textures,
audio, video, scripts. Neither has a global table of contents. Each is a
sequence of self-describing [NORM archives](formats/norm-mron.md) laid end to
end on 2048-byte boundaries, with video streams and compressed blocks filling
the gaps.

The two files divide the work by kind, not by area:

* **`ud1.bin`** carries what the game needs everywhere — 5 700+ animations,
  1 500+ meshes, 1 200+ sounds, and a `WEAP` set that is byte-for-byte
  identical in count on both discs (217 entries).
* **`ud2.bin`** carries per-area content — dominated by `EPAC`/`APAC` packed
  blocks and `MTEX` textures, organised into 40 groups.

Container offsets, for feeding to the tools:

| Container | Offset | Length |
| --- | ---: | ---: |
| Disc 1 `ud1.bin` | 1 703 536 640 | 2 207 584 256 |
| Disc 1 `ud2.bin` | 3 919 380 480 | 2 800 330 752 |
| Disc 2 `ud1.bin` | 682 409 984 | 3 217 651 712 |
| Disc 2 `ud2.bin` | 3 919 380 480 | 3 289 788 416 |

## Video

Roughly 3.2 GB across the four containers is Windows Media (ASF) video, found
by its header GUID `75B22630-668E-11CF-A6D9-00AA0062CE6C`. It sits in the gaps
between archives rather than inside them. The current tooling reports each
contiguous run as one gap, so those figures are runs of concatenated streams,
not single files — splitting them into individual movies is still to do.

## Reproducing this

```
python tools/xdvdfs.py info "disc1.iso"
python tools/xdvdfs.py list "disc1.iso"
python tools/mron.py census "disc1.iso" --offset 1703536640 --length 2207584256
```
