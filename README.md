# pc-infiniteundiscovery

Reverse engineering notes, file format documentation and analysis tooling for
**Infinite Undiscovery** (tri-Ace / Square Enix, Xbox 360, 2008).

The game is the first title built on tri-Ace's in-house **ASKA** engine
("tri-Ace Superlative Knowledge-based Architecture"), later reused across
several of the studio's projects. Very little about that engine has been
documented publicly, which is the main reason this repository exists.

## Scope

This is a **documentation and analysis** project. It contains:

* tools that parse the disc filesystem and the game's own container formats,
* written specifications of those formats,
* observations about the engine, its data layout and whatever the developers
  left behind in the shipped build.

It does **not** contain, and will never contain, any data extracted from the
retail disc: no assets, no executables, no text dumps, no disc images. Every
tool here operates on files you supply yourself. See `.gitignore` for the
enforcement.

Infinite Undiscovery is still commercially available in this same Xbox 360
form on the Microsoft Store, so there is no preservation argument for
redistributing it, and this repository does not.

## Repository layout

```
tools/        analysis tools, all standalone Python 3, no dependencies
docs/         written findings
docs/formats/ format specifications, one file per format
docs/sessions/ chronological work log
```

## Tools

| Tool | Purpose |
| --- | --- |
| `tools/xdvdfs.py` | Read the XDVDFS filesystem on an Xbox / Xbox 360 disc image: volume info, full file listing, extraction. |
| `tools/mron.py` | Walk the NORM/MRON resource containers (`ud1.bin`, `ud2.bin`): list archives, dump a per-entry CSV, take a census by resource type, or extract payloads by tag, decompressing them on the way out. Reads in place inside a disc image, so the 12 GB of containers never need extracting. |
| `tools/xex.py` | Read and decrypt XEX2 Xbox 360 executables: full header dump with structured decoding, plus recovery of the PE image. Falls back to a bundled pure-Python AES when pycryptodome is absent. |
| `tools/rtti.py` | Recover a C++ class inventory from the MSVC RTTI type descriptors in a decrypted PE. Demangles namespaces, nested types and templates. |
| `tools/xdbf.py` | Read the XDBF title-metadata database embedded in the executable: achievements in every shipped language, string tables, embedded PNGs. |
| `tools/lzx.py` | LZX decompressor for the XCompress variant, written from the published algorithm. Frame-based and stateful, which is what the format actually requires. |
| `tools/slz.py` | The SLZ compressed-resource wrapper, with bulk self-verification against payload self-reported lengths. |
| `tools/aif.py` | Read AIF textures: header, Xbox 360 untiling, DXT and uncompressed decoding, and a PNG writer with no dependencies. |

### Quick start

```
python tools/xdvdfs.py info    "path/to/disc1.iso"
python tools/xdvdfs.py list    "path/to/disc1.iso" --csv disc1.csv
python tools/xdvdfs.py extract "path/to/disc1.iso" extract/disc1

# Walk the resource container in place, no extraction needed
python tools/mron.py census "path/to/disc1.iso" --offset 1703536640 --length 2207584256

# Pull out every texture, decompressing as needed, and turn one into a PNG
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640     --length 2207584256 --tag MTEX --decompress extract/textures
python tools/aif.py info extract/textures/317BD800_003_MTEX.aif
python tools/aif.py png  extract/textures/317BD800_003_MTEX.aif texture.png

# Recover the executable, then read its class inventory
python tools/xex.py  info    extract/disc1/default.xex
python tools/xex.py  extract extract/disc1/default.xex extract/disc1/default.exe
python tools/rtti.py groups  extract/disc1/default.exe
python tools/rtti.py list    extract/disc1/default.exe --filter "Aska::"
python tools/xdbf.py achievements extract/disc1/default.exe
```

Container offsets for the European release are tabulated in
[docs/disc-layout.md](docs/disc-layout.md).

## Documentation

* [The ASKA engine](docs/aska-engine.md) — what the retail binary reveals about
  tri-Ace's engine: 1 740 recovered class names, the renderer, the AI and
  battle architecture, the shader library.
* [Disc layout](docs/disc-layout.md) — how the two retail discs are physically
  organised, and where the containers sit.
* [NORM / MRON](docs/formats/norm-mron.md) — the ASKA resource archive that
  holds essentially all of the game's content.
* [Resource payloads](docs/formats/resource-payloads.md) — what each resource
  tag actually contains, and the `A?F` file-kind family.
* [SLZ](docs/formats/slz.md) — the compressed-resource wrapper, which turns out
  to be Microsoft XCompress. Solved: all 1 812 blocks in disc 1's `ud1.bin`
  decompress, with nothing left unexplained.
* [AIF](docs/formats/aif.md) — the Aska Image File: every texture in the game,
  stored in the Xbox 360 GPU's own tiled layout.
* [XDBF](docs/formats/xdbf.md) — the title metadata database, achievements
  included.
* [XEX2](docs/formats/xex.md) — the Xbox 360 executable format, and this
  title's header values.
* [XDVDFS](docs/formats/xdvdfs.md) — the on-disc filesystem, fully specified.
* [`docs/census.txt`](docs/census.txt) — resource-type census of all four
  retail containers.

## Status

The disc layout, the container format, the executable, the resource-payload
vocabulary, the compression and the texture format are solved. All 1 812 SLZ
blocks in disc 1's `ud1.bin` decompress with no failures, and all 220 image
resources decode to correct pixels — 150.9 megapixels, checked by eye as well
as by arithmetic.

What remains is the internal structure of the payloads themselves: `ASF `
scenes, `AAF ` animations and `ACF ` collision. Those are now plain files
sitting behind tools that work, rather than questions blocked on compression.
[`TODO.md`](TODO.md) lists what is still open, and
[`docs/sessions/`](docs/sessions/) is the running log of how each piece was
established.
