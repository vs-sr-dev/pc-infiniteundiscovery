# Session 10 — what drives the model

**Date:** 2026-08-25
**Goal:** open question 1, the `-CNS` / `SNC-` scene data behind the `SCE-`
resources. After session 9 a model had geometry, materials, textures, a
skeleton, animation and collision; what was missing was whatever tells it to
do anything.

## Outcome

Solved as a container and as an instruction set. `SNC-` is a **compiled
script**, and the format is now readable end to end: all 61 payloads on both
discs parse, and every cross-reference inside every instruction resolves.

```
files                       61 parsed, 0 failed
sections walk exactly       61 / 61
instructions                420532, over 413467 blocks of data
opcodes                     253 distinct, 253 with one operand count, 217 with one signature
$ lands                     5035 / 5035  100.0000%
@ lands                     413467 / 413467  100.0000%
& lands                     18666 / 18666  100.0000%
entry lands                 82 / 82  100.0000%
handles are 512.. and dense 50 / 50
0x0149 operands 5..8 unit   987 / 990  99.697%
```

The full specification is [docs/formats/snc.md](../formats/snc.md). What
follows is how it was arrived at, including the two readings that were wrong.

## Everything is counted in words

The header is 0x30 bytes and holds four (offset, length) pairs. Read as byte
offsets none of them make sense; read as **32-bit word counts** they tile the
file exactly, and `max(offset + length) * 4` is the file size on all 61
payloads without exception.

That last detail matters more than it looks. The pairs are *not* in file
order: the code and the data always come first, but the entry table sits
before the string table in 15 files of 61. Taking the file end from the last
pair in the header gets 15 files wrong and looks like a decompression bug.

Four sections: **code**, a **data pool**, a **string table** and an **entry
table**.

## One encoding, used twice

An instruction is `u16 operand-words, u16 opcode`, then the operands. An
operand is eight bytes: a kind letter, a sub-kind byte, an aux word and a
value. That is all of it.

Two measurements say the reading is right, and neither is something a wrong
reading produces:

* Walking the code section from its start lands **exactly** on its end in all
  61 files — never one word over, never one short.
* **Every one of the 253 opcodes has one operand count and only one**, over
  420 532 instructions. If the header split were wrong, arity would scatter.

The data pool uses the same operand encoding under a `u32` length, and walks
exactly too. A length of zero is legal — an empty block, which is what a
command passes where an optional curve is absent.

## The letters

The kind byte is a printable ASCII letter, and four of them are sigils that
address the other sections. All three reference classes resolve completely:

| | |
| --- | --- |
| `$` — byte offset into the string table | 5 035 of 5 035 |
| `@` — word offset into the data pool | 413 467 of 413 467 |
| `&` — word offset into the code | 18 666 of 18 666 |
| entry-table address | 82 of 82 |

`&` was the one that needed work, and it is where the first wrong reading was.
Taken as an absolute offset it lands on an instruction 75.8 % of the time, and
the failures are all in two opcodes, `0002` and `0003`. Those two read the
same operand **relative to their own address, signed** — and then 5 182 of
5 182 land. Read absolutely they get 679 of 4 949, which is roughly what
chance gives on a section whose instructions average four words apart.

The second wrong reading was quieter. The value of a `&` operand has to be
sign-extended, because a relative branch reaches backwards; leaving it
unsigned left 52 instructions failing in a way that looked like a real gap in
the format rather than a bug in the reader.

`n` is the immediate, and it carries its own type: aux `0x0100` means an IEEE
float, otherwise a signed int. That is a property of the **literal**, not of
the argument slot — the compiler stored `0` as an int and `-697.383` as a
float, so the same argument of the same command is an int in one instruction
and a float in the next.

The rest of the letters are reference classes. `h` is an object handle, and it
behaves exactly as one: **allocated in file order from 512, dense, with 0 as
null**, on all 50 files that use more than two. `m` is a second such space,
allocated from 1, appearing only in the data pool and always two to a block.

## What the strings say

The string table is the artists' Maya node names, the same ones the ASF node
tree and the ACF sphere tree carry, and only **six opcodes take a string**.
That is what identifies them, because the argument names what the command
does:

| Opcode | Strings it is given |
| --- | --- |
| `0142` | `R:M:SK_HipR`, `R:M:WEPLINK_RtHand`, `ROOT` — bones |
| `0141` | `$WEAPON`, `R:M:EUGUNE_Backpack`, `R:M:SIGMUND_shield` — slots |
| `0105` | `CTRL_chair`, `CTRL_elevator`, `DOOR_01_BOTH`, `A16_BON01` |
| `0106` | `directionalLight1`, `Dlt_Key_sun`, `GLOBAL_Hemi_Ch` — lights |
| `0114` | `shadow_B1_01Shape`, `GLOBAL_Key_DLt_SdwShape` — shadows |
| `0154` | `R:M:DRAIN_VIGOR`, `R:M:eyeA` |

`Dlt` and `Hemi` are Maya's directional and hemisphere lights; every string
`0114` takes is a `shadow_*` or a `*_SdwShape`. Those readings are less a
guess about the opcode than an observation about its only argument.

Of the 922 strings in the disc 1 scripts, 223 appear verbatim among the node
names of the 400-file ASF sample. The ones that do not are the same kind of
name — `R:M:EUGUNE_Backpack`, `R:M:DUMMY_WEP_Sub_G_4` — naming character
models that sample does not contain.

## The one opcode arithmetic identified

`0149` takes no string, but its nine numbers give it away. Three of them are a
position, and the **next four have length 1.0 in 987 of 990 instructions**:

```
0149  h520 e33    -697.383 0.11 416.493   -0 -0.005 -0 1     1  7702
0149  h526 e4844  -66.827 3.198 2793.31    0 0.965 0 -0.264  1  7704
```

`0.965² + 0.264² = 1.0007`. It is a unit quaternion, so `0149` is spawn: a
handle, an asset, a position, a rotation, a scale, an identifier. The three
that miss are off in the fourth decimal.

`0032` is the other spawn command, and it is a useful contrast — same handle
and asset, but its rotation is **three Euler angles in degrees**, and its
fourth operand is sometimes an `h`, which is a parent.

## The data pool is why commands can hold curves

A move command does not carry an X. It carries `@` at a block that holds the
X values, so one instruction can hold a whole keyframe track. Expanded, a
timeline command reads:

```
0147  @31388 @31391 @31394 @31397  0 10 10 1 1 4 0 4 4  @31400 @31405  0 0
        @31388 = [-10327.5]        @31397 = [230]
        @31391 = [172.059]         @31400 = [0 1]
        @31394 = [-14368.2]        @31405 = [0 1]
```

Three coordinates, a duration, and a pair of `[0 1]` blocks. Nineteen opcodes
end in that same `@@nn` tail — 88 690 instructions of 420 532 — so it is a
shared trailing structure, and the most likely reading is an easing curve and
its endpoints. `0133` has the same tail in front of **two quaternions**, which
is a rotation tween from one pose to another over a stated duration.

## What the executable says

The RTTI in the retail binary, which [session 1](session-01.md) recovered,
names this file's contents directly. `CSceVar` and `.?AUVar@sce@@` — a struct
`Var` in a namespace `sce` — which is exactly the tagged eight-byte operand
the whole format is built from. Around it: `CSceSceneController`,
`CSceDelayTask` (a wait), `CScenario`, and three hard-coded set pieces named
after where they happen — `CSceSpecialProcess_01Tsunami`,
`CSceSpecialProcess_02OgreJump`, `CSceProcess03_VeszpremMirrorRoom`.

Two things that were looked for and are **not** there. There is no opcode
arity table in the image — the instruction carries its own arity, so the
interpreter never needs one. And no dispatch table of 468 handler pointers
survives a sliding-window search of the pointer regions in `.rdata` and
`.data`; the best candidate scores 0.17 against a scoring function that would
give a real table nearly 1. So the opcode names are not going to come out of
the binary this way.

## A small thing about SLZ

Seven of disc 1's 40 `ud2.bin` scripts fail `mron.py --decompress` with *no
XCompress magic at 0x18*. They are not corrupt: their SLZ wrapper gives the
**same value for the compressed and the uncompressed size**, and the payload
is simply stored. All seven are under 200 bytes, which is presumably the point.
Worth knowing before assuming a decompressor bug.

## Tooling

`tools/snc.py` is new: `info`, `dis` (with `--blocks`, which expands every data
block an instruction points at), `strings` (which prints the table alongside
the opcodes that use each entry), `blocks`, and `check` over a corpus, which
is what produced the figures at the top.

## Left open

1. **The header word at `+0x08`.** It is 4 in twelve files, 11 in another, and
   564 146 in the largest. It matches no count in the file — instructions,
   blocks, entries, strings, or any section length — and a 530-instruction
   script and a 9-instruction script both carry 4.
2. **What 246 of the 253 opcodes do.** The `@@nn` family of 19 is the place to
   start, since they demonstrably share a trailing structure.
3. **The reference spaces `e`, `c`, `k`, `s`, `i`, `u`, `v`, `r`, `g`.** `e`
   reaches 29 079, far beyond any one archive's resource count, so it is
   probably an index into a global asset table.
4. **What `m` is.** Allocated like a handle but from 1, only ever in the data
   pool, always two to a block.
5. **The five-digit identifier** that ends `0149`, `0032`, `0105`, `0106` and
   `0141`. It runs in near-consecutive clusters (7702, 7703, 7704 … then 4991
   … then 5737, 5738) and is not monotone across a file, so it looks like a
   persistent instance id assigned when the scene was authored.
6. **`NODE`**, which sits beside every `SCE-` in the same archive. Its payload
   has no magic and is not a script: it opens with an id and a table of
   offsets, and holds floats that read as world bounds (±5 200). A spatial
   partition is the obvious guess and it is still only a guess.
