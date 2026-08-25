# SNC — the Aska scene script

Every `SCE-` resource decompresses to a payload beginning `-CNS00.3` — the
byte-reversed `SNC-` plus a version, the same convention the
[NORM container](norm-mron.md) uses for itself. There are 44 on disc 1 and 17
more in disc 2's `ud1.bin`, 61 payloads and 30 MB uncompressed.

A model was complete after [session 9](../sessions/session-09.md): geometry,
materials, textures, a skeleton, animation, collision. What was missing was
whatever *drives* them, and this is it. An SNC is a **compiled script**. It
says which objects a scene spawns, what asset each of them is, where it stands,
which bone it is attached to, which light and which shadow belong to it, and
how all of that moves over the course of a cutscene.

**Status: the container and the instruction encoding are solved.** All 61
payloads parse, every cross-reference in every instruction resolves, and the
253 opcodes each have exactly one operand count. What the opcodes *mean* is
another matter — seven of them are identified here from evidence outside the
decode, and the rest are named only by number.

The engine confirms the name. The executable's RTTI carries `CSceVar` and
`sce::Var`, along with `CSceSceneController`, `CSceDelayTask`,
`CSceSpecialProcess_01Tsunami`, `CSceProcess03_VeszpremMirrorRoom` and
`CSceSpecialProcess_02OgreJump` — a scene controller, a wait task, and
hard-coded set pieces named after the places they happen in. `sce` is the
namespace and **`Var` is the tagged value this whole file is made of**.

## 1. The header

0x30 bytes, big-endian. Every offset and length in it counts **32-bit words**,
not bytes — the one thing that has to be got right before anything else reads.

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 8 | `-CNS00.3` |
| `+0x08` | 4 | Unidentified — see [§7](#7-what-is-left) |
| `+0x0C` | 4 | Version, 1 in all 61 |
| `+0x10` | 8 | **Code**: offset, length — the offset is word `0x0C` in all 61 |
| `+0x18` | 8 | **Data**: offset, length |
| `+0x20` | 8 | **Strings**: offset, length |
| `+0x28` | 8 | **Entries**: offset, length |

The four sections tile the file with nothing between them, each padded up to a
four-word boundary, and the end of the last one is the end of the file on all
61 payloads. But **the header does not list them in file order**: the code and
data always come first, and then the entry table precedes the string table in
15 files of 61. Reading the pairs as an ordered list works until it does not,
so take the file end as `max(offset + length) * 4` rather than from the last
pair.

## 2. Code — instructions

A flat list. An instruction is four bytes of header and then its operands:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 2 | Operand size in words — two per operand, so always even |
| `+0x02` | 2 | Opcode |
| `+0x04` | .. | The operands, eight bytes each |

The next instruction follows immediately. Walking that from the start of the
section lands **exactly** on its end in all 61 files.

Two things fall out of the walk that a wrong reading would not produce:

* **253 distinct opcodes, and every one of them has a single operand count**
  across 420 532 instructions. 217 of the 253 also have a single sequence of
  operand *kinds*; the 36 that vary swap one kind for another in the same
  slot, which is what a tagged value is for.
* Every file begins with **four zero words** — opcode 0, no operands — and
  every file ends on opcode `0x0005`, which is also the commonest zero-operand
  instruction inside the body. So `0x0005` is a terminator.

## 3. Operands — `sce::Var`

Eight bytes: a four-byte tag and a four-byte value.

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 1 | Kind — a printable ASCII letter |
| `+0x01` | 1 | Sub-kind, 0 or 1 |
| `+0x02` | 2 | Aux — `0x0100` marks a floating-point immediate |
| `+0x04` | 4 | Value |

The kind letter is what makes the file readable, and four of the letters are
sigils that address the other three sections. Measured over all 61 payloads:

| Kind | Meaning | Lands |
| --- | --- | ---: |
| `$` | String, as a **byte** offset into the string section | 5 035 / 5 035 |
| `@` | Data block, as a **word** offset into the data section | 413 467 / 413 467 |
| `&` | Code address, as a **word** offset into the code section | 18 666 / 18 666 |
| `n` | Immediate | — |

`&` is read two ways, and both are exact. Sixteen opcodes — `0001`, `0006`,
`0045`, `0098`, `00e0`, `00e4`, `00fa`, `00fb`, `00fc`, `011f`, `012e`, `0136`,
`0148`, `014b`, `01a6`, `01d2` — take it as an absolute word offset, and all
13 484 of those land on an instruction start. Opcodes `0002` and `0003` take
it **relative to their own address and signed**, and all 5 182 of those land
too. Reading them absolutely instead gets 679 of 4 949 right, which is what a
coincidence looks like.

`n` carries its own type. Aux `0x0100` means the four bytes are an IEEE float;
otherwise they are a signed integer. That is a property of the *literal*, not
of the slot: the compiler stored `0` as an int and `-697.383` as a float, so
the same argument of the same command is an int in one instruction and a float
in the next. Anything reading a position has to coerce.

The remaining letters are reference classes whose spaces are not all
identified:

| Kind | Count | What is known |
| --- | ---: | --- |
| `h` | 125 420 | Object handle. **Allocated in file order from 512, dense, with 0 as null** — exactly so in all 50 files that use more than two |
| `c` | 46 946 | A small enumerated reference; 0 in four cases of five, never above 77 |
| `e` | 45 575 | Asset or type identifier, up to 29 079 |
| `#` | 12 757 | Only ever the sole operand of opcode `0009`; 0..19 |
| `k` | 8 720 | Only in `0016` and `0018`, both `kn`; up to 610 |
| `m` | 19 826 | A second handle space, **allocated from 1 and dense in all 34 files that use it**, and always two to a data block. Appears only in the data section |
| `a` `b` `d` `j` `o` `p` `t` | 8 795 | Value zero in every occurrence, so keywords rather than references |
| `i` `r` `s` `u` `v` `g` | 7 131 | Further reference classes, all small |

## 4. Data — the argument pool

A record is a four-byte length in words followed by that many words of
operands, in exactly the encoding above. Walking it lands on the section end
in all 61 files. A length of zero is legal and common, and commands use an
empty block where an optional curve is absent.

The reason for a pool at all is that **an argument can be a list**. A move
command does not carry an X; it carries `@` at a block that holds the X values,
so a single instruction can hold a whole keyframe track. Here is one timeline
command from `34C6D000_017`, with its blocks expanded:

```
0147  @31388 @31391 @31394 @31397  0 10 10 1 1 4 0 4 4  @31400 @31405  0 0
        @31388 = [-10327.5]        @31397 = [230]
        @31391 = [172.059]         @31400 = [0 1]
        @31394 = [-14368.2]        @31405 = [0 1]
```

Three coordinates, a duration, and two `[0 1]` blocks at the end. Nineteen
opcodes end in the same `@@nn` tail — 88 690 instructions of 420 532 — so that
pair of blocks is a shared trailing structure, most likely the easing curve and
its endpoints. A neighbouring instruction shows the same shape with a list
instead of a scalar: `@31432 = [5 6 7 8 9 10 11 12]`.

## 5. Strings, and the seven opcodes they identify

NUL-terminated ASCII, padded to four bytes. They are **the artists' Maya node
names** — the same names the [ASF node tree](asf.md) and the
[ACF sphere tree](acf.md) carry. Of 922 strings in the disc 1 scripts, 223 are
found verbatim in the node names of the 400-file ASF sample, and the ones that
are not are of the same kind, naming character models the sample does not
contain (`R:M:EUGUNE_Backpack`, `R:M:SIGMUND_shield`).

Only six opcodes take a string, which is what identifies them, and the seventh
comes out of the values it carries:

| Opcode | Operands | Strings it names | Reading |
| --- | --- | --- | --- |
| `0141` | `$nnn` | `$WEAPON`, `R:M:EUGUNE_Backpack`, `R:M:DUMMY_WEP_Sub_G` | attach to a named slot |
| `0142` | `h$nnnnnnnnnn` | `R:M:SK_HipR`, `R:M:WEPLINK_RtHand`, `ROOT` | attach a handle to a named bone |
| `0105` | `h$nnnnnn` | `CTRL_chair`, `CTRL_elevator`, `DOOR_01_BOTH`, `A16_BON01` | bind a handle to a named control node |
| `0106` | `h$nnnnnnnnnnn` | `directionalLight1`, `Dlt_Key_sun`, `GLOBAL_Hemi_Ch` | bind a light |
| `0114` | `$nnnn` | `shadow_B1_01Shape`, `GLOBAL_Key_DLt_SdwShape` | bind a shadow |
| `0154` | `$$nnnnnnn@@nn` | `R:M:DRAIN_VIGOR`, `R:M:eyeA` | bind two named nodes |
| `0149` | `hennnnnnnnn` | — | spawn an object |

`Dlt` and `Hemi` are Maya's directional and hemisphere lights, and every string
`0114` takes is a `shadow_*` or a `*_SdwShape`, so those two readings are not
guesses about the opcode so much as observations about its only argument.

`0149` has no string but gives itself away arithmetically. Its nine numbers
read as a position, then **four numbers whose length is 1.0 in 987 of 990
instructions** — a unit quaternion — then a scale, then an identifier:

```
0149  h520 e33    -697.383 0.11 416.493   -0 -0.005 -0 1     1  7702
0149  h526 e4844  -66.827 3.198 2793.31    0 0.965 0 -0.264  1  7704
```

`0.965² + 0.264² = 1.0007`. The three that miss are off in the fourth decimal.

The last number of `0149`, and of `0032`, `0105`, `0106` and `0141`, is a
five-digit value that runs in near-consecutive clusters — 7702, 7703, 7704,
7705 … then 4991 … then 5737, 5738 — and is **not** monotone across the file.
It behaves like a persistent instance identifier assigned when the scene was
authored, not like a position in the file.

`0032`, the other spawn command, takes the same handle-and-asset pair but
gives its rotation as **three Euler angles in degrees** rather than a
quaternion, and takes a fourth operand that is sometimes an `h` — a parent.

## 6. Entries

Pairs of words: an identifier, small and starting at 1, and a code address in
the same word units `&` uses. All 82 land on an instruction start. Several
entries commonly share one address. They are the script's labelled entry
points — 46 of the 61 files have none at all.

## 7. What is left

* **The word at `+0x08`.** It is 4 in twelve files, 11 in another, and 564 146
  in the largest. It matches no count in the file — not instructions, blocks,
  entries, strings, or the size of any section — and a 530-instruction script
  and a 9-instruction script both carry 4.
* **What the opcodes do.** 246 of 253 are known only by number, arity and
  operand kinds. The `@@nn` family of 19 is the most promising group, since
  they clearly share a trailing structure.
* **The reference spaces `e`, `c`, `k`, `s`, `i`, `u`, `v`, `r`, `g`.** `e`
  reaches 29 079, far more than any resource count in one archive, so it is
  probably a global asset table.
* **What `m` is.** It is allocated like `h` but from 1, lives only in the data
  section, and always comes two to a block.
* **`NODE`** is no longer among these. It travels beside every `SCE-` in the
  same archive, and [session 11](../sessions/session-11.md) showed it is the
  navigation mesh the AI walks on — see [node.md](node.md). It also gave this
  format a check from outside: 99.44 % of the positions a script spawns objects
  at fall inside its own scene's nav mesh.

## 8. Reproducing

```
python tools/mron.py extract <image> --offset N --length N \
    --tag SCE- --decompress out/
python tools/snc.py info    out/xxx_SCE.bin
python tools/snc.py dis     out/xxx_SCE.bin --limit 40 --blocks
python tools/snc.py strings out/xxx_SCE.bin
python tools/snc.py check   out/*.bin
```

A handful of `SCE-` payloads are **stored, not compressed**: their SLZ wrapper
gives the same value for the compressed and uncompressed size and there is no
XCompress stream behind it, just the bytes. Seven of disc 1's 40 `ud2.bin`
scripts are like that, all of them under 200 bytes. `tools/mron.py --decompress`
reports those as failures; the payload is the `uncompressed size` bytes
starting at `0x18`.

`snc.py check` over the whole corpus:

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

## 9. The commonest opcodes

For reference, with the operand-kind signature each one always has.

| Opcode | Count | Operands |
| --- | ---: | --- |
| `0010` | 142 933 | `h` — also `c` and `b` in the same slot |
| `0147` | 21 853 | `@@@@nnnnnnnnn@@nn` |
| `0007` | 21 098 | `n` — also `a`, `r` and others |
| `0043` | 16 142 | `@@@n@@nn` |
| `0133` | 14 836 | `nnnnnnnnnnn@@nn` — the first eight are two quaternions |
| `0131` | 13 158 | `eennnnnnnnnnn@@nn` |
| `0009` | 12 757 | `#` |
| `003e` | 11 951 | `hnnnnnnnnnnnnnnnnn@@nn` |
| `0040` | 11 233 | `nnnnn@@nnn` |
| `0001` | 10 621 | `&` — absolute |
| `014f` | 9 446 | `nnn` |
| `0005` | 9 337 | none — the terminator |
| `000f` | 7 950 | `nn` |
| `013b` | 6 441 | `nnnn` |
| `0134` | 6 430 | 33 numbers |
| `0013` | 6 254 | `n` |
| `00d3` | 5 407 | `@@@@@@@n@@nn` |
| `0166` | 4 828 | `ennnnnnnnnnnn` |
| `0032` | 4 822 | `hennnnnnnnnnnnn` — spawn with Euler angles |
| `0016` | 4 534 | `kn` |
| `00d7` | 4 320 | `nn@@nnn` |
| `0119` | 4 305 | `@ennhnnnnnnnn` |
