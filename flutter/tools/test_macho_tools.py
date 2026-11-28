import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wl = load("weaklink")
sf = load("strip-frameworks")

MH64 = 0xFEEDFACF
ARM64 = 0x0100000C


def lc(cmd, body):
    size = 8 + len(body)
    size += -size % 8
    return struct.pack("<II", cmd, size) + body.ljust(size - 8, b"\0")


def dylib(cmd, name):
    # dylib_command: name.offset counts from the command start, so the
    # string sits at body offset 16 (after cmd/cmdsize).
    return lc(cmd, struct.pack("<4I", 24, 0, 0, 0) + name.encode() + b"\0")


def macho(cmds, extra=b""):
    body = b"".join(cmds)
    return struct.pack("<8I", MH64, ARM64, 0, 2, len(cmds), len(body), 0, 0) + body + extra


class Ordinals(unittest.TestCase):
    def test_special_ordinal_boundaries(self):
        for bits, limit in ((8, 0xF0), (16, 0xFFF0)):
            self.assertTrue(wl.is_special_ordinal(0, bits))
            self.assertTrue(wl.is_special_ordinal(limit + 1, bits))
            self.assertTrue(wl.is_special_ordinal(0xFF if bits == 8 else 0xFFFF, bits))
            self.assertFalse(wl.is_special_ordinal(1, bits))
            self.assertFalse(wl.is_special_ordinal(limit, bits))  # 0xF0/0xFFF0 is ordinary
            self.assertFalse(wl.is_special_ordinal(200 if bits == 8 else 40000, bits))


class Slices(unittest.TestCase):
    def test_thin_fat_truncated_and_other(self):
        self.assertEqual(wl.slices(macho([])), [0])
        fat = struct.pack(">2I", 0xCAFEBABE, 1) + \
            struct.pack(">5I", ARM64, 0, 0x400, 0x1000, 12)
        self.assertEqual(wl.slices(fat + b"\0" * 0x400), [0x400])
        with self.assertRaises(ValueError):
            wl.slices(struct.pack(">2I", 0xCAFEBABE, 9) + b"\0" * 8)
        self.assertEqual(wl.slices(b"ELF!" + b"\0" * 64), [])


class Names(unittest.TestCase):
    def test_dylib_name_and_framework_of(self):
        name = "@rpath/Foo.framework/Foo"
        data = macho([dylib(0xC, name)])
        _, cmdsize = struct.unpack_from("<II", data, 32)
        # find the dylib command's address (first load command)
        self.assertEqual(wl.dylib_name(data, 32), name)
        self.assertEqual(wl.framework_of(name), "Foo.framework")
        self.assertEqual(wl.framework_of("/usr/lib/libx.dylib"), "lib")
        self.assertEqual(wl.framework_of("plain"), "")


class ParseSlice(unittest.TestCase):
    def blob(self, cmds, chained=b""):
        return macho(cmds, chained)

    def test_dylib_list_flips_and_lazy_flag(self):
        cmds = [
            dylib(0xC, "@rpath/Foo.framework/Foo"),
            dylib(0x80000018, "@rpath/Bar.framework/Bar"),          # weak already: ordinal slot, no flip
            dylib(0x80000023, "@rpath/Baz.framework/Baz"),          # upward: ordinal slot
            dylib(0x20, "@rpath/Lazy.framework/Lazy"),              # lazy: flag only, NO slot
        ]
        info = wl.parse_slice(self.blob(cmds), 0, {"Foo.framework"})
        self.assertEqual(info.dylibs, ["Foo.framework", "Bar.framework", "Baz.framework"])
        self.assertEqual(info.flips, [(32, "@rpath/Foo.framework/Foo")])
        self.assertTrue(info.lazy_load)

    def test_chained_fixups_offset_and_classic_binds(self):
        fixups = lc(0x80000034, struct.pack("<II", 0x100, 0x40))
        info_with = wl.parse_slice(self.blob([fixups]), 0, set())
        self.assertEqual(info_with.chained, (0x100, 0x40))
        dyld_info = lc(0x80000022, struct.pack("<10I", *range(10))[:24] + struct.pack("<4I", 1, 0, 1, 0))
        info2 = wl.parse_slice(self.blob([dyld_info]), 0, set())
        self.assertTrue(info2.classic_binds)


class ImportWrites(unittest.TestCase):
    def chained_blob(self, imports, fmt=1, version=0):
        entries = struct.pack(f"<{len(imports)}{'I' if fmt == 1 else 'Q'}", *imports)
        header = struct.pack("<7I", version, 28, 28, 0, len(imports), fmt, 0)
        return header + entries

    def info(self, **kw):
        i = wl.SliceImports()
        i.dylibs = kw.get("dylibs", ["Foo.framework", "Bar.framework"])
        i.chained = kw.get("chained")
        i.classic_binds = kw.get("classic_binds", False)
        i.lazy_load = kw.get("lazy_load", False)
        return i

    def data_with_blob(self, blob):
        # header (32) + one load cmd pointing at the blob right after it
        lcsize = 16
        cmd = struct.pack("<4I", 0x80000034, lcsize, 32 + lcsize, len(blob))
        return macho([lc(0x80000034, struct.pack("<II", 48, len(blob)))], blob), 48

    def test_refusal_paths(self):
        blob = self.chained_blob([1])
        data, off = self.data_with_blob(blob)
        with self.assertRaises(ValueError):   # lazy load cannot be trusted
            wl.import_writes(data, 0, len(data), self.info(lazy_load=True, chained=(off, len(blob))), set())
        with self.assertRaises(ValueError):   # classic binds unverifiable
            wl.import_writes(data, 0, len(data), self.info(classic_binds=True), set())
        with self.assertRaises(ValueError):   # version
            bad = self.chained_blob([1], version=1)
            d, o = self.data_with_blob(bad)
            wl.import_writes(d, 0, len(d), self.info(chained=(o, len(bad))), set())
        with self.assertRaises(ValueError):   # unknown imports format
            bad = self.chained_blob([1], fmt=9)
            d, o = self.data_with_blob(bad)
            wl.import_writes(d, 0, len(d), self.info(chained=(o, len(bad))), set())

    def test_no_fixups_and_no_binds_means_no_imports(self):
        writes, counts = wl.import_writes(macho([]), 0, 32, self.info(), set())
        self.assertEqual((writes, counts), ([], {}))

    def test_wanted_imports_get_the_weak_bit(self):
        # two imports: ordinal 1 (Foo, wanted) and a special ordinal (skipped)
        blob = self.chained_blob([1, 0])
        data, off = self.data_with_blob(blob)
        writes, counts = wl.import_writes(data, 0, len(data),
                                          self.info(chained=(off, len(blob))), {"Foo.framework"})
        self.assertEqual(counts, {"Foo.framework": 1})
        self.assertEqual(len(writes), 1)
        at, code, value = writes[0]
        self.assertEqual(struct.unpack_from(code, data, at)[0] | (1 << 8), value)  # weak bit set


class StripFrameworksLoads(unittest.TestCase):
    def test_slice_loads_and_dylib_loads(self):
        cmds = [dylib(0xC, "/System/Foo.framework/Foo"),
                dylib(0x80000018, "/System/Bar.framework/Bar")]
        data = macho(cmds)
        loads = sf._slice_loads(data, 0)
        self.assertEqual(loads, [(0xC, "/System/Foo.framework/Foo"),
                                 (0x80000018, "/System/Bar.framework/Bar")])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.dylib"
            p.write_bytes(data)
            self.assertEqual(sf.dylib_loads(p), loads)
            (Path(tmp) / "elf").write_bytes(b"\x7fELF" + b"\0" * 32)
            self.assertEqual(sf.dylib_loads(Path(tmp) / "elf"), [])


if __name__ == "__main__":
    unittest.main()
