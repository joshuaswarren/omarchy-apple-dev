import importlib.util
import os
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def load(name, argv=()):
    _argv, sys.argv = sys.argv, [name, *argv]
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass  # script-level main ran against the fixture argv
    finally:
        sys.argv = _argv
    return mod


hm = load("host-manifests", ["/tmp", "/tmp"])

# macho-lint runs its ipa walk on import: hand it a zip holding one
# non-Mach-O file so the walk is a no-op and the module still binds lint().
_ipa = Path(tempfile.mkdtemp()) / "empty.ipa"
import zipfile  # noqa: E402
with zipfile.ZipFile(_ipa, "w") as z:
    z.writestr("Payload/notes.txt", "not a mach-o")
ml = load("macho-lint", [str(_ipa)])

MH64, ARM64 = 0xFEEDFACF, 0x0100000C


def lc(cmd, body):
    size = 8 + len(body)
    size += -size % 8
    return struct.pack("<II", cmd, size) + body.ljust(size - 8, b"\0")


def build_version():
    # platform=2 (iOS), minos=15.0, sdk=17.0, ntools=0
    return lc(0x32, struct.pack("<4I", 2, 15 << 16, 17 << 16, 0))


def symtab(stroff, strsize):
    return lc(0x2, struct.pack("<IIII", 0, 0, stroff, strsize))


def macho(cmds, tail=b""):
    body = b"".join(cmds)
    return struct.pack("<8I", MH64, ARM64, 0, 6, len(cmds), len(body), 0, 0) + body + tail


class Lint(unittest.TestCase):
    def lint(self, data):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            return ml.lint(path)
        finally:
            os.unlink(path)

    def test_clean_image_has_no_problems(self):
        data = macho([build_version(), symtab(256, 16), lc(0x1D, b"\0" * 8)])
        data = data.ljust(256, b"\0") + b"\0" * 16
        r = self.lint(data)
        self.assertEqual(r["problems"], [])
        self.assertEqual((r["minos"], r["sdk"]), ("15.0", "17.0"))

    def test_each_problem_reports(self):
        non_arm = struct.pack("<8I", MH64, 7, 0, 6, 1, 16, 0, 0) + build_version()
        self.assertIn("is not arm64", self.lint(non_arm)["problems"][0])
        no_bv = macho([symtab(256, 16), lc(0x1D, b"\0" * 8)]).ljust(256, b"\0") + b"\0" * 16
        self.assertIn("platform is not iOS", self.lint(no_bv)["problems"])
        unaligned = macho([build_version(), symtab(253, 8), lc(0x1D, b"\0" * 8)]).ljust(264, b"\0")
        self.assertTrue(any("not 8-byte aligned" in p for p in self.lint(unaligned)["problems"]))
        overrun = macho([build_version(), symtab(260, 64), lc(0x1D, b"\0" * 8)])
        self.assertTrue(any("past the end" in p for p in self.lint(overrun)["problems"]))
        unsigned = macho([build_version(), symtab(256, 8)]).ljust(256, b"\0") + b"\0" * 8
        self.assertIn("no LC_CODE_SIGNATURE", self.lint(unsigned)["problems"])

    def test_non_macho_returns_none(self):
        self.assertIsNone(self.lint(b"\x7fELF" + b"\0" * 64))


class Manifests(unittest.TestCase):
    def test_identity_strips_git_and_lowercases(self):
        self.assertEqual(hm.identity("https://github.com/Org/Foo.git"), "foo")
        self.assertEqual(hm.identity("https://github.com/Org/Foo/"), "foo")
        self.assertEqual(hm.identity("git@example.com:team/Bar-Baz"), "bar-baz")

    def test_manifests_matches_versioned_and_plain(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("Package.swift", "Package@swift-5.9.swift", "notes.txt",
                         "Package@swift-x.swift", "xPackage.swift"):
                (Path(tmp) / name).write_text("// m")
            got = [Path(m).name for m in hm.manifests(tmp)]
            self.assertEqual(sorted(got), ["Package.swift", "Package@swift-5.9.swift"])

    def test_tests_host_detects_and_ignores_longer_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Package.swift").write_text(
                "#if canImport(Darwin)\n.target(name: \"h\")\n#endif\n")
            self.assertTrue(hm.tests_host(tmp))
            (Path(tmp) / "Package.swift").write_text("#if myos(Linux)\n#endif\n")
            self.assertFalse(hm.tests_host(tmp))

    def test_writable_then_force_rmtree_clears_a_readonly_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "checkout"
            box.mkdir()
            f = box / "Package.swift"
            f.write_text("// m")
            os.chmod(f, 0o444)
            os.chmod(box, 0o555)
            hm.writable(box)
            self.assertTrue(os.stat(f).st_mode & stat.S_IWUSR)
            hm.force_rmtree(box)
            self.assertFalse(box.exists())


if __name__ == "__main__":
    unittest.main()
