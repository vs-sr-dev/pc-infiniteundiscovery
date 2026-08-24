# AAC — the Aska Audio Container

Every sound in the game lives in an `AAC ` container: the sound effects, the
voice acting, and the music. It is not MPEG AAC — tri-Ace's four bytes are
their own, and what is inside is Xbox Media Audio. The collision is only in the
three letters, the same situation as [`ASF `](asf.md), which is not Microsoft's
ASF either.

The name is the engine's own. The retail binary carries the debug string
`AAC version problem  BGM ID=%d`.

Everything here was measured on disc 1's `ud1.bin`: 830 non-empty `SOND`
payloads holding 22 243 sounds, all of which pass every check in
`tools/aac.py`, and 79 music tracks, all of which decode.

## 1. Where the containers are

Two places, and the second is why the music took a while to find.

**As `SOND` resources.** 1275 of them in disc 1's `ud1.bin`. 445 are unused —
sixteen zero bytes — and the other 830 are containers holding one to several
hundred sounds each: footsteps, doors, spell effects, monster voices, and the
line-by-line voice acting.

**As bare containers in the gaps between archives.** The
[census](../census.txt) used to call these regions "unclassified": two in disc
1's `ud1.bin`, 143 654 912 bytes at `0x28EBD800` and 146 067 456 at
`0x3FC44000`, and twenty-one more in `ud2.bin` totalling 135 483 392. Every one
of them is a run of `AAC ` containers laid end to end with nothing in between,
and every one is accounted for to **100.00 %** of its own length. That is where
the music is, and it is why walking `SOND` alone would never have found it.

Since a container states its own total size, a run needs no outer index — and
because these are gaps, no archive points at them either:

```
python tools/aac.py bank <image> --offset 0x8E75C000 --length 143654912
```

With the audio identified, the only gap left unaccounted for in all four
containers is the `0x16000` bytes at the start of each `ud1.bin`, which has
been open since session 1.

## 2. Layout

Big-endian throughout. A 0x30-byte header, a directory, the sounds, and a
playback table.

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | `AAC ` |
| `0x04` | 4 | Total size of the container, header included |
| `0x08` | 8 | Zero, or `0xFFFFFFFF` twice |
| `0x10` | 4 | Number of directory entries |
| `0x14` | 4 | Offset of the directory — `0x30` everywhere |
| `0x18` | 4 | Size of the directory region |
| `0x1C` | 4 | Offset of the playback table |
| `0x20` | 4 | `0x00010003`, a version, constant everywhere |
| `0x24` | 12 | Zero |

The size at `0x04` matched the file length on all 830 non-empty `SOND`
payloads, with nothing left over. It is the same self-describing length that
`ASF `, `AIF ` and `AAF ` carry at the same offset.

Chunks use the 16-byte header [ASF](asf.md) uses — tag, content size, a
reserved zero, and a step to the next sibling where the step is the content
size rounded up:

```
AAC                      the container
  DIR                    a count, then one entry per sound
    dirn                 one entry, 0xA0 bytes
  WAVE                   one sound
    strm                 the stream description
  PLBK                   one playback record per entry
```

`PLBK` is the exception: its two words after the size are not a reserved zero
and a step. In some containers they hold values that would walk straight out of
the file, so the reader advances by the stated size, which is `0x70` in all
20 755 records seen.

## 3. The directory

`DIR ` opens with the entry count repeated, then `0x10` bytes, then one `dirn`
chunk per entry, `0xA0` bytes each.

| Offset in `dirn` | Size | Field |
| --- | --- | --- |
| `0x10` | `0x80` | Name, NUL-padded |
| `0x90` | 4 | Offset of the `WAVE`, from the start of the container |
| `0x94` | 8 | Zero |
| `0x9C` | 4 | Entry id, in the high 16 bits |

The name is the original `.wav` filename the sound was built from —
`BGM_24_BATTLE_SCENE.wav`, `DOOR_001_WOOD_S_OPEN.wav`, `AYA_SP_0001.wav`. The
game therefore ships a complete, human-readable inventory of its own audio,
which is the single most useful thing about the format.

An entry whose offset is zero is an unused slot. 350 of the 22 593 entries in
disc 1's `ud1.bin` are empty that way.

## 4. The sound

| Offset in the `WAVE` body | Size | Field |
| --- | --- | --- |
| `0x00` | 4 | `0x04` in the top byte, then the entry id |
| `0x04` | 4 | `0x00010165`, a version, constant everywhere |
| `0x08` | 8 | Zero, or the constant `0x995A7C80_00000015` |
| `0x10` | 4 | Size of the audio data |
| `0x14` | 4 | Sample rate |
| `0x18` | 4 | Play begin, in samples |
| `0x1C` | 4 | Play end, in samples |
| `0x20` | 4 | `0x8000`, the block size |
| `0x24` | 4 | Total samples encoded |
| `0x28` | 4 | A second sample count, slightly smaller |
| `0x2C` | 4 | Number of blocks |

`strm` follows at `+0x50` and restates the rate and the play range, adding the
channel count as a byte at its own `+0x00`. Only 1 and 2 occur: the sound
effects and the voice acting are mono, the music is stereo.

**The audio begins `0x1000` bytes after the start of the `WAVE` chunk**, on all
22 243 sounds measured — the same 4096-byte convention `AIF ` uses for pixel
data.

The entry id at `0x00` equals the id in the entry that points at the sound, in
all 22 243 cases, so the directory and the sounds cross-check each other.

## 5. The audio is XMA2

Three numbers say so before anything is decoded:

* the block size at `0x20` is `0x8000`, which is XMA2's;
* the block count at `0x2C` is exactly `ceil(data size / 0x8000)`, on all
  22 243 sounds;
* the total at `0x24` is always a multiple of 512, the XMA frame length.

Decoding settles it. `tools/aac.py xma` copies the payload into the RIFF header
an XMA2 decoder expects — format tag `0x166`, an `XMA2WAVEFORMATEX` built
entirely from the fields above — and re-encodes nothing. Fed to ffmpeg:

* all **79 music tracks decode with no errors**, 189 minutes of audio;
* a spread sample of **411 sound effects and voice lines decodes with no
  errors**.

The decoded length is a check from outside the file, since nothing in this
repository produced it. It agrees with the count at `0x28` to within 156
samples — a third of one 512-sample frame — across every sound decoded, which
is what identifies that field as the number of samples the decoder emits.

### Sample rates are per-sound

Rates cluster around 48 kHz but are rarely exactly 48 000: 47 999, 48 128,
47 820 and 500 other values occur across the corpus. Sounds are detuned
individually, so the rate is a pitch chosen per sound rather than a constant of
the format.

### Play begin is a loop point

`0x18` is 384 in 22 159 of the 22 243 sounds. 384 is the XMA encoder's leading
delay, so those play from their first real sample.

Where it is larger, the sound loops, and the music makes the case:
`BGM_01_SIGUMUND` begins at 630 016 samples, 13.1 seconds in, and 69 of the 79
tracks carry a value like it. The ten that keep the 384 are the five flute
cues, the prologue, two of the endings, the staff roll and
`BGM_78_RAIN_OF_MOON_B` — the pieces written to run once and stop. A field that
separates the looping music from the one-shot music along exactly that line is
a loop point.

## 6. The playback table

After the last sound comes a run of `PLBK` chunks, `0x70` bytes each, one per
directory entry. 829 of the 830 `SOND` containers have exactly that; the odd
one states an offset of zero and has no table.

The music does not have one at all. Of the 209 containers in disc 1's two
`ud1.bin` music gaps, 49 state an offset of zero — the 48 music tracks, plus a
single one-sound container holding `SYSTEM_006_WARNING.wav`. Which fits: a
music track is one stream played on its own, with nothing to place in a
soundscape.

The first word repeats the entry id in its high 16 bits, which is what ties a
record to its sound. Everything after it is the same in all 20 755 records —
`800, 100, 2, 0xFF7F, -10000, 100, 50, -10000, 19, -10000, 39, 1000, 1000,
50000` — except the signed value at `+0x04`, which takes eight values across
the corpus, `0`, `-400` and `-1200` among them.

Three of those constants are `-10000`, which is the minimum volume of the Xbox
audio API in hundredths of a decibel, and `1000, 1000, 50000` reads like a pair
of 3D attenuation distances and a maximum. So the record is very likely a
mixing template with a per-sound trim at `+0x04`. **That is a reading of the
numbers and nothing more**: none of it has been checked against what the engine
does with them.

## 7. What is in there

Disc 1's `ud1.bin` alone holds 22 243 sounds. The names group them: `EV_` event
audio, `SYSTEM_` interface, `DOOR_`, `GMK_` gimmicks, `NPC_`, and per-character
banks — `AYA_`, `CAPEL_`, `EDARUD_`, `SIGUMUND_` — running to `_Situ_057_` and
beyond, which is the situational battle chatter the game is known for.

The music comes to **79 tracks and 189 minutes**, in four places:

| Where | Tracks | Contents |
| --- | --- | --- |
| `ud1.bin` gap at `0x28EBD800` | 38 | Character and mood themes, the flute cues, the movie music |
| `ud1.bin` gap at `0x3FC44000` | 10 | Battle and boss themes, followed by 3 663 voice lines |
| `ud2.bin`, 21 gaps | 30 | Area, town, castle and dungeon themes |
| Disc 2 `ud1.bin` gap at `0x7AC1A800` | 1 | `BGM_62_DUNGEON_07`, which disc 1 does not carry |

Those offsets are relative to the container, as the [census](../census.txt)
reports them; the commands below take offsets into the disc image, which are
the container base plus these.

Five numbers in the sequence — 35, 45, 46, 55 and 74 — never appear on either
disc.

Disc 2 carries the same two `ud1.bin` banks as disc 1, byte for byte the same
sizes, plus the one extra track. That is consistent with each disc having to be
playable on its own.

## 8. Reproducing

```
# The music, walked in place inside the disc image
python tools/aac.py bank "disc1.iso" --offset 0x8E75C000 --length 143654912
python tools/aac.py info "disc1.iso" --offset 0x8E75C000 --length 3842048

# One track out as RIFF-wrapped XMA2, then to PCM
python tools/aac.py xma "disc1.iso" out/ --offset 0x8E75C000 --length 3842048
ffmpeg -i out/000_BGM_01_SIGUMUND.xma track.wav

# Sound effects and voice, from the resource containers
python tools/mron.py extract "disc1.iso" --offset 1703536640 --length 2207584256 \
    --tag SOND --decompress extract/sound
python tools/aac.py verify extract/sound/*.bin
python tools/aac.py wav extract/sound/317BD800_029_SOND.bin out/

# The area music: 21 gaps in ud2.bin, each its own run of containers
python tools/aac.py bank "disc1.iso" --offset 0x1036BF800 --length 20414464

# Containers anywhere in a region, for when they are not laid end to end
python tools/aac.py find "disc1.iso" --offset 0xE99D0000 --length 2800330752
```

## 9. What is not known

* The eight-byte field at `WAVE +0x08`, zero in most sounds and the constant
  `0x995A7C80_00000015` in 2404 of them.
* What `+0x24` counts exactly. It is always a multiple of 512 and always at
  least the play end, exceeding it by less than 640 samples in all but six
  sounds, but no reading has been pinned down.
* The two words inside a `PLBK` header that are not a step, and what the
  engine does with the record.
* Whether the missing track numbers were cut or live somewhere not yet walked.
