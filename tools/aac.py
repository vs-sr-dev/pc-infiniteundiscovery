#!/usr/bin/env python3
"""
aac.py -- reader for AAC, the Aska Audio Container.

`AAC ` is what every `SOND` resource is, and it is also what every gap the
census used to call "unclassified" turns out to hold: the music. Nothing
here is MPEG AAC. tri-Ace's four bytes are their own, the payload inside is
Xbox Media Audio, and the collision is only in the three letters -- the same
situation as `ASF `, which is not Microsoft's ASF either.

The engine's own name for the format is visible in the retail binary, in the
debug string `AAC version problem  BGM ID=%d`.

Layout
------
A container is a 0x30-byte header, a directory, and then the audio, all
big-endian:

    +0x00  4  `AAC `
    +0x04  4  total size of the container, header included
    +0x10  4  number of directory entries
    +0x14  4  offset of the directory, 0x30 in everything seen
    +0x18  4  size of the directory region
    +0x1C  4  offset of the playback table, past the last sound
    +0x20  4  0x00010003, a version, constant everywhere

The size at +0x04 is exact -- it matched the file length on all 830 non-empty
`SOND` payloads of disc 1's `ud1.bin` -- so a container can be walked out of a
raw byte run without any outer index. That is what `bank` does.

Chunks use the same 16-byte header as ASF: tag, content size, a reserved zero,
and a step to the next sibling where the step is the content size rounded up.

    AAC                      the container
      DIR                    the directory: a count, then one entry per sound
        dirn                 one entry, 0xA0 bytes: name, offset, id
      WAVE                   one sound: format, then 0x1000 bytes in, the data
        strm                 stream description, duplicating part of WAVE
      PLBK                   one playback record per entry, 0x70 bytes

A `dirn` entry carries a NUL-padded name of up to 0x80 bytes -- the original
`.wav` filename, `BGM_24_BATTLE_SCENE.wav` or `DOOR_001_WOOD_S_OPEN.wav` --
then at +0x80 the offset of its `WAVE` inside the container, and at +0x8C an
id in the high 16 bits. An entry whose offset is zero is an unused slot; 350
of the 22 593 entries in disc 1's `ud1.bin` are empty that way.

The WAVE body
-------------
    +0x00  4  0x04 in the top byte, then the entry's own id
    +0x04  4  0x00010165, a version, constant everywhere
    +0x08  8  zero, or the constant 0x995A7C80_00000015; unexplained
    +0x10  4  size of the audio data
    +0x14  4  sample rate
    +0x18  4  play begin, in samples
    +0x1C  4  play end, in samples
    +0x20  4  0x8000, the block size
    +0x24  4  total samples encoded
    +0x28  4  a second sample count, slightly smaller
    +0x2C  4  number of blocks

`strm` restates the rate and the play range, and adds the channel count as a
byte at its own +0x00. The audio itself begins 0x1000 bytes after the start of
the `WAVE` chunk, always -- true for all 22 243 sounds measured.

The playback table
------------------
After the last sound comes a run of `PLBK` chunks, 0x70 bytes each, one per
directory entry -- 829 of the 830 containers have exactly that, and the odd one
states an offset of zero and has no table at all. The first word repeats the
entry's id in its high 16 bits, which is what ties a record to its sound.

Almost everything else in a record is the same in all 20 755 of them: 800, 100,
2, 0xFF7F, -10000, 100, 50, -10000, 19, -10000, 39, 1000, 1000, 50000. Only the
signed value at +0x04 varies with the sound, taking eight values -- 0, -400 and
-1200 among them. Three of the constants are -10000, which is the minimum
volume of the Xbox audio API in hundredths of a decibel, so the record is very
likely a mixing and 3D-attenuation template with a per-sound trim at +0x04.
That is a reading of the numbers, not a decode: nothing here has been checked
against what the engine does with them.

What the audio is
-----------------
XMA2, the Xbox 360's own codec. Three numbers say so before anything is
decoded: the block size is 0x8000, which is XMA2's, the block count at +0x2C is
exactly `ceil(data size / 0x8000)` in every sound measured, and the total at
+0x24 is always a multiple of 512, the XMA frame length. Decoding then confirms
it -- `xma` wraps a sound in the RIFF header a decoder expects, and ffmpeg
reads them back as music.

Rates cluster around 48 kHz but are not exactly 48 000: 47 999, 48 128, 47 820
and 500 other values occur. Sounds are detuned individually, so the rate is a
per-sound pitch rather than a constant of the format.

Play begin is 384 in 22 159 of the 22 243 sounds, which is the XMA encoder's
leading delay, so those play from their first real sample. The ones where it is
larger are the looping music: `BGM_01_SIGUMUND` begins its loop 630 016 samples
in, 13.1 seconds, and the tracks written to run once -- the prologue, the two
endings, the staff roll -- are exactly the ones that keep the 384.

Usage
-----
    python tools/aac.py info   <file.aac>
    python tools/aac.py xma    <file.aac> <outdir>
    python tools/aac.py wav    <file.aac> <outdir>           [needs ffmpeg]
    python tools/aac.py bank   <image> --offset N --length N [--extract dir]
    python tools/aac.py find   <image> --offset N --length N [--extract dir]
    python tools/aac.py verify <file.aac> [...]

`--offset` and `--length` work on every command, so a container can be read in
place inside a disc image without extracting anything first.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys

MAGIC = b"AAC "
HEADER = 0x30
CHUNK = 16
ENTRY = 0xA0
NAME_MAX = 0x80

# The audio of a WAVE begins this far after the chunk starts, always.
DATA_OFFSET = 0x1000

# XMA constants the header agrees with everywhere.
XMA_BLOCK = 0x8000
XMA_FRAME_SAMPLES = 512
XMA_ENCODER_DELAY = 384

# The version every container states at +0x20.
VERSION = 0x00010003

# Speaker masks for the RIFF wrapper: front centre, then front left + right.
SPEAKERS = {1: 0x4, 2: 0x3}


class AacError(Exception):
    pass


class Wave:
    """One sound: an XMA2 stream and the format that describes it."""

    def __init__(self, blob, offset):
        if blob[offset:offset + 4] != b"WAVE":
            raise AacError("no WAVE chunk at 0x%X (found %r)"
                           % (offset, bytes(blob[offset:offset + 4])))
        self.blob = blob
        self.offset = offset
        self.size, _reserved, step = struct.unpack_from(">III", blob, offset + 4)
        self.step = step or self.size
        (ident, self.version, self._a, self._b, self.data_size, self.rate,
         self.play_begin, self.play_end, self.block_size, self.total_samples,
         self.other_samples, self.block_count) = struct.unpack_from(
            ">12I", blob, offset + CHUNK)
        self.kind = ident >> 24
        self.ident = ident & 0xFFFFFF
        self.channels = 0
        if blob[offset + 0x50:offset + 0x54] == b"strm":
            self.channels = blob[offset + 0x60]

    @property
    def data_offset(self):
        return self.offset + DATA_OFFSET

    @property
    def data(self):
        return bytes(self.blob[self.data_offset:self.data_offset + self.data_size])

    @property
    def seconds(self):
        return self.play_end / self.rate if self.rate else 0.0

    @property
    def loops(self):
        """Does the play range begin past the encoder delay?"""
        return self.play_begin > XMA_ENCODER_DELAY

    def problems(self):
        """Everything about this sound that does not hold together."""
        bad = []
        if self.size - self.data_size != DATA_OFFSET:
            bad.append("audio does not start 0x1000 into the chunk")
        if self.block_size != XMA_BLOCK:
            bad.append("block size is 0x%X, not 0x8000" % self.block_size)
        if self.block_count != -(-self.data_size // (self.block_size or 1)):
            bad.append("block count %d does not match the data size" % self.block_count)
        if self.total_samples % XMA_FRAME_SAMPLES:
            bad.append("total samples %d is not a multiple of 512" % self.total_samples)
        if self.play_begin > self.play_end:
            bad.append("the play range runs backwards")
        if self.channels not in SPEAKERS:
            bad.append("channel count %d is neither mono nor stereo" % self.channels)
        # The step is the content size rounded up to 4096, so on the last
        # sound of a container that does not end on a boundary it points past
        # the file. What has to fit is the audio, not the rounding.
        if self.data_offset + self.data_size > len(self.blob):
            bad.append("audio runs past the end of the container")
        return bad

    def riff(self):
        """The sound wrapped in the RIFF header an XMA2 decoder expects.

        Nothing is re-encoded: the payload is copied through untouched, and
        every number in the wrapper comes from the WAVE chunk.
        """
        data = self.data
        streams = (self.channels + 1) // 2
        extra = struct.pack(
            "<HIIIIIIIBBH", streams, SPEAKERS.get(self.channels, 0),
            self.play_end, self.block_size, 0, self.play_end, 0, 0,
            0, 4, self.block_count)
        fmt = struct.pack("<HHIIHHH", 0x166, self.channels, self.rate,
                          self.rate * self.channels * 2, self.channels * 2,
                          16, len(extra)) + extra
        return (b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data))
                + b"WAVE"
                + b"fmt " + struct.pack("<I", len(fmt)) + fmt
                + b"data" + struct.pack("<I", len(data)) + data)


class Entry:
    """One `dirn`: a name, and the sound it points at."""

    def __init__(self, blob, offset, base):
        self.offset = offset
        raw = bytes(blob[offset + 0x10:offset + 0x10 + NAME_MAX]).split(b"\0")[0]
        self.name = raw.decode("latin-1")
        self.wave_offset, _, _, ident = struct.unpack_from(">4I", blob, offset + 0x90)
        self.ident = ident >> 16
        self.wave = None
        at = base + self.wave_offset
        if self.wave_offset and blob[at:at + 4] == b"WAVE":
            self.wave = Wave(blob, at)

    @property
    def empty(self):
        return self.wave is None


class Playback:
    """One `PLBK`: how a sound is to be mixed, as far as can be told."""

    SIZE = 0x70
    # Everything a record holds after its id, in order. All of it is constant
    # across the 20 755 records measured except `trim`.
    FIELDS = ("trim", "_08", "_0c", "_10", "_14", "_18", "_1c", "_20", "flags",
              "_28", "_2c", "_30", "_34", "_38", "_3c", "_40", "_44", "_48",
              "_4c", "_50", "_54", "_58", "_5c")

    def __init__(self, blob, offset):
        self.offset = offset
        # Only the size is dependable here. Unlike every other chunk in the
        # format, the two words after it are not a reserved zero and a step:
        # in some containers they hold values that would walk straight out of
        # the file, so the walk advances by the size instead.
        self.size, self._08, self._0c = struct.unpack_from(">III", blob, offset + 4)
        values = struct.unpack_from(">24i", blob, offset + CHUNK)
        self.ident = (values[0] >> 16) & 0xFFFF
        for name, value in zip(self.FIELDS, values[1:]):
            setattr(self, name, value)


class Bank:
    """One `AAC ` container."""

    def __init__(self, blob, base=0):
        if blob[base:base + 4] != MAGIC:
            raise AacError("no `AAC ` magic at 0x%X (found %r)"
                           % (base, bytes(blob[base:base + 4])))
        self.blob = blob
        self.base = base
        (self.total_size, _, _, self.count, self.dir_offset, self.dir_size,
         self.playback_offset, self.version) = struct.unpack_from(
            ">8I", blob, base + 4)
        first = base + self.dir_offset + CHUNK + 0x10
        self.entries = [Entry(blob, first + i * ENTRY, base)
                        for i in range(self.count)]
        self.playback = self._read_playback()

    def _read_playback(self):
        """The run of `PLBK` records the header points at, if there is one."""
        records = []
        pos = self.base + self.playback_offset
        if not self.playback_offset:
            return records
        while pos + Playback.SIZE <= len(self.blob) and \
                self.blob[pos:pos + 4] == b"PLBK":
            record = Playback(self.blob, pos)
            records.append(record)
            pos += record.size or Playback.SIZE
        return records

    @property
    def waves(self):
        return [e.wave for e in self.entries if e.wave is not None]

    def problems(self, declared_length=None):
        bad = []
        if declared_length is not None and self.total_size != declared_length:
            bad.append("states 0x%X bytes but the file holds 0x%X"
                       % (self.total_size, declared_length))
        if self.dir_offset != HEADER:
            bad.append("directory sits at 0x%X, not 0x30" % self.dir_offset)
        at = self.base + self.dir_offset
        if self.blob[at:at + 4] != b"DIR ":
            bad.append("no DIR chunk where the header says")
        else:
            stated = struct.unpack_from(">I", self.blob, at + CHUNK)[0]
            if stated != self.count:
                bad.append("DIR counts %d entries, the header %d"
                           % (stated, self.count))
        if self.playback_offset:
            at = self.base + self.playback_offset
            if self.blob[at:at + 4] != b"PLBK":
                bad.append("the playback table is not where the header says")
            elif len(self.playback) != self.count:
                bad.append("%d playback records for %d entries"
                           % (len(self.playback), self.count))
        for entry in self.entries:
            if entry.wave_offset and entry.wave is None:
                bad.append("%s points at 0x%X, which is not a WAVE"
                           % (entry.name or "<unnamed>", entry.wave_offset))
            elif entry.wave is not None:
                if entry.wave.ident != entry.ident:
                    bad.append("%s: id %d in the directory, %d in the WAVE"
                               % (entry.name, entry.ident, entry.wave.ident))
                bad += ["%s: %s" % (entry.name, p) for p in entry.wave.problems()]
        return bad


def read(path, offset=0, length=None):
    with open(path, "rb") as fi:
        fi.seek(offset)
        return fi.read(length if length is not None else -1)


def load(path, offset=0, length=None):
    blob = read(path, offset, length)
    return Bank(blob), len(blob)


def walk_bank(blob):
    """Yield the containers laid end to end in a raw byte run.

    Each one states its own size, so no outer index is needed; the walk stops
    at the first thing that is not a container, which is how a run ends.
    """
    pos = 0
    while pos + HEADER <= len(blob):
        if blob[pos:pos + 4] != MAGIC:
            return
        size = struct.unpack_from(">I", blob, pos + 4)[0]
        if size < HEADER or pos + size > len(blob):
            return
        yield pos, Bank(blob, pos)
        pos += size


def looks_like_bank(blob, pos):
    """Is there a plausible container header at `pos`?

    The magic alone is four bytes and turns up by accident, so a candidate has
    to state the directory at 0x30, carry the version every container carries,
    and give a size that fits and is not absurd.
    """
    if blob[pos:pos + 4] != MAGIC or pos + HEADER > len(blob):
        return False
    size, _, _, count, dir_offset, _, _, version = struct.unpack_from(
        ">8I", blob, pos + 4)
    return (dir_offset == HEADER and version == VERSION
            and HEADER < size <= len(blob) - pos and 0 < count < 0x10000)


def find_banks(blob, step=16):
    """Yield every container in a byte run, wherever it starts.

    `bank` walks containers that are laid end to end, which is how the music
    banks in the gaps are stored; this finds them when something else shares
    the region, as happens inside the archives.
    """
    pos = 0
    while True:
        pos = blob.find(MAGIC, pos)
        if pos < 0:
            return
        if pos % step == 0 and looks_like_bank(blob, pos):
            bank = Bank(blob, pos)
            yield pos, bank
            pos += bank.total_size
        else:
            pos += 4


def _describe(wave):
    if wave is None:
        return "empty slot"
    loop = ""
    if wave.loops and wave.rate:
        loop = "  loop from %.2f s" % (wave.play_begin / wave.rate)
    return ("%s %5d Hz  %8.3f s  %4d block%s%s"
            % ("stereo" if wave.channels == 2 else "mono  ", wave.rate,
               wave.seconds, wave.block_count,
               " " if wave.block_count == 1 else "s", loop))


def cmd_info(args):
    bank, length = load(args.file, args.offset, args.length)
    whole = not args.offset and args.length is None
    bad = bank.problems(length if whole else None)
    print("size    : %d bytes%s"
          % (bank.total_size,
             "" if bank.total_size == length else " (the file holds %d)" % length))
    print("version : 0x%08X" % bank.version)
    print("entries : %d, %d empty"
          % (bank.count, sum(1 for e in bank.entries if e.empty)))
    waves = bank.waves
    if waves:
        print("audio   : %d sounds, %.1f s, %d looping, %s"
              % (len(waves), sum(w.seconds for w in waves),
                 sum(1 for w in waves if w.loops),
                 "stereo" if any(w.channels == 2 for w in waves) else "mono"))
    trims = sorted({r.trim for r in bank.playback})
    print("playback: %d records%s"
          % (len(bank.playback),
             ", trim %s" % ", ".join(str(t) for t in trims[:6]) if trims else ""))
    for entry in bank.entries[:args.limit]:
        print("  %-40s %s" % (entry.name or "<unnamed>", _describe(entry.wave)))
    if len(bank.entries) > args.limit:
        print("  ... %d more" % (len(bank.entries) - args.limit))
    print("checks  : %s" % ("all pass" if not bad else "%d FAILED" % len(bad)))
    for line in bad[:10]:
        print("  ! %s" % line)
    return 1 if bad else 0


def _outname(entry, index, suffix):
    stem = entry.name[:-4] if entry.name.lower().endswith(".wav") else entry.name
    keep = ("abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    stem = "".join(c if c in keep else "_" for c in stem).strip("_")
    return "%03d_%s%s" % (index, stem or "sound", suffix)


def cmd_xma(args):
    bank, _ = load(args.file, args.offset, args.length)
    if not os.path.isdir(args.outdir):
        os.makedirs(args.outdir)
    written = 0
    for index, entry in enumerate(bank.entries):
        if entry.wave is None:
            continue
        path = os.path.join(args.outdir, _outname(entry, index, ".xma"))
        with open(path, "wb") as fo:
            fo.write(entry.wave.riff())
        written += 1
    print("wrote %d sounds to %s" % (written, args.outdir))
    print("each is RIFF-wrapped XMA2, the payload copied through untouched:")
    print("   ffmpeg -i <file>.xma <file>.wav")
    return 0


def cmd_wav(args):
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise AacError("ffmpeg is not on PATH; `xma` writes files it can read")
    bank, _ = load(args.file, args.offset, args.length)
    if not os.path.isdir(args.outdir):
        os.makedirs(args.outdir)
    written = failed = 0
    for index, entry in enumerate(bank.entries):
        if entry.wave is None:
            continue
        path = os.path.join(args.outdir, _outname(entry, index, ".wav"))
        proc = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", "pipe:0", path],
            input=entry.wave.riff(), capture_output=True)
        if proc.returncode:
            failed += 1
            if failed <= 3:
                print("  ! %s: %s"
                      % (entry.name, proc.stderr.decode("latin-1").strip()[:120]))
        else:
            written += 1
    print("decoded %d sounds to %s%s"
          % (written, args.outdir, ", %d FAILED" % failed if failed else ""))
    return 1 if failed else 0


def _report(args, blob, found):
    total = covered = sounds = 0
    seconds = 0.0
    if args.extract and not os.path.isdir(args.extract):
        os.makedirs(args.extract)
    for pos, bank in found:
        waves = bank.waves
        first = next((e.name for e in bank.entries if e.name), "<unnamed>")
        seconds += sum(w.seconds for w in waves)
        sounds += len(waves)
        total += 1
        covered = pos + bank.total_size
        if total <= args.limit:
            print("  +0x%08X  %9d bytes  %3d sound%s  %s"
                  % (pos, bank.total_size, len(waves),
                     " " if len(waves) == 1 else "s", first))
        if args.extract:
            stem = os.path.splitext(first)[0]
            keep = ("abcdefghijklmnopqrstuvwxyz"
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
            stem = "".join(c if c in keep else "_" for c in stem).strip("_")
            path = os.path.join(args.extract,
                                "%03d_%s.aac" % (total, stem or "bank"))
            with open(path, "wb") as fo:
                fo.write(blob[pos:pos + bank.total_size])
    if total > args.limit:
        print("  ... %d more" % (total - args.limit))
    print("containers %d, %d sounds, %.1f minutes" % (total, sounds, seconds / 60))
    print("covered 0x%X of 0x%X bytes (%.1f%%)"
          % (covered, len(blob), 100.0 * covered / max(len(blob), 1)))
    if args.extract:
        print("wrote %d containers to %s" % (total, args.extract))
    return 0


def cmd_bank(args):
    blob = read(args.file, args.offset, args.length)
    return _report(args, blob, walk_bank(blob))


def cmd_find(args):
    blob = read(args.file, args.offset, args.length)
    return _report(args, blob, find_banks(blob, args.align))


def cmd_verify(args):
    failures = files = sounds = empty = 0
    for path in args.files:
        if os.path.getsize(path) <= CHUNK:
            empty += 1  # an unused SOND resource: sixteen zero bytes
            continue
        bank = None
        try:
            bank, length = load(path, args.offset, args.length)
            bad = bank.problems(length)
        except AacError as exc:
            bad = [str(exc)]
        files += 1
        sounds += len(bank.waves) if bank is not None else 0
        if bad:
            failures += 1
            print("%s: %d problem%s" % (os.path.basename(path), len(bad),
                                        "" if len(bad) == 1 else "s"))
            for line in bad[:5]:
                print("   %s" % line)
    print("%d containers, %d sounds, %d empty resources, %d with problems"
          % (files, sounds, empty, failures))
    return 1 if failures else 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Reader for AAC, the Aska Audio Container.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def region(parser):
        parser.add_argument("--offset", type=lambda s: int(s, 0), default=0,
                            help="byte offset of the container inside the file")
        parser.add_argument("--length", type=lambda s: int(s, 0), default=None,
                            help="bytes to read from that offset")

    s = sub.add_parser("info", help="header, entry table and self-checks")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=40, help="entries to list")
    region(s)
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("xma", help="write each sound as RIFF-wrapped XMA2")
    s.add_argument("file")
    s.add_argument("outdir")
    region(s)
    s.set_defaults(func=cmd_xma)

    s = sub.add_parser("wav", help="decode each sound to PCM WAV, using ffmpeg")
    s.add_argument("file")
    s.add_argument("outdir")
    region(s)
    s.set_defaults(func=cmd_wav)

    s = sub.add_parser("bank", help="walk a run of containers laid end to end")
    s.add_argument("file")
    s.add_argument("--extract", help="write each container out as a .aac file")
    s.add_argument("--limit", type=int, default=80, help="containers to list")
    region(s)
    s.set_defaults(func=cmd_bank)

    s = sub.add_parser("find", help="find containers anywhere in a byte run")
    s.add_argument("file")
    s.add_argument("--extract", help="write each container out as a .aac file")
    s.add_argument("--limit", type=int, default=80, help="containers to list")
    s.add_argument("--align", type=lambda v: int(v, 0), default=16,
                   help="only consider offsets that are a multiple of this")
    region(s)
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("verify", help="check the invariants over many containers")
    s.add_argument("files", nargs="+")
    region(s)
    s.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except AacError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
