# The ASKA engine, as the retail binary describes it

Infinite Undiscovery is the first title built on tri-Ace's in-house engine,
which the studio calls **ASKA** — reportedly for "tri-Ace Superlative
Knowledge-based Architecture". Almost nothing about it has been documented
publicly.

The shipped executable turns out to describe itself in considerable detail,
because it was built with C++ RTTI enabled. Every polymorphic type carries a
`type_descriptor` holding its mangled name, since `dynamic_cast` and `typeid`
need those names at runtime. No symbols, no debug section and no PDB are
required for this — the names are simply there, in a retail binary, and
demangling them recovers the class inventory.

**1 740 distinct types** were recovered this way from disc 1's executable, of
which 13 candidate strings failed to parse. Everything below comes from those
names and from string data in the same image.

Method and tooling: [`tools/rtti.py`](../tools/rtti.py), run against the PE
image that [`tools/xex.py`](../tools/xex.py) produces.

## 1. Shape of the codebase

| Group | Types | What it is |
| --- | ---: | --- |
| `C…` | 751 | Game-side classes, Hungarian `C` prefix |
| `Btl…` | 342 | Battle system |
| `AI…` | 138 | AI framework |
| `AIBehavior_…` | 94 | Individual AI behaviours |
| `Aska::` | 63 | The engine namespace proper |
| `BtlShootCallback_…` | 47 | Projectile behaviour callbacks |
| `AIFsm_…` | 33 | AI state machines |
| `BtlSigCallBack_…` | 26 | Battle signal callbacks |
| `CAI…` | 20 | AI support classes |
| `std::` | 9 | Standard library |

The split is worth noting. The `Aska::` namespace is small — 63 types — and
holds only engine services: tasks, memory, resources, rendering, cameras,
collision, physics. Everything game-specific lives outside it in the global
namespace under Hungarian prefixes. That is a deliberately thin engine
boundary, and it is consistent with ASKA having been designed to be reused
across projects while the game code stays separate.

## 2. The `Aska::` namespace

Recovered in full.

**Application and scheduling**

```
Aska::App          Aska::Task        Aska::FiberTask      Aska::Thread
Aska::MemoryManager
```

Fibers alongside threads suggests cooperative task scheduling on top of the
Xbox 360's hardware threads. One string names a worker thread directly:
`Aska::ObjectManagerWorkerThread(%d)`.

**Resources**

```
Aska::ResourceManager
Aska::ResourceManager::LoadNotify
Aska::ResourceManager::IntermediateLoadNotify
Aska::ResourceManager::DecompressNotify
```

Three separate notification interfaces — load, intermediate load, decompress —
imply asynchronous streaming with progress callbacks at distinct stages.
`DecompressNotify` is the engine-side counterpart to the SLZ compressed blocks
found in the containers.

**File handlers**

```
Aska::AofHandler   Aska::DirectAofHandler   Aska::AofObject
Aska::AsfHandler
Aska::AcfPrimitiveData_capsule / _cube / _sphere
```

Three-letter file kinds in an `A…F` pattern: **AOF** objects, **ASF** scenes,
**ACF** collision. The ACF primitive types — capsule, cube, sphere — are the
collision volume shapes, and they appear as template arguments to
`TCollisionExBase<>`.

**Rendering**

```
Aska::RenderPassManager      Aska::RenderPassManagerList
Aska::RenderableObject       Aska::RenderablePrimitive
Aska::Primitive              Aska::PrimitiveBufferXe
Aska::ShadowManager          Aska::FrustumObject
Aska::TextureHandler         Aska::ITextureHandler
Aska::TextureModifier        Aska::TextureModifierManager
```

`PrimitiveBufferXe` — `Xe` for Xenos, the console's GPU — is the one place
where the platform leaks into a class name.

**Post-processing**

```
Aska::BackBufferEffect            Aska::CameraFilter
Aska::BrightnessContrastFilter    Aska::MonotoneFilter
Aska::FramePersistanceEffect      Aska::CrossFader
```

`FramePersistanceEffect` is misspelled in the shipped binary, which is the
kind of detail that only survives in a build nobody expected you to read.

**Cameras**

```
Aska::Camera   Aska::CameraSynchronizer   Aska::Camera::AFPoint
```

**Animation and hierarchy**

```
Aska::Joint                  Aska::HierarchicalObject
Aska::HierarchicalObjectContainer
Aska::IAnimatable            Aska::AnimatableLinkElement
Aska::AimingObject
```

**Physics and wind**

```
Aska::Dynamics
Aska::DynamicsForceEmitter
Aska::DynamicsWorldWind   ::_WorldWind
Aska::DynamicsOmniWind    ::_OmniWind
Aska::DynamicsCircleWind  ::_CircleWind
```

Three distinct wind field types — global, omnidirectional point source, and
circular — each with a nested implementation struct. A dedicated wind system
of this size is a notable investment for a 2008 title, and matches a game
whose environments lean heavily on cloth and vegetation motion.

**Collision and terrain**

```
Aska::CollisionHandler   Aska::ILandscapeConstraint
```

**Containers**

```
Aska::TArray<T, N>   Aska::TList<T>   Aska::TSmartPointer<N>
Aska::List           Aska::LinkElement   Aska::INotify
```

A custom container library, with `std::` used for only 9 types in the whole
binary. Typical of a console engine of the period that wanted control over
allocation.

## 3. AI

The AI layer is the largest non-battle subsystem and it is structured as a
behaviour tree over a finite state machine, both bridged through a generic
adapter:

```
AIObjectInterfaceBridge<AIBehavior, AICompositeBehavior>
AIObjectInterfaceBridge<AIFsm, AIBrainBase>
AIObjectInterfaceBridge<AIObjectBase, AIBrainBase>
```

Pathfinding is A*, with its supporting types in the engine namespace:
`CAISearchAStar` and its `RouteData`, `CAIAStarPoint`, `CAINodeLink`,
`CAIPartition`, `CAIRoutePoint`. Perception has its own path:
`CSenseeObject`, `CSensorResult::foundInfo`.

State machines are named after what they do, and they name the game's content
as they go:

```
AIFsm_Battle        AIFsm_Camp          AIFsm_Caution       AIFsm_Escape
AIFsm_Order         AIFsm_Normal        AIFsm_NoMesh        AIFsm_PigeonEscape
AIFsm_AvoidTsunami  AIFsm_EscapeVillager
AIFsm_BattleSeiryu  AIFsm_Ex01_QueenSpider  AIFsm_Ex01_HornBear
AIFsm_Ex01_Harpy    AIFsm_Ex01_GremrinFish  AIFsm_Ex01_Kandelaar
AIFsm_Ex01_Sarande_A    AIFsm_Ex02_QueenSpider
AIFsm_Niedzielan_Action01
```

`AIFsm_NoMesh` is the fallback for an agent with no navigation mesh;
`AIFsm_AvoidTsunami` and `AIFsm_EscapeVillager` are set-piece behaviours built
for single scenes.

## 4. Battle

342 `Btl…` types, organised around templated callbacks parameterised on the
projectile class and a numeric variant:

```
BtlShootCallback_StraightMove<BtlArrowObject, 13>
BtlShootCallback_ParabolaMove<BtlCollisionEffectObject, 1>
BtlShootCallback_HomingMove<BtlEffCol_DivideSet, 1>
BtlShootCallback_DefaultArrow_typeA<BtlArrowObject, 8>
BtlShootCallback_DragonFirePiller<BtlCollisionEffectObject>
```

Movement styles — straight, parabolic, homing — are composed with effect types
at compile time rather than configured at runtime, so each combination the game
uses becomes its own instantiated type. That is why the class count is so high.

Character-specific attacks are named after their owners, which recovers an
internal cast list: `Btl_AYA_Sp10Collision`, `BtlArrow_AYA_Blitz`,
`BtlShootCallback_EUGUNE_RockThrow`, `BtlShootCallback_MIRUCE_Page`,
`BtlShootCallback_StraightMove_KOMAC`, `Btl_SEIRYU_FireBall`,
`LUKA_FamiliarSpiritObject`, `CLichSkeltonEffect` (sic).

## 5. Shaders

Disc 1's `ud1.bin` contains exactly **160 compiled shaders** — 114 pixel and
46 vertex, all Shader Model 3.0. They are Xenos microcode with D3D constant
tables attached, not HLSL source: each blob carries its reflection metadata,
then the target string `ps_3_0` or `vs_3_0`, then the compiler's version
stamp.

Those version stamps are an archaeological record of the project:

| Compiler version | Shaders |
| --- | ---: |
| 2.0.4025.0 | 1 |
| 2.0.4314.0 | 5 |
| 2.0.4802.0 | 11 |
| 2.0.4929.0 | 4 |
| 2.0.5426.0 | 2 |
| 2.0.5632.0 | 5 |
| 2.0.6132.0 | 2 |
| 2.0.6274.0 | 29 |
| 2.0.6534.0 | 1 |
| 2.0.6534.1 | 100 |

Ten different SDK compilers across the shader library. A hundred shaders were
rebuilt with the final November 2007 toolchain and sixty were carried forward
untouched from as far back as five SDK generations earlier — the shader library
was never rebuilt wholesale, only incrementally.

Constant names follow a consistent prefix convention, visible in the constant
tables: `cv…` for constant vectors (`cvLightContext`, `cvLightMask`,
`cvLightMaskMix`, `cvSHAmbContext`, `cvColorOffset`), `cm…` for constant
matrices (`cmView`), `s…` for samplers (`sTexStage0`), and `e…` for effect
parameters (`eBlinn_Ambient_Color0`, `eBlinn_Diffuse_Color0`,
`eBlinn_Specular_Color0`, `ePROJECTORCASCADEMATRIX0`, `ePROJECTORCUBECOEF0`,
`ePLANEABSORPTION0`).

That vocabulary describes the renderer: Blinn shading, spherical-harmonic
ambient (`cvSHAmbContext`), light masking, cascaded shadow projection, and cube
projectors.

### Where 70 of them sit

Session 7 pinned down the largest single block of them. The `0x16000` bytes at
the start of each `ud1.bin`, before the first archive — the last gap in all
four containers that nothing had explained — are mostly the shader library:

| Range | Size | What |
| --- | ---: | --- |
| `0x00000`–`0x07717` | 30 488 | A table, still unidentified |
| `0x07718`–`0x14803` | 53 484 | 70 compiled shaders: 60 pixel, 10 vertex |
| `0x14804`–`0x15FFF` | 6 140 | Zero padding |

The shader half is **byte-identical on both discs**, as a fixed engine asset
should be. The 30 KB before it is not: it differs between the two, though 51 %
of its `0x100`-byte blocks are still shared verbatim, it holds nothing that
points into the shader area, and it reads as a table of 32-bit values whose
columns repeat every `0x100` bytes. What it is remains open.

### What the constant names say the renderer does

Reading the constant tables of those 70 shaders adds a good deal to the
vocabulary above. Names are recovered by scanning, so a few come out clipped or
run together where the tables abut.

* **Tone mapping and post**: `cvReinhardWhite` — Reinhard tone mapping, with
  its white point exposed — alongside `cvBloomBlend`, `cvBias`, `cvGatherBlend`
  and `cvDitther`, the last spelt that way in the shipped data.
* **Depth of field**: `cavDOF`, in nine shaders, sampled through `poissonTb`, a
  Poisson-disc kernel.
* **Sky and sun**: `cvSunDir`, `cvSunCol`, `cvZenithDir`.
* **Water simulated on the GPU**: `heightSampler` and `prevHeightSampler` — two
  successive height fields, which is a wave equation integrated in a pixel
  shader — with `cvWaveParams`, `cvGridSize`, and then `cvExportAddr` and
  `cvExportNormal`. An export address is the Xbox 360's memexport, so the
  simulation writes its results and the normals it derives straight back to
  memory for the geometry pass to read.
* **Video**: `YTexture`, `UTexture`, `VTexture` — the YUV conversion for the
  WMV streams that occupy 3.2 GB of the four containers.
* **Effects**: `SpriteAnimTex`, `ImageTexture`, `ParamTexture`, and
  `eKamaitachiAnim`, named for the kamaitachi of Japanese folklore — the
  sickle-weasel whose wind attack the effect presumably draws.
* **Materials**: `eBlinn_Diffuse_Color0`, `eBlinn_Ambient_Color0`,
  `eBlinn_Specular_Color0`, `eBlinn_Translucent_Color0`,
  `eParallax_Offset_Scalar0`, `eConstColor_Color`. The `e` names are the ones a
  material fills in: an ASF `mats` carries exactly those values as float
  constants, diffuse and ambient and specular in that order. See
  [ASF](formats/asf.md).

### The shading system

Elsewhere in the executable, outside the shader library itself, sits the
vocabulary of the system that assembles those shaders — a fragment table and a
register file:

* **Shader fragments**, named as such: `MarschnerShader`, `AshikhminShader`,
  `KajiyaKayShader`, `NormalMap`, `NormalMapXYH`, `DoubleSided`,
  `DoubleSidedBackFaceOnly`, `ParallaxMappingLo`, `DecodeTexRGBE`,
  `DecodeTexRGBL`, `Fresnel`, `LightMaskMixer`, `PlaneAbsorption`,
  `UVSetTransform`, `Lerp`, `BranchGTZBegin` / `BranchEnd`.
* **Registers**: `avUVSet[0..15]`, `avWorkReg[0..31]`, `avTexCoord[0..3]`,
  `afScalarWork[0..3]`, `avTmpReg[0..5]`, `avVertexLighting[0..1]`,
  `eamUVShiftMatrix[0..3]`, and the outputs `vFinalColor`, `vFinalMultiply`,
  `vFinalOffset`, `vNormal`, `vReflection`, `vLightMask`.
* **Passes**: `ShadowCascadeDepthProjector`, `ShadowCubeMapDepthProjector`,
  `ShadowDepthProjectorCond_PCF16` / `_PCF9` / `_PointSample`, `PoissonDOF`
  with `_Eclipse` / `_MaskTest` / `_Odd` variants, `PostPrsCombinerCond_*` for
  vignetting, film grain, dither and tone mapping, `DistortionFilter_*` for
  radial blur and waves, and a fifteen-strong `Particle_Cond*` family.

Two of the fragment names are named BRDFs — **Marschner** for hair and
**Ashikhmin–Shirley** for anisotropic surfaces, with Kajiya–Kay as the cheaper
hair alternative. Both appear as node types in the shading networks shipped
inside the models, which is where the corroboration runs both ways: the ASF
render lists name nodes `marschner` and `ashikhmin` from the artists' side, and
the executable names shaders of the same kind from the engine's.

### Reproducing

```
python - <<'EOF'
import re
f = open("disc1.iso", "rb"); f.seek(1703536640)
d = f.read(0x16000)[0x7718:0x14804]
print(d.count(b"ps_3_0"), "pixel,", d.count(b"vs_3_0"), "vertex shaders")
print(sorted({m.group().decode() for m in re.finditer(rb"c[vma][A-Z][A-Za-z0-9_]+", d)}))
EOF
```

### AHSL

Three strings point at a shading-language layer of tri-Ace's own:

```
e:\AHSLCacheUD4\AHSLProfileData
e:\AHSLCacheUD4\AHSLv2DiskCache
e:\AHSLCacheUD4\ahsl\
```

`E:` is the development kit's drive, and `UD4` is presumably an internal
project code. A versioned disk cache plus profile data implies AHSL was
compiled through a caching pipeline during development. What AHSL expands to
is not stated anywhere in the binary; "Aska High-level Shading Language" is a
guess, not a finding.

Note that the retail executable also contains Microsoft's **entire Xenon
microcode compiler** — the full HLSL front end, optimiser, register allocator
and R500 assembler, with all of its diagnostics intact (`Microcode Compiler %s`,
`error X%u: `, `Register allocation : ColorGraph -> %d preference(s) assigned`,
`Optimization : Dead code elimination -> %d instruction(s) removed`). The
source paths confirm it is Microsoft's, from `xgraphics\ucode\compiler` and
`xgraphics\ucode\ssm` in the November 2007 XDK, pulled in through the statically
linked `D3DX9` and `XGRAPHC`. Whether the game actually invokes it at runtime
is not established by its mere presence, though the AHSL cache paths make
runtime or tool-time compilation on the dev kit very likely.

## 6. Audio

Sparse but suggestive: `AAC version problem  BGM ID=%d`, `AirPlayAac - %d`,
and `WavetableSynth %i`. Background music is AAC, and a wavetable synthesiser
sits alongside it. This has not been followed into the container data yet.

## 7. Developer leftovers

The kind of thing that only survives because nobody expected it to be read:

```
weirdness: global texture (%d) not FOUND!
could not allocate global texture, id=%d
TextureStage %d misses DCLPT
Assertion failed: %s (%s:%u)
```

And, from the title's own metadata rather than its code:
`Tri-Ace presents an exciting new RPG for the Xbox 360!`

## 8. What this does not tell you

RTTI gives type *names*, not their layouts, members, or relationships. Nothing
here establishes inheritance, field offsets, or call graphs — only that these
types existed and roughly what they were for. Meanings assigned to names are
readings, not decompilation.
