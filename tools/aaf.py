#!/usr/bin/env python3
"""
aaf.py -- reader for AAF, the Aska Animation File.

Every `ANIM` resource is an `AAF ` payload, and there are more of them than of
anything else on the disc: 5 718 in disc 1's `ud1.bin`, 278 MB in all. An AAF
animates the node tree of an ASF -- its records are named after `attr` nodes,
and its channels write the same translation, rotation and scale those nodes
carry as a rest pose.

Layout
------
A 0x24-byte header, big-endian throughout:

    +0x00  4  'AAF '
    +0x04  4  total length             (zero in every file seen)
    +0x10  4  version, 0x16 everywhere
    +0x14  2  record count
    +0x16  2  duration, in the same units as a keyframe time
    +0x18  2  zero, or 0x0001 in some files
    +0x1A  2  animated track count
    +0x1C  2  constant track count
    +0x1E  2  keyframe block count
    +0x20  4  unidentified

Then four regions, laid end to end with nothing between them:

    records          one per animated node, `record count` of them
    block table      one (offset, time) pair per keyframe block
    constant curves  the value of every track that never changes
    keyframe blocks  one per entry in the block table

A record is a 0x28-byte header -- track count at +0x02, record size at +0x04,
then a 0x20-byte NUL-padded name -- followed by its tracks, which tile the rest
of it exactly. Counts and sizes sit in the low half of a 32-bit slot; most
files leave the high half zero, and enough do not that reading the whole word
walks off the end of a record.

A track is 0x14 bytes, plus 0x10 more when it is animated:

    +0x00  2  zero, or 0x0200 on a handful of tracks
    +0x02  2  track size
    +0x04  2  flags: 0x20 keys in the blocks, 0x80 a constant curve, 0x400 a
              packed quaternion with no tangent; a few tracks carry neither of
              the first two and are self-contained
    +0x06  2  0x000C in every track in the corpus
    +0x08  4  target: 0x40 a scalar slot, 0x70 a three-float slot, 0x80 a
              quaternion slot -- it follows the storage form, not the channel
    +0x0C  2  channel: 5 translation, 6 rotation, 7 scale (see below)
    +0x0E  2  usually zero
    +0x10  4  key format: [is-animated, layout, semantic, 0]
    +0x14 16  animated tracks only: three floats and a count

The last word of an animated track is the number of keyframe blocks the track
appears in -- which it is for all 4 931 animated tracks in the corpus.

Constant curves
---------------
The region opens with its own total size as a `u16`, then one `u16` offset per
constant track, in the order the tracks appear. The offsets are counted from
two bytes into the region, i.e. from just past that size word, and the data
they point at follows the offset array. The region size lands exactly on the
first keyframe block.

Keyframe blocks
---------------
Each block is a count, then that many `(u16 track, u16 offset)` pairs, then the
key data. The track number indexes the file's animated tracks in order; the
offset is from the start of the block; a key's length runs to the next offset,
or to the end of the block for the last one -- so the last key in a block also
carries whatever padding aligns the next block.

A block is one instant. A track present in the block has one key there.

Key layouts
-----------
The byte at `+0x11` of a track picks the layout, and it decides the key size:

    0  one float + two tangents                  12 B
    1  one float                                  4 B
    2  one float                                  4 B
    5  three floats + two tangents               36 B    <- translation, scale
    6  three floats                              12 B
    7  three floats                              12 B
    8  four floats + two tangents                48 B
    9  four floats                               16 B
    10 four floats                               16 B
    12 a packed quaternion                        8 B
    13 a packed quaternion, and a tangent        16 B    <- 8 B when 0x400 set

Where a layout stores tangents, the key is value, in-tangent, out-tangent, and
the two tangents are equal wherever the curve is smooth. The outgoing tangent
is as long as the step from this key's value to the next -- median ratio 0.988
over 60 210 keys -- and points along the line through the keys either side,
within 5 degrees half the time. That is a Maya smooth tangent, scaled to the
segment it opens; `check` measures both halves of it.

The packed quaternion
---------------------
Eight bytes, of which the top sixteen are always zero, leaving a 48-bit word
holding the rotation in axis-and-angle form. Three fields, and each of them is
an angle quantised the same way -- as a fraction of a right angle:

    bits  0..13   the axis' angle away from the Y axis, 16383 = 90 degrees
    bits 14..27   the angle of the axis' xz part away from the X axis
    bits 28..30   the signs of z, y and x, one bit each, set means negative
    bits 31..47   the rotation itself: w = 1 - (field / 131071)^2

So the axis is |y| = cos(a), |x| = sin(a)cos(b), |z| = sin(a)sin(b) with the
three sign bits applied, and the quaternion is (axis * sqrt(1 - w*w), w). The
angle field is the odd one: squaring it spends the precision near w = 1, which
is where small rotations live and where a fixed-point quaternion normally goes
wrong.

Comparing a node's constant channels against the rest pose the matching ASF
stores is a check on numbers this reader did not produce -- and it is what
identifies the channels in the first place: channel 5 lands on the ASF node's
translation at `attr +0x50` (61 805 of 62 104), channel 6 on its rotation at
`+0x60` (37 522 of 40 541), channel 7 on its scale at `+0x70` (7 871 of 7 903).
`rest` runs that comparison.
"""

import argparse
import collections
import glob
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAGIC = b"AAF "
HEADER = 0x24
RECORD_HEADER = 0x28
TRACK_HEADER = 0x14


class AafError(Exception):
    pass


def _u32(blob, at):
    return struct.unpack_from(">I", blob, at)[0]


def _u16(blob, at):
    return struct.unpack_from(">H", blob, at)[0]


def _f32(blob, at):
    return struct.unpack_from(">f", blob, at)[0]


# The byte at track +0x11. Each entry is (bytes in one value, values per key).
# A key with three values is a Hermite key: the value, then the tangent going
# in and the tangent coming out.
KEY_LAYOUTS = {
    0:  (4, 3),
    1:  (4, 1),
    2:  (4, 1),
    5:  (12, 3),
    6:  (12, 1),
    7:  (12, 1),
    8:  (16, 3),
    9:  (16, 1),
    10: (16, 1),
    12: (8, 1),
    13: (8, 2),
}

CHANNELS = {
    5: "translation",
    6: "rotation",
    7: "scale",
}


def unpack_quaternion(word):
    """The 48-bit packed rotation, as (x, y, z, w).

    Two angles for the axis and one field for the rotation, each measured as a
    fraction of a right angle, with three sign bits between them. See the
    module docstring for where the reading comes from.
    """
    polar = (word & 0x3FFF) / 16383.0 * (math.pi / 2)
    azimuth = ((word >> 14) & 0x3FFF) / 16383.0 * (math.pi / 2)
    signs = (word >> 28) & 7
    y = math.cos(polar)
    radius = math.sin(polar)
    x = radius * math.cos(azimuth)
    z = radius * math.sin(azimuth)
    if signs & 4:
        x = -x
    if signs & 2:
        y = -y
    if signs & 1:
        z = -z
    w = 1.0 - (((word >> 31) & 0x1FFFF) / 131071.0) ** 2
    scale = math.sqrt(max(0.0, 1.0 - w * w))
    return (x * scale, y * scale, z * scale, w)


class Track:
    """One channel of one node: either a constant or a stream of keys."""

    __slots__ = ("offset", "size", "wide", "flags", "target", "channel",
                 "kind", "range", "block_count", "index", "record")

    def __init__(self, blob, at, record):
        self.offset = at
        # The size is the low half of the word: a handful of tracks set 0x0200
        # in the high half, and those are the only files where reading the
        # whole word as a size walks off the end of the record.
        self.wide = _u16(blob, at)
        self.size = _u16(blob, at + 0x02)
        if self.size < TRACK_HEADER:
            raise AafError("track at %#x states a size of %#x" % (at, self.size))
        self.flags = _u16(blob, at + 0x04)
        self.target = _u32(blob, at + 0x08)
        self.channel = _u16(blob, at + 0x0C)
        self.kind = tuple(blob[at + 0x10:at + 0x14])
        self.record = record
        self.index = None          # set for animated tracks, in file order
        self.range = None
        self.block_count = None
        if self.size >= TRACK_HEADER + 0x10:
            self.range = struct.unpack_from(">3f", blob, at + 0x14)
            self.block_count = _u32(blob, at + self.size - 4)

    @property
    def animated(self):
        """True if the track's keys live in the keyframe blocks.

        The 0x20 flag says so, and it agrees with the header's animated count
        on all 900 files of the corpus. A handful of tracks carry neither 0x20
        nor 0x80: those are self-contained, with their payload inline.
        """
        return bool(self.flags & 0x20)

    @property
    def constant(self):
        return bool(self.flags & 0x80)

    @property
    def channel_name(self):
        return CHANNELS.get(self.channel, "channel %d" % self.channel)

    @property
    def layout(self):
        """(bytes in one value, values in one key), or None if unknown.

        A packed-quaternion track normally stores the value and a tangent; the
        0x400 flag drops the tangent and leaves the key at eight bytes.
        """
        layout = KEY_LAYOUTS.get(self.kind[1])
        if layout and self.kind[1] == 13 and self.flags & 0x400:
            return (layout[0], 1)
        return layout

    @property
    def key_size(self):
        layout = self.layout
        return layout[0] * layout[1] if layout else None

    def decode(self, data):
        """One key, as a list of values -- value first, then any tangents."""
        layout = self.layout
        if layout is None:
            return None
        width, count = layout
        out = []
        for i in range(count):
            at = i * width
            if at + width > len(data):
                break
            if width == 8:
                out.append(unpack_quaternion(
                    int.from_bytes(data[at:at + 8], "big")))
            else:
                out.append(struct.unpack_from(">%df" % (width // 4), data, at))
        return out


class Record:
    """One animated node, named after an `attr` in the matching ASF."""

    __slots__ = ("offset", "size", "name", "tracks")

    def __init__(self, blob, at):
        self.offset = at
        # Counts and sizes are 16-bit fields in 32-bit slots. Reading the
        # whole word works until a file sets the high half, which some do.
        count = _u16(blob, at + 0x02)
        self.size = _u32(blob, at + 0x04)
        if self.size < RECORD_HEADER:
            raise AafError("record at %#x states a size of %#x" % (at, self.size))
        self.name = blob[at + 0x08:at + RECORD_HEADER].split(b"\0")[0].decode(
            "latin-1", "replace")
        self.tracks = []
        walk = at + RECORD_HEADER
        for _ in range(count):
            track = Track(blob, walk, self)
            self.tracks.append(track)
            walk += track.size
        if walk != at + self.size:
            raise AafError("record %r: tracks end at %#x, record ends at %#x"
                           % (self.name, walk, at + self.size))


class Block:
    """One instant: the time, and one key for each track that moves in it."""

    __slots__ = ("offset", "time", "keys")

    def __init__(self, offset, time):
        self.offset = offset
        self.time = time
        self.keys = []             # (track index, bytes)


class AafFile:
    def __init__(self, data):
        if data[:4] != MAGIC:
            raise AafError("not an AAF payload")
        self.data = data
        self.version = _u32(data, 0x10)
        self.duration = _u16(data, 0x16)
        self.animated_count = _u16(data, 0x1A)
        self.constant_count = _u16(data, 0x1C)
        self.unknown20 = _u32(data, 0x20)

        self.records = []
        walk = HEADER
        for _ in range(_u16(data, 0x14)):
            record = Record(data, walk)
            self.records.append(record)
            walk += record.size
        self.table_end = walk

        self.tracks = [t for r in self.records for t in r.tracks]
        self.animated = [t for t in self.tracks if t.animated]
        self.constants = [t for t in self.tracks if t.constant]
        for i, track in enumerate(self.animated):
            track.index = i

        count = _u16(data, 0x1E)
        self.blocks = [Block(_u32(data, walk + i * 8), _f32(data, walk + i * 8 + 4))
                       for i in range(count)]
        walk += count * 8

        # -- the constant curves ------------------------------------------
        # The offsets are counted from just past the region's size word, and
        # the data begins where the offset array ends.
        self.constant_region = walk
        self.constant_size = _u16(data, walk)
        offsets = [_u16(data, walk + 2 + i * 2) for i in range(len(self.constants))]
        base = walk + 2
        ends = offsets[1:] + [self.constant_size - 2]
        self.constant_curves = [data[base + a:base + b]
                                for a, b in zip(offsets, ends)]

        # -- the keyframe blocks -------------------------------------------
        for i, block in enumerate(self.blocks):
            pairs = [(_u16(data, block.offset + 4 + j * 4),
                      _u16(data, block.offset + 6 + j * 4))
                     for j in range(_u32(data, block.offset))]
            stop = (self.blocks[i + 1].offset if i + 1 < len(self.blocks)
                    else len(data))
            for j, (index, at) in enumerate(pairs):
                end = pairs[j + 1][1] if j + 1 < len(pairs) else stop - block.offset
                block.keys.append(
                    (index, data[block.offset + at:block.offset + end]))

    def constant_of(self, track):
        try:
            return self.constant_curves[self.constants.index(track)]
        except (ValueError, IndexError):
            return None

    def keys_of(self, track):
        """Every (time, bytes) this animated track has, in time order."""
        return [(b.time, data) for b in self.blocks
                for index, data in b.keys if index == track.index]

    def problems(self):
        """Everything about this file that does not add up. Empty is good."""
        bad = []
        if self.version != 0x16:
            bad.append("version %#x" % self.version)
        if len(self.animated) != self.animated_count:
            bad.append("header counts %d animated tracks, the records hold %d"
                       % (self.animated_count, len(self.animated)))
        if len(self.constants) != self.constant_count:
            bad.append("header counts %d constant tracks, the records hold %d"
                       % (self.constant_count, len(self.constants)))
        if self.blocks:
            end = self.constant_region + self.constant_size
            if end != self.blocks[0].offset:
                bad.append("constant region ends at %#x, first block is at %#x"
                           % (end, self.blocks[0].offset))
        if self.constants and self.constant_size < 2 + 2 * len(self.constants):
            bad.append("constant region is too small for its offset array")
        counted = collections.Counter(
            index for b in self.blocks for index, _ in b.keys)
        for track in self.animated:
            if counted[track.index] != track.block_count:
                bad.append("a track appears in %d blocks but states %d"
                           % (counted[track.index], track.block_count))
                break
        for block in self.blocks:
            for j, (index, data) in enumerate(block.keys):
                if j + 1 == len(block.keys) or index >= len(self.animated):
                    continue          # the last key carries the block padding
                want = self.animated[index].key_size
                if want is not None and len(data) != want:
                    bad.append("a key is %d bytes, its layout wants %d"
                               % (len(data), want))
                    break
            if bad and bad[-1].startswith("a key is"):
                break
        if counted and max(counted) >= len(self.animated):
            bad.append("a block names track %d of %d"
                       % (max(counted), len(self.animated)))
        return bad


def load(path):
    with open(path, "rb") as fh:
        return AafFile(fh.read())


# -- commands --------------------------------------------------------------

def _describe(track):
    what = "constant" if not track.animated else "%d keys" % track.block_count
    size = "%d B" % track.key_size if track.key_size else "?"
    return ("      %-12s flags %#05x  target %#04x  kind %-16s %-10s key %s"
            % (track.channel_name, track.flags, track.target, str(track.kind),
               what, size))


def cmd_tree(args):
    aaf = load(args.file)
    print("AAF version %#x, %d records, duration %d, %d keyframe blocks"
          % (aaf.version, len(aaf.records), aaf.duration, len(aaf.blocks)))
    for record in aaf.records[:args.limit]:
        print("  %-32s %d track(s)" % (repr(record.name), len(record.tracks)))
        for track in record.tracks:
            print(_describe(track))


def cmd_info(args):
    aaf = load(args.file)
    print("%s" % args.file)
    print("  version          %#x" % aaf.version)
    print("  records          %d" % len(aaf.records))
    print("  duration         %d" % aaf.duration)
    print("  tracks           %d animated, %d constant"
          % (len(aaf.animated), len(aaf.constants)))
    print("  keyframe blocks  %d, t = %g .. %g"
          % (len(aaf.blocks),
             aaf.blocks[0].time if aaf.blocks else 0,
             aaf.blocks[-1].time if aaf.blocks else 0))
    channels = collections.Counter(t.channel_name for t in aaf.tracks)
    print("  channels         %s"
          % ", ".join("%s x%d" % (k, v) for k, v in channels.most_common()))
    bad = aaf.problems()
    print("  self-check       %s" % ("clean" if not bad else "; ".join(bad)))


def _value_at(aaf, track, time):
    """The track's value at `time`, taking the last key at or before it."""
    if not track.animated:
        data = aaf.constant_of(track)
        decoded = track.decode(data) if data else None
        return decoded[0] if decoded else None
    best = None
    for when, data in aaf.keys_of(track):
        if best is None or when <= time:
            best = (when, data)
    if best is None:
        return None
    decoded = track.decode(best[1])
    return decoded[0] if decoded else None


def cmd_pose(args):
    aaf = load(args.file)
    print("t = %g" % args.time)
    for record in aaf.records[:args.limit]:
        parts = []
        for track in record.tracks:
            value = _value_at(aaf, track, args.time)
            if value is None:
                continue
            parts.append("%s (%s)" % (track.channel_name,
                                      " ".join("%8.3f" % v for v in value)))
        print("  %-24s %s" % (record.name, "  ".join(parts)))


def cmd_rest(args):
    """Constants against the rest pose of the matching ASF.

    An AAF record is named after an `attr` node of the scene it animates, and a
    channel that never changes usually holds that node's rest value. Comparing
    the two is a check against numbers this reader did not produce -- and it is
    what identifies the channels in the first place.
    """
    import asf as asf_module

    scenes = collections.defaultdict(list)
    for path in _expand(args.models):
        scenes[os.path.basename(path).split("_")[0]].append(path)

    rows = collections.defaultdict(lambda: [0, 0])
    named = [0, 0]
    whole = collections.Counter()
    for path in _expand(args.files):
        group = os.path.basename(path).split("_")[0]
        if group not in scenes:
            continue
        nodes = {}
        for scene in scenes[group]:
            try:
                loaded = asf_module.load(scene)
            except Exception:
                continue
            for chunk in _all_chunks(loaded.chunks):
                if chunk.tag == "attr":
                    nodes.setdefault(chunk.name() or "", chunk.raw())
        if not nodes:
            continue
        try:
            aaf = load(path)
        except (AafError, struct.error):
            continue
        hit = sum(1 for r in aaf.records if r.name in nodes)
        named[0] += hit
        named[1] += len(aaf.records)
        if aaf.records:
            whole[hit == len(aaf.records)] += 1
        rest = {5: 0x50, 6: 0x60, 7: 0x70}
        for track in aaf.constants:
            raw = nodes.get(track.record.name)
            where = rest.get(track.channel)
            if raw is None or where is None or where + 16 > len(raw):
                continue
            data = aaf.constant_of(track)
            decoded = track.decode(data) if data else None
            if not decoded:
                continue
            value = decoded[0]
            if track.channel == 6 and len(value) != 4:
                continue          # an Euler rotation, not a quaternion
            stored = struct.unpack_from(">4f", raw, where)[:len(value)]
            error = min(max(abs(a - b) for a, b in zip(value, stored)),
                        max(abs(a + b) for a, b in zip(value, stored)))
            row = rows[track.channel_name]
            row[1] += 1
            row[0] += error < 3e-3
    print("record names found in the matching scene's node tree: %d of %d (%.1f%%)"
          % (named[0], named[1], 100.0 * named[0] / max(1, named[1])))
    print("  files where every record name is found: %d of %d"
          % (whole[True], whole[True] + whole[False]))
    for name, where in (("translation", 0x50), ("rotation", 0x60), ("scale", 0x70)):
        hit, total = rows.get(name, (0, 0))
        if not total:
            continue
        print("%-12s constants reproducing attr +0x%02X: %d of %d (%.1f%%)"
              % (name, where, hit, total, 100.0 * hit / total))


def _all_chunks(chunks):
    for chunk in chunks:
        yield chunk
        for child in _all_chunks(chunk.children()):
            yield child


def _expand(patterns):
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern) if any(c in pattern for c in "*?")
                     else [pattern])
    return sorted(files)


def cmd_check(args):
    files = _expand(args.files)
    clean = 0
    unreadable = []
    faults = collections.Counter()
    tangents = []
    angles = []
    for path in files:
        try:
            aaf = load(path)
        except (AafError, struct.error, IndexError) as exc:
            unreadable.append((path, exc))
            continue
        bad = aaf.problems()
        if bad:
            for line in bad:
                faults[line.split(",")[0][:60]] += 1
            if args.verbose:
                print("%s: %s" % (path, "; ".join(bad[:3])))
            continue
        clean += 1
        # A Hermite tangent should say where the curve is going. Two
        # measurements: its length against the step to the next key, and its
        # direction against the line through the keys either side -- which is
        # what a Maya "smooth" tangent is.
        for track in aaf.animated:
            if track.channel != 5 or (track.layout or (0, 0))[1] != 3:
                continue
            keys = [track.decode(data) for _, data in aaf.keys_of(track)]
            keys = [k if k and len(k) == 3 and len(k[0]) == 3 else None
                    for k in keys]
            for i, key in enumerate(keys):
                if key is None or i + 1 >= len(keys) or keys[i + 1] is None:
                    continue
                here, ahead = key[0], keys[i + 1][0]
                step = [ahead[k] - here[k] for k in range(3)]
                out = key[2]
                size = math.sqrt(sum(v * v for v in step))
                length = math.sqrt(sum(v * v for v in out))
                if size < 1e-3 or length < 1e-6:
                    continue
                tangents.append(size / length)
                if i == 0 or keys[i - 1] is None:
                    continue
                behind = keys[i - 1][0]
                through = [ahead[k] - behind[k] for k in range(3)]
                across = math.sqrt(sum(v * v for v in through))
                if across < 1e-6:
                    continue
                cosine = sum(through[k] * out[k] for k in range(3)) / (across * length)
                angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    print("%d files: %d parse and self-check clean, %d unreadable, %d with faults"
          % (len(files), clean, len(unreadable), len(files) - clean - len(unreadable)))
    for path, exc in unreadable[:args.limit]:
        print("  unreadable  %s: %s" % (path, exc))
    for line, count in faults.most_common(args.limit):
        print("  %5d x %s" % (count, line))
    if tangents:
        tangents.sort()
        print("translation tangents, over %d keys:" % len(tangents))
        print("  length of the step to the next key, over the tangent's own:"
              " median %.4f" % tangents[len(tangents) // 2])
    if angles:
        angles.sort()
        print("  angle to the line through the neighbouring keys: median"
              " %.2f deg, within 5 deg on %.1f%% of %d"
              % (angles[len(angles) // 2],
                 100.0 * sum(1 for a in angles if a < 5) / len(angles),
                 len(angles)))


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Reader for AAF, the Aska Animation File.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("tree", help="print the records and their tracks")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_tree)

    s = sub.add_parser("info", help="summarise one animation and self-check it")
    s.add_argument("file")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("pose", help="print every channel's value at one time")
    s.add_argument("file")
    s.add_argument("--time", type=float, default=0.0)
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_pose)

    s = sub.add_parser("rest",
                       help="check constants against the rest pose of the "
                            "matching ASF, which is what names the channels")
    s.add_argument("files", nargs="+", help="AAF payloads")
    s.add_argument("--models", nargs="+", required=True, help="ASF payloads")
    s.set_defaults(func=cmd_rest)

    s = sub.add_parser("check", help="parse a corpus and measure the decode")
    s.add_argument("files", nargs="+")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
