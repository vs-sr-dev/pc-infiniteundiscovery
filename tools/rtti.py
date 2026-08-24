#!/usr/bin/env python3
"""
rtti.py -- recover a C++ class inventory from MSVC RTTI type descriptors.

A Visual C++ binary built with RTTI enabled carries, for every polymorphic
type, a `type_descriptor` whose name field holds the mangled type name. Those
names survive into the shipped executable because `dynamic_cast` and
`typeid` need them at runtime. Nothing else about the build has to be
preserved for this to work -- no symbols, no PDB, no debug section.

So a retail binary that uses RTTI hands you its class hierarchy for free. This
tool finds those names and demangles them.

Mangled form
------------
    ?AVName@@              class Name
    ?AUName@@              struct Name
    ?AW4Name@@             enum Name
    ?AVName@Namespace@@    class Namespace::Name

Namespace fragments are stored innermost-first, so they read backwards.
Templates are `?$Name@` followed by arguments and a closing `@`:

    ?AV?$TArray@PAVCAIAStarPoint@@$0A@@Aska@@
        -> class Aska::TArray<CAIAStarPoint *, 0>

Integer template arguments use MSVC's number encoding: `A@` is zero, a bare
digit `d` means `d + 1`, longer values are base-16 in the letters `A`..`P`
terminated by `@`, and a leading `?` negates.

This implements the subset of the grammar that RTTI names actually use.
Anything it cannot parse is reported verbatim and counted, so the failure rate
is always visible rather than silently swallowed.

Usage
-----
    python tools/rtti.py list   <image> [--filter TEXT] [--csv out.csv]
    python tools/rtti.py groups <image> [--min N]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys

# Type descriptor names as they appear in the binary.
NAME_PATTERN = re.compile(rb"\?A[VUW][0-9A-Za-z_@?$]{2,400}")

KIND_NAMES = {"V": "class", "U": "struct", "W4": "enum", "T": "union"}

BASIC_TYPES = {
    "C": "signed char", "D": "char", "E": "unsigned char",
    "F": "short", "G": "unsigned short",
    "H": "int", "I": "unsigned int",
    "J": "long", "K": "unsigned long",
    "M": "float", "N": "double", "O": "long double",
    "X": "void", "Z": "...",
    "_N": "bool", "_J": "__int64", "_K": "unsigned __int64", "_W": "wchar_t",
}


class DemangleError(Exception):
    pass


class Demangler:
    """Recursive-descent parser over the RTTI subset of MSVC mangling."""

    def __init__(self, text):
        self.text = text
        self.pos = 0

    # -- primitives --------------------------------------------------------

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, n=1):
        out = self.text[self.pos:self.pos + n]
        if len(out) < n:
            raise DemangleError("ran off the end")
        self.pos += n
        return out

    def expect(self, ch):
        if self.take(1) != ch:
            raise DemangleError("expected %r at %d" % (ch, self.pos - 1))

    # -- names -------------------------------------------------------------

    def parse_identifier(self):
        start = self.pos
        while self.peek() and self.peek() != "@":
            self.pos += 1
        if self.pos == start:
            raise DemangleError("empty identifier at %d" % start)
        name = self.text[start:self.pos]
        self.expect("@")
        return name

    def parse_fragment(self):
        if self.text.startswith("?$", self.pos):
            self.take(2)
            name = self.parse_identifier()
            args = []
            while self.peek() and self.peek() != "@":
                args.append(self.parse_template_argument())
            self.expect("@")
            return "%s<%s>" % (name, ", ".join(args))
        return self.parse_identifier()

    def parse_qualified_name(self):
        """Fragments run innermost-first and end with an empty fragment."""
        fragments = []
        while True:
            if not self.peek():
                raise DemangleError("unterminated qualified name")
            if self.peek() == "@":
                self.take(1)
                break
            fragments.append(self.parse_fragment())
            if len(fragments) > 32:
                raise DemangleError("qualified name too deep")
        if not fragments:
            raise DemangleError("qualified name with no fragments")
        return "::".join(reversed(fragments))

    # -- numbers -----------------------------------------------------------

    def parse_number(self):
        negative = False
        if self.peek() == "?":
            self.take(1)
            negative = True
        ch = self.peek()
        if ch.isdigit():
            self.take(1)
            value = int(ch) + 1
        elif "A" <= ch <= "P":
            value = 0
            while "A" <= self.peek() <= "P":
                value = value * 16 + (ord(self.take(1)) - ord("A"))
            self.expect("@")
        else:
            raise DemangleError("bad number at %d" % self.pos)
        return -value if negative else value

    # -- types -------------------------------------------------------------

    def parse_template_argument(self):
        if self.peek() == "$":
            self.take(1)
            marker = self.peek()
            if marker == "0":
                self.take(1)
                return str(self.parse_number())
            if marker == "$":
                self.take(1)
                # $$C and friends are cv-qualifier wrappers; skip the tag.
                self.take(1)
                return self.parse_template_argument()
            raise DemangleError("unsupported template literal $%s" % marker)
        return self.parse_type()

    def parse_type(self):
        for prefix, suffix in (("PA", " *"), ("PB", " const *"),
                               ("QA", " *const"), ("AA", " &"), ("AB", " const &")):
            if self.text.startswith(prefix, self.pos):
                self.take(2)
                return self.parse_type() + suffix

        if self.text.startswith("W4", self.pos):
            self.take(2)
            return "enum " + self.parse_qualified_name()

        ch = self.peek()
        if ch in ("V", "U", "T"):
            self.take(1)
            keyword = {"V": "class", "U": "struct", "T": "union"}[ch]
            return "%s %s" % (keyword, self.parse_qualified_name())

        if ch == "_":
            token = self.take(2)
            if token in BASIC_TYPES:
                return BASIC_TYPES[token]
            raise DemangleError("unknown basic type %s" % token)

        if ch in BASIC_TYPES:
            self.take(1)
            return BASIC_TYPES[ch]

        raise DemangleError("unknown type marker %r at %d" % (ch, self.pos))

    # -- entry point -------------------------------------------------------

    def parse_type_descriptor(self):
        if not self.text.startswith("?A"):
            raise DemangleError("not a type descriptor")
        self.pos = 2
        if self.text.startswith("W4", self.pos):
            self.take(2)
            kind = "enum"
        else:
            ch = self.take(1)
            if ch not in KIND_NAMES:
                raise DemangleError("unknown kind %r" % ch)
            kind = KIND_NAMES[ch]
        name = self.parse_qualified_name()
        return kind, name


def demangle(text):
    """Return (kind, name), or raise DemangleError."""
    return Demangler(text).parse_type_descriptor()


def extract(path):
    """Yield (raw, kind, name) for every type descriptor that parses."""
    with open(path, "rb") as fh:
        data = fh.read()

    seen = set()
    results = []
    failures = []
    for match in NAME_PATTERN.findall(data):
        raw = match.decode("latin-1")
        if raw in seen:
            continue
        seen.add(raw)
        # A descriptor name always ends at its first "@@" that closes the
        # qualified name; the regex greedily grabs whatever follows it.
        try:
            kind, name = demangle(raw)
        except DemangleError:
            # Retry against successively shorter prefixes: adjacent strings in
            # the binary run together and the regex cannot tell where one ends.
            for end in range(len(raw), 4, -1):
                if not raw.startswith("?A", 0):
                    break
                try:
                    kind, name = demangle(raw[:end])
                except DemangleError:
                    continue
                results.append((raw[:end], kind, name))
                break
            else:
                failures.append(raw)
            continue
        results.append((raw, kind, name))
    return results, failures


def top_level_group(name):
    """The leading namespace, or a heuristic prefix for flat C-style names."""
    if "::" in name:
        return name.split("::", 1)[0]
    bare = name.split("<", 1)[0]
    for prefix in ("AIBehavior_", "AIObject", "AIFsm", "AI",
                   "BtlShootCallback_", "BtlSigCallBack_", "BtlEffCol_", "Btl",
                   "CTutorial", "CResource", "CSensor", "CAI", "C"):
        if bare.startswith(prefix):
            return prefix
    return "(other)"


def cmd_list(args):
    results, failures = extract(args.image)
    rows = sorted({(name, kind) for _, kind, name in results})
    if args.filter:
        needle = args.filter.lower()
        rows = [r for r in rows if needle in r[0].lower()]

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fo:
            writer = csv.writer(fo)
            writer.writerow(["name", "kind"])
            writer.writerows((name, kind) for name, kind in rows)
        print("wrote %d names to %s" % (len(rows), args.csv))
    else:
        for name, kind in rows:
            print("%-6s %s" % (kind, name))

    print("%d demangled, %d unparsed" % (len(rows), len(failures)), file=sys.stderr)
    return 0


def cmd_groups(args):
    results, failures = extract(args.image)
    names = sorted({name for _, _, name in results})
    tally = collections.Counter(top_level_group(n) for n in names)
    print("%-24s %6s" % ("group", "types"))
    print("%-24s %6s" % ("-" * 24, "-" * 6))
    for group, count in tally.most_common():
        if count >= args.min:
            print("%-24s %6d" % (group, count))
    print()
    print("%d distinct types, %d unparsed strings" % (len(names), len(failures)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Recover a C++ class inventory from MSVC RTTI type descriptors.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="print every demangled type name")
    s.add_argument("image", help="a decrypted PE image")
    s.add_argument("--filter", help="only names containing this text")
    s.add_argument("--csv", help="write to CSV instead of stdout")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("groups", help="tally types by leading namespace or prefix")
    s.add_argument("image")
    s.add_argument("--min", type=int, default=1, help="hide groups below this size")
    s.set_defaults(func=cmd_groups)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
