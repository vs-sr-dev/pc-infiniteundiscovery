#!/usr/bin/env python3
"""
disasm.py -- find the code behind a string, in a PlayStation or PlayStation 2
executable.

This is the tool session 17 used to read SLZ's methods 2 and 3, and it exists
because the method that worked is worth keeping rather than the addresses it
produced. The method is three steps:

1.  `strings` -- find the magic in the image and note its virtual address.
2.  `xref` -- find the code that constructs that address. On MIPS an address
    is built with `lui` followed by `addiu`/`ori`, or by a load or store with
    the `lui` as its base, so a linear pass that remembers the last `lui` per
    register catches essentially all of them. There are usually one or two.
3.  `dis` -- read the function.

For `SLZ` that took about ten minutes and gave up a dispatcher with the method
byte in it. What made the result trustworthy rather than merely plausible was
that one arm of that dispatcher had to be method 1, which had been specified
two sessions earlier from the outside, by search. It was. A disassembly with no
such check in it is worth much less.

Two image formats, because they are the two the discs use:

* **`PS-X EXE`**, the PlayStation's. A 0x800-byte header, then a flat image;
  the load address and size are in the header at 0x18.
* **ELF**, the PlayStation 2's. The first program header is the loaded image;
  the rest are overlays with no file content.

The PlayStation 2 is an R5900, which has `lq` and `sq` -- 128-bit load and
store, used for register saves in every prologue. Capstone decodes those
opcodes as MSA vector instructions, which is wrong and noisy, so they are
disassembled here by hand and everything else is handed to capstone.

    python tools/disasm.py strings extract/ps1/SCUS_944.21 SLZ
    python tools/disasm.py xref    extract/ps1/SCUS_944.21 0x8002A860
    python tools/disasm.py dis     extract/ps1/SCUS_944.21 0x800121A8 --length 0xF0
    python tools/disasm.py table   extract/ps1/SCUS_944.21 0x8002A868
"""

import argparse
import struct
import sys

try:
    from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
except ImportError:
    Cs = None

REGS = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
        "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
        "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
        "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]

# Opcodes whose immediate is an offset from a base register, so a preceding
# lui makes them an address reference too.
MEM_OPS = {0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B, 0x1E, 0x1F}


class Image:
    """A loaded executable: file bytes, plus where the code sits in memory."""

    def __init__(self, path):
        self.data = open(path, "rb").read()
        if self.data[:8] == b"PS-X EXE":
            base, size = struct.unpack_from("<II", self.data, 0x18)
            self.base, self.offset, self.size = base, 0x800, size
            self.kind = "PS-X EXE"
        elif self.data[:4] == b"\x7fELF":
            phoff = struct.unpack_from("<I", self.data, 0x1C)[0]
            _, offset, vaddr, _, filesz, _ = struct.unpack_from(
                "<6I", self.data, phoff)
            self.base, self.offset, self.size = vaddr, offset, filesz
            self.kind = "ELF"
        else:
            raise SystemExit("%s: not a PS-X EXE or an ELF" % path)

    def va(self, offset):
        return self.base + offset - self.offset

    def fo(self, addr):
        return addr - self.base + self.offset

    def holds(self, addr):
        return self.base <= addr < self.base + self.size

    def words(self):
        for at in range(self.offset, self.offset + self.size - 3, 4):
            yield at, struct.unpack_from("<I", self.data, at)[0]


def cmd_strings(args):
    img = Image(args.file)
    needle = args.text.encode("latin-1").replace(b"\\0", b"\x00")
    at = 0
    found = 0
    while True:
        at = img.data.find(needle, at)
        if at < 0:
            break
        found += 1
        print("0x%08X  file 0x%X  %r"
              % (img.va(at), at, img.data[max(0, at - 8):at + 24]))
        at += 1
    print("%d occurrences" % found)
    return 0


def cmd_xref(args):
    """Every instruction that builds one of the given addresses.

    A linear scan rather than a real dataflow: remember the last `lui` per
    register, and when an `addiu`, `ori` or memory op uses that register as its
    base, work out the constant. It misses addresses built across a branch and
    invents nothing, which is the right way round for this job.
    """
    img = Image(args.file)
    targets = {int(a, 0) for a in args.address}
    high = {}
    hits = 0
    for at, word in img.words():
        op = word >> 26
        rs, rt, imm = (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
        signed = imm - 0x10000 if imm & 0x8000 else imm
        if op == 0x0F:                                   # lui
            high[rt] = imm << 16
        elif op in (0x09, 0x0D):                         # addiu, ori
            if rs in high:
                value = (high[rs] + (signed if op == 0x09 else imm)) & 0xFFFFFFFF
                if value in targets:
                    print("0x%08X  builds 0x%08X" % (img.va(at), value))
                    hits += 1
                if op == 0x09:
                    high[rt] = value
        elif op in MEM_OPS and rs in high:
            value = (high[rs] + signed) & 0xFFFFFFFF
            if value in targets:
                print("0x%08X  accesses 0x%08X" % (img.va(at), value))
                hits += 1
    print("%d references" % hits)
    return 0


def cmd_dis(args):
    if Cs is None:
        raise SystemExit("capstone is required for dis")
    img = Image(args.file)
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    addr = int(args.address, 0)
    at = img.fo(addr)
    for step in range(0, args.length, 4):
        word = struct.unpack_from("<I", img.data, at + step)[0]
        op = word >> 26
        if op in (0x1E, 0x1F):
            # R5900 lq/sq. Capstone reads these as MSA and gets them wrong.
            rs, rt, imm = (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
            signed = imm - 0x10000 if imm & 0x8000 else imm
            text = "%-8s $%s, %d($%s)" % ("lq" if op == 0x1E else "sq",
                                          REGS[rt], signed, REGS[rs])
        else:
            got = list(md.disasm(img.data[at + step:at + step + 4], addr + step))
            text = ("%-8s %s" % (got[0].mnemonic, got[0].op_str) if got
                    else ".word 0x%08X" % word)
        print("%08X  %08X  %s" % (addr + step, word, text))
    return 0


def cmd_table(args):
    """Print a run of code pointers and the gaps between their targets.

    The gaps are the point. A table of routines whose sizes grow by a few bytes
    at a time is an unrolled loop indexed by a count, and that is what gave
    away both SLZ codecs before a single instruction was read.
    """
    img = Image(args.file)
    at = img.fo(int(args.address, 0))
    values = []
    while at + 4 <= len(img.data):
        value = struct.unpack_from("<I", img.data, at)[0]
        if not img.holds(value):
            break
        values.append(value)
        at += 4
    for index, value in enumerate(values):
        gap = "" if index == 0 else "  +0x%X" % (value - values[index - 1])
        print("%3d  0x%08X%s" % (index, value, gap))
    print("%d entries" % len(values))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Find the code behind a string in a MIPS executable.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("strings", help="locate a byte string, with its address")
    s.add_argument("file")
    s.add_argument("text", help=r"literal text; \0 means a NUL")
    s.set_defaults(func=cmd_strings)

    s = sub.add_parser("xref", help="find the code that builds an address")
    s.add_argument("file")
    s.add_argument("address", nargs="+")
    s.set_defaults(func=cmd_xref)

    s = sub.add_parser("dis", help="disassemble, with R5900 lq/sq handled")
    s.add_argument("file")
    s.add_argument("address")
    s.add_argument("--length", type=lambda v: int(v, 0), default=0x100)
    s.set_defaults(func=cmd_dis)

    s = sub.add_parser("table", help="print a pointer table and its gaps")
    s.add_argument("file")
    s.add_argument("address")
    s.set_defaults(func=cmd_table)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
