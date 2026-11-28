import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MKF = ROOT / "sdk-free/swift/mk-foundation-src.py"
MKCORE = ROOT / "sdk-free/swift/mk-core.py"
MKCONC = ROOT / "sdk-free/swift/mk-conc.py"
_spec = importlib.util.spec_from_file_location(
    "dumpgen", ROOT / "sdk-free/swiftui/dumpgen.py")
dumpgen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dumpgen)


def env(**kw):
    e = dict(os.environ)
    e.update(kw)
    return e


class MkFoundationSrc(unittest.TestCase):
    def make(self, tmp, files):
        src = Path(tmp) / "src/stdlib/public/Darwin/Foundation"
        src.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (src / (name + ".swift")).write_text(body)
        out = Path(tmp) / "out"
        e = env(SWIFT53_SRC=str(Path(tmp) / "src"), SWIFT53_OUT=str(out))
        return src, out, e

    def test_copy_patch_and_objectivec_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out, e = self.make(tmp, {
                "Foo": "@_exported import Foundation // Clang module\nlet x = 1\n",
                "String": "extension String: CVarArg {}\n",
            })
            r = subprocess.run([sys.executable, str(MKF), "Foo", "String"],
                               env=e, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            foo = (out / "Foo.swift").read_text()
            self.assertIn("@_exported import ObjectiveC", foo)
            got = (out / "String.swift").read_text()
            self.assertIn("public var _cVarArgEncoding", got)
            self.assertNotIn("CVarArg {}\n", got)

    def test_remove_blocks_and_repeats(self):
        body = (
            "keep()\n"
            "public struct MachError : _BridgedStoredNSError {\n  a\n}\n"
            "      _errorDomainUserInfoProviderQueue.sync {\n"
            "        if NSError.userInfoValueProvider(forDomain: domain) != nil { return }\n"
            "        NSError.setUserInfoValueProvider(forDomain: domain) { (error, key) in\n"
            "    hasher.combine(_nsError)\n  }\n\n"
            "  @_alwaysEmitIntoClient public var hashValue: Int {\n    return _nsError.hashValue\n"
            "  public var failureURLPeerTrust: SecTrust? {\n    nil\n  }\n"
            "extension MachErrorCode {\n  b\n}\n"
            "extension MachErrorCode {\n  c\n}\n"
            "extension MachError {\n  d\n}\n"
            "keep2()\n")
        with tempfile.TemporaryDirectory() as tmp:
            _, out, e = self.make(tmp, {"NSError": body})
            r = subprocess.run([sys.executable, str(MKF), "NSError"],
                               env=e, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = (out / "NSError.swift").read_text()
            self.assertNotIn("MachError", got)
            self.assertNotIn("failureURLPeerTrust", got)
            self.assertIn("keep()", got)
            self.assertIn("keep2()", got)
            self.assertIn("(error: Error, key: String) -> Any?", got)  # patch applied

    def test_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, e = self.make(tmp, {"String": "no anchor here\n"})
            r = subprocess.run([sys.executable, str(MKF), "String"],
                               env=e, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("PATCH MISS", r.stderr)
            _, _, e = self.make(tmp, {"NSError": "x\n"})
            r = subprocess.run([sys.executable, str(MKF), "NSError"],
                               env=e, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)  # PATCH MISS fires first
            r = subprocess.run([sys.executable, str(MKF), "NoSuch"],
                               env=e, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("missing NoSuch", r.stderr)


GYB = (
    "import sys\n"
    "out = sys.argv[sys.argv.index('-o') + 1]\n"
    "open(out, 'w').write('// gyb out\\n')\n")


class MkCore(unittest.TestCase):
    def tree(self, tmp, mod):
        core = Path(tmp) / "src/stdlib/public" / mod
        core.mkdir(parents=True)
        (Path(tmp) / "src/utils").mkdir()
        (Path(tmp) / "src/utils/gyb.py").write_text(GYB)
        return core, env(SWIFT_SRC=str(Path(tmp) / "src"),
                         SWIFT_GEN=str(Path(tmp) / "gen"))

    def test_file_list_and_gyb(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, e = self.tree(tmp, "core")
            (core / "CMakeLists.txt").write_text(
                'NORMAL "Array.swift"\nEMBEDDED "SmallList.swift.gyb"\n'
                'NORMAL "EmbeddedDrop.swift"\n')
            for n in ["Array.swift", "SmallList.swift.gyb", "EmbeddedDrop.swift",
                      "SIMDVector.swift", "SIMDIntegerConcreteOperations.swift.gyb",
                      "SIMDFloatConcreteOperations.swift.gyb",
                      "SIMDMaskConcreteOperations.swift.gyb",
                      "SIMDVectorTypes.swift.gyb"]:
                (core / n).write_text("// " + n)
            r = subprocess.run([sys.executable, str(MKCORE)], env=e,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            self.assertTrue(any(l.endswith("Array.swift") for l in lines))
            self.assertTrue(any(l.endswith("EmbeddedDrop.swift") is False or True
                                for l in lines))
            names = [Path(l).name for l in lines]
            self.assertNotIn("EmbeddedDrop.swift", names)  # Embedded* filtered
            self.assertIn("SmallList.swift", names)        # gyb output, in GEN
            self.assertTrue((Path(tmp) / "gen/core/SmallList.swift").is_file())

    def test_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, e = self.tree(tmp, "core")
            (core / "CMakeLists.txt").write_text('NORMAL "Absent.swift"\n')
            for n in ["SIMDVector.swift", "SIMDIntegerConcreteOperations.swift.gyb",
                      "SIMDFloatConcreteOperations.swift.gyb",
                      "SIMDMaskConcreteOperations.swift.gyb",
                      "SIMDVectorTypes.swift.gyb"]:
                (core / n).write_text("// " + n)
            r = subprocess.run([sys.executable, str(MKCORE)], env=e,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("MISSING Absent.swift", r.stderr)


class MkConc(unittest.TestCase):
    def test_skip_list_and_missing_is_soft(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = Path(tmp) / "src/stdlib/public/Concurrency"
            c.mkdir(parents=True)
            (Path(tmp) / "src/utils").mkdir()
            (Path(tmp) / "src/utils/gyb.py").write_text(GYB)
            (c / "CMakeLists.txt").write_text(
                "Task.swift\nPlatformExecutorLinux.swift\nAsyncStream.swift.gyb\n")
            (c / "Task.swift").write_text("// t")
            # AsyncStream.swift.gyb deliberately absent -> soft "missing"
            e = env(SWIFT_SRC=str(Path(tmp) / "src"),
                    SWIFT_GEN=str(Path(tmp) / "gen"))
            r = subprocess.run([sys.executable, str(MKCONC)], env=e,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            names = [Path(l).name for l in r.stdout.splitlines()]
            self.assertEqual(names, ["Task.swift"])  # skip prefix + missing dropped
            self.assertIn("missing AsyncStream.swift.gyb", r.stderr)


class Dumpgen(unittest.TestCase):
    LINES = [
        "struct Color {",
        "  var r: Double",
        "}",
        "struct Palette.Color {",
        "  var x: Int",
        "}",
        "struct Other {",
        "  var z: Int",
        "}",
        "extension SwiftUI.Color : Equatable {}",
        "extension SwiftUI.Colored : Hashable {}",
    ]

    def test_blocks_for(self):
        hits = dumpgen.blocks_for(self.LINES, "Color")
        fulls = [f for f, _ in hits]
        self.assertEqual(fulls, ["struct Color", "struct Palette.Color"])
        self.assertIn("  var r: Double", hits[0][1])

    def test_conformances(self):
        got = dumpgen.conformances(self.LINES, "Color")
        self.assertEqual(got, ["extension SwiftUI.Color : Equatable {}"])

    def test_symbol_hits(self):
        n, sample = dumpgen.symbol_hits(["a.Color.f", "x"], "Color")
        self.assertEqual(n, 1)
        self.assertEqual(dumpgen.symbol_hits(None, "Color"), (0, []))


if __name__ == "__main__":
    unittest.main()
