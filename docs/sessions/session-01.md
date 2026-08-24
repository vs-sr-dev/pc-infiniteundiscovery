# Session 1 — orientation and the container format

**Date:** 2026-08-24
**Material:** European retail discs 1 and 2, Redump-style XGD2 images.

## Goal

Establish what is physically on the discs, and find a way into the game data.

## What was established

### The discs

Both images are 7 835 492 352 bytes — the canonical XGD2 size, so the dumps
cover the DVD-Video compatibility area as well as the game partition. The
filesystem is XDVDFS with the game partition at `0x0FD90000`.

Volume timestamps put both masters on the evening of **8 July 2008**, disc 1 at
20:52:54 UTC and disc 2 at 21:19:37 UTC — 27 minutes apart, two months before
the European release.

### The filesystem is nearly empty

Four files per disc: `default.xex`, `ud1.bin`, `ud2.bin`, and Microsoft's stock
`$SystemUpdate` blob. No asset tree at all. Everything is inside the two `ud`
containers.

### The container format is solved

`ud1.bin` and `ud2.bin` are sequences of self-describing archives whose magic
is `MRON00.2` — read reversed, **NORM version 2.00**. Header and entry table
are fully specified in [formats/norm-mron.md](../formats/norm-mron.md), and the
layout formula

```
data_start = align_up(0x20 + count * 32, alignment)
total      = align_up(max(entry.offset + entry.size), 2048)
```

was confirmed against four archives with three different alignments, then used
to walk all four retail containers front to back without an index. The walk
completes cleanly: 1 198 archives in disc 1's `ud1.bin`, 1 224 in disc 2's.

Type tags are stored byte-reversed. Sixteen were catalogued, five of them
(`SEEK`, `WEAP`, `SKAC`, `MINI`, `LNS-`) only surfacing once the full census
ran.

### How the game splits its data

Not by area, but by kind:

* `ud1.bin` — common content. 5 718 `ANIM`, 1 505 `MESH`, 1 275 `SOND`, and a
  217-entry `WEAP` set with an identical count on both discs.
* `ud2.bin` — per-area content in 40 groups, dominated by `EPAC`/`APAC` packed
  blocks (1.19 GB in disc 1 alone) and `MTEX` textures.

Archives sharing a **group id** sit consecutively and describe one area, with
the packed-data archive following the mesh/texture one at `0x800` alignment.

### Engine evidence

String sampling turned up Direct3D shader bytecode in `ud1.bin`: `ps_3_0` and
`vs_3_0` targets, HLSL compiler version stamps (`2.0.4802.0`, `2.0.6534.1`,
`2.0.6274.0`, `2.0.4314.0`, `2.0.4929.0`), and constant names including
`ePROJECTORCASCADEMATRIX0`, `ePROJECTORCUBECOEF0`, `sTexStage0`, `niso_Coef0`,
`cmView`. Cascaded shadow projection and cube projectors were in the renderer.

Skeleton naming from `ud2.bin` follows a `R:M:` namespace — `R:M:SK_Hip`,
`R:M:POS_ROOT`, `R:M:JUMPMARKER`, `R:M:MARK_OBJ_01`, `R:M:DummyPos` — carried
through from the authoring tool.

### The two executables

Same size (11 055 104 bytes), different content in four clusters: security
info, media ID, image body, and a multi-disc header that is identical except
for its last byte (`01` / `02`). Consistent with one program encrypted under
two per-disc session keys, though that is unconfirmed until decryption.

## Tools written

* `tools/xdvdfs.py` — XDVDFS reader: partition autodetection, volume info,
  full listing, CSV manifest, extraction.
* `tools/mron.py` — NORM/MRON container walker: `scan`, `scan --csv`,
  `census`. Reads in place inside a disc image via `--offset` / `--length`, so
  the 12 GB of containers never need extracting.

## Left open

1. **XEX decryption.** The retail key is publicly documented; decrypting and
   decompressing `default.xex` is the single highest-value next step — it would
   give strings, debug output, and the engine's own naming.
2. **The first `0x16000` bytes of disc 1's `ud1.bin`.** Precedes the first
   archive, matches no known magic. Entropy 6.74 bits/byte with a strong
   128-byte self-correlation where many byte pairs differ by exactly `0x80`.
3. **SLZ compression.** Header is mapped, algorithm is not. 357 blocks in disc
   1's `ud1.bin`.
4. **Gap splitting.** The walker reports each contiguous non-archive run as one
   gap, so the ~3.2 GB of ASF video is measured as runs, not individual movies.
5. **Payload formats** for every tag beyond the broad strokes of `MESH`.
