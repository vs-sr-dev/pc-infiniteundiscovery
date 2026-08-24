#!/usr/bin/env python3
"""
xex.py -- reader and decryptor for XEX2, the Xbox 360 executable format.

An .xex is a wrapper around an ordinary PE image. The wrapper carries the
metadata the console needs before it can load anything -- entry point, load
address, import libraries, region, media restrictions -- and then the PE image
itself, optionally compressed and optionally encrypted.

Getting at the PE takes three steps:

1. **Recover the session key.** The security info block carries a 16-byte AES
   key that is itself encrypted, AES-128-ECB, under a fixed key baked into
   every console. Retail discs use the retail key; development builds use an
   all-zero key. Decrypting the block with the right one yields the session
   key for this particular image.

2. **Decrypt the image.** AES-128-CBC with a zero IV, using the session key,
   over everything from `pe_data_offset` to the end of the file.

3. **Decompress.** The "basic" scheme is a run-length description of the
   address space: a list of (data length, zero length) pairs, where the data is
   copied from the stream and the zeros are the .bss-style gaps that were never
   stored. The "normal" scheme is LZX and is not implemented here.

The retail key is not a secret and never was -- it is public in every Xbox 360
emulator and homebrew toolchain, because it has to be in order to load a game
the console already loads. It is included here for the same reason.

Header layout
-------------
    0x00  4  magic "XEX2"
    0x04  4  module flags
    0x08  4  offset of the PE data within the file
    0x0C  4  reserved
    0x10  4  offset of the security info block
    0x14  4  optional header count
    0x18  .. optional headers, 8 bytes each: (key, value)

An optional header's low byte says how to read `value`: `0x00` or `0x01` means
the value *is* the datum, `0xFF` means it points at a length-prefixed block,
and anything else means it points at that many 4-byte words.

Security info (relative to its own offset)
------------------------------------------
    0x000  4  header size
    0x004  4  image size
    0x008 256 RSA signature
    0x10C  4  image flags
    0x110  4  load address
    0x140 16  media id
    0x150 16  encrypted AES session key
    0x178  4  region code
    0x17C  4  allowed media types
    0x180  4  page descriptor count

Usage
-----
    python tools/xex.py info    <file.xex>
    python tools/xex.py extract <file.xex> <out.exe>
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

# The two fixed key-encryption keys. Neither is secret.
RETAIL_KEY = bytes.fromhex("20b185a59d28fdc340583fbb0896bf91")
DEVKIT_KEY = bytes(16)

OPTIONAL_HEADER_NAMES = {
    0x000002FF: "RESOURCE_INFO",
    0x000003FF: "FILE_FORMAT_INFO",
    0x000005FF: "DELTA_PATCH_DESCRIPTOR",
    0x000080FF: "BOUNDING_PATH",
    0x00008105: "DEVICE_ID",
    0x00010001: "ORIGINAL_BASE_ADDRESS",
    0x00010100: "ENTRY_POINT",
    0x00010201: "IMAGE_BASE_ADDRESS",
    0x000103FF: "IMPORT_LIBRARIES",
    0x00018002: "CHECKSUM_TIMESTAMP",
    0x00018102: "ENABLED_FOR_CALLCAP",
    0x00018200: "ENABLED_FOR_FASTCAP",
    0x000183FF: "ORIGINAL_PE_NAME",
    0x000200FF: "STATIC_LIBRARIES",
    0x00020104: "TLS_INFO",
    0x00020200: "DEFAULT_STACK_SIZE",
    0x00020301: "DEFAULT_FILESYSTEM_CACHE_SIZE",
    0x00020401: "DEFAULT_HEAP_SIZE",
    0x00028002: "PAGE_HEAP_SIZE_AND_FLAGS",
    0x00030000: "SYSTEM_FLAGS",
    0x00040006: "EXECUTION_INFO",
    0x00040201: "TITLE_WORKSPACE_SIZE",
    0x00040310: "GAME_RATINGS",
    0x00040404: "LAN_KEY",
    0x000405FF: "XBOX360_LOGO",
    0x000406FF: "MULTIDISC_MEDIA_IDS",
    0x000407FF: "ALTERNATE_TITLE_IDS",
    0x00040801: "ADDITIONAL_TITLE_MEMORY",
    0x00E10402: "EXPORTS_BY_NAME",
}

REGION_NAMES = {
    0x000000FF: "NTSC/U (North America)",
    0x0000FF00: "NTSC/J (Japan and Asia)",
    0x00FF0000: "PAL (Europe and Australia)",
    0xFF000000: "Other",
    0xFFFFFFFF: "All regions",
}

ENCRYPTION_NAMES = {0: "none", 1: "normal (AES-128-CBC)"}
COMPRESSION_NAMES = {0: "none", 1: "basic", 2: "normal (LZX)", 3: "delta"}


# ---------------------------------------------------------------------------
# AES-128 decryption
#
# pycryptodome is used when it is installed, because it is roughly two orders
# of magnitude faster. The pure-Python implementation below is the fallback
# that keeps this tool dependency-free; it is correct but slow, and it verifies
# itself against the FIPS-197 test vector before use.
# ---------------------------------------------------------------------------

def _build_tables():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x ^= ((x << 1) ^ (0x1B if x & 0x80 else 0)) & 0xFF
    for i in range(255, 512):
        exp[i] = exp[i - 255]

    def inverse(a):
        return 0 if a == 0 else exp[255 - log[a]]

    def rotl8(v, n):
        return ((v << n) | (v >> (8 - n))) & 0xFF

    sbox = [0] * 256
    for a in range(256):
        b = inverse(a)
        sbox[a] = b ^ rotl8(b, 1) ^ rotl8(b, 2) ^ rotl8(b, 3) ^ rotl8(b, 4) ^ 0x63
    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    return exp, log, sbox, inv_sbox


_EXP, _LOG, _SBOX, _INV_SBOX = _build_tables()


def _gmul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


class PurePythonAES128:
    """Decrypt-only AES-128. Correct, and slow enough that you will notice."""

    def __init__(self, key):
        if len(key) != 16:
            raise ValueError("AES-128 needs a 16-byte key")
        self.round_keys = self._expand(key)

    @staticmethod
    def _expand(key):
        words = [list(key[i * 4:i * 4 + 4]) for i in range(4)]
        rcon = 1
        for i in range(4, 44):
            temp = list(words[i - 1])
            if i % 4 == 0:
                temp = temp[1:] + temp[:1]
                temp = [_SBOX[b] for b in temp]
                temp[0] ^= rcon
                rcon = ((rcon << 1) ^ 0x1B) & 0xFF if rcon & 0x80 else rcon << 1
            words.append([words[i - 4][j] ^ temp[j] for j in range(4)])
        return [sum(words[r * 4:r * 4 + 4], []) for r in range(11)]

    def decrypt_block(self, block):
        s = [block[i] ^ self.round_keys[10][i] for i in range(16)]
        for rnd in range(9, 0, -1):
            s = self._inv_shift_rows(s)
            s = [_INV_SBOX[b] for b in s]
            k = self.round_keys[rnd]
            s = [s[i] ^ k[i] for i in range(16)]
            s = self._inv_mix_columns(s)
        s = self._inv_shift_rows(s)
        s = [_INV_SBOX[b] for b in s]
        k = self.round_keys[0]
        return bytes(s[i] ^ k[i] for i in range(16))

    @staticmethod
    def _inv_shift_rows(s):
        out = list(s)
        for row in range(1, 4):
            col = [s[row + 4 * c] for c in range(4)]
            col = col[-row:] + col[:-row]
            for c in range(4):
                out[row + 4 * c] = col[c]
        return out

    @staticmethod
    def _inv_mix_columns(s):
        out = [0] * 16
        for c in range(4):
            a = s[c * 4:c * 4 + 4]
            out[c * 4 + 0] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
            out[c * 4 + 1] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
            out[c * 4 + 2] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
            out[c * 4 + 3] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)
        return out


def _self_test():
    """FIPS-197 appendix C.1: the canonical AES-128 vector."""
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    cipher = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    if PurePythonAES128(key).decrypt_block(cipher) != plain:
        raise RuntimeError("pure-Python AES failed its self test")


try:
    from Crypto.Cipher import AES as _PyCryptoAES
except ImportError:
    _PyCryptoAES = None


def aes_ecb_decrypt_block(key, block):
    if _PyCryptoAES is not None:
        return _PyCryptoAES.new(key, _PyCryptoAES.MODE_ECB).decrypt(block)
    _self_test()
    return PurePythonAES128(key).decrypt_block(block)


def aes_cbc_decrypt(key, data, iv=bytes(16)):
    if len(data) % 16:
        data = data[:len(data) - len(data) % 16]
    if _PyCryptoAES is not None:
        return _PyCryptoAES.new(key, _PyCryptoAES.MODE_CBC, iv=iv).decrypt(data)

    _self_test()
    print("  (pycryptodome not installed -- falling back to pure Python, "
          "this will take a few minutes)", file=sys.stderr)
    engine = PurePythonAES128(key)
    out = bytearray(len(data))
    prev = iv
    for off in range(0, len(data), 16):
        block = data[off:off + 16]
        clear = engine.decrypt_block(block)
        out[off:off + 16] = bytes(a ^ b for a, b in zip(clear, prev))
        prev = block
    return bytes(out)


# ---------------------------------------------------------------------------
# XEX2
# ---------------------------------------------------------------------------

class Xex:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        d = self.data
        if d[:4] != b"XEX2":
            raise ValueError("not an XEX2 file: %s" % path)
        (self.module_flags, self.pe_data_offset, self.reserved,
         self.security_offset, self.optional_count) = struct.unpack_from(">IIIII", d, 4)

        self.optional = []
        for i in range(self.optional_count):
            key, value = struct.unpack_from(">II", d, 0x18 + i * 8)
            self.optional.append((key, value))
        self.optional_map = dict(self.optional)

        so = self.security_offset
        self.security_header_size, self.image_size = struct.unpack_from(">II", d, so)
        self.image_flags = struct.unpack_from(">I", d, so + 0x10C)[0]
        self.load_address = struct.unpack_from(">I", d, so + 0x110)[0]
        self.media_id = d[so + 0x140:so + 0x150]
        self.encrypted_key = d[so + 0x150:so + 0x160]
        (self.region, self.allowed_media,
         self.page_descriptor_count) = struct.unpack_from(">III", d, so + 0x178)

        self._read_file_format_info()

    def _read_file_format_info(self):
        off = self.optional_map.get(0x000003FF)
        self.encryption = self.compression = None
        self.basic_blocks = []
        if off is None:
            return
        size, self.encryption, self.compression = struct.unpack_from(">IHH", self.data, off)
        if self.compression == 1:
            n = (size - 8) // 8
            for i in range(n):
                data_size, zero_size = struct.unpack_from(">II", self.data, off + 8 + i * 8)
                self.basic_blocks.append((data_size, zero_size))

    # -- decryption --------------------------------------------------------

    def session_key(self, keyname="retail"):
        base = {"retail": RETAIL_KEY, "devkit": DEVKIT_KEY}[keyname]
        return aes_ecb_decrypt_block(base, self.encrypted_key)

    def decrypt_image(self, keyname=None):
        """Return the decrypted, decompressed PE image."""
        body = self.data[self.pe_data_offset:]

        if self.encryption == 0:
            clear = body
        else:
            names = [keyname] if keyname else ["retail", "devkit"]
            clear = None
            for name in names:
                candidate = aes_cbc_decrypt(self.session_key(name), body)
                if candidate[:2] == b"MZ":
                    self.key_used = name
                    clear = candidate
                    break
            if clear is None:
                raise ValueError(
                    "decryption produced no PE header with any known key; "
                    "the image may use a key this tool does not have")

        if self.compression in (0, None):
            return clear
        if self.compression == 1:
            out = bytearray()
            pos = 0
            for data_size, zero_size in self.basic_blocks:
                out += clear[pos:pos + data_size]
                pos += data_size
                out += bytes(zero_size)
            return bytes(out)
        raise NotImplementedError(
            "compression type %d (%s) is not implemented"
            % (self.compression, COMPRESSION_NAMES.get(self.compression, "?")))


def _decode_execution_info(blob):
    (media_id, version, base_version, title_id) = struct.unpack_from(">IIII", blob, 0)
    platform, exec_table, disc_number, disc_count = blob[16:20]
    savegame_id = struct.unpack_from(">I", blob, 20)[0]
    title_ascii = struct.pack(">I", title_id)
    return [
        "media id (low)  0x%08X" % media_id,
        "version         %d, base version %d" % (version, base_version),
        "title id        0x%08X  (%r)" % (title_id, title_ascii[:2].decode("latin-1")),
        "platform        %d, executable table %d" % (platform, exec_table),
        "disc            %d of %d" % (disc_number, disc_count),
        "savegame id     0x%08X" % savegame_id,
    ]


def _decode_resource_info(blob):
    out = []
    for i in range(len(blob) // 16):
        name, address, size = struct.unpack_from(">8sII", blob, i * 16)
        out.append("resource %r at 0x%08X, %d bytes"
                   % (name.rstrip(b"\0").decode("latin-1"), address, size))
    return out


def _decode_import_libraries(blob):
    """The block opens with a string-table size and a library count, then the
    NUL-separated names, then one descriptor per library."""
    table_size, count = struct.unpack_from(">II", blob, 0)
    names = blob[8:8 + table_size].split(b"\0")
    out = ["%d import librar%s" % (count, "y" if count == 1 else "ies")]
    for raw in names:
        text = raw.decode("latin-1", "replace").strip()
        if text:
            out.append("  %s" % text)
    return out


def _decode_pe_name(blob):
    return ["original name %s" % blob.split(b"\0")[0].decode("latin-1", "replace")]


def _decode_static_libraries(blob):
    out = []
    for i in range(len(blob) // 16):
        name, major, minor, build, qfe = struct.unpack_from(">8sHHHH", blob, i * 16)
        text = name.rstrip(b"\0").decode("latin-1", "replace")
        if not text:
            continue
        out.append("%-10s %d.%d.%d.%d" % (text, major, minor, build, qfe & 0x7FFF))
    return out


def _decode_multidisc_media_ids(blob):
    return ["disc %d media id %s" % (i + 1, blob[i * 16:i * 16 + 16].hex())
            for i in range(len(blob) // 16)]


def _decode_game_ratings(blob):
    boards = ["ESRB", "PEGI", "PEGI-FI", "PEGI-PT", "PEGI-UK", "OFLC-AU", "OFLC-NZ",
              "KMRB", "BRAZIL", "FPB"]
    out = []
    for i, name in enumerate(boards):
        if i < len(blob) and blob[i] != 0xFF:
            out.append("%-8s 0x%02X" % (name, blob[i]))
    return out or ["all boards unrated (0xFF)"]


def _decode_checksum_timestamp(blob):
    import datetime
    checksum, stamp = struct.unpack_from(">II", blob, 0)
    when = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
    return ["checksum 0x%08X" % checksum,
            "timestamp 0x%08X  %s" % (stamp, when.isoformat())]


STRUCTURED_DECODERS = {
    0x00040006: _decode_execution_info,
    0x000002FF: _decode_resource_info,
    0x000200FF: _decode_static_libraries,
    0x000406FF: _decode_multidisc_media_ids,
    0x00040310: _decode_game_ratings,
    0x00018002: _decode_checksum_timestamp,
    0x000103FF: _decode_import_libraries,
    0x000183FF: _decode_pe_name,
}


def optional_payload(xex, key, value):
    """Return the raw bytes an optional header points at, or None if it is inline."""
    low = key & 0xFF
    d = xex.data
    if low in (0x00, 0x01):
        return None
    if low == 0xFF:
        size = struct.unpack_from(">I", d, value)[0]
        return d[value + 4:value + size]
    return d[value:value + low * 4]


def describe_optional(xex, key, value):
    """Render one optional header's payload in whatever way suits its type."""
    low = key & 0xFF
    if low in (0x00, 0x01):
        return "0x%08X" % value
    blob = optional_payload(xex, key, value)
    return "@0x%X  %d bytes  %s" % (value, len(blob), blob[:32].hex(" "))


def cmd_info(args):
    xex = Xex(args.file)
    print("file             : %s" % os.path.basename(args.file))
    print("size             : %d bytes" % len(xex.data))
    print("module flags     : 0x%08X" % xex.module_flags)
    print("PE data offset   : 0x%X" % xex.pe_data_offset)
    print("image size       : 0x%X (%d bytes)" % (xex.image_size, xex.image_size))
    print("load address     : 0x%08X" % xex.load_address)
    print("image flags      : 0x%08X" % xex.image_flags)
    print("media id         : %s" % xex.media_id.hex())
    print("region           : 0x%08X  %s"
          % (xex.region, REGION_NAMES.get(xex.region, "unknown")))
    print("allowed media    : 0x%08X" % xex.allowed_media)
    print("page descriptors : %d" % xex.page_descriptor_count)
    print("encryption       : %s" % ENCRYPTION_NAMES.get(xex.encryption, xex.encryption))
    print("compression      : %s" % COMPRESSION_NAMES.get(xex.compression, xex.compression))
    if xex.basic_blocks:
        print("basic blocks     : %d" % len(xex.basic_blocks))
        for i, (ds, zs) in enumerate(xex.basic_blocks):
            print("    [%d] data 0x%08X  zero 0x%08X" % (i, ds, zs))
    print("encrypted key    : %s" % xex.encrypted_key.hex())
    for name in ("retail", "devkit"):
        print("session key (%-6s): %s" % (name, xex.session_key(name).hex()))
    print()
    print("optional headers : %d" % xex.optional_count)
    for key, value in xex.optional:
        print("  0x%08X %-30s %s"
              % (key, OPTIONAL_HEADER_NAMES.get(key, "unknown"),
                 describe_optional(xex, key, value)))
        decoder = STRUCTURED_DECODERS.get(key)
        if decoder is None:
            continue
        blob = optional_payload(xex, key, value)
        try:
            lines = decoder(blob)
        except (struct.error, ValueError, IndexError) as exc:
            lines = ["<could not decode: %s>" % exc]
        for line in lines:
            print("               %s" % line)
    return 0


def cmd_extract(args):
    xex = Xex(args.file)
    image = xex.decrypt_image(args.key)
    with open(args.output, "wb") as fo:
        fo.write(image)
    print("key used   : %s" % getattr(xex, "key_used", "none (unencrypted)"))
    print("wrote      : %s, %d bytes" % (args.output, len(image)))
    print("PE header  : %s" % ("yes" if image[:2] == b"MZ" else "NO -- check the key"))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Reader and decryptor for XEX2 Xbox 360 executables.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="print every header field")
    s.add_argument("file")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("extract", help="decrypt and decompress to a PE image")
    s.add_argument("file")
    s.add_argument("output")
    s.add_argument("--key", choices=["retail", "devkit"], default=None,
                   help="force a key-encryption key (default: try both)")
    s.set_defaults(func=cmd_extract)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
