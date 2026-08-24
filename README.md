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
| `tools/mron.py` | Walk the NORM/MRON resource containers (`ud1.bin`, `ud2.bin`): list archives, dump a per-entry CSV, or take a census by resource type. Reads in place inside a disc image, so the 12 GB of containers never need extracting. |

### Quick start

```
python tools/xdvdfs.py info    "path/to/disc1.iso"
python tools/xdvdfs.py list    "path/to/disc1.iso" --csv disc1.csv
python tools/xdvdfs.py extract "path/to/disc1.iso" extract/disc1

# Walk the resource container in place, no extraction needed
python tools/mron.py census "path/to/disc1.iso" --offset 1703536640 --length 2207584256
```

Container offsets for the European release are tabulated in
[docs/disc-layout.md](docs/disc-layout.md).

## Documentation

* [Disc layout](docs/disc-layout.md) — how the two retail discs are physically
  organised, and where the containers sit.
* [NORM / MRON](docs/formats/norm-mron.md) — the ASKA resource archive that
  holds essentially all of the game's content.
* [XDVDFS](docs/formats/xdvdfs.md) — the on-disc filesystem, fully specified.
* [`docs/census.txt`](docs/census.txt) — resource-type census of all four
  retail containers.

## Status

The disc layout and the container format are solved; payload formats mostly are
not. See [`docs/sessions/`](docs/sessions/) for the running log of what has been
established and what is still open.
