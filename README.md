# pc-infiniteundiscovery

*Everything written here is falsifiable and should be read that way. These are
our own findings, arrived at by looking at the shipped data from the outside:
no source, no documentation, no contact with anyone who worked on the game. A
claim survives here because nothing has contradicted it yet, not because it has
been confirmed. Where a conclusion rests on measurement the measurement is
given, so it can be checked and, if wrong, overturned — and past sessions have
already had findings retracted for exactly that reason. Nothing in this
repository should be taken as established fact about how the game actually
works until a full recompilation demonstrates it.*

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
| `tools/asf.py` | Read ASF scenes: the chunk tree, the named node graph, the full vertex format — positions, normals, binormals, texture coordinates, colour and skinning — the materials and which texture each mesh uses, export to Wavefront OBJ with an MTL and decoded PNGs, and a bulk check of the decode against the geometry. |
| `tools/snc.py` | Read SNC scene scripts, the compiled script behind every `SCE-` resource: summarise and self-check one file, disassemble it with its data blocks expanded, print the string table with the opcodes that use each name, and check a whole corpus. |
| `tools/aac.py` | Read AAC audio containers: the sound directory with the original filenames, rates, durations and loop points; export to RIFF-wrapped XMA2 or straight to PCM; walk or search a disc region for the containers the music is stored in. |

### Quick start

```
python tools/xdvdfs.py info    "path/to/disc1.iso"
python tools/xdvdfs.py list    "path/to/disc1.iso" --csv disc1.csv
python tools/xdvdfs.py extract "path/to/disc1.iso" extract/disc1

# Walk the resource container in place, no extraction needed
python tools/mron.py census "path/to/disc1.iso" --offset 1703536640 --length 2207584256

# Pull out every texture, decompressing as needed, and turn one into a PNG
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 --length 2207584256 --tag MTEX --decompress extract/textures
python tools/aif.py info extract/textures/317BD800_003_MTEX.aif
python tools/aif.py png  extract/textures/317BD800_003_MTEX.aif texture.png

# Pull out a model, look at its scene tree, and export the geometry
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 --length 2207584256 --tag MESH --decompress extract/models
python tools/asf.py info      extract/models/000A4000_006_MESH.asf
python tools/asf.py materials extract/models/000A4000_006_MESH.asf
python tools/asf.py obj       extract/models/000A4000_006_MESH.asf sword.obj --textures
python tools/asf.py skeleton  extract/models/53EC3800_000_MESH.asf
python tools/asf.py check     extract/models/*.asf

# Pull out the animations and check them against the scene they animate
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 --length 2207584256 --tag ANIM --decompress --limit 900 extract/anim
python tools/aaf.py tree  extract/anim/000A4000_008_ANIM.aaf
python tools/aaf.py pose  extract/anim/000A4000_008_ANIM.aaf --time 40
python tools/aaf.py check "extract/anim/*.aaf"
python tools/aaf.py rest  "extract/anim/*.aaf" --models "extract/models/*.asf"

# Pull out the collision and turn one file into a viewable OBJ
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 --length 2207584256 --tag COLL --decompress extract/coll
python tools/acf.py tree  extract/coll/49450000_036_COLL.acf
python tools/acf.py obj   extract/coll/49450000_036_COLL.acf collision.obj
python tools/acf.py check "extract/coll/*.acf" --models "extract/models/*.asf"

# Pull out the scene scripts and read one
python tools/mron.py extract "path/to/disc1.iso" --offset 3919380480 --length 2800330752 --tag SCE- --decompress extract/scene
python tools/snc.py info    extract/scene/4F0A3000_041_SCE.bin
python tools/snc.py strings extract/scene/4F0A3000_041_SCE.bin
python tools/snc.py dis     extract/scene/4F0A3000_041_SCE.bin --limit 40 --blocks
python tools/snc.py check   extract/scene/*.bin

# Walk the music, which sits between the archives rather than inside them
python tools/aac.py bank "path/to/disc1.iso" --offset 0x8E75C000 --length 143654912
python tools/aac.py info "path/to/disc1.iso" --offset 0x8E75C000 --length 3842048
python tools/aac.py xma  "path/to/disc1.iso" music/ --offset 0x8E75C000 --length 3842048

# Pull out the sound effects and voice, then check every container
python tools/mron.py extract "path/to/disc1.iso" --offset 1703536640 --length 2207584256 --tag SOND --decompress extract/sound
python tools/aac.py verify extract/sound/*.bin

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
* [ASF](docs/formats/asf.md) — the Aska Scene File: what every `MESH` resource
  holds. A chunk tree carrying geometry, materials, embedded textures and a
  named node graph. The vertex format is solved: normals and binormals to
  within a degree of the geometry, and blend weights that sum to one on every
  skinned vertex in the game. So are the materials: every mesh points at the
  one that shades it, and every material names its textures by the same key the
  texture header carries. Skinning too: a vertex's one-byte bone index runs
  through the mesh's palette and the object's pool to a node in the tree.
* [AAF](docs/formats/aaf.md) — the Aska Animation File: the most numerous
  resource on the disc. It animates an ASF's node tree, and its constant
  channels reproduce that tree's rest pose, which is what identifies them.
  Rotations are a 48-bit packed axis-and-angle quaternion.
* [ACF](docs/formats/acf.md) — the Aska Collision File: a sphere tree over
  spheres, cubes and capsules, hung off the same bones the scene and the
  animation name. Solved: all 972 files pass every check, and the shape code
  agrees with the name the artist typed on all 8 119 primitives that carry one.
* [SNC](docs/formats/snc.md) — the Aska scene script: the compiled script
  behind every `SCE-` resource, and what actually drives a model. Solved as a
  container and an instruction set: all 61 payloads on both discs parse, every
  string, data-block and code-address reference resolves, and each of the 253
  opcodes has exactly one operand count. Seven opcodes are identified from the
  Maya node names they are given and from a quaternion that is a unit
  quaternion 987 times out of 990.
* [AAC](docs/formats/aac.md) — the Aska Audio Container, which is not MPEG AAC:
  every sound in the game, named with the filename it was built from, wrapping
  XMA2. Solved: 22 243 sounds pass every check, and all 79 music tracks decode.
* [XDBF](docs/formats/xdbf.md) — the title metadata database, achievements
  included.
* [XEX2](docs/formats/xex.md) — the Xbox 360 executable format, and this
  title's header values.
* [XDVDFS](docs/formats/xdvdfs.md) — the on-disc filesystem, fully specified.
* [`docs/census.txt`](docs/census.txt) — resource-type census of all four
  retail containers.

## Status

The disc layout, the container format, the executable, the resource-payload
vocabulary, the compression, the texture format, the scene container and the
audio are solved. All 1 812 SLZ blocks in disc 1's `ud1.bin` decompress with no
failures; all 220 image resources decode to correct pixels; 400 `MESH`
resources parse without error into 3 855 objects and 1.3 million triangles,
98.4 % of which reproduce the bounding boxes the files state independently; and
every one of the 22 243 sounds in disc 1's `ud1.bin` passes its checks, with
all 79 music tracks decoding through a standard XMA2 decoder.

Session 6 added the rest of the vertex: every attribute of all 14 618 meshes
decodes, and the decode agrees with geometry it did not produce — normals a
median 2.3° from the triangles around them, blend weights summing to one on
100.0 % of 2 919 607 skinned vertices.

Session 8 closed the last gap in a textured model. A mesh carries a signed
displacement to the material that shades it — it lands on one for all 4 176
meshes measured — and a material names its textures by the same eight bytes the
texture's own header carries. A model now exports as an OBJ with materials and
decoded PNGs.

Session 9 opened `AAF `, the animation format and the most numerous resource on
the disc. All 900 payloads sampled parse and pass every internal check, and the
constant channels reproduce the rest pose of the scene they animate — 99.5 % of
translations, 92.6 % of rotations and 99.6 % of scales — which is what names
the channels. Rotations are stored as a 48-bit axis-and-angle quaternion whose
three fields are all angles measured as fractions of a right angle. The same
session closed the bone chain in ASF: a vertex's one-byte bone index runs
through `bnpi` and `bnpl` to a node in the `tree`, on every skinned mesh in the
corpus.

Session 9 also opened `ACF ` collision, which turned out small enough to finish
in the same sitting: a sphere tree of spheres, cubes and capsules whose groups
are named after bones, with three independent checks on the shape reading —
the redundant bounding radius, the file's own length, and the name the artist
typed in Maya.

Session 10 opened the scene scripting behind `SCE-`. `SNC-` is a compiled
script whose container and instruction encoding are now solved: 420 532
instructions across 61 payloads walk exactly, all 18 666 code addresses, all
413 467 data-block references and all 5 035 string references resolve, and
every one of the 253 opcodes has a single operand count. The engine's own RTTI
names the tagged eight-byte operand the format is built from — `sce::Var`.
Seven opcodes are identified: what a scene spawns, where it stands, which bone
it hangs off, and which light and shadow belong to it.

What remains is mostly meaning rather than structure — 246 of the 253 opcodes
are known by number, arity and operand kinds but not by what they do.
[`TODO.md`](TODO.md) lists what is still open, and
[`docs/sessions/`](docs/sessions/) is the running log of how each piece was
established.
