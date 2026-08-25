# SLZ — the compressed resource wrapper

**The oldest thing in the engine, and older than the engine.** It is on Star
Ocean: The Second Story's PlayStation disc in **1998**, ten years before
Infinite Undiscovery, and still in Star Ocean 5 in 2016 — older than the
container, older than the payload formats, older than the name ASKA is attached
to in this repository. Nothing it wraps in 1998 is tri-Ace's own: the blocks
hold MIPS overlay code and Sony `TIM` textures, so the wrapper predates the
studio's file formats rather than accompanying them. See
[§2a](#2a-three-revisions-and-what-the-oldest-one-explains) and
[aska-across-titles.md](../aska-across-titles.md).

**Every PlayStation codec is readable.** Method 0 is stored, and methods 1, 2
and 3 are three settings of one LZ77 that tri-Ace wrote itself: the same
framing, three different ways of spending the token —
[§2b](#2b-the-playstation-codec-method-1),
[§2b-2](#2b-2-method-2-the-same-lz77-with-runs-instead-of-the-longest-match),
[§2b-3](#2b-3-method-3-the-same-lz77-again-in-halfwords). Method 1 is unchanged
from 1998 to 2006 and so are the other two. `SLE`, the string that has sat
beside `SLZ` since 2003 without ever being explained, is not a codec but an
encryption envelope around all four —
[§2b-4](#2b-4-what-sle-is).

**And a neighbouring studio did something very similar.** Eternal Sonata, by
tri-Crescendo on the Xbox 360 in 2007, compresses every file it ships with an
LZSS of the same family, the same framing and the same method numbering — but
its LZSS is the stock Okumura routine and tri-Ace's is the one that departs
from it, so the resemblance is smaller than it first looked. The comparison is
[§2d](#2d-the-tri-crescendo-comparison); the format itself is
[vmtoc.md](vmtoc.md).

Most of Infinite Undiscovery's bulk is compressed. Every `MESH`, `MTEX`,
`SCE-`, `SKAC` and `APAC` resource sits behind a header whose first three bytes
are `SLZ` — 1 812 blocks in disc 1's `ud1.bin` alone, holding 1.88 GB of
uncompressed data. Nothing much can be read out of the game without going
through it.

The name is tri-Ace's. The compression is not.

**Status: solved.** All 1 812 blocks in disc 1's `ud1.bin` decompress without
error, and every payload that states a usable length agrees with the decode.
See [§6](#6-status) for the exact numbers.

## 1. It is XCompress underneath, on the Xbox 360

The constant `0x0FF512EE` at offset `0x18` is Microsoft **XCompress**'s stream
magic, and it is byte-identical in all 1 812 blocks along with the version field
that follows it — so it is a signature, not a checksum. XCompress is the Xbox
360 XDK's `XMemCompress`, which is LZX with a configurable window.

So SLZ is a 24-byte tri-Ace wrapper in front of a stock SDK stream. Given that
the same executable links `XGRAPHC` and `D3DX9` from the same SDK, that is
exactly the pragmatic choice one would expect.

## 2. Layout

All big-endian.

**tri-Ace wrapper**, 24 bytes:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 3 | `SLZ` |
| `0x03` | 1 | Version — 4 everywhere |
| `0x04` | 4 | Header size (`0x20`) |
| `0x08` | 4 | Compressed size, counted from `0x18` |
| `0x0C` | 4 | Uncompressed size |
| `0x10` | 4 | Zero |
| `0x14` | 4 | One |

**XCompress stream header**, 48 bytes, starting at `0x18`:

| Offset | Size | Field |
| --- | --- | --- |
| `0x18` | 4 | Magic `0x0FF512EE` |
| `0x1C` | 4 | Version `0x01020000` |
| `0x20` | 4 | Context flags |
| `0x24` | 4 | Flags |
| `0x28` | 4 | Window size — `0x20000`, 128 KB |
| `0x2C` | 4 | Compression partition size — `0x80000` |
| `0x30` | 8 | Uncompressed size |
| `0x38` | 8 | Compressed size |
| `0x40` | 4 | Uncompressed chunk size — `0x20000` |
| `0x44` | 4 | Largest compressed chunk in this stream |

**Chunk table**, from `0x48`:

| Offset | Size | Field |
| --- | --- | --- |
| `+0x00` | 4 | Compressed size of this chunk, counted from `+0x04` |
| `+0x04` | .. | Chunk payload, that many bytes |

The next chunk header follows at `+0x04 + size`.

Two independent checks say the chunk table is right: walking it lands
**exactly** on the end of the compressed region in every block tested, and the
largest size encountered always equals the field at `0x44`.

Entries holding an SLZ block are padded, with
`entry size == align_up(compressed size, 4) + 24` — the 24 being the wrapper
that sits before the counted region.

## 2a. Three revisions, and what the oldest one explains

The name is the same in every tri-Ace title from 1998 on. The header is not,
and the differences are small enough to line up in one table. The first column
covers **five discs and eight years** — the PlayStation and PlayStation 2
titles from Star Ocean: The Second Story to Valkyrie Profile 2 — with not one
field moved between them.

| | PlayStation 1–2, 1998–2006 | Xbox 360, 2008–10 | PlayStation 3, 2016 |
| --- | --- | --- | --- |
| `0x00` | `SLZ` | `SLZ` | `SLZ` |
| `0x03` | **method** — 0 stored, 1–3 compressed | 4, always | **method** — 0 stored, 1–3 compressed |
| `0x04` | compressed size | `0x20` | `0x00010025` |
| `0x08` | uncompressed size | compressed size | compressed size |
| `0x0C` | zero | uncompressed size | uncompressed size |
| `0x10` | payload | zero | zero |
| `0x14` | | one | `0x20` |
| `0x18` | | XCompress stream | `0x00400001` |
| `0x20` | | | payload |
| byte order | little-endian | big-endian | big-endian |

So the header held still for eight years and then moved once. Between 2006 and
2008 **one word was inserted at `0x04`**. The size pair and
the zero behind it move down by four bytes and nothing else changes. Between
2008 and 2016 the `0x20` moves from `0x04` to `0x14`, where it is genuinely the
header size, and XCompress goes away — which it had to, being an Xbox library.

**The fourth byte is a method, and the 2005 disc is what proves it.** Reading
only Infinite Undiscovery it looks like a version: the value is 4 in all 1 812
blocks. Star Ocean 5 was the first specimen to show it selecting a codec, Star
Ocean 4's stored blocks agreed, and Radiata Stories settles it — 68 of 661
sampled blocks say 0, and every one of those 68 has its two sizes equal and its
payload in the clear. Infinite Undiscovery is the exception.

Two more measurements from that sample of 661, taken from three widely
separated regions of the disc: the word at `0x0C` is zero in **661 of 661**,
and the compressed size is less than or equal to the uncompressed in **661 of
661**.

### What a second Xbox 360 title changed

Star Ocean 4 writes XCompress version `0x01030000` where Infinite Undiscovery
writes `0x01020000`, and sets the chunk size to the whole uncompressed length
rather than a fixed `0x20000`, so a block is one chunk however large it is. The
window stays `0x20000`.

One consequence reached the reader. Infinite Undiscovery's frame walk lands
exactly on the end of the chunk; Star Ocean 4's leaves a few bytes of zero
padding behind the last frame. `slz.py` now stops on the **output** count
rather than the input length, and checks that whatever follows is zero — so a
walk that went wrong still fails, because non-zero bytes after the last frame
are an error. With that one change, 797 of Star Ocean 4's blocks decompress
into `AAF`, `ASF`, `ACF`, `AIF` and `-CNS` payloads that their own readers then
parse.

### What is behind the two later revisions

XCompress is only the Xbox 360 answer, and it is an Xbox library, so it could
never have been the other two.

**All three PlayStation codecs are solved**, and they are one codec. Method 1
is [§2b](#2b-the-playstation-codec-method-1); method 2, which trades the
longest match for a run, is
[§2b-2](#2b-2-method-2-the-same-lz77-with-runs-instead-of-the-longest-match);
method 3, which widens every unit to a halfword, is
[§2b-3](#2b-3-method-3-the-same-lz77-again-in-halfwords). Between them they
decode every block that claims them on all five discs, 1998 to 2006, with no
failures and one arithmetic special case.

Until session 17 read them off the executable, methods 2 and 3 were reached for
only by search, and the record of that is worth keeping: 480 combinations of
offset width, length width, byte order, minimum match, flag polarity and bit
order, tried against 60 PlayStation 3 blocks, decoding none. **That search was
looking in the wrong title.** Method 2 on the PlayStation is byte-flag framed
and always was — it is method 1's framing exactly — and no amount of searching
Star Ocean 5's blocks could have said so.

One habit from those years is still useful and outlives them. A compressed
block begins with a flag byte and its first tokens are ordinarily literals, so
**the payload magic is legible even when the block is not**, which is where
most of the vocabulary in
[§2c](#2c-what-the-playstation-2-titles-call-their-assets--and-what-the-playstation-ones-do-not)
came from before there was a decoder to confirm it with.

**The PlayStation 3 codecs are still open**, and are now known to be genuinely
different rather than merely untried. Star Ocean 5 carries the same method
numbers 0–3 and the same stored method 0, but its methods 1, 2 and 3 were each
run against 400 of its blocks with the decoders below and decode none of them.

## 2b. The PlayStation codec, method 1

An LZ77 with byte-wide flags, and nothing more — no ring buffer, no entropy
coding, no end marker. The decoder stops when it has produced the number of
bytes the header states.

A **flag byte** carries eight tokens, read from the least significant bit up:

| Bit | Token |
| --- | --- |
| 1 | a literal — copy the next byte |
| 0 | a back-reference — two bytes follow |

A **back-reference** is two bytes, `a` then `b`:

| | |
| --- | --- |
| distance | <code>a &#124; ((b & 0x0F) << 8)</code> — 1 to 4 095, counted back from the current end of the output |
| length | `(b >> 4) + 3` — 3 to 18 |

Overlapping copies are ordinary: a distance of 1 is how a run of identical
bytes is written, and it is what fills the zero padding in every file header.

The encoder pads the compressed stream to a multiple of four, so the walk ends
two or three bytes short of the stated compressed size. Anything more than
eight bytes short means it drifted, and `slz.py` treats that as an error.

### How each field was pinned down

None of this is guessable, and each field was fixed by a different measurement
rather than by trying variants until something looked plausible.

**The flag framing** comes from a block whose plaintext begins
`so3mclib 1.80i`. Reading the first payload byte as a flag and taking bit 0 as
"literal" makes `0xFF` mean eight literals — and under that reading the parse
lands on a `0xFF` byte, three times consecutively, exactly where the next flag
belongs. A wrong framing desynchronises within a token or two.

**The length field** comes from the output landing on *exactly* the stated
uncompressed size in 12 of 12 blocks. That test is blind to the distance field
— a back-reference of the wrong length changes how much is produced, a
back-reference from the wrong place does not — so it isolates the length nibble
on its own.

**The distance field** comes from a known-plaintext search. Star Ocean 3's
skeletons are 3ds Max bipeds, so the plaintext must contain `Bip01 `. Every
composition of the two bytes into a 12-bit distance was tried, against a
sliding window and against a ring buffer at every one of its 4 096 possible
start positions — 8 194 candidates. **One produces the string, and it produces
it eleven times in the first 6 KB.** The rest produce it never.

### Status

Written from a 2003 disc, applied unmodified to 1998 data:

| | SO2 1998 | Valkyrie Profile 1999 | Star Ocean 3 2003 | Valkyrie Profile 2 2006 |
| --- | ---: | ---: | ---: | ---: |
| method 1 blocks sampled | 283 | 1 174 | 152 | 153 |
| decode to exactly the stated size | **283** | **1 174** | **152** | **153** |
| failures | 0 | 0 | 0 | 0 |

**1 762 blocks over eight years, no failures and no special cases.**

Radiata Stories writes no method 1 at all in 64 sample windows across its disc,
which is its own small oddity: it is the only one of the five that does not use
the codec.

### Which methods each disc uses

| Method | SO2 1998 | VP1 1999 | SO3 2003 | Radiata 2005 | VP2 2006 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0, stored | 1 | 4 | — | 14 | 2 |
| 1, LZ77 | 242 | 722 | 152 | **none** | 153 |
| 2 | 2 303 | 1 627 | 482 | 2 | 390 |
| 3 | **none** | **none** | 1 505 | 827 | 333 |

**Method 3 does not exist on the PlayStation.** It arrives with the PlayStation
2 and becomes the default there. **Method 2 is on every disc from 1998 on.**

Both are specified below. Neither was guessed: session 17 read them off the two
dispatchers, and the two dispatchers were found by the string.

### How both were found: the string sits on top of its own jump table

`SLZ\0` occupies an eight-byte slot **twice** in Star Ocean 2's `SCUS_944.21`,
at `0x8002A860` and `0x8002AB0C`, and twice again in every PlayStation 2
executable — `0x0014D6C0` and `0x0014D7B0` in Star Ocean 3's `SLES_820.28`.
Immediately after each copy sits a table of 31 code pointers whose gaps grow
`0x24, 0x20, 0x24, 0x2C, 0x34 …` for sixteen entries, jump by `0x140`, and then
repeat the same sequence for fifteen more.

That shape is the whole answer in miniature. The table is one jump table of
**unrolled copy routines**, indexed by a length nibble: entries 0 to 15 are
lengths 3 to 18 and belong to method 1, entries 16 to 30 are lengths 3 to 17
and belong to method 2. Two codecs sharing one table is why the two functions
sit beside each other, and finding the table found both.

The single code reference to the string is the dispatcher. In Star Ocean 2 it
is at `0x800121A8`:

    strncmp(header, "SLZ", 3)      -- at 0x800121DC; a non-zero result returns 0
    skip n blocks by header +0x0C  -- the loop at 0x800121FC
    lbu $v1, 3($s0)                -- the method byte, at 0x8001221C
      0 -> memcpy of header +0x08 bytes from header +0x10
      1 -> 0x800122B4
      2 -> 0x8001275C
      anything else -> return 0

which is also a **free check on the whole exercise**: one of the three arms has
to be the codec that was already specified, from the outside, by search. It is.

The PlayStation 2 dispatcher, at `0x00102540`, is the same function with two
additions — `SLE` beside `SLZ`, and a fourth arm:

    0 -> memcpy    1 -> 0x00101ED0    2 -> 0x001019C0    default -> 0x00101520

Method 2 is handed **four** arguments there and method 3 **three**. That
difference is the specification talking: method 2 has to be told how much
output to make, and method 3 does not.

## 2b-2. Method 2: the same LZ77, with runs instead of the longest match

Method 2 is method 1 with one slot of the length field spent differently. The
framing is identical — byte-wide flags read from the least significant bit up,
a 1 for a literal and a 0 for a two-byte token — and so is the distance field:

| | |
| --- | --- |
| distance | <code>a &#124; ((b & 0x0F) << 8)</code>, as in method 1 |
| length | `(b >> 4) + 3` — but only **3 to 17**, for a nibble of 0 to 14 |

A nibble of **15** is not a match. The same two bytes are re-read as a **run**,
in one of two forms, chosen by whether the low nibble of `b` is zero:

| `b & 0x0F` | count | byte | token size |
| --- | --- | --- | ---: |
| 1 .. 15 | `(b & 0x0F) + 3` — 4 to 18 | `a` | 2 |
| 0 | `a + 0x13` — 19 to 274 | the third token byte | 3 |

So a run of up to 18 bytes costs two bytes and a run of up to 274 costs three,
where method 1 would spend two bytes for every 18. That is the whole
difference, and on the sparse, zero-heavy data these discs are full of it is
worth a great deal: method 2 reaches 2.65:1 on Star Ocean 2 against method 1's
2.07:1 on the same disc.

**There is no end-of-stream token.** Method 1 stops on a distance of zero;
method 2 stops when the output reaches the size stated at header `+0x08`, which
is exactly why the dispatcher passes it that size and passes method 1 nothing.

One consequence is worth stating, because it is what the corpus test below
rests on: with no terminator, the input is consumed to its last byte rather
than to a marker somewhere before it.

## 2b-3. Method 3: the same LZ77 again, in halfwords

Method 3 is method 1 with every unit widened from a byte to a 16-bit halfword.
Nothing else changes — not the framing, not the field split, not the
terminator.

| | Method 1 | Method 3 |
| --- | --- | --- |
| flag unit | one `u8`, 8 tokens | one `u16`, **16 tokens**, still least significant bit first |
| literal | one byte | one **halfword** |
| token | two bytes, `a` and `b` | one `u16` |
| distance | <code>a &#124; ((b & 0x0F) << 8)</code>, in bytes | `tok & 0x0FFF`, in **halfwords** — 2 to 8 190 bytes |
| length | `(b >> 4) + 3`, in bytes — 3 to 18 | `(tok >> 12) + 2`, in **halfwords** — 4 to 34 bytes |
| end of stream | distance 0 | distance 0 |

Because it keeps the terminator it needs no size, which is the argument-count
difference in the dispatcher.

One detail matters for anyone reimplementing it. Distances below 18 halfwords
route through a halfword-at-a-time loop at `0x00101978`, so overlapping copies
propagate the way an LZ77 is expected to. The unrolled copies above that
threshold read their entire source before writing any of it, which would be
wrong for an overlap and is safe only because the threshold excludes one. A
decoder that propagates byte by byte over `distance * 2` bytes gets the same
answer everywhere.

**Odd stated sizes overshoot by one.** The codec emits halfwords and stops on a
token rather than on a count, so its output is always an even number of bytes.
A block whose header states an odd size therefore produces exactly one byte too
many, and that byte is padding — 3 blocks of 3 000 on the Radiata Stories disc,
all three with an odd stated size, and no other kind of mismatch anywhere in
the corpus.

## 2b-4. What `SLE` is

`SLE` has sat beside `SLZ` in every executable from 2003 to 2010 and had never
been anything but a string. The PlayStation 2 dispatcher says what it is,
because it compares both magics two instructions apart and gives `SLE` a branch
of its own ahead of the method switch.

That branch is a **decryption pass over the payload, in place**:

    plain[j] = (cipher[j] - 3 * (j + 1)) ^ key[j & 15]

— a 16-byte key XOR, with a subtractive counter that starts at 3 and advances
by 3 per byte, unrolled eight bytes at a time with a byte-wise remainder loop
at `0x001027A8`. The key is not in the file: it is read with a single `lq` from
`0x001CC730`, past the end of the loaded image, and those two `lq`
instructions — one per copy of the dispatcher — are the **only** two accesses
at that offset anywhere in the executable. Nothing in the executable writes it.

Then comes the part that settles the name. Having decrypted the payload, the
branch does this:

    addiu $v0, $zero, 0x5A
    sb    $v0, 2($s1)

It stores `Z` over the `E` at header `+0x02`, turning the block into an
ordinary `SLZ` one, and falls through into the method switch. **`SLE` is not a
codec at all: it is an encryption envelope around the same four methods**, and
the last thing it does is erase itself.

### And nothing on these discs is inside it

| | SO2 1998 | VP1 1999 | SO3 2003 | Radiata 2005 | VP2 2006 |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw `SLE` byte sequences | 0 | 0 | 220 | 210 | 312 |
| with a header that could be real | — | — | 3 | 16 | 127 |
| that walk to a neighbouring magic | — | — | 0 | 0 | 0 |
| that decode, encrypted or not | — | — | 0 | 0 | 0 |

Valkyrie Profile 2's 127 are the cautionary number. "Sizes that make sense and
a zero at `+0x0C`" sounds like a test and is not one: 40 % of chance `SLE`
sequences inside compressed data pass it. Only one of the 127 is even
sector-aligned, none is followed by another block where its own length says one
should be, and none decodes under any of the four methods, with or without the
zero-key decrypt. So the 2003 executable ships the envelope and the 2003, 2005
and 2006 discs ship nothing in it.

## 2c. What the PlayStation 2 titles call their assets — and what the PlayStation ones do not

Before this, the PlayStation 2 discs were recorded as "`SLZ` and nothing else
this repository recognises". They have a vocabulary, and it is not Infinite
Undiscovery's. Some of it comes out of decoded method-0 and method-1 blocks;
the rest is read off the leading literals of blocks that still do not open:

| Payload magic | Reversed | Seen on | Related to |
| --- | --- | --- | --- |
| `FAS\0` | `SAF` | SO3, VP2, Radiata | the commonest payload on all three |
| `RTA\0` | `ATR` | SO3, VP2, Radiata | second commonest |
| `FPS\0` | `SPF` | SO3, VP2, Radiata | |
| `FIS\0` | `SIF` | SO3, VP2 | |
| `LCTP` | `PTCL` | SO3, VP2, Radiata | Infinite Undiscovery's ASF `ptcl` chunk |
| `DMM\0` | `MMD` | SO3 | Star Ocean 4's `MMD ` |
| `RMAC` | `CAMR` | VP2 | a camera |
| `DTT\0` | `TTD` | VP2, stored | Infinite Undiscovery's `TTD-`, byte for byte |
| `PACK` | — | SO3 | Star Ocean 4's container tag, six years earlier |
| `SEQW`, `RLF2` | — | Radiata, stored | audio |
| `so3mclib 1.80i` | — | SO3 | a library stamp, not a magic |

The "reversed" column is the convention the container already uses for itself:
Infinite Undiscovery writes `MRON` for NORM and `-CNS` for SNC-, and these
three-letter names carry their padding byte in the same place, so a
little-endian build writes `\0`, then the name backwards.

### The `F?S` family, and what the two commonest payloads look like

Three of the magics share a shape, and the shape is the interesting part:

| Magic | Star Ocean 3 | Radiata | Valkyrie Profile 2 |
| --- | ---: | ---: | ---: |
| `FAS\0` | 96 | seen | 346 |
| `FPS\0` | 153 | 36 | 72 |
| `FIS\0` | 51 | — | 1 |

`F?S` as stored is `S?F` read the other way, which sits exactly where the Xbox
360's `A?F` family sits — `ASF `, `AIF `, `AAF `, `ACF `, the A for Aska, a
letter for the content, an F for file. Whether `SAF` became `ASF ` is not
something these counts can settle, and it is recorded as a resemblance rather
than an identification.

What is measured is the structure of the two commonest, both of which decode
completely under method 1:

**`FAS\0`**, header then a name, all little-endian:

| Offset | Field | example |
| --- | --- | --- |
| `0x00` | `FAS\0` | |
| `0x04` | a size | `0x6DA0` |
| `0x08` | zero | |
| `0x0C` | that size plus `0x10` | `0x6DB0` |
| `0x10` | a 16-byte name field | `Bip01` |

After it, records on a **144-byte** pitch, each carrying a node name — 45 names
in the 28 KB specimen, `Bip01 Pelvis` through `DummyBox22` and `CTRL01`.

**`RTA\0`** states its own total size at `0x04` — exactly the file length, which
`FAS\0` does not — then two counts and two offsets, and its name table is on a
**20-byte** pitch. A file that names the same bones as a scene and then carries
float arrays behind offset tables is shaped like an animation, which would put
`ATR` where `AAF ` later sits, but no field beyond the header has been checked.

### The PlayStation discs have none of it

Not one of those tags appears on Star Ocean 2's or Valkyrie Profile's disc — as
a payload head, as a leading literal of an unopened block, or anywhere inside
the decoded data. What the 1998 and 1999 blocks hold instead is **MIPS overlay
code**, **Sony `TIM` textures** (29 of 29 sampled on Valkyrie Profile have a
self-consistent header) and offset-table archives with no magic at all.

That dates the vocabulary. The wrapper is 1998; the named formats are not, and
they appear between 1999 and 2003. Seven `DTT\0` sequences across the two
PlayStation discs were checked and are false — all unaligned, all inside
nibble-packed image data, three of them inside byte-identical copies of one
blob.

### Two rows that matter beyond the census

**`DTT\0` is the payload of
`TTD-`**, the one resource tag on Infinite Undiscovery's disc with no reading
at all — and Valkyrie Profile 2 ships it stored, in the clear, two years
earlier. **`PACK`** was recorded as new in Star Ocean 4 in 2009; it is the
leading literal of roughly 190 of the 1 987 blocks on the 2003 disc that were
undecodable when that count was taken. Those blocks open now, so the header
*can* be checked, and checking it is the outstanding half of
[question 24](../../TODO.md).

## 2d. The tri-Crescendo comparison

*Eternal Sonata* (Xbox 360, 2007) is not a tri-Ace game. It is tri-Crescendo,
the studio founded by people who left tri-Ace, and it has no `SLZ` block, no
`Aska`, no engine namespace and no container — every asset is an ordinary file
in an ordinary directory tree, indexed by a table called `index.vmtoc`.

What it has instead is **its own compression, of the same family**, and the two
are worth putting side by side. The full specification of tri-Crescendo's is
[vmtoc.md](vmtoc.md); this section is only the comparison.

### The differences, in full

| | tri-Ace, 1998–2006 | tri-Crescendo, 2007 |
| --- | --- | --- |
| framing | flag byte, 8 tokens, bit 0 first, literal on 1 | **identical** |
| back-reference | two bytes, `a` then `b` | **identical** |
| what the 12-bit field means | a **distance**, counted back from the end of the output | an **absolute position** in a 4 096-byte ring buffer |
| the field | <code>a &#124; ((b & 0x0F) << 8)</code> | <code>a &#124; ((b >> 4) << 8)</code> |
| length | `(b >> 4) + 3` | `(b & 0x0F) + 3` |
| length range | 3 – 18 | **identical** |
| window | sliding | ring, zero-filled, write position starting at `0xFEE` |
| where the stream lives | inside an `SLZ` block | the whole file, from byte 0 |
| where the sizes live | the `SLZ` header | `index.vmtoc`, one 48-byte record per file |
| what the method byte is | a codec selector, 0..3 | **two flag bits**: LZSS, and a range coder |

Two differences, then, not one — and the second is the one that matters.
tri-Crescendo's is **Okumura's `lzss.c`** unchanged: `N = 4096`, `F = 18`,
`THRESHOLD = 2`, `r = N - F = 0xFEE`, the token split exactly as published.
tri-Ace's is that routine's field layout with the nibbles the other way round
and a true sliding window in place of the ring.

So the resemblance is real but it is mostly the resemblance of **both** to the
most widely copied LZSS in existence, and tri-Ace's is the one that departs
from it. That is a weaker statement than this section used to make, and
[§2d-1](#2d-1-what-the-first-reading-got-wrong-and-why-its-tests-could-not-tell)
is why it changed.

### The method byte, which is the part that does not dissolve

`index.vmtoc` holds, per file, the uncompressed size, a Unix timestamp and a
**method byte** taking the values 0, 1, 2 and 3 — where **0 means stored, on
136 of 136 files whose stated size equals their size on disc.** That is `SLZ`'s
byte at `+0x03`, with the same range and the same meaning, moved from a block
header into a per-file table.

The meanings above 0 differ, though, and knowing that sharpens the comparison
rather than blunting it. tri-Ace's 1, 2 and 3 select **three settings of one
LZ77**. tri-Crescendo's 1, 2 and 3 are **two independent flags** — bit 0 for
the LZSS layer, bit 1 for a range coder — so its method 3 is its method 1
running on top of its method 2. Same encoding of the same decision, arrived at
differently.

That also explains, in retrospect, a negative this file used to report as a
puzzle. `btldata/voice/bos01.csf` is method 3 and must decompress to `CSF `, so
its first output byte is `C`; its first byte on disc has bit 0 clear, which
under byte-flag framing would put a back-reference at output position zero.
Correct, and the reason is that on method 3 the bytes on disc are not the LZSS
stream at all — they are the arithmetic stream the LZSS layer reads *through*.

## 2d-1. What the first reading got wrong, and why its tests could not tell

The 2007 files were first read here with tri-Ace's sliding-window decoder and
the two nibbles swapped, and reported as 8 of 8 successes. The framing,
polarity, bit order and length field were all right. **The match target was
not**: the field is a ring position, and reading it as a back-distance puts
every copy in the wrong place.

The oracle used was: the output lands on exactly the size the index states, and
the input is consumed to its last byte, on every file at once. Both halves are
**blind to where a match copies from** — a match of the right length consumes
two input bytes and produces the right number of output bytes wherever it
points. Two extra checks were run at the time and both are real, but both sit
too early in the file to help:

| Check | Where it reads | Diverges after |
| --- | --- | --- |
| a Unix timestamp matching `index.vmtoc` to the second, on 5 files | `+0x04` | — |
| the file restating its own length, on 7 of 8 | `+0x0C` | — |
| the two readings first disagreeing | | **byte 27 to 53** |

Every one of those checks lands inside the prefix where the two decodings are
identical, because that prefix is all literals. Both readings reproduce the
timestamps and the self-lengths; neither fact separates them.

Content past the first match does. `op.bmd` under the ring reading resolves
into 16-byte records with ascending offsets —

    00 00 02 88 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0
    00 00 02 b8 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0
    00 00 02 e4 | 00 00 00 05 | ff ff d8 f0 | ff ff d8 f0

— and under the window reading the same bytes interleave into nothing.

**The same test was then run in the other direction**, because a correction
that only goes one way is half a measurement, and it confirms tri-Ace really
does use a sliding window. Over 40 Star Ocean 3 method-1 blocks:

| | window | ring |
| --- | ---: | ---: |
| occurrences of `Bip01`, the 3ds Max biped prefix | **1 356** | 63 |

and only the window reading reconstructs the header word at `+0x0C` as a second
offset just past the first (`0x0F30` against `0x0F20`) rather than as `0x30`.

The general lesson is the one session 17 recorded from the other side. **A test
that counts bytes cannot check where bytes came from.** Sizes and input
consumption pin the framing and the length field, and they pin them well —
that is how tri-Ace's method 1 was found in the first place. Only a
known-plaintext or structural check reaches the distance field, and tri-Ace's
distance field was fixed that way. tri-Crescendo's was not.

### What to make of it, now

Both of tri-Crescendo's layers are well-known public routines: Okumura's LZSS
over Dmitry Subbotin's carryless range coder. Two teams reaching for those
independently is ordinary and says little. What is still not ordinary is the
**convention** — a method code of 0 to 3 with 0 meaning stored, and
four-character space-padded big-endian magics with the size behind them, and a
chunk tree inside `CSF ` that is `ASF `'s shape with different tags.

The full argument, and the layers that did *not* travel, are in
[aska-across-titles.md §13](../aska-across-titles.md#13-eternal-sonata--what-an-offshoot-studio-took-with-it).

## 3. Frames

A chunk is not one LZX bitstream, and this is the part that decides whether a
decoder works.

A chunk decodes to `0x20000` bytes. LZX produces output in **frames** of
`0x8000`, so an ordinary chunk holds four of them, laid end to end, each
introduced by a short header giving its compressed length:

```
hh ll               ordinary: 16-bit compressed length; output is 0x8000
ff  hh ll  hh ll    extended: 16-bit output length, then 16-bit compressed length
```

The extended form is what a short frame needs, so it appears as the last frame
of the last chunk — and, because the marker is `0xFF`, also whenever an
ordinary frame's compressed length would reach `0xFF00`.

This is the same framing XNB files use for LZX. It belongs to XCompress, not to
LZX: the codec has frames, but says nothing about how a container marks them.

Walking it is exact, not probabilistic. In every chunk of every block tested,
each frame header lands precisely where the previous frame's length says it
should, the walk finishes on the final byte of the chunk payload, and the frame
output lengths sum to the chunk's uncompressed size. `slz.py` treats any
departure from that as an error rather than a hint.

### What crosses a frame boundary

Only the bit reader restarts at a frame boundary. Everything else survives:
the Huffman tables, the repeated offsets R0/R1/R2, and — the one that matters —
**the current block and how much of it is left**.

Blocks are routinely longer than a frame. Instrumenting the decoder over 500
SLZ blocks — 3 636 chunks, 13 994 frames, 5 405 LZX blocks — **81 % of blocks
span more than one frame**, and a chunk averages 1.5 blocks across its roughly
four. A decoder that expects a block header at the start of each frame is
therefore reading Huffman code lengths out of the middle of coded data four
times out of five. It will resynchronise often enough to look like it nearly
works, which is the worst way for this to fail.

Of those 5 405 blocks, 5 089 are aligned-offset, 308 verbatim and 8
uncompressed, so all three block types occur and all three are exercised.

### What a chunk restarts

A chunk *is* an independent LZX stream: fresh Huffman tables, fresh repeated
offsets, and the E8 header bit read again. `LzxDecoder.reset()` marks it.

That independence is real and not merely assumed. Across those same 3 636
chunks, **no match ever referenced output from before the start of its own
chunk** — not once. Chunks can therefore be decompressed independently and in
any order, which is presumably the point of chunking the stream at all.

## 4. Window size

`window_bits = 17`, and this is not taken on trust from the header. Every other
size was tried: 15, 16, 18, 19, 20 and 21 all fail, because the window size
determines the number of position slots and therefore the size of the main
Huffman tree, so a wrong guess misparses immediately.

## 5. Two things session 3 believed that turned out not to be true

Both were artefacts of the missing frame model, and both are worth recording,
because each is a plausible reading that survives testing for a while.

**"The window is shared across chunks."** It is not — see above, no match ever
reaches back that far. The symptom that suggested it (decode chunks
independently and the third turns to noise) came from the block state being
lost, not the window.

The reason the mistake was invisible: the chunk size and the window size are
both `0x20000`. A ring buffer that wraps every `0x20000` bytes and a buffer
reset every `0x20000` bytes hold identical contents, so the two models cannot
be told apart by their output at all — only by instrumenting how far back the
matches actually reach.

**"Matches may point into the unwritten window."** Legal in LZX, and worth
supporting, but it never happens here: since no match reaches past the start of
its chunk, the zero-filled region is never read. `lzx.py` still implements it,
as the specification requires, but it is dead code on this game's data and is
no longer offered as an observation about it.

The third of session 3's findings does hold: **a block produces exactly its
declared length**, and a match that would overrun it is clipped. What changed is
the boundary that does the clipping — the block's end, not the frame's. Frames
are an output-side division the encoder cannot see, and matches cross them
freely.

## 6. Status

Over disc 1's `ud1.bin`, all 1 812 SLZ blocks:

| | Blocks |
| --- | ---: |
| Decompressed without error | **1 812** |
| Confirmed by the payload's own length | 1 066 |
| Payload declares less, and the extra bytes are real data | 6 |
| Payload has a length field but leaves it zero | 62 |
| Payload has no length field | 678 |
| Failures | **0** |

1 134 payloads carry a length field. 62 of those leave it zero, saying nothing.
Of the 1 072 that state a length, 1 066 match the decode exactly and 6 come out
short — and no payload anywhere claims to be *longer* than what was decoded,
which is the only outcome that would mean output had gone missing.

The confirmation is worth something: `ASF `, `AIF ` and `AAF ` payloads store
their own total length at offset 4, a value the compressor never touches, so
each match is a check against a number that came from somewhere else entirely.

The six "plus trailing data" cases are not failures. The stream carries more
than the one payload, and the extra bytes are coherent: three of them continue
with the ASCII string `MessageConvertLib_1.0.0.0`, a build-tool version left in
the shipped data, and the rest with arrays of plausible floats. Decoded
payloads by magic: `ASF ` 916, `AAC ` 349, `MRON` 324, `AIF ` 156, `AAF ` 62,
`-CNS` 4.

## 6a. Some blocks are stored, not compressed

A wrapper whose **compressed size equals its uncompressed size** has no
XCompress stream behind it at all: the payload is simply that many bytes
starting at `0x18`. On every other title this is what the method byte at
`0x03` says outright — see
[§2a](#2a-three-revisions-and-what-the-oldest-one-explains) — and here it has
to be inferred from the sizes, because this title writes a constant there. None of disc 1's `ud1.bin` blocks are like that, which is
why session 3 never met one, but seven of the 40 `SCE-` resources in `ud2.bin`
are — all of them under 200 bytes, where compression would not pay. A decoder
should check the two sizes before looking for the magic at `0x18`, or it will
report a corrupt block that is nothing of the kind.

## 7. Implementation

* [`tools/lzx.py`](../../tools/lzx.py) — the LZX decoder, written from the
  published algorithm. No dependencies. Stateful, and fed one frame at a time.
* [`tools/slz.py`](../../tools/slz.py) — the SLZ/XCompress container:
  `info`, `decompress`, and `verify` for bulk self-checking; `scan` for a
  PlayStation or PlayStation 2 image, which decodes all four methods.
* [`tools/disasm.py`](../../tools/disasm.py) — how §2b-2, §2b-3 and §2b-4 were
  read: `strings`, `xref`, `table` and `dis` over a `PS-X EXE` or a
  PlayStation 2 ELF.

```
python tools/slz.py info       <file> --offset N
python tools/slz.py decompress <file> --offset N out.bin
python tools/slz.py verify     <image> --csv entries.csv --base N
```
