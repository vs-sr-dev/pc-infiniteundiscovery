# Resource payloads — what each NORM tag actually contains

The [NORM/MRON container](norm-mron.md) labels each resource with a four-byte
tag. Those tags say what a resource *is*, but not what its bytes look like. The
payloads answer that themselves: nearly all of them open with their own magic.

Taking one entry per tag from disc 1's `ud1.bin` gives the whole picture at
once.

| Tag | Payload starts with | Reading |
| --- | --- | --- |
| `ANIM` | `AAF ` | Aska Animation File |
| `COLL` | `ACF ` | Aska Collision File |
| `IMG-` | `AIF ` | Aska Image File |
| `MAIF` | `AIF ` | also an image |
| `RMD-` | `AIF ` | a font atlas, followed by message data |
| `SOND` | `AAC ` | AAC audio |
| `MESH` | `SLZ` → `ASF ` | Aska Scene File, compressed |
| `MTEX` | `SLZ` → `AIF ` | image, compressed — or a nested archive |
| `SCE-` | `SLZ` → `-CNS00.3` | `SNC-` version 3.00, compressed |
| `SKAC` | `SLZ` → `MRON00.2` | nested NORM archive, compressed |
| `APAC` | `SLZ` → `MRON00.2` | nested NORM archive, compressed |
| `EPAC` | `MRON00.2` | nested NORM archive |
| `SEEK` | `MRON00.2` | nested NORM archive |
| `TTEX` | `MRON00.2` | nested NORM archive |
| `WEAP` | `MRON00.2` | nested NORM archive |
| `AREA` | `AERA00.4` | `AREA` version 4.00 |
| `MINI` | `INIM00.1` | `MINI` version 1.00 |
| `SIG-` | `-GIS00.1` | `SIG-` version 1.00 |
| `TTD-` | `DTT\0` | unidentified |
| `NODE` | — | no magic, raw data |

## The `A?F` family

Four three-letter file kinds share a pattern — an `A` for Aska, a letter for
the content, an `F` for file, padded to four bytes with a space:

```
AAF   animation
ACF   collision
AIF   image
ASF   scene
```

This confirms and extends what the executable's RTTI already hinted at. The
engine carries `Aska::AofHandler`, `Aska::AsfHandler` and
`Aska::AcfPrimitiveData_capsule` / `_cube` / `_sphere`, so ACF and ASF were
named in the binary before they were seen on disc, and the ACF collision
primitives are capsule, cube and sphere.

`AOF` is named in the engine (`Aska::AofHandler`, `Aska::AofObject`,
`Aska::DirectAofHandler`) but has not turned up as a payload magic. It is
presumably an object file appearing inside another container, or a runtime type
rather than an on-disc one.

Note that `MESH` decompresses to `ASF `, not to an object format — so in ASKA's
vocabulary a "mesh" resource is a scene file. Three tags (`IMG-`, `MAIF`,
`RMD-`) all decompress to `AIF `, so those distinctions are about *role*, not
about format.

`SOND` payloads are `AAC `, which matches the debug string
`AAC version problem  BGM ID=%d` found in the executable.

## Self-describing lengths

`ASF `, `AIF ` and `AAF ` all store their own total length as a big-endian
`u32` at offset 4. That is worth more than it looks: for a compressed
resource, the length recorded inside the payload is a value the compressor
never touched, so it independently confirms a decompression. Every SLZ decode
in this repository is checked that way.

## Nested archives

Six tags contain another NORM archive rather than a leaf format — `EPAC`,
`SEEK`, `TTEX`, `WEAP` directly, and `SKAC`, `APAC` behind SLZ compression. So
the container structure recurses, and `tools/mron.py` can be pointed at a
decompressed payload as readily as at a disc image.

`MTEX` is a seventh, but only sometimes: of its entries in disc 1's `ud1.bin`,
most hold an image and 46 hold a nested archive. So the tag says what the
resource is *for*, and the payload magic says what it *is* — the two are worth
keeping apart.

## The versioned magics

Several payloads use the same convention as the container itself: a
byte-reversed FourCC followed by an ASCII version.

```
AERA00.4  ->  AREA  4.00
INIM00.1  ->  MINI  1.00
-GIS00.1  ->  SIG-  1.00
-CNS00.3  ->  SNC-  3.00
MRON00.2  ->  NORM  2.00
```

`SNC-` is the odd one: it comes from a `SCE-` resource, and the two names are
close enough to be the same concept ("scene") under two spellings, but that is
a reading rather than a finding.

## What the image payloads turned out to be

`AIF ` is now fully readable — see [aif.md](aif.md). Decoding all 220 images in
disc 1's `ud1.bin` settled two of the tags above:

* **`RMD-` is a message resource, not just an image.** Its `AIF ` is a font
  atlas — a grid of outlined glyphs covering Latin, kana and kanji. In three
  cases the same SLZ stream continues past the end of the image with the ASCII
  string `MessageConvertLib_1.0.0.0`, a build-tool version left in the shipped
  data, which is what the second half of an `RMD-` resource is.
* **`MTEX` is material-bound texture**, including normal-map atlases that pack
  four ground or wall surfaces into a single 1024x1024 sheet.

`IMG-` covers user interface art: the title screen logo, button and control
atlases, damage-number sheets. Every `AIF ` also carries a four-character asset
identifier whose prefix groups it — `CH` character, `BG` background, `EF`
effect, `PG` interface.

## Reproducing

```
python tools/mron.py scan    <image> --offset N --length N --csv entries.csv
python tools/mron.py extract <image> --offset N --length N --tag MTEX --decompress out/
python tools/slz.py decompress <image> --offset <entry offset> out.bin
```
