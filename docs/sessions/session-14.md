# Session 14 — two unlikely titles, and the codec one of them gave up

**Date:** 2026-08-25
**Goal:** two more specimens for
[aska-across-titles.md](../aska-across-titles.md), both chosen because they
looked unlikely: *Star Ocean: Blue Sphere* (2001, Game Boy Color, Japan) and
*Star Ocean: Till the End of Time* (2003, PlayStation 2, PAL disc 1). The
first is a handheld title on a Z80 derivative with 4 MB of ROM; the second is
two years older than the oldest disc measured so far, and the question was
whether anything in it prefigures ASKA.

## Outcome

**Blue Sphere: no, and cleanly no.** Every signature scores zero, in both byte
orders, on the whole ROM.

**Star Ocean 3: yes, and it moved the whole `SLZ` thread back two years.** It
also, unexpectedly, gave up a codec. Session 13 left "what is behind `SLZ` on
the PlayStation 2" as an open question and this session answers it for **method
1** — which is what turned a census into a reading. Two titles that were
recorded as "`SLZ` and nothing else this repository recognises" now have a
named vocabulary, and one of the names is Infinite Undiscovery's oldest unread
resource.

## 1. Star Ocean: Blue Sphere, and what a real "no" looks like

The cartridge header, in full, because it is the whole of what the ROM says
about itself:

| | |
| --- | --- |
| title | `STAROCEANGBBO2J` |
| licensee | `B4` — Enix |
| cartridge type | `0x1B` — MBC5 + RAM + battery |
| ROM / RAM | 4 MiB, 256 banks / 32 KB battery-backed |
| flags | CGB `0x80` (Game Boy compatible), SGB `0x03` |
| region / version | Japan, 1.0; header checksum and Nintendo logo both correct |

`aska.py identify` over all 4 MiB finds **nothing at all** — not a single hit
of any signature, reversed or not, which no other specimen has managed. The
targeted checks agree: no `SLZ`, no `SLE`, no `Aska`, no `AHSL`, no `R:M:`, no
`pCol`, no `Tri_ace`, and **zero** matches for the general versioned-magic
pattern (four printable bytes then `NN.N`) that `MRON00.1` and its five
relatives belong to. The 19 350 runs of six or more printable bytes in the ROM
are all tile data; there is not one readable string in the image.

That is the honest reading and it is what was expected: an 8-bit handheld with
a 4 MB address space shares nothing structural with a 2003 console engine.
There is no argument to make here.

One observation is worth recording anyway, because it is the only deliberate
convention the ROM shows: **every non-empty bank begins with its own bank
number**. 242 of 255 banks do, and the thirteen that do not are entirely
zero-filled — so 242 of 242. It is a common Game Boy practice rather than a
tri-Ace one, and it is offered as an observation, not as evidence.

## 2. Star Ocean 3 — the disc, before anything is decompressed

The PAL disc 1, `SLES_820.28`, `VER = 1.01`, is laid out **exactly** like
Radiata Stories' and Valkyrie Profile 2's: an ISO 9660 filesystem holding three
files and nothing else, with four gigabytes of data in raw sectors outside it,
addressed by LBA.

```
SLES_820.28      LBA 270   751 024 bytes
SYSTEM.CNF       LBA 269        56
IOPRP271.IMG     LBA 637   274 097
```

So the convention that session 13 found on the 2005 and 2006 discs is already
in place in 2003.

### `SLZ` and `SLE` in the executable, in the same shape

The executable is 751 KB of MIPS ELF, and its string area carries:

```
0x4DD40  "SLZ\0"   0x4DD48  "SLE\0"
0x4DE30  "SLZ\0"   0x4DE38  "SLE\0"
```

Two adjacent eight-byte-aligned constants, twice per binary — which is
precisely the shape session 13 measured in Radiata Stories and Valkyrie Profile
2, and the mirror of the four-byte-aligned `SLE`-then-`SLZ` pair in the three
Xbox 360 executables. **Six titles, three CPUs, 2003 to 2010.**

Nothing else in the executable names the engine: no `Aska`, no `AHSL`, no
`R:M:`, no `pCol`, no payload magic. What it does carry beside the pair is the
hard-disk install path — `hdd0:`, `pfs0:sotet.bin`, `PS2ICON3D` — which dates
it precisely to the PlayStation 2 HDD era and is of no relevance to the engine.

### The blocks themselves

In four 32 MiB windows spread across the data area, **1 641 `SLZ` magics, 1 566
sound**, and every sound one is in the PlayStation 2 header shape — not one is
in the Xbox 360 shape. The walk is the stronger test: in one window, **695 of
727 consecutive blocks are followed by the next at four-byte alignment**, and
the 32 that are not sit on the boundaries between runs.

The method byte takes 1, 2 and 3. Method 0 does not appear anywhere sampled,
which is a small difference from Radiata Stories, where it does.

And **no versioned magic anywhere**: 56 candidates for the `XXXXnn.n` pattern
in 128 MiB, all of them digit runs inside compressed data. That is expected —
on this disc everything is behind `SLZ`, and a sweep cannot see through it.

## 3. The method-1 codec

This is the part that was not planned.

The first payload byte of a compressed block turned out to be a flag byte, and
under the right reading its literals expose the beginning of the file. That was
visible immediately: `FAS\0`, `RTA\0`, `LCTP`, `DMM\0` and, in one block,
`so3mclib 1.80i` in plain text. A block whose first fourteen plaintext bytes
are known is a known-plaintext attack waiting to happen.

The full specification and the three separate measurements that fix its three
fields are in [formats/slz.md §2b](../formats/slz.md#2b-the-playstation-2-codec-method-1).
In one line: **LZ77, byte-wide flags read from bit 0 up, literals on 1, a
two-byte back-reference with a 12-bit distance and a 4-bit length biased by 3.**

The result:

| | Star Ocean 3, 2003 | Valkyrie Profile 2, 2006 |
| --- | ---: | ---: |
| method 1 blocks sampled | 152 | 153 |
| decode to exactly the stated size | **152** | **153** |
| failures | **0** | **0** |

Two titles, three years apart, no failures and no special cases. Radiata
Stories writes no method 1 at all in 64 sample windows, which is odd and is
recorded as odd.

### What came out of the blocks

The decoded payloads are skeletons and scenes, and they name their bones:

```
Bip01           Bip01 Pelvis     Bip01 Spine1     Bip01 L Clavicle
Bip01 Neck      Bip01 L Thigh    Bip01 R Finger3  Bip01 Footsteps
DummyBox01      MOVEBOX          CTRL01           RHAND
```

`Bip01` and its children are **3ds Max Character Studio's** biped, exactly as
the tool names them. That is the same kind of evidence as Infinite
Undiscovery's Maya `R:M:` prefixes and `pCol` primitives — an artist's naming
surviving onto the shipped disc — and it says something the magics do not:
**tri-Ace was on 3ds Max in 2003 and 2006 and on Maya by 2008.** The art
pipeline changed between Valkyrie Profile 2 and Infinite Undiscovery.

One block on the Star Ocean 3 disc is not an asset at all. It begins
`so3mclib 1.80i`, a library stamp, and holds the game's English script. The
text is lightly obfuscated — adding `0x39` to every byte makes the lowercase
words readable, which is enough to recognise sentences (*"the ship has served
valiantly in several battles"*) but leaves capitals and punctuation elsewhere,
so the mapping is a table rather than a plain shift. It is not pursued further
here; it is recorded because a library version string is a dateable artefact.

## 4. What that unlocked, which is not about the PlayStation 2

The payload census is in
[formats/slz.md §2c](../formats/slz.md#2c-what-the-playstation-2-titles-call-their-assets).
Three rows of it reach back into open questions about the Xbox 360 disc:

* **`DTT\0`** is a stored payload on Valkyrie Profile 2. It is byte for byte
  the payload of Infinite Undiscovery's `TTD-` resource —
  [question 12](../../TODO.md), the last tag on that disc with no reading at
  all. There is now a copy of it, uncompressed, on a disc two years older.
* **`LCTP`** is `PTCL` backwards, and `ptcl` is one of the ASF chunks nobody
  has opened ([question 3](../../TODO.md)). It is a whole file on the
  PlayStation 2 and a chunk inside a scene by 2008.
* **`DMM\0`** is `MMD` backwards, and `MMD ` is one of Star Ocean 4's three
  unread magics ([question 25](../../TODO.md)). It is on the 2003 disc.

And one row corrects something session 13 wrote. **`PACK` is not new in 2009.**
It was recorded as a Star Ocean 4 invention because Infinite Undiscovery has
none; it is the leading literal of roughly 190 of the 1 987 blocks on the 2003
disc that do not yet decode. The header cannot be checked until methods 2 and 3 open, so what
is established is the tag, not the container.

## Tooling

`slz.py` grew a second wrapper and a second codec. It now reads the 16-byte
PlayStation 2 header alongside the 24-byte Xbox 360 one, decodes methods 0 and
1, and has a `scan` command that censuses an image: method histogram, how many
consecutive blocks land on the next, and the payload magics of everything it
can open.

```
python tools/slz.py scan <ps2-image.iso> --windows 12 --window 0x800000
```

## Left open

1. **PlayStation 2 methods 2 and 3.** They are 1 987 of the 2 139 blocks
   sampled on the 2003 disc and they hold the bulk of all three — every texture and every
   mesh, on the evidence of what method 1 turned out to contain. Neither is
   method 1 under another number. The way in is probably the MIPS decompressor
   in `SLES_820.28`, which is small enough to disassemble.
2. **The PlayStation 3 methods 1, 2 and 3.** Star Ocean 5 uses the same method
   numbering and the same stored method 0, and its method 1 is *not* this
   method 1 — tried against its blocks it decodes none.
3. **What `SAF`, `ATR` and `SPF` are.** They are the three commonest payloads
   on all three PlayStation 2 discs and the first two decode completely; what
   is missing is a reader, not the bytes. `SAF` carries a skeleton and node
   names, `ATR` carries a skeleton and float arrays, and whether either is the
   ancestor of `ASF ` is a question the structure can answer and this session
   did not ask.
4. **`PACK` on the 2003 disc.** Whether the header is Star Ocean 4's — a
   version word, a count at `+0x08`, a total size, then 16-byte entries — is
   not testable until the block it sits in decompresses.
5. **Radiata Stories writes no method 1.** It is the middle title of the three
   and the only one that does not use the codec, and its method-0 blocks are
   all audio. Whether it simply compresses everything harder, or the method
   numbering is per-title, is not known.
6. **The `so3mclib` string table.** Adding `0x39` reads the lowercase letters
   and nothing else, so the character mapping is a table. It is the game's
   script, and this repository has no reason to dump it.
