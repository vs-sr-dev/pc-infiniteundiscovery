# Session 12 — the shared skeleton that was not there

**Date:** 2026-08-25
**Goal:** question 2, where a `tree`-less scene keeps its skeleton. Session 9
had found 44 skinned objects whose bone pool overshot their own file's node
count, every one of them in a file that appeared to have no node tree, and
named `SKAC` as the place a shared skeleton would live.

## Outcome

**There is no shared skeleton.** The tree was in the file all along and the
reader was refusing to walk it. With that fixed, every skinned object in the
corpus indexes its own file's node tree:

```
bone pool inside the node tree             261 of 261 objects
mesh palette inside the bone pool          642 of 642 meshes
vertex bone index inside the palette       642 of 642 meshes
```

It used to read 217 of 217 with 44 elsewhere. The 44 were an artefact.

`SKAC` turned out to be worth opening anyway, and it is now identified — see
below.

## The rule that was too strict

An ASF is a tree of chunks, and `asf.py` finds where a parent's children begin
by requiring that they **tile its body exactly**. That rule is right nearly
everywhere and it is what makes the chunk walk trustworthy: a wrong offset
almost never produces an exact tiling.

`tree` breaks it. **86 of the 369 files in the model corpus put a block that is
not chunks at all after the last `attr`** — from 144 bytes to 3 600. The
tiling test then fails at every candidate offset, `children()` returns nothing,
and the file reports as having no node tree.

The count is what to trust instead, and it is stated:

* a `tree` gives its node count in the first four bytes of its body;
* its `attr` chunks begin at **body + 0xB0**;
* the run of `attr` chunks is exactly that long on **all 369 trees**.

That last measurement is the one that matters. The stated count and the walked
count agree on every tree in the corpus, including the 283 the old rule already
handled — so the count is not a workaround, it is the format.

| | Before | After |
| --- | ---: | ---: |
| Files with a readable node graph | 283 of 369 | **369 of 369** |
| Nodes | 19 328 | **23 979** |

Ten of the newly-readable files are the game's playable characters, with
skeletons of 315, 332, 358, 559 and 581 nodes. Those are precisely the files
whose bone pools were overshooting.

## The check that says the new trees are real

A count-driven walk could in principle read garbage that happens to start with
`attr`. The evidence that it does not comes from a different format.

An [AAF animation](../formats/aaf.md) names the nodes it drives, and stores the
constant value of every channel that never moves. Session 9 showed those
constants reproduce the **rest pose** stored in the ASF `attr`. That comparison
can be re-run before and after the fix, over the same 900 animations:

| | Names found | Translations | Rotations | Scales |
| --- | ---: | ---: | ---: | ---: |
| Exact tiling only | 68 664 / 131 035 (52.4 %) | 61 805 / 62 104 — 99.5 % | 92.6 % | 99.6 % |
| Counted children | **95 010 / 146 154 (65.0 %)** | **86 246 / 86 642 — 99.5 %** | 91.9 % | 99.5 % |

**26 346 more animation channels came into the comparison and the agreement
held at 99.5 %.** If the newly-walked trees held anything other than the
skeletons those animations drive, the rate would have collapsed. It did not
move.

The "before" row also reproduces session 9's published figures exactly
(61 805 of 62 104, 37 522 of 40 541), which confirms the comparison is the same
one and only the input changed.

## The tail

What follows the `attr` chunks is new and is not read yet. Two shapes:

* **Most** begin with four rows of four floats, each row ending in `1.0` —
  homogeneous points reading as two centre-and-extent pairs — then a
  `0x01010000` marker and more floats.
* **The largest character skeletons** begin instead with a run of **32-byte
  records**: a node index, five floats, two more words. The node indices name
  bones in chains — `R:M:SK_A_LtBdySt`, `R:M:SK_A_LtHipFt`, `R:M:SK_A_LtHipCt`,
  `R:M:SK_A_LtHipRr` — and the floats read as damping and stiffness:
  `0.1, 1.0, 1.0, 0.01, 0.01` on one chain, `0.1, 2.5, 1.0, 0.025, 0.002` on
  the next. `R:M:pColCube` names appear beside them.

Bone chains with per-chain damping and collision cubes is hair and skirt
simulation, and `Aska::Dynamics`, `Aska::DynamicsForceEmitter` and
`Aska::DynamicsWorldWind` are all in the binary to run it. That is a reading of
the shape, not a decode, and it goes on the open list.

## What `SKAC` actually is

Worth doing regardless, since it was the session's stated destination.

All 98 `SKAC` resources on disc 1 unpack to nested NORM archives holding
**250 `ANIM`, 161 `MESH`, 129 `SIG-` and 90 `COLL`** and nothing else. Every
one of the 161 inner meshes has a readable node tree.

But only **16.8 %** of a `SKAC`'s animation record names appear in its own
meshes — so the skeleton those animations drive is outside the bundle. It is
next door. The `SKAC` archives and the character-model archives **alternate**
through one stretch of `ud1.bin`, and matching each bundle's record names
against all 160 model archives:

> for **13 of the 15 `SKAC` groups the model archive immediately below it is
> the best match**, and the two exceptions are within 1 % of the best — a tie
> between characters that share a bone naming convention.

```
SKAC 48D3D000 -> model 48791000      SKAC 4C83F000 -> model 4C39F800
SKAC 4A308800 -> model 49DAF000      SKAC 4DAE2000 -> model 4D6A1800
SKAC 4AE33000 -> model 4A931000      SKAC 5130A800 -> model 50C52800
```

59.8 % of a bundle's record names resolve there. The rest are cameras, lights
and effect emitters living elsewhere again. So the census line "travels with
skeletons" was right, and it is now precise: **a `SKAC` is the overflow
animation set for the character in the archive before it**.

## What this says about method

Session 9's conclusion was not carelessly drawn. It was stated as a
measurement — 44 objects, all in files with no `tree` chunk — and the
measurement was correct given the reader. What was wrong was reading a
*reader's* silence as a *format's* absence.

The tell was available at the time and was not looked at: the files reporting
no node tree were the game's main characters, and a character model with no
skeleton is not a plausible thing for a shipped disc to contain. When a decode
says an asset is missing something it obviously must have, the reader is the
first suspect.

## Tooling

`tools/asf.py` gained `Chunk._counted_children` and `Chunk.tail()`, and its
`check` no longer reports objects in "files with no tree". `tools/mron.py`'s
census now calls `SKAC` a character animation bundle rather than unknown.

## Left open

1. **The tree tail**, described above — the block after the `attr` chunks in 86
   files of 369. The dynamics reading is a shape, not a decode.
2. **The rotation residual**, now 91.9 % rather than 92.6 % over a 40 % larger
   sample. Session 9 sampled it and found the decoded *axis* matching with the
   angle differing, which is an animation whose rest pose genuinely is not the
   scene's; more of them is what a larger sample would give.
3. **Where the remaining 35 % of animation record names live.** Cameras,
   lights and emitters are named in animations that no extracted mesh
   contains.
