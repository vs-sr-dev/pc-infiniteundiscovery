# Open questions

What is not yet known, roughly in order of how much it would unlock. Each
session's log carries its own "Left open" list; this file is the consolidated
view, kept current at the end of every session.

Solved work lives in [docs/formats/](docs/formats/) and is not repeated here.

## Now the main line of work

**1. `ASF ` — the Aska Scene File.** 916 of the 1 812 compressed blocks in disc
1's `ud1.bin`, and what every `MESH` resource decompresses to. It stores its own
length at offset 4 and nothing else about it is known. This is the largest
remaining unknown, and geometry is behind it.

**2. `AAF ` animation and `ACF ` collision.** Both are plain readable files now.
The engine's RTTI already names the collision primitives — capsule, cube and
sphere, via `Aska::AcfPrimitiveData_capsule` / `_cube` / `_sphere` — so ACF has
a head start.

**3. `-CNS` / `SNC-` scene data**, from `SCE-` resources. Only four blocks, but
scene scripting is likely to explain a lot of the rest.

## Smaller and self-contained

4. **AIF mip chains.** The base level decodes. The Xbox 360 packs the small mip
   levels into a shared tile, and working that out would complete the texture
   format.

5. **The unidentified AIF fields**: the `u32` at `0x24`, which varies per asset,
   and the flags at `0x34` (`0x500`, `0x200`, `0x40400`, zero).

6. **`NODE` payloads**, which carry no magic at all, and **`TTD-`**, whose
   payload begins `DTT\0`.

7. **The first `0x16000` bytes of disc 1's `ud1.bin`**, before the first
   archive. Unchanged since session 1.

8. **The ASF/WMV video runs** in the container gaps — they need splitting into
   individual movies.

9. **`AOF`**, named three times in the engine's RTTI (`Aska::AofHandler`,
   `Aska::AofObject`, `Aska::DirectAofHandler`) but never seen as a payload
   magic on disc.

10. **Disc 2.** Everything established so far was measured on disc 1. Disc 2 has
    been walked but its containers have not been put through the same checks.

## Verified, needs no further work

* Disc layout and XDVDFS — [docs/formats/xdvdfs.md](docs/formats/xdvdfs.md)
* NORM/MRON containers — [docs/formats/norm-mron.md](docs/formats/norm-mron.md)
* XEX2 and the decrypted executable — [docs/formats/xex.md](docs/formats/xex.md)
* XDBF title metadata — [docs/formats/xdbf.md](docs/formats/xdbf.md)
* SLZ / XCompress — [docs/formats/slz.md](docs/formats/slz.md)
* AIF textures — [docs/formats/aif.md](docs/formats/aif.md)
