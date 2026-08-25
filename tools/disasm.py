#!/usr/bin/env python3
"""
disasm.py -- find the code behind a string, in a MIPS or PowerPC executable.

This is the tool sessions 17 and 18 used to read four compressors, and it exists
because the method that worked is worth keeping rather than the addresses it
produced. The method is three steps:

1.  `strings` -- find the magic in the image and note its virtual address.
2.  `xref` -- find the code that constructs that address. Both architectures
    build a 32-bit constant the same way, in two halves: `lui` then
    `addiu`/`ori` on MIPS, `lis` then `addi`/`ori` on PowerPC, or a load or
    store using the high half as its base. A linear pass that remembers the
    last high half per register catches essentially all of them, and there are
    usually one or two.
3.  `dis` -- read the function.

For `SLZ` that took about ten minutes and gave up a dispatcher with the method
byte in it. What made the result trustworthy rather than merely plausible was
that one arm of that dispatcher had to be method 1, which had been specified
two sessions earlier from the outside, by search. It was. A disassembly with no
such check in it is worth much less.

Three image formats, because they are the three these discs use:

* **`PS-X EXE`**, the PlayStation's. A 0x800-byte header, then a flat image;
  the load address and size are in the header at 0x18. MIPS, little-endian.
* **ELF**, the PlayStation 2's. The first program header is the loaded image;
  the rest are overlays with no file content. MIPS, little-endian.
* **a flat image with `--base`**, which is what `xex.py extract` writes for an
  Xbox 360 executable -- a decrypted PowerPC image where a file offset is an
  RVA. Big-endian; pass `--base 0x82000000`.

The PlayStation 2 is an R5900, which has `lq` and `sq` -- 128-bit load and
store, used for register saves in every prologue. Capstone decodes those
opcodes as MSA vector instructions, which is wrong and noisy, so they are
disassembled here by hand and everything else is handed to capstone. Capstone
also gives up on the odd PowerPC word, so `dis` never stops on one: an
instruction it cannot read is printed as `.word` and the walk continues.

    python tools/disasm.py strings extract/ps1/SCUS_944.21 SLZ
    python tools/disasm.py xref    extract/ps1/SCUS_944.21 0x8002A860
    python tools/disasm.py dis     extract/ps1/SCUS_944.21 0x800121A8 --length 0xF0
    python tools/disasm.py table   extract/ps1/SCUS_944.21 0x8002A868

    python tools/disasm.py strings extract/es/default.exe index.vmtoc --base 0x82000000
    python tools/disasm.py xref    extract/es/default.exe 0x82082E8C --base 0x82000000
    python tools/disasm.py dis     extract/es/default.exe 0x8210E0F8 --base 0x82000000
"""

import argparse
import struct
import sys

try:
    from capstone import (Cs, CS_ARCH_MIPS, CS_ARCH_PPC, CS_MODE_MIPS32,
                          CS_MODE_32, CS_MODE_LITTLE_ENDIAN, CS_MODE_BIG_ENDIAN)
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
    """A loaded executable: file bytes, plus where the code sits in memory.

    The two console formats say where they load; a flat image does not, so
    `base` has to be given for one. A base also picks the architecture, because
    the only flat images here are decrypted Xbox 360 executables.
    """

    def __init__(self, path, base=None):
        self.data = open(path, "rb").read()
        if base is not None:
            self.base, self.offset, self.size = base, 0, len(self.data)
            self.kind, self.big, self.arch = "flat", True, "ppc"
        elif self.data[:8] == b"PS-X EXE":
            load, size = struct.unpack_from("<II", self.data, 0x18)
            self.base, self.offset, self.size = load, 0x800, size
            self.kind, self.big, self.arch = "PS-X EXE", False, "mips"
        elif self.data[:4] == b"\x7fELF":
            phoff = struct.unpack_from("<I", self.data, 0x1C)[0]
            _, offset, vaddr, _, filesz, _ = struct.unpack_from(
                "<6I", self.data, phoff)
            self.base, self.offset, self.size = vaddr, offset, filesz
            self.kind, self.big, self.arch = "ELF", False, "mips"
        else:
            raise SystemExit("%s: not a PS-X EXE or an ELF -- give --base for "
                             "a flat PowerPC image" % path)

    @property
    def endian(self):
        return ">" if self.big else "<"

    def va(self, offset):
        return self.base + offset - self.offset

    def fo(self, addr):
        return addr - self.base + self.offset

    def holds(self, addr):
        return self.base <= addr < self.base + self.size

    def word(self, at):
        return struct.unpack_from(self.endian + "I", self.data, at)[0]

    def words(self):
        for at in range(self.offset, self.offset + self.size - 3, 4):
            yield at, self.word(at)

    def capstone(self):
        if Cs is None:
            raise SystemExit("capstone is required for dis")
        if self.arch == "ppc":
            return Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
        return Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)


def cmd_strings(args):
    img = Image(args.file, args.base)
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
    img = Image(args.file, args.base)
    targets = {int(a, 0) for a in args.address}
    scan = _xref_ppc if img.arch == "ppc" else _xref_mips
    hits = 0
    for addr, value, how in scan(img, targets):
        print("0x%08X  %-8s 0x%08X" % (addr, how, value))
        hits += 1
    print("%d references" % hits)
    return 0


def _xref_mips(img, targets):
    high = {}
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
                    yield img.va(at), value, "builds"
                if op == 0x09:
                    high[rt] = value
        elif op in MEM_OPS and rs in high:
            value = (high[rs] + signed) & 0xFFFFFFFF
            if value in targets:
                yield img.va(at), value, "accesses"


# PowerPC memory ops whose D field is an offset from rA, so a preceding `lis`
# makes them an address reference too: lbz/lhz/lha/lwz and their stores.
PPC_MEM = {32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47,
           48, 50, 52, 54}


def _xref_ppc(img, targets):
    """The same idea as the MIPS pass, with two things to be careful about.

    `addis rD, rA, SIMM` names its destination in bits 6..10 and its source in
    11..15; `ori rA, rS, UIMM` is the other way round, and reading them the same
    way silently tracks the wrong register. And an `addis` with a non-zero rA
    extends an address rather than starting one, which compilers do emit, so it
    is followed rather than treated as a fresh `lis`.
    """
    high = {}
    for at, word in img.words():
        op = word >> 26
        a, b, imm = (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
        signed = imm - 0x10000 if imm & 0x8000 else imm
        if op == 15:                                     # addis / lis
            if b == 0:
                high[a] = (imm << 16) & 0xFFFFFFFF
            elif b in high:
                high[a] = (high[b] + (imm << 16)) & 0xFFFFFFFF
            else:
                high.pop(a, None)
        elif op == 14:                                   # addi / li
            if b in high:
                value = (high[b] + signed) & 0xFFFFFFFF
                if value in targets:
                    yield img.va(at), value, "builds"
                high[a] = value
            else:
                high.pop(a, None)
        elif op == 24:                                   # ori rA, rS, UIMM
            if a in high:
                value = (high[a] | imm) & 0xFFFFFFFF
                if value in targets:
                    yield img.va(at), value, "builds"
                high[b] = value
            else:
                high.pop(b, None)
        elif op in PPC_MEM and b in high:
            value = (high[b] + signed) & 0xFFFFFFFF
            if value in targets:
                yield img.va(at), value, "accesses"


def cmd_dis(args):
    """One instruction at a time, so a word capstone cannot read stops nothing.

    Handing capstone a whole range makes it give up at the first word it does
    not recognise and return everything before it, which on an R5900 prologue
    or an odd PowerPC word looks exactly like the function ending early. It
    does not; that is how this tool nearly missed the function that mattered.
    """
    img = Image(args.file, args.base)
    md = img.capstone()
    addr = int(args.address, 0)
    at = img.fo(addr)
    for step in range(0, args.length, 4):
        if not 0 <= at + step + 4 <= len(img.data):
            break
        word = img.word(at + step)
        text = None
        if img.arch == "mips" and (word >> 26) in (0x1E, 0x1F):
            # R5900 lq/sq. Capstone reads these as MSA and gets them wrong.
            op = word >> 26
            rs, rt, imm = (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
            signed = imm - 0x10000 if imm & 0x8000 else imm
            text = "%-8s $%s, %d($%s)" % ("lq" if op == 0x1E else "sq",
                                          REGS[rt], signed, REGS[rs])
        if text is None:
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
    img = Image(args.file, args.base)
    at = img.fo(int(args.address, 0))
    values = []
    while at + 4 <= len(img.data):
        value = img.word(at)
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

    for action in sub.choices.values():
        action.add_argument("--base", type=lambda v: int(v, 0),
                            help="load address of a flat PowerPC image, e.g. "
                                 "0x82000000 for an Xbox 360 executable")

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
