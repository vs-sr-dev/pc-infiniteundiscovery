#!/usr/bin/env python3
"""
snc.py -- reader for SNC, the Aska scene script.

Every `SCE-` resource decompresses to a payload whose magic is `-CNS00.3`, the
byte-reversed `SNC-` plus a version, in the same convention the NORM container
itself uses. There are 44 of them on disc 1 and 17 more on disc 2's `ud1.bin`.

It is a compiled script. A model was complete after session 9 -- geometry,
materials, textures, skeleton, animation, collision -- and this is what drives
it: the file that says which objects a scene spawns, where they stand, what
they are attached to, and how they move over the course of a cutscene.

The engine names it. `CSceVar` and `sce::Var` appear in the executable's RTTI,
along with `CSceSceneController`, `CSceDelayTask` and `CSceSpecialProcess`, so
`sce` is the namespace and `Var` is the tagged value this file is made of.

Layout
------
0x30-byte header, big-endian, then four sections. Every offset and length in
the header counts 32-bit words, not bytes:

    +0x00  8  '-CNS00.3'
    +0x08  4  unknown
    +0x0C  4  1 in every file
    +0x10  8  code:    offset, length -- always at word 0x0C
    +0x18  8  data:    offset, length
    +0x20  8  strings: offset, length
    +0x28  8  entries: offset, length

The sections are laid out in ascending offset order, each padded up to a
four-word boundary, but the header does not list them in that order: the entry
table comes before the string table in the file whenever both are present.
The end of the last section is the end of the file, on all 61 payloads.

Code
----
A flat instruction list. An instruction is

    +0x00  2  operand words -- 2 per operand, so always even
    +0x02  2  opcode
    +0x04 ..  the operands

and the next instruction follows immediately. Walking that from the start of
the section lands exactly on its end in all 61 files, and each of the 253
opcodes seen has one operand count and only one across the whole corpus.

Operands
--------
Eight bytes: a four-byte tag and a four-byte value.

    +0x00  1  kind -- a printable ASCII letter
    +0x01  1  sub-kind, 0 or 1
    +0x02  2  aux, 0x0100 on a floating-point immediate
    +0x04  4  value

The kind letter is what makes the file readable. Four of them address the
other sections, and every reference lands:

    n   immediate.  aux 0x0100 means the value is a float; otherwise the
        compiler stored an integral literal as an int, so a slot that holds a
        distance may be n(0) in one instruction and n(-697.383) in the next
    $   string, as a byte offset into the string section  (5 035 of 5 035)
    @   data block, as a word offset into the data section (413 467 of 413 467)
    &   code address, as a word offset into the code section. Sixteen opcodes
        read it absolutely (13 484 of 13 484 land on an instruction); 0x0002
        and 0x0003 read it relative to their own address, signed (5 182 of
        5 182)

    h   object handle, allocated in file order from 512, with 0 as null
    m   a second handle space, allocated from 1, always two to a data block
    e   asset or type identifier
    c   a small enumerated reference, 0 in four cases out of five
    k s i u v r b t o p a d g j   further reference classes

The letters a, b, d, j, o, p and t carry a zero value in every occurrence, so
they are keywords rather than references.

Data
----
A pool of argument lists. A record is a four-byte length in words followed by
that many words of operands, in exactly the encoding above; walking it lands on
the section end in all 61 files. A length of zero is a legal empty record, and
commands use one where a curve or a list is optional.

The point of the pool is that an argument can be a *list*. A move command does
not carry an X, it carries @ at a block holding the X values, so one command
can hold a whole keyframe track.

Strings
-------
NUL-terminated ASCII, padded to four bytes. They are Maya node names, and the
same names the ASF node tree and the ACF sphere tree carry -- R:M:SK_HipR,
R:M:SIGMUND_shield, directionalLight1, shadow_B1_01Shape. Only six opcodes
take one, which is what identifies them.

Entries
-------
Pairs of words: an identifier, small and starting at 1, and a code address in
the same units & uses. All 82 land on an instruction start.

Reproducing
-----------
    python tools/mron.py extract <image> --offset N --length N \
        --tag SCE- --decompress out/
    python tools/snc.py info  out/xxx_SCE.bin
    python tools/snc.py dis   out/xxx_SCE.bin --limit 40
    python tools/snc.py check out/*.bin
"""

import argparse
import collections
import math
import os
import struct
import sys

MAGIC = b"-CNS00.3"
HEADER = 0x30

# Kinds whose value addresses another section.
STRING, BLOCK, ADDRESS, IMMEDIATE = 0x24, 0x40, 0x26, 0x6E

# The opcodes that read an address operand relative to their own address.
RELATIVE_BRANCH = (0x0002, 0x0003)

# What the six string-taking opcodes name, read off the strings themselves.
OPCODE_NAMES = {
    0x0105: "bind control node",     # CTRL_chair, DOOR_01_BOTH, A16_BON01
    0x0106: "bind light",            # directionalLight1, GLOBAL_Hemi_Ch
    0x0114: "bind shadow",           # shadow_B1_01Shape, *_SdwShape
    0x0141: "attach to slot",        # $WEAPON, R:M:EUGUNE_Backpack
    0x0142: "attach to bone",        # R:M:SK_HipR, R:M:WEPLINK_RtHand
    0x0149: "spawn object",          # handle, asset, position, quaternion
    0x0154: "bind two named nodes",
}


class SncError(Exception):
    pass


class Operand(object):
    """One sce::Var: a kind letter, a sub-kind, an aux word and a value."""

    __slots__ = ("kind", "sub", "aux", "raw")

    def __init__(self, blob, at):
        self.kind, self.sub, self.aux = struct.unpack_from(">2BH", blob, at)
        self.raw = struct.unpack_from(">I", blob, at + 4)[0]

    @property
    def letter(self):
        return chr(self.kind) if 0x20 <= self.kind < 0x7F else "?"

    @property
    def is_float(self):
        return self.kind == IMMEDIATE and bool(self.aux & 0xFF00)

    @property
    def value(self):
        """The value in its own type: float, signed int, or a raw index."""
        if self.is_float:
            return struct.unpack(">f", struct.pack(">I", self.raw))[0]
        if self.kind in (IMMEDIATE, ADDRESS):
            # a relative branch reaches backwards, so an address is signed too
            return self.raw - (1 << 32) if self.raw >> 31 else self.raw
        return self.raw

    def number(self):
        """The value as a float, whichever way the compiler stored it."""
        if self.kind != IMMEDIATE:
            return None
        return float(self.value)

    def __str__(self):
        if self.kind == IMMEDIATE:
            return "%g" % self.value
        text = "%s%d" % (self.letter, self.raw)
        if (self.sub, self.aux) != (0, 0):
            text += "<%d,%d>" % (self.sub, self.aux)
        return text


class Instruction(object):

    __slots__ = ("offset", "word", "opcode", "operands")

    def __init__(self, blob, at, word):
        size, self.opcode = struct.unpack_from(">2H", blob, at)
        if size % 2:
            raise SncError("odd operand size %d at 0x%X" % (size, at))
        self.offset, self.word = at, word
        self.operands = [Operand(blob, at + 4 + 8 * i) for i in range(size // 2)]

    @property
    def size(self):
        return 4 + 8 * len(self.operands)

    @property
    def signature(self):
        return "".join(o.letter for o in self.operands)

    def __str__(self):
        name = OPCODE_NAMES.get(self.opcode)
        text = "%04x%s" % (self.opcode, "" if name is None else " (%s)" % name)
        return "%-32s %s" % (text, " ".join(str(o) for o in self.operands))


class Block(object):
    """One data-pool record: a length in words, then that many words."""

    __slots__ = ("offset", "word", "operands")

    def __init__(self, blob, at, word):
        size = struct.unpack_from(">I", blob, at)[0]
        if size % 2:
            raise SncError("odd block size %d at 0x%X" % (size, at))
        self.offset, self.word = at, word
        self.operands = [Operand(blob, at + 4 + 8 * i) for i in range(size // 2)]

    @property
    def size(self):
        return 4 + 8 * len(self.operands)

    def __str__(self):
        return " ".join(str(o) for o in self.operands)


class SncFile(object):

    def __init__(self, data):
        if data[:8] != MAGIC:
            raise SncError("not an SNC payload: %r" % data[:8])
        self.blob = data
        self.unknown = struct.unpack_from(">I", data, 0x08)[0]
        self.version = struct.unpack_from(">I", data, 0x0C)[0]
        self.sections = [struct.unpack_from(">2I", data, 0x10 + 8 * i)
                         for i in range(4)]
        self.code_at, self.code_len = self.sections[0]
        self.data_at, self.data_len = self.sections[1]
        self.string_at, self.string_len = self.sections[2]
        self.entry_at, self.entry_len = self.sections[3]
        self.code = self._read_code()
        self.data = self._read_data()
        self._blocks = dict((b.word, b) for b in self.data)
        self._starts = set(i.word for i in self.code)
        self._strings = self._read_strings()

    # -- sections ----------------------------------------------------------

    def _read_code(self):
        out, at = [], self.code_at * 4
        end = (self.code_at + self.code_len) * 4
        while at < end:
            item = Instruction(self.blob, at, (at - self.code_at * 4) // 4)
            out.append(item)
            at += item.size
        if at != end:
            raise SncError("code walk ended at 0x%X, section ends at 0x%X"
                           % (at, end))
        return out

    def _read_data(self):
        out, at = [], self.data_at * 4
        end = (self.data_at + self.data_len) * 4
        while at < end:
            item = Block(self.blob, at, (at - self.data_at * 4) // 4)
            out.append(item)
            at += item.size
        if at != end:
            raise SncError("data walk ended at 0x%X, section ends at 0x%X"
                           % (at, end))
        return out

    def _read_strings(self):
        """Byte offset within the section -> string."""
        base = self.string_at * 4
        end = (self.string_at + self.string_len) * 4
        out, at = {}, base
        while at < end:
            stop = self.blob.find(b"\0", at, end)
            if stop < 0:
                break
            if stop > at:
                out[at - base] = self.blob[at:stop].decode("latin-1")
            at = stop
            while at < end and self.blob[at] == 0:
                at += 1
        return out

    def strings(self):
        return self._strings

    def entries(self):
        base = self.entry_at * 4
        return [struct.unpack_from(">2I", self.blob, base + 8 * i)
                for i in range(self.entry_len)]

    # -- resolving ---------------------------------------------------------

    def string(self, offset):
        return self._strings.get(offset)

    def block(self, word):
        return self._blocks.get(word)

    def target(self, instruction, operand):
        """Where an address operand points, as a word offset in the code."""
        if instruction.opcode in RELATIVE_BRANCH:
            return instruction.word + operand.value
        return operand.raw

    def is_instruction(self, word):
        return word in self._starts

    # -- checking ----------------------------------------------------------

    def problems(self):
        out = []
        end = max(off + length for off, length in self.sections) * 4
        if end != len(self.blob):
            out.append("sections end at 0x%X, file is 0x%X"
                       % (end, len(self.blob)))
        table = self._strings
        for item in self.code:
            for operand in item.operands:
                if operand.kind == STRING and operand.raw not in table:
                    out.append("string %d is not a string start" % operand.raw)
                elif operand.kind == BLOCK and operand.raw not in self._blocks:
                    out.append("block @%d is not a record start" % operand.raw)
                elif operand.kind == ADDRESS:
                    if not self.is_instruction(self.target(item, operand)):
                        out.append("address &%d is not an instruction"
                                   % operand.value)
        for _, where in self.entries():
            if not self.is_instruction(where):
                out.append("entry point %d is not an instruction" % where)
        return out[:8]

    def handles(self):
        out = set()
        for item in self.code:
            for operand in item.operands:
                if operand.letter == "h" and operand.raw:
                    out.add(operand.raw)
        return sorted(out)


def load(path):
    with open(path, "rb") as fh:
        return SncFile(fh.read())


# -- commands --------------------------------------------------------------

def cmd_info(args):
    snc = load(args.file)
    kinds = collections.Counter()
    opcodes = collections.Counter()
    for item in snc.code:
        opcodes[item.opcode] += 1
        for operand in item.operands:
            kinds[operand.letter] += 1
    print("%s" % args.file)
    print("  version      %d, word at 0x08 %d" % (snc.version, snc.unknown))
    print("  code         %d instructions, %d words at 0x%X"
          % (len(snc.code), snc.code_len, snc.code_at * 4))
    print("  data         %d blocks, %d words at 0x%X"
          % (len(snc.data), snc.data_len, snc.data_at * 4))
    print("  strings      %d, %d bytes at 0x%X"
          % (len(snc.strings()), snc.string_len * 4, snc.string_at * 4))
    print("  entries      %d at 0x%X" % (snc.entry_len, snc.entry_at * 4))
    handles = snc.handles()
    if handles:
        dense = handles == list(range(handles[0], handles[-1] + 1))
        print("  handles      %d, %d..%d%s"
              % (len(handles), handles[0], handles[-1],
                 "" if dense else " (with gaps)"))
    print("  opcodes      %d distinct: %s"
          % (len(opcodes), ", ".join("%04x x%d" % (o, c)
                                     for o, c in opcodes.most_common(8))))
    print("  operands     %s"
          % ", ".join("%s x%d" % (k, c) for k, c in kinds.most_common(10)))
    bad = snc.problems()
    print("  self-check   %s" % ("clean" if not bad else "; ".join(bad)))
    return 0


def cmd_dis(args):
    snc = load(args.file)
    table = snc.strings()
    entries = dict((where, which) for which, where in snc.entries())
    shown = 0
    for item in snc.code:
        if shown >= args.limit:
            print("   ... %d more" % (len(snc.code) - shown))
            break
        if item.word in entries:
            print("entry %d:" % entries[item.word])
        text = str(item)
        notes = []
        for operand in item.operands:
            if operand.kind == STRING:
                notes.append("%r" % table.get(operand.raw))
            elif operand.kind == ADDRESS:
                notes.append("-> %d" % snc.target(item, operand))
            elif operand.kind == BLOCK and args.blocks:
                notes.append("@%d = [%s]" % (operand.raw,
                                             snc.block(operand.raw)))
        if notes:
            text += "   ; " + "  ".join(notes)
        print("%6d  %s" % (item.word, text))
        shown += 1
    return 0


def cmd_strings(args):
    snc = load(args.file)
    users = collections.defaultdict(collections.Counter)
    for item in snc.code:
        for operand in item.operands:
            if operand.kind == STRING:
                users[operand.raw][item.opcode] += 1
    for offset, text in sorted(snc.strings().items()):
        who = ", ".join("%04x%s" % (o, "" if o not in OPCODE_NAMES
                                    else " %s" % OPCODE_NAMES[o])
                        for o in users[offset])
        print("%6d  %-40s %s" % (offset, repr(text), who))
    return 0


def cmd_blocks(args):
    snc = load(args.file)
    for block in snc.data[:args.limit]:
        print("@%-8d [%d] %s" % (block.word, len(block.operands), block))
    return 0


def cmd_check(args):
    """Parse a corpus and measure everything the format claims about itself."""
    counts = collections.Counter()
    arity = collections.defaultdict(set)
    signatures = collections.defaultdict(set)
    kinds = collections.Counter()
    quaternions = [0, 0]
    for path in args.files:
        try:
            snc = load(path)
        except (SncError, struct.error) as exc:
            counts["failed"] += 1
            if args.verbose:
                print("  %s: %s" % (os.path.basename(path), exc))
            continue
        counts["files"] += 1
        bad = snc.problems()
        counts["clean"] += not bad
        if bad and args.verbose:
            print("  %s: %s" % (os.path.basename(path), "; ".join(bad)))
        counts["instructions"] += len(snc.code)
        counts["blocks"] += len(snc.data)
        counts["strings"] += len(snc.strings())
        for item in snc.code:
            arity[item.opcode].add(len(item.operands))
            signatures[item.opcode].add(item.signature)
            for operand in item.operands:
                kinds[operand.letter] += 1
                if operand.kind == STRING:
                    counts["$ total"] += 1
                    counts["$ landed"] += operand.raw in snc.strings()
                elif operand.kind == BLOCK:
                    counts["@ total"] += 1
                    counts["@ landed"] += snc.block(operand.raw) is not None
                elif operand.kind == ADDRESS:
                    counts["& total"] += 1
                    counts["& landed"] += snc.is_instruction(
                        snc.target(item, operand))
            if item.opcode == 0x0149 and len(item.operands) == 11:
                quat = [o.number() for o in item.operands[5:9]]
                if all(v is not None for v in quat):
                    quaternions[1] += 1
                    length = math.sqrt(sum(v * v for v in quat))
                    quaternions[0] += abs(length - 1.0) < 1e-3
        for _, where in snc.entries():
            counts["entry total"] += 1
            counts["entry landed"] += snc.is_instruction(where)
        handles = snc.handles()
        if len(handles) > 2:
            counts["handle files"] += 1
            counts["handle runs"] += (
                handles[0] == 512
                and handles == list(range(512, 512 + len(handles))))

    print("files                       %d parsed, %d failed"
          % (counts["files"], counts["failed"]))
    print("sections walk exactly       %d / %d"
          % (counts["clean"], counts["files"]))
    print("instructions                %d, over %d blocks of data"
          % (counts["instructions"], counts["blocks"]))
    print("opcodes                     %d distinct, %d with one operand count,"
          " %d with one signature"
          % (len(arity),
             sum(1 for k in arity if len(arity[k]) == 1),
             sum(1 for k in signatures if len(signatures[k]) == 1)))
    for what in ("$", "@", "&", "entry"):
        total = counts["%s total" % what]
        if total:
            print("%-27s %d / %d  %.4f%%"
                  % ("%s lands" % what, counts["%s landed" % what], total,
                     100.0 * counts["%s landed" % what] / total))
    print("handles are 512.. and dense %d / %d"
          % (counts["handle runs"], counts["handle files"]))
    if quaternions[1]:
        print("0x0149 operands 5..8 unit   %d / %d  %.3f%%"
              % (quaternions[0], quaternions[1],
                 100.0 * quaternions[0] / quaternions[1]))
    print("operand kinds               %s"
          % ", ".join("%s x%d" % (k, c) for k, c in kinds.most_common()))
    return 0 if not counts["failed"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Reader for SNC, the Aska scene script.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("info", help="summarise one script and self-check it")
    s.add_argument("file")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("dis", help="print the instruction list")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=60)
    s.add_argument("--blocks", action="store_true",
                   help="expand every data block an instruction points at")
    s.set_defaults(func=cmd_dis)

    s = sub.add_parser("strings", help="print the string table and its users")
    s.add_argument("file")
    s.set_defaults(func=cmd_strings)

    s = sub.add_parser("blocks", help="print the data pool")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=60)
    s.set_defaults(func=cmd_blocks)

    s = sub.add_parser("check", help="parse a corpus and measure the decode")
    s.add_argument("files", nargs="+")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
