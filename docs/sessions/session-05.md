# Session 5 — the audio, and the music that was hiding in the gaps

**Date:** 2026-08-24
**Goal:** none of the open questions. The question asked was whether the music
would come out by following the [TODO](../../TODO.md), and it would not: no
item on that list touches audio. So this session pivoted deliberately.

## Outcome

`AAC `, the Aska Audio Container, is readable end to end. The payload inside is
XMA2, which means every sound in the game decodes with a standard decoder and
nothing had to be reverse engineered about the codec itself.

Two results are worth stating separately.

**Everything is named.** The container carries the original `.wav` filenames —
`BGM_24_BATTLE_SCENE.wav`, `DOOR_001_WOOD_S_OPEN.wav`, `AYA_SP_0001.wav` — so
the game ships a complete, human-readable inventory of its own audio.

**The music is not in an archive.** It sits in the regions the
[census](../census.txt) had been calling "unclassified" — 289 MB of disc 1's
`ud1.bin` and another 135 MB of its `ud2.bin`, in the gaps between archives —
as bare containers laid end to end. Every one of those gaps is covered to
100.00 % that way. That is why walking `SOND` alone would never have found it,
and it settles the census: with the audio identified, the only gap left
unaccounted for in all four containers is the `0x16000` bytes at the start of
each `ud1.bin`, open since session 1.

## How it went

The starting point was one line from [session 3](session-03.md): `SOND`
payloads begin `AAC `, matched to the executable's debug string `AAC version
problem  BGM ID=%d`. Nothing had been done with it since.

Pulling all 1275 `SOND` payloads out of disc 1's `ud1.bin` gave a corpus to
measure against. 445 are unused — sixteen zero bytes each — and the other 830
are containers. Their chunk header is the one [ASF](../formats/asf.md) uses, so
the tree fell out immediately: `DIR ` holding one `dirn` per sound, then the
`WAVE` chunks, then something at the end that turned out to be a playback
table. The audio of a `WAVE` begins `0x1000` bytes in, the same 4096-byte
convention `AIF ` uses for pixel data.

### Finding the music

Scanning the whole container region for `.wav` names turned up 101 name
prefixes, and one of them was `BGM`, 48 times — but none of those names were in
any `SOND` payload. Their offsets fell inside the two unclassified gaps.

Both gaps parse as runs of containers with nothing in between, exactly, to the
last byte. The area and dungeon themes sit the same way in `ud2.bin`, spread
across 21 separate gaps that hold 30 containers between them and cover
135 483 392 bytes with no residue.

That last part took a wrong turn worth recording. A first pass used a container
offset 128 KB off the one [disc-layout.md](../disc-layout.md) documents, which
shifted every gap and made `ud2.bin` look like it began with data that was not
audio. It was the regenerated census, run with the documented offset, that
showed all 21 gaps for what they are. The `find` subcommand written to work
around the imagined problem stayed, since containers do also turn up inside
archives.

The full picture is 79 tracks and 189 minutes:

| Where | Tracks |
| --- | --- |
| Disc 1 `ud1.bin` gap at `0x28EBD800` | 38 — character and mood themes, flute cues, movie music |
| Disc 1 `ud1.bin` gap at `0x3FC44000` | 10 — battle and boss themes, ahead of the voice banks |
| Disc 1 `ud2.bin`, 21 gaps | 30 — area, town, castle and dungeon themes |
| Disc 2 `ud1.bin` gap at `0x7AC1A800` | 1 — `BGM_62_DUNGEON_07`, which disc 1 does not carry |

Disc 2 was checked as well, and carries the same two banks as disc 1 at the
same sizes, plus that one extra track. Five numbers in the sequence — 35, 45,
46, 55, 74 — appear on neither disc.

### Establishing the codec

Three numbers in the `WAVE` header say XMA2 before anything is decoded: the
block size is `0x8000`, the block count is exactly `ceil(data size / 0x8000)`
on all 22 243 sounds, and the total sample count is always a multiple of 512,
the XMA frame length.

The proof is the decode. `aac.py xma` copies the payload into the RIFF header
an XMA2 decoder expects, re-encoding nothing and taking every field from the
`WAVE` chunk. Through ffmpeg:

* **79 of 79 music tracks decode with no errors**, 189 minutes;
* **411 of 411 sampled sound effects and voice lines decode with no errors**.

The decoded length is a measurement from outside the file. It agrees with the
count at `WAVE +0x28` to within 156 samples — a third of one frame — on every
sound decoded, which is what identifies that field.

### Two fields worth the space

**Sample rates are per-sound.** 506 distinct values across the corpus, clustered
around 48 kHz but rarely exactly 48 000: 47 999, 48 128, 47 820. Sounds are
detuned individually.

**Play begin is a loop point.** It is 384 — the XMA encoder's leading delay —
in 22 159 of the 22 243 sounds. Where it is larger, the sound loops, and the
music makes the case cleanly: 69 of the 79 tracks carry a real value, and the
ten that keep the 384 are the five flute cues, the prologue, two of the
endings, the staff roll and `BGM_78_RAIN_OF_MOON_B`. A field that splits
looping music from one-shot music along exactly that line is a loop point.

## Verification

* All 830 non-empty `SOND` containers of disc 1's `ud1.bin` pass every check in
  `aac.py verify`: stated size against file length, directory count against the
  `DIR ` chunk, every entry offset landing on a `WAVE`, ids agreeing between
  the directory and the sound, the audio starting `0x1000` in, block count
  against data size, total samples a multiple of 512, one playback record per
  entry. 22 243 sounds, 0 problems.
* All 23 audio gaps across `ud1.bin` and `ud2.bin`: 100.00 % covered by
  containers, no residue.
* 490 sounds decoded through ffmpeg, 0 failures.

One check had to be relaxed, and it is worth recording why. A `WAVE` states a
step that is its content size rounded up to 4096, so on the last sound of a
container that does not end on a boundary the step points past the file. The
audio still fits; the rounding does not. Sixteen containers failed on that
before the check was corrected to test the data rather than the padding.

## Tools

* `tools/aac.py` — new. Container tree, entry table with rates, durations and
  loop points, RIFF-XMA2 export, PCM decode through ffmpeg where it is
  installed, a walker for runs of containers, a finder for containers sitting
  among other data, and a bulk verifier.

## Left open

1. The eight-byte field at `WAVE +0x08`, zero in most sounds and the constant
   `0x995A7C80_00000015` in 2404 of them.
2. What `+0x24` counts exactly. Always a multiple of 512, always at least the
   play end, exceeding it by under 640 samples in all but six sounds.
3. The `PLBK` record. Its shape is known and its id ties it to a sound, but
   only one of its 23 values varies, nothing has been checked against what the
   engine does with them, and the music carries no table at all.
4. Whether the five missing track numbers were cut or live somewhere not yet
   walked.
