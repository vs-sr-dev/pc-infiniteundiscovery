# Session 2 — decrypting the executable

**Date:** 2026-08-24
**Goal:** open question 1 from [session 1](session-01.md) — decrypt
`default.xex` and see what the binary says about itself.

## Outcome

The executable is fully recovered, and it turned out to describe its own
architecture in detail.

### Decryption

`default.xex` uses `encryption = 1` (AES-128-CBC) and, importantly,
`compression = 1` — **basic**, not LZX. Basic compression is a list of
`(data length, zero length)` pairs, so no LZX implementation was needed and
the whole recovery is three straightforward steps:

1. AES-128-ECB decrypt the 16-byte session key with the public retail key.
2. AES-128-CBC decrypt from `pe_data_offset` with a zero IV.
3. Expand the two basic blocks.

Result: an 11 370 496-byte PE image starting with `MZ`. Format and this
title's header values are written up in [formats/xex.md](../formats/xex.md).

### The build

Every static library is XDK build **6534**, the November 2007 release, which
the Microsoft source paths left in the binary confirm independently
(`e:\xenon\nov07\core\private\...`). The title id is `0x535107DB`, whose high
half is ASCII `SQ`. `MDISC` is linked — the multi-disc library — and both
discs' media ids are listed inside each executable, which is how the disc-swap
prompt validates what you inserted.

### The engine

The binary was built with RTTI enabled, so every polymorphic type carries its
mangled name. A demangler recovers **1 740 distinct types**, 13 candidate
strings failing to parse.

The `Aska::` namespace is small and clean — 63 types covering tasks, fibers,
memory, resource streaming, rendering passes, cameras, collision, and a
three-flavour wind system — while 751 `C…`-prefixed and 342 `Btl…` game
classes live outside it. A deliberately thin engine boundary.

Full write-up: [aska-engine.md](../aska-engine.md).

Highlights worth repeating here:

* `Aska::PrimitiveBufferXe` — the only class name where the Xenos GPU leaks
  through.
* `Aska::FramePersistanceEffect` — misspelled in the shipped retail binary.
* Three wind field types (`DynamicsWorldWind`, `DynamicsOmniWind`,
  `DynamicsCircleWind`), each with a nested implementation struct.
* AOF / ASF / ACF file kinds, with ACF collision primitives being capsule,
  cube and sphere.
* Battle projectiles are compile-time compositions —
  `BtlShootCallback_StraightMove<BtlArrowObject, 13>` — which is why there are
  342 battle types.
* Internal character codes recovered from attack classes: `AYA`, `EUGUNE`,
  `MIRUCE`, `KOMAC`, `LUKA`, `SEIRYU`.

### Shaders

Disc 1's `ud1.bin` holds exactly 160 compiled shaders, 114 pixel and 46
vertex, all SM3.0 Xenos microcode with D3D constant tables — not HLSL source,
as the first session's string sampling had suggested.

Their compiler version stamps span ten different SDK releases from
`2.0.4025.0` to `2.0.6534.1`. A hundred were rebuilt with the final toolchain;
sixty were carried forward untouched from as much as five SDK generations
earlier. The shader library was never rebuilt wholesale.

Constant naming is systematic (`cv` vectors, `cm` matrices, `s` samplers, `e`
effect parameters) and describes the renderer: Blinn shading, spherical
harmonic ambient, light masks, cascaded shadow projection, cube projectors.

Three strings — `e:\AHSLCacheUD4\AHSLProfileData`, `AHSLv2DiskCache`,
`ahsl\` — point at a tri-Ace shading-language layer with a versioned disk
cache. What AHSL stands for is not stated in the binary.

### A correction to session 1

Session 1 recorded shader compiler source filenames (`r500assembler.cpp`,
`shaderstore.cpp`, `ssmstatecompiler.cpp`) as engine evidence. They are not
tri-Ace's — they are Microsoft's, from `xgraphics\ucode` in the XDK, pulled in
through the statically linked `D3DX9` and `XGRAPHC`. The full Xenon microcode
compiler does ship inside the retail executable, diagnostics and all, but it is
SDK code rather than engine code.

## Tools written

* `tools/xex.py` — XEX2 reader and decryptor. `info` prints every header with
  structured decoding for the known layouts; `extract` recovers the PE image.
  Uses pycryptodome when present, otherwise a pure-Python AES-128 included in
  the file, verified against FIPS-197 and cross-checked against pycryptodome.
* `tools/rtti.py` — MSVC RTTI extractor and demangler. Handles namespaces,
  nested types, templates and MSVC's integer encoding; reports rather than
  swallows what it cannot parse.

Also corrected in `tools/xex.py`: several optional header key names were wrong
in the first draft. `0x00040006` is `EXECUTION_INFO`, not multi-disc media ids;
`0x000406FF` is `MULTIDISC_MEDIA_IDS`; `0x00040310` is `GAME_RATINGS`;
`0x00040404` is `LAN_KEY`; `0x000405FF` is `XBOX360_LOGO`; `0x00030000` is
`SYSTEM_FLAGS`.

## Left open

Carried forward from session 1, unchanged:

1. The first `0x16000` bytes of disc 1's `ud1.bin`.
2. SLZ compression — now with a name for its counterpart in the engine,
   `Aska::ResourceManager::DecompressNotify`.
3. Splitting the ASF video runs into individual movies.
4. Payload formats for the resource tags.

New:

5. The AOF / ASF / ACF file kinds named in the engine do not obviously
   correspond to the container's resource tags (`MESH`, `ANIM`, `MTEX`, …).
   Working out how the two vocabularies map is probably the fastest route into
   the payload formats.
6. The XEX resource section at `0x82AB0000` (159 023 bytes) has not been
   looked at. On most titles it holds the embedded XDBF with achievement and
   title metadata.
7. Audio: `AAC`, `WavetableSynth`, and the `SOND` tag have not been connected.
