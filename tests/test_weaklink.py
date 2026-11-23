import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "flutter/tools/weaklink.py"

LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_DYLD_CHAINED_FIXUPS = 0x80000034
LC_DYLD_INFO_ONLY = 0x80000022
HEADER_SIZE = 32  # 64-bit Mach-O header: eight uint32


def dylib(name, cmd=LC_LOAD_DYLIB):
    path = f"/System/Library/Frameworks/{name}.framework/{name}".encode() + b"\0"
    size = (24 + len(path) + 7) & ~7
    command = struct.pack("<6I", cmd, size, 24, 0, 0, 0) + path
    return command + bytes(size - len(command))


def chained_fixups(other_commands, blob):
    """An LC_DYLD_CHAINED_FIXUPS command whose dataoff points at blob,
    which the caller appends right after the load commands (the fixups
    command itself is always last, so 16 bytes for it are added here)."""
    dataoff = HEADER_SIZE + sum(map(len, other_commands)) + 16
    return struct.pack("<4I", LC_DYLD_CHAINED_FIXUPS, 16, dataoff, len(blob))


def dyld_info_only(bind_size=16, weak_bind_size=0, lazy_bind_size=0):
    """An LC_DYLD_INFO_ONLY command with the given bind table sizes."""
    return struct.pack("<12I", LC_DYLD_INFO_ONLY, 48, 0, 0, 0, bind_size,
                       0, weak_bind_size, 0, lazy_bind_size, 0, 0)


def fixups_blob(imports, imports_format=1, fixups_version=0, symbols_format=0,
                symbols=b"_$ss5NeverO7SwiftUI4ViewACWP\0_$s8symbol02D\0"):
    """A dyld_chained_fixups blob: header, an empty starts table
    (seg_count 0), the imports array, dummy symbol strings.

    imports is a list of (ordinal, weak, name_offset[, addend]) tuples;
    formats 2 and 3 take an addend. Entries follow Apple's
    mach-o/fixup-chains.h: DYLD_CHAINED_IMPORT and
    DYLD_CHAINED_IMPORT_ADDEND share the first uint32
    (lib_ordinal:8, weak_import:1 at bit 8, name_offset:23; ADDEND only
    appends an int32 addend), DYLD_CHAINED_IMPORT_ADDEND64 starts with a
    uint64 (lib_ordinal:16, weak_import:1 at bit 16, reserved:15,
    name_offset:32) followed by a uint64 addend.
    """
    entries = b""
    for item in imports:
        ordinal, weak, name_offset = item[0], item[1], item[2]
        addend = item[3] if len(item) > 3 else 0
        if imports_format == 1:      # DYLD_CHAINED_IMPORT: one uint32
            entries += struct.pack("<I", (name_offset << 9) | (weak << 8) | ordinal)
        elif imports_format == 2:    # DYLD_CHAINED_IMPORT_ADDEND: + int32 addend
            entries += struct.pack("<Ii",
                                   (name_offset << 9) | (weak << 8) | ordinal,
                                   addend)
        else:                        # DYLD_CHAINED_IMPORT_ADDEND64: uint64 + uint64
            entries += struct.pack("<QQ",
                                   (name_offset << 32) | (weak << 16) | ordinal,
                                   addend)
    header = struct.pack("<7I", fixups_version, 28, 32, 32 + len(entries),
                         len(imports), imports_format, symbols_format)
    starts = b"\0\0\0\0"  # dyld_chained_starts_in_image: seg_count 0
    return header + starts + entries + symbols


def executable(commands, count=None, size=None):
    return struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2,
                       len(commands) if count is None else count,
                       sum(map(len, commands)) if size is None else size, 0, 0) + b"".join(commands)


def with_fixups(imports, libraries=("SwiftUICore", "UIKit"), **blob_opts):
    """A thin executable plus its appended fixups blob."""
    libs = [dylib(name) for name in libraries]
    blob = fixups_blob(imports, **blob_opts)
    commands = libs + [chained_fixups(libs, blob)]
    return executable(commands) + blob


def fat_image(slices_data, align=12, cpu_type=0x0100000C):
    """A fat Mach-O wrapping the given thin binaries (one cputype)."""
    header_size = 8 + 20 * len(slices_data)
    out = bytearray(struct.pack(">2I", 0xCAFEBABE, len(slices_data)))
    offset = header_size
    entries = b""
    bodies = b""
    for body in slices_data:
        entries += struct.pack(">5I", cpu_type, 0, offset, len(body), align)
        bodies += body
        offset += len(body)
    return bytes(out + entries + bodies)


class WeaklinkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.binary = Path(temporary.name) / "Runner"

    def run_cli(self, *extra):
        if not extra:
            extra = ("SwiftUICore",)
        return subprocess.run([sys.executable, str(TOOL), str(self.binary), *extra],
                              capture_output=True, text=True, timeout=5, check=False)

    def rewrite(self, data, *extra):
        self.binary.write_bytes(data)
        return self.run_cli("SwiftUICore", *extra)

    def test_truncated_later_command_leaves_input_unchanged(self):
        first = dylib("SwiftUICore")
        data = executable([first, b"\0" * 4], count=2, size=len(first) + 8)
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.binary.read_bytes(), data, "failed parse must not partly rewrite the executable")
        self.assertIn("weaklink:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_valid_rewrite_changes_only_requested_command_and_is_idempotent(self):
        data = executable([dylib("SwiftUICore"), dylib("UIKit")])
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        struct.pack_into("<I", expected, 32, 0x80000018)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertIn("SwiftUICore LOAD -> WEAK", result.stdout)
        again = self.run_cli()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertIn("nothing to rewrite", again.stdout)

    def fixups_layout(self, commands):
        """File offset of the imports table of the appended blob."""
        blob_start = HEADER_SIZE + sum(map(len, commands))
        return blob_start + 32  # header (7 * 4) + seg_count 0

    def test_strong_import_into_weak_framework_becomes_weak(self):
        commands = [dylib("SwiftUICore"), dylib("UIKit"),
                    chained_fixups([], b"")]
        blob = fixups_blob([
            (1, 0, 0),    # strong, bound to SwiftUICore (ordinal 1)
            (2, 0, 8),    # strong, bound to UIKit -> stays strong
            (1, 1, 0),    # already weak -> untouched
            (255, 0, 8),  # special ordinal -> untouched
        ])
        commands[2] = chained_fixups(commands[:2], blob)
        data = executable(commands) + blob
        result = self.rewrite(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        struct.pack_into("<I", expected, 32, LC_LOAD_WEAK_DYLIB)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<I", expected, imports_at,
                         struct.unpack_from("<I", expected, imports_at)[0] | 0x100)
        patched = self.binary.read_bytes()
        self.assertEqual(patched, bytes(expected), "exactly the weak load command and the one weak-import bit must change")
        self.assertEqual(len(patched), len(data), "file length must not change")
        self.assertIn("SwiftUICore LOAD -> WEAK", result.stdout)
        self.assertIn("1 strong import -> weak", result.stdout)

    def test_second_run_changes_nothing(self):
        data = with_fixups([(1, 0, 0)])
        result = self.rewrite(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        once = self.binary.read_bytes()
        again = self.run_cli()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.binary.read_bytes(), once, "a second run must change no bytes")
        self.assertIn("nothing to rewrite", again.stdout)

    def test_weak_imports_flag_leaves_the_load_command_strong(self):
        commands = [dylib("SwiftUI"), dylib("UIKit"), chained_fixups([], b"")]
        blob = fixups_blob([(1, 0, 0)])  # strong import into SwiftUI
        commands[2] = chained_fixups(commands[:2], blob)
        data = executable(commands) + blob
        result = self.rewrite(data, "--weak-imports", "SwiftUI")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<I", expected, imports_at,
                         struct.unpack_from("<I", expected, imports_at)[0] | 0x100)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertEqual(struct.unpack_from("<I", self.binary.read_bytes(), 32)[0],
                         LC_LOAD_DYLIB, "SwiftUI's load command must stay strong")
        self.assertNotIn("LOAD -> WEAK", result.stdout)
        self.assertIn("SwiftUI: 1 strong import -> weak", result.stdout)

    def test_every_import_format_weaks_exactly_its_own_bit(self):
        imports = {1: [(1, 0, 0, 0)],
                   2: [(1, 0, 0, -8)],
                   3: [(1, 0, 0, 1 << 40)]}
        for fmt, entries in imports.items():
            with self.subTest(format=fmt):
                commands = [dylib("SwiftUICore"), chained_fixups([], b"")]
                blob = fixups_blob(entries, imports_format=fmt)
                commands[1] = chained_fixups(commands[:1], blob)
                data = executable(commands) + blob
                result = self.rewrite(data)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = bytearray(data)
                struct.pack_into("<I", expected, 32, LC_LOAD_WEAK_DYLIB)
                imports_at = self.fixups_layout(commands)
                if fmt in (1, 2):
                    # weak_import is bit 8 of the first uint32 (both
                    # formats share that word per fixup-chains.h).
                    struct.pack_into("<I", expected, imports_at, 0x101)
                else:
                    # ADDEND64: weak_import is bit 16 of the first uint64.
                    struct.pack_into("<Q", expected, imports_at, 0x10001)
                self.assertEqual(self.binary.read_bytes(), bytes(expected),
                                 "only the weak bit may change; addend and reserved stay byte-identical")

    def test_format2_weak_bit_is_bit_eight_of_an_eight_bit_ordinal(self):
        """Pins DYLD_CHAINED_IMPORT_ADDEND to the header layout: the weak
        bit is bit 8, just above an 8-bit lib_ordinal. A name_offset of
        300 reaches into the bits the old (wrong) layout called the
        ordinal, so a tool reading ordinal:16/weak:16 would reject or
        mispatch this file."""
        commands = [dylib("SwiftUICore"), dylib("UIKit"), chained_fixups([], b"")]
        blob = fixups_blob([(2, 0, 300, -8)], imports_format=2)
        commands[2] = chained_fixups(commands[:2], blob)
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "UIKit")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<I", expected, imports_at,
                         struct.unpack_from("<I", expected, imports_at)[0] | 0x100)
        self.assertEqual(self.binary.read_bytes(), bytes(expected),
                         "exactly the bit-8 weak flag may change; ordinal, "
                         "name offset and addend stay byte-identical")
        self.assertIn("UIKit: 1 strong import -> weak", result.stdout)

    def test_special_ordinals_pass_through_in_format1(self):
        commands = [dylib("SwiftUICore"), chained_fixups([], b"")]
        # 0 = self, 253 = weak lookup (-3), 254 = flat lookup (-2),
        # 255 = main executable (-1) — all past the 0xF0 normal-ordinal
        # limit, hence special per fixup-chains.h.
        blob = fixups_blob([(0, 0, 0), (253, 0, 8), (254, 0, 16), (255, 0, 24)],
                           imports_format=1)
        commands[1] = chained_fixups(commands[:1], blob)
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUICore")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.binary.read_bytes(), data,
                         "special ordinals must stay untouched")
        self.assertIn("nothing to rewrite", result.stdout)

    def test_special_ordinals_pass_through_in_format3(self):
        commands = [dylib("SwiftUICore"), chained_fixups([], b"")]
        # The same specials in the 16-bit field: 0 = self, 0xFFFD =
        # weak lookup (-3), 0xFFFE = flat lookup (-2), 0xFFFF = main
        # executable (-1) — all past the 0xFFF0 normal-ordinal limit,
        # hence special per fixup-chains.h.
        blob = fixups_blob([(0, 0, 32), (0xFFFD, 0, 0), (0xFFFE, 0, 8),
                            (0xFFFF, 0, 16)],
                           imports_format=3)
        commands[1] = chained_fixups(commands[:1], blob)
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUICore")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.binary.read_bytes(), data,
                         "16-bit negative specials must stay untouched")
        self.assertIn("nothing to rewrite", result.stdout)

    def test_format1_ordinal_130_is_a_library_index(self):
        """Pins the fixup-chains.h rule against the old signed reading:
        in the 8-bit field only 0 and 0xF1..0xFF are special, so
        ordinal 130 — which an int8 cast turns into -126 — is an
        ordinary library index and must be weakened, not skipped."""
        libraries = tuple(f"L{i}" for i in range(129)) + ("SwiftUICore",)
        libs = [dylib(name) for name in libraries]
        blob = fixups_blob([(130, 0, 0)])  # strong, bound to ordinal 130
        commands = libs + [chained_fixups(libs, blob)]
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUICore")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<I", expected, imports_at,
                         struct.unpack_from("<I", expected, imports_at)[0] | 0x100)
        self.assertEqual(self.binary.read_bytes(), bytes(expected),
                         "ordinal 130 into SwiftUICore must be weakened")
        self.assertIn("SwiftUICore: 1 strong import -> weak", result.stdout)

    def test_format1_ordinal_limit_is_0xF0_not_the_sign_bit(self):
        """The 8-bit boundary per fixup-chains.h: 0xF0 (240) is the last
        normal ordinal, 0xF1..0xFF are the negative specials — so 241
        stays untouched without an out-of-list error, like 0 and 255."""
        libraries = tuple(f"L{i}" for i in range(239)) + ("SwiftUICore",)
        libs = [dylib(name) for name in libraries]
        blob = fixups_blob([
            (240, 0, 0),   # 0xF0: last normal ordinal -> weakened
            (241, 0, 8),   # 0xF1 = weak lookup (-3): special, no error
            (0, 0, 16),    # self
            (255, 0, 24),  # main executable (-1)
        ])
        commands = libs + [chained_fixups(libs, blob)]
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUICore")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<I", expected, imports_at,
                         struct.unpack_from("<I", expected, imports_at)[0] | 0x100)
        self.assertEqual(self.binary.read_bytes(), bytes(expected),
                         "only the 0xF0 import may change; 0xF1, 0 and 0xFF stay untouched")
        self.assertIn("SwiftUICore: 1 strong import -> weak", result.stdout)

    def test_ordinal_241_is_a_library_index_in_format3(self):
        """Pins the 16-bit width of the format-3 ordinal field: 0x00F1
        (241) is an ordinary library index, not the 8-bit special 0xF1 —
        with the default two dylibs it lands one past the list end and
        is an error, never a silent pass-through."""
        data = with_fixups([(0x00F1, 0, 0)], imports_format=3)
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.binary.read_bytes(), data,
                         "a refused binary must stay unchanged")
        self.assertIn("dylib ordinal 241", result.stderr)

    def test_format3_ordinal_0x8000_is_a_library_index(self):
        """Pins the 16-bit field against the old signed reading: 0x8000
        is an ordinary library index (an int16 cast would call it
        -32768 and skip it), 0xFFF1 is the negative-special start."""
        libraries = tuple(f"L{i}" for i in range(0x7FFF)) + ("SwiftUICore",)
        libs = [dylib(name) for name in libraries]
        blob = fixups_blob([(0x8000, 0, 0), (0xFFF1, 0, 8)], imports_format=3)
        commands = libs + [chained_fixups(libs, blob)]
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUICore")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<Q", expected, imports_at,
                         struct.unpack_from("<Q", expected, imports_at)[0] | (1 << 16))
        self.assertEqual(self.binary.read_bytes(), bytes(expected),
                         "ordinal 0x8000 must be weakened, 0xFFF1 stay untouched")
        self.assertIn("SwiftUICore: 1 strong import -> weak", result.stdout)

    def test_format3_ordinal_limit_is_0xFFF0(self):
        """The 16-bit boundary per fixup-chains.h: 0xFFF0 (65520) is the
        last normal ordinal, 0xFFF1 (weak lookup) is special."""
        libraries = tuple(f"L{i}" for i in range(0xFFF0 - 1)) + ("SwiftUICore",)
        libs = [dylib(name) for name in libraries]
        blob = fixups_blob([(0xFFF0, 0, 0), (0xFFF1, 0, 8)], imports_format=3)
        commands = libs + [chained_fixups(libs, blob)]
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUICore")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<Q", expected, imports_at,
                         struct.unpack_from("<Q", expected, imports_at)[0] | (1 << 16))
        self.assertEqual(self.binary.read_bytes(), bytes(expected),
                         "only the 0xFFF0 import may change; 0xFFF1 stays untouched")
        self.assertIn("SwiftUICore: 1 strong import -> weak", result.stdout)

    def test_lazy_binds_alone_are_refused(self):
        data = executable([dylib("SwiftUICore"),
                           dyld_info_only(lazy_bind_size=16)])
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.binary.read_bytes(), data,
                         "a refused binary must stay unchanged")
        self.assertIn("classic dyld bind opcodes are not supported", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_input_without_arm64_slice_fails_closed(self):
        x86 = bytearray(executable([dylib("SwiftUICore")]))
        struct.pack_into("<I", x86, 4, 0x01000007)  # CPU_TYPE_X86_64
        cases = {
            "not a Mach-O": b"\0" * 64,
            "fat without an arm64 slice": fat_image([bytes(x86)],
                                                    cpu_type=0x01000007),
            "fat with zero arches": struct.pack(">2I", 0xCAFEBABE, 0),
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.binary.write_bytes(data)
                result = self.run_cli()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("no arm64 Mach-O slice found", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_truncated_fat_table_fails_closed(self):
        # Promises three arch entries but carries only one.
        data = struct.pack(">2I", 0xCAFEBABE, 3) + \
            struct.pack(">5I", 0x0100000C, 0, 0, 0, 12)
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("too short for its arch table", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_fat_with_more_than_eight_slices_patches_all(self):
        body = executable([dylib("SwiftUICore")])
        data = fat_image([body] * 9)
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        patched = self.binary.read_bytes()
        self.assertEqual(len(patched), len(data), "file length must not change")
        base = 8 + 20 * 9
        for i in range(9):
            at = base + i * len(body) + 32
            self.assertEqual(struct.unpack_from("<I", patched, at)[0],
                             LC_LOAD_WEAK_DYLIB,
                             f"slice {i} must be patched")
        self.assertEqual(result.stdout.count("LOAD -> WEAK"), 9)

    def test_weak_imports_alone_is_a_valid_call(self):
        commands = [dylib("SwiftUI"), chained_fixups([], b"")]
        blob = fixups_blob([(1, 0, 0)])
        commands[1] = chained_fixups(commands[:1], blob)
        data = executable(commands) + blob
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-imports", "SwiftUI")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        imports_at = self.fixups_layout(commands)
        struct.pack_into("<I", expected, imports_at,
                         struct.unpack_from("<I", expected, imports_at)[0] | 0x100)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertEqual(struct.unpack_from("<I", self.binary.read_bytes(), 32)[0],
                         LC_LOAD_DYLIB, "the load command must stay strong")
        self.assertIn("SwiftUI: 1 strong import -> weak", result.stdout)

    def test_call_with_neither_frameworks_nor_imports_is_usage(self):
        self.binary.write_bytes(executable([dylib("SwiftUICore")]))
        result = subprocess.run([sys.executable, str(TOOL), str(self.binary)],
                                capture_output=True, text=True, timeout=5,
                                check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stdout)

    def test_unknown_option_is_usage_and_touches_nothing(self):
        data = with_fixups([(1, 0, 0)])
        self.binary.write_bytes(data)
        result = self.run_cli("--weak-import", "SwiftUICore")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.binary.read_bytes(), data,
                         "an unknown option must touch no byte")
        self.assertIn("--weak-import", result.stderr)
        self.assertIn("Usage:", result.stdout)
        self.assertNotIn("LOAD -> WEAK", result.stdout)

    def test_malformed_fixups_fail_closed(self):
        blob = fixups_blob([(1, 0, 0)])
        libs = [dylib("SwiftUICore")]

        def build(blob_data, datasize=None):
            command = chained_fixups(libs, blob_data)
            if datasize is not None:
                command = struct.pack("<4I", LC_DYLD_CHAINED_FIXUPS, 16,
                                      struct.unpack_from("<I", command, 8)[0],
                                      datasize)
            return executable(libs + [command]) + blob_data

        cases = {
            "blob past the file end": build(blob, datasize=len(blob) + 64),
            "imports past the blob end": build(
                blob[:16] + struct.pack("<I", 1000) + blob[20:]),
            "imports_format 9": build(
                blob[:20] + struct.pack("<I", 9) + blob[24:]),
            "fixups_version 7": build(b"\x07" + blob[1:]),
            "truncated blob": executable(
                libs + [chained_fixups(libs, blob)]) + blob[:-4],
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.binary.write_bytes(data)
                result = self.run_cli()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(self.binary.read_bytes(), data, "a rejected binary must stay unchanged")
                self.assertIn("weaklink:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_fixups_version_one_is_refused(self):
        data = with_fixups([(1, 0, 0)], fixups_version=1)
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.binary.read_bytes(), data,
                         "a refused binary must stay unchanged")
        self.assertIn("fixups version 1", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_classic_binds_are_refused(self):
        data = executable([dylib("SwiftUICore"), dyld_info_only(bind_size=16)])
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.binary.read_bytes(), data, "a refused binary must stay unchanged")
        self.assertIn("classic dyld bind opcodes are not supported", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_fat_binary_patches_every_arm64_slice(self):
        blob_a = fixups_blob([(1, 0, 0)])
        libs_a = [dylib("SwiftUICore")]
        commands_a = libs_a + [chained_fixups(libs_a, blob_a)]
        slice_a = executable(commands_a) + blob_a
        blob_b = fixups_blob([(1, 0, 0), (1, 1, 0)])
        libs_b = [dylib("SwiftUICore")]
        commands_b = libs_b + [chained_fixups(libs_b, blob_b)]
        slice_b = executable(commands_b) + blob_b
        data = fat_image([slice_a, slice_b])
        result = self.rewrite(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        first, second = 8 + 20 * 2, 8 + 20 * 2 + len(slice_a)
        struct.pack_into("<I", expected, first + 32, LC_LOAD_WEAK_DYLIB)
        struct.pack_into("<I", expected, second + 32, LC_LOAD_WEAK_DYLIB)
        struct.pack_into("<I", expected, first + len(executable(commands_a)) + 32,
                         struct.unpack_from("<I", expected, first + len(executable(commands_a)) + 32)[0] | 0x100)
        struct.pack_into("<I", expected, second + len(executable(commands_b)) + 32,
                         struct.unpack_from("<I", expected, second + len(executable(commands_b)) + 32)[0] | 0x100)
        self.assertEqual(self.binary.read_bytes(), bytes(expected), "both slices must be patched")
        self.assertIn("2 strong imports -> weak", result.stdout)

    def test_no_imports_into_the_framework_keeps_the_old_output(self):
        commands = [dylib("SwiftUICore"), dylib("UIKit"), chained_fixups([], b"")]
        blob = fixups_blob([(2, 0, 0)])  # the only import binds to UIKit
        commands[2] = chained_fixups(commands[:2], blob)
        data = executable(commands) + blob
        result = self.rewrite(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        struct.pack_into("<I", expected, 32, LC_LOAD_WEAK_DYLIB)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertIn("SwiftUICore LOAD -> WEAK", result.stdout)
        self.assertNotIn("-> weak", result.stdout, "no import line when no import changed")


if __name__ == "__main__":
    unittest.main()
