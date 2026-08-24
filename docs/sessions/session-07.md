# Session 7 — the last unexplained gap is the shader library

**Date:** 2026-08-24
**Goal:** open question 9, the `0x16000` bytes at the start of each `ud1.bin`.
Open since session 1, and after session 5 identified every other gap in all
four containers as audio, the only one left.

## Outcome

Most of it is the compiled shader library. The region splits in three:

| Range | Size | What |
| --- | ---: | --- |
| `0x00000`–`0x07717` | 30 488 | A table, still unidentified |
| `0x07718`–`0x14803` | 53 484 | **70 compiled shaders: 60 pixel, 10 vertex** |
| `0x14804`–`0x15FFF` | 6 140 | Zero padding |

[The engine notes](../aska-engine.md) had counted 160 shaders across disc 1's
`ud1.bin` since session 2 but had never said where they physically sat. 70 of
them sit here, in one block, before the first archive.

## How it went

The region looked like nothing at first: high entropy, no magic, no ASCII in
the first pages. Three measurements turned it round.

**It is not random.** A byte-match test across strides found a strong
periodicity at `0x100` — 38 % against 0.4 % for random data — and the byte
histogram is dominated by 0, 1, 2, 3, 4 and 16. Structured binary, not
compression and not encryption.

**The two discs disagree only in the first 30 KB.** Comparing the same region
on disc 2 showed the two byte-identical from `0x7718` to the end, and differing
only before it. That put a boundary exactly where one existed, before knowing
what either side was.

**The second half names itself.** Scanning for ASCII past that boundary gives
`ps_3_0`, `vs_3_0`, compiler stamps `2.0.6534.1` down to `2.0.4025.0`, and
constant names: `cvFogCoef`, `eBlinn_Diffuse_Color0`, `cvSunDir`, `cavDOF`,
`heightSampler`.

## What the constants add

Reading the constant tables of those 70 shaders extends what session 2 could
say about the renderer from the executable alone:

* `cvReinhardWhite` — Reinhard tone mapping with its white point exposed —
  with `cvBloomBlend`, `cvGatherBlend`, `cvBias` and `cvDitther`, spelt that
  way in the shipped data.
* `cavDOF` in nine shaders, sampled through `poissonTb`, a Poisson-disc kernel.
* `cvSunDir`, `cvSunCol`, `cvZenithDir` for the sky.
* `heightSampler` and `prevHeightSampler` together with `cvWaveParams`,
  `cvGridSize`, `cvExportAddr` and `cvExportNormal`. Two successive height
  fields is a wave equation integrated in a pixel shader, and an export address
  is the Xbox 360's memexport, so the simulation writes the heights and the
  normals it derives straight back to memory for the geometry pass. **Water
  simulated on the GPU**, which is not a small thing for 2008.
* `YTexture`, `UTexture`, `VTexture` — the YUV conversion for the WMV video.
* `eKamaitachiAnim`, named for the sickle-weasel of Japanese folklore.

## The 30 KB that is left

It is a table of 32-bit values whose columns repeat every `0x100` bytes: a word
and the word `0x100` bytes after it share their top 16 bits three times out of
ten, against a flat baseline. Values span the whole 32-bit range, none of them
points into the shader area or anywhere else in the region, and 51 % of its
`0x100`-byte blocks are byte-identical between the two discs while the rest are
not. So it is per-disc data drawn from something shared, in a fixed-size slot,
and that is as far as this session took it.

## Left open

1. What the first 30 488 bytes are.
2. Where the other 90 shaders of the 160 sit — presumably inside archives,
   which has not been checked.
3. Parsing a shader blob properly rather than scanning it for strings: the
   constant tables have a structure, and reading it would give each shader its
   full signature.
