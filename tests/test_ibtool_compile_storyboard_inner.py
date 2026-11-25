"""Refusal paths of the storyboard driver in tools/ibtool (_compile_storyboard_inner):
the device and scene checks, the navigation relationship checks and the
per-scene view controller checks. Each case compiles a variant of a corpus
storyboard with one attribute or tag changed and checks the exact XibError
text."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
LAUNCH = HERE / "ibtool" / "src" / "NetNewsWire" / "Base.lproj" / "LaunchScreenPhone.storyboard"
SHARE = HERE / "ibtool" / "src" / "ShareActionExtension" / "Base.lproj" / "MainInterface.storyboard"
FLAGS = ["--module", "NetNewsWire", "--target-device", "iphone",
         "--target-device", "ipad", "--minimum-deployment-target", "17.0"]


def compile_variant(xml):
    """(source path, returncode, stderr) for one storyboard text."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp, "Variant.storyboard")
        src.write_text(xml)
        out = Path(tmp, "out")
        p = subprocess.run([sys.executable, str(TOOLS / "ibtool"), *FLAGS,
                            "--compilation-directory", str(out), str(src)],
                           capture_output=True, text=True, timeout=280)
        return str(src), p.returncode, p.stderr


class CompileStoryboardInner(unittest.TestCase):
    def unique_sub(self, xml, old, new):
        self.assertEqual(xml.count(old), 1, f"anchor not unique: {old}")
        return xml.replace(old, new)

    def assert_refused(self, xml, message):
        _, rc, err = compile_variant(xml)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"error: ibtool: {message}", err)

    def test_device_unsupported(self):
        xml = LAUNCH.read_text().replace(
            '<device id="retina6_1" orientation="portrait"',
            '<device id="retina6_1" orientation="landscape"')
        path, rc, err = compile_variant(xml)
        self.assertNotEqual(rc, 0)
        self.assertIn("error: ibtool: "
                      f"{path}: device {{'id': 'retina6_1', 'orientation': 'landscape', "
                      "'appearance': 'light'} unsupported", err)

    def test_retina6_12_device_supported(self):
        xml = LAUNCH.read_text().replace(
            '<device id="retina6_1" orientation="portrait"',
            '<device id="retina6_12" orientation="portrait"')
        _, rc, err = compile_variant(xml)
        self.assertEqual(rc, 0, err)

    def test_no_scenes(self):
        xml = LAUNCH.read_text()
        start = xml.index("<scenes>") + len("<scenes>")
        xml = xml[:start] + xml[xml.index("</scenes>"):]
        path, rc, err = compile_variant(xml)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"error: ibtool: {path}: no scenes", err)

    def test_nav_needs_exactly_one_root(self):
        xml = SHARE.read_text()
        xml = self.unique_sub(xml, 'relationship="rootViewController"',
                              'relationship="contentViewController"')
        self.assert_refused(xml, "Variant.storyboard: navigationController jKX-MD-OMs"
                                 " needs exactly one rootViewController")

    def test_nav_root_not_found(self):
        xml = SHARE.read_text()
        xml = self.unique_sub(xml, 'destination="j1y-V4-xli"',
                              'destination="zz9-no-such-vc"')
        self.assert_refused(xml, "Variant.storyboard: navigationController jKX-MD-OMs"
                                 " root not found")

    def test_scene_has_no_view_controller(self):
        xml = LAUNCH.read_text()
        xml = self.unique_sub(xml, '<viewController id="2hg-qO-omg" sceneMemberID="viewController">',
                              '<viewControllerZ id="2hg-qO-omg" sceneMemberID="viewController">')
        xml = self.unique_sub(xml, "</viewController>", "</viewControllerZ>")
        self.assert_refused(xml, "Variant.storyboard: scene has no viewController"
                                 " (unsupported scene kind)")

    def test_view_controller_has_no_keyed_view(self):
        xml = self.unique_sub(LAUNCH.read_text(), 'key="view"', 'key="viewX"')
        self.assert_refused(xml, "Variant.storyboard: viewController has no keyed view")

    def test_view_controller_has_no_id(self):
        xml = self.unique_sub(LAUNCH.read_text(),
                              '<viewController id="2hg-qO-omg" sceneMemberID="viewController">',
                              '<viewController sceneMemberID="viewController">')
        self.assert_refused(xml, "Variant.storyboard: viewController has no id")

    def test_unsupported_view_kind(self):
        xml = LAUNCH.read_text()
        xml = self.unique_sub(xml, '<view key="view" contentMode="scaleToFill" id="wsU-Ys-fCl">',
                              '<glView key="view" contentMode="scaleToFill" id="wsU-Ys-fCl">')
        xml = self.unique_sub(xml, "</view>", "</glView>")
        self.assert_refused(xml, "Variant.storyboard: unsupported view kind <glView>")


if __name__ == "__main__":
    unittest.main()
