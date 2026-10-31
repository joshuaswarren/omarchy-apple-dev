"""The command-line entry main() in tools/ibtool: the --version and --self-test
exits, argument parsing (flags that take a value, bare flags, the argv[:-1]
--module lookup), the partial-info-plist side file, and every action's error
exit. Each case runs the CLI with subprocess and checks the exact return code
and stderr."""
import importlib.machinery
import importlib.util
import io
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
SRC = HERE / "ibtool" / "src"
XIB = SRC / "TinyView.xib"
SB = SRC / "NetNewsWire" / "Base.lproj" / "LaunchScreenPhone.storyboard"
FLAGS = ["--target-device", "iphone", "--target-device", "ipad",
         "--minimum-deployment-target", "17.0"]

# Loaded once (no __main__ block runs) to read VERSION_XML for the --version pin.
_loader = importlib.machinery.SourceFileLoader(
    "ibtool_under_test", str(TOOLS / "ibtool"))
IBTOOL = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("ibtool_under_test", _loader))
_loader.exec_module(IBTOOL)

NO_ACTION = ("error: ibtool: no action given (expected --compile, --link, a "
             ".storyboard input, or --version)\n")
NEED_DIR = ("error: ibtool: storyboard compile needs one .storyboard and "
            "--compilation-directory\n")


def run_cli(*argv):
    """(returncode, stdout, stderr) for one ibtool command line."""
    p = subprocess.run([sys.executable, str(TOOLS / "ibtool"), *argv],
                       capture_output=True, text=True, timeout=280)
    return p.returncode, p.stdout, p.stderr


class MainEntry(unittest.TestCase):
    def test_version(self):
        rc, out, err = run_cli("--version")
        self.assertEqual((rc, out, err), (0, IBTOOL.VERSION_XML, ""))

    def test_self_test(self):
        rc, out, err = run_cli("--self-test")
        self.assertEqual(rc, 0)
        self.assertIn("self-test passed", out)

    def test_version_wins_over_self_test(self):
        rc, out, err = run_cli("--self-test", "--version")
        self.assertEqual((rc, out, err), (0, IBTOOL.VERSION_XML, ""))

    def test_bare_flags(self):
        """Bare known flags consume one token; a value-swallowing regression
        would eat --compile and change the arg count."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o.nib")
            rc, stdout, err = run_cli("--errors", "--warnings", "--notices",
                                      "--auto-activate-custom-fonts",
                                      "--compile", out, str(XIB))
            self.assertEqual((rc, stdout, err), (0, "", ""))
            self.assertTrue(os.path.exists(out))

    def test_unknown_argument(self):
        rc, out, err = run_cli("nonsense.txt")
        self.assertEqual((rc, out, err),
                         (2, "", "error: ibtool: unknown argument 'nonsense.txt'\n"))

    def test_value_flag_at_end(self):
        """A value flag with no value left is skipped, not an error."""
        rc, out, err = run_cli("--module")
        self.assertEqual((rc, out, err), (2, "", NO_ACTION))

    def test_value_lookup_ignores_final_arg(self):
        for flag in ("--module", "--minimum-deployment-target"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as tmp:
                outdir = os.path.join(tmp, "out")
                rc, stdout, err = run_cli("--compilation-directory", outdir,
                                          str(SB), flag)
                self.assertEqual((rc, stdout, err),
                                 (0, "", f"/* {outdir}/LaunchScreenPhone.storyboardc */\n"))

    def test_no_action(self):
        rc, out, err = run_cli("--errors")
        self.assertEqual((rc, out, err), (2, "", NO_ACTION))

    def test_partial_info_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            plist = os.path.join(tmp, "nested", "dir", "p.plist")
            outdir = os.path.join(tmp, "out")
            rc, stdout, err = run_cli("--output-partial-info-plist", plist,
                                      *FLAGS, "--compilation-directory", outdir,
                                      str(SB))
            self.assertEqual(rc, 0, err)
            self.assertEqual(err, f"/* {outdir}/LaunchScreenPhone.storyboardc */\n")
            with open(plist, "rb") as f:
                data = f.read()
            buf = io.BytesIO()
            plistlib.dump({}, buf)
            self.assertEqual(data, buf.getvalue())

    def test_storyboard_needs_one_input_and_directory(self):
        rc, out, err = run_cli(str(SB))
        self.assertEqual((rc, out, err), (2, "", NEED_DIR))
        rc, out, err = run_cli(str(SB), str(SB), "--compilation-directory", "x")
        self.assertEqual((rc, out, err), (2, "", NEED_DIR))

    def test_compile_needs_two_args(self):
        rc, out, err = run_cli("--compile", "o.nib")
        self.assertEqual((rc, out, err),
                         (2, "", "error: ibtool: --compile needs OUT.nib and IN.xib\n"))
        rc, out, err = run_cli("--compile", "a", "b", "c")
        self.assertEqual((rc, out, err),
                         (2, "", "error: ibtool: --compile needs OUT.nib and IN.xib\n"))

    def test_compile_xib_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o.nib")
            rc, stdout, err = run_cli(*FLAGS, "--compile", out, str(XIB))
            self.assertEqual((rc, stdout, err), (0, "", ""))
            self.assertTrue(os.path.exists(out))
            self.assertFalse(os.path.exists(out + ".tmp-nibarchive"))

    def test_module_override_reaches_compiled_class(self):
        import nibarchive

        src = SRC / "NetNewsWire" / "SettingsTableViewCell.xib"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "cell.nib")
            rc, stdout, err = run_cli(*FLAGS, "--module", "Override",
                                      "--compile", str(out), str(src))
            self.assertEqual((rc, stdout, err), (0, "", ""))
            a = nibarchive.load(out)
            classes = [a.object_string(v.payload)
                       for obj in a.objects for v in a.object_values(obj)
                       if a.key(v.key_idx) == "UIClassName"]
            self.assertEqual(classes, ["_TtC8Override20VibrantTableViewCell"])

    def test_compile_xib_parse_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.xib")
            bad.write_text("<document>")
            rc, stdout, err = run_cli(*FLAGS, "--compile",
                                      os.path.join(tmp, "o.nib"), str(bad))
            self.assertEqual(rc, 1)
            self.assertIn("error: ibtool: no element found: line 1, column 10", err)

    def test_compile_storyboard_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "Bad.storyboard")
            bad.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                           '<document type="com.apple.InterfaceBuilder3.CocoaTouch.'
                           'Storyboard.XIB" version="3.0" targetRuntime="MacOSX.Cocoa"/>\n')
            rc, stdout, err = run_cli(*FLAGS, "--compilation-directory",
                                      os.path.join(tmp, "out"), str(bad))
            self.assertEqual(rc, 1)
            self.assertIn(f"error: ibtool: {bad}: targetRuntime 'MacOSX.Cocoa' "
                          "is not iOS.CocoaTouch", err)

    def test_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = os.path.join(tmp, "out")
            rc, _, err = run_cli(*FLAGS, "--compilation-directory", outdir, str(SB))
            self.assertEqual(rc, 0, err)
            rc, stdout, err = run_cli("--link", os.path.join(tmp, "app.storyboardd"))
            self.assertEqual(
                (rc, stdout, err),
                (2, "", "error: ibtool: --link needs OUT and at least one .storyboardc\n"))
            missing = os.path.join(tmp, "no", "Foo.storyboardc")
            rc, stdout, err = run_cli("--link", os.path.join(tmp, "app.storyboardd"),
                                      missing)
            self.assertEqual(
                (rc, stdout, err),
                (1, "", f"error: ibtool: [Errno 2] No such file or directory: '{missing}'\n"))
            appd = os.path.join(tmp, "app.storyboardd")
            rc, stdout, err = run_cli("--link", appd,
                                      os.path.join(outdir, "LaunchScreenPhone.storyboardc"))
            self.assertEqual((rc, stdout, err), (0, "", ""))
            self.assertTrue(os.path.exists(os.path.join(
                appd, "LaunchScreenPhone.storyboardc", "Info.plist")))

    def test_link_keeps_lproj_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp, "out")
            rc, _, err = run_cli(*FLAGS, "--compilation-directory", str(outdir), str(SB))
            self.assertEqual(rc, 0, err)
            lproj = outdir / "Base.lproj"
            lproj.mkdir()
            os.rename(outdir / "LaunchScreenPhone.storyboardc",
                      lproj / "LaunchScreenPhone.storyboardc")
            appd = Path(tmp, "app.storyboardd")
            rc, stdout, err = run_cli("--link", str(appd), str(lproj / "LaunchScreenPhone.storyboardc"))
            self.assertEqual((rc, stdout, err), (0, "", ""))
            self.assertTrue((appd / "Base.lproj" / "LaunchScreenPhone.storyboardc" / "Info.plist").exists())


if __name__ == "__main__":
    unittest.main()
