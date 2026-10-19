"""tools/ibtool on React Native's template LaunchScreen.storyboard
(tests/ibtool/src/HelloWorld, unchanged from react-native-community/template,
MIT). The byte layout is checked against Apple's golden (tests/ibtool/golden/
HelloWorld, Xcode 27.1) by `tools/ibtool --self-test`; this checks the decoded
values."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
SRC = HERE / "ibtool" / "src" / "HelloWorld" / "LaunchScreen.storyboard"
sys.path.insert(0, str(TOOLS))
import nibarchive  # noqa: E402


def values(nib):
    """(key, rendered value) for every value in the nib, in order."""
    a = nibarchive.load(str(nib))
    return [(a.key(v.key_idx), a.render(v))
            for obj in a.objects for v in a.object_values(obj)]


class ReactNativeLaunchScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        subprocess.run([sys.executable, str(TOOLS / "ibtool"), "--module", "HelloWorld",
                        "--compilation-directory", cls.tmp.name, str(SRC)],
                       check=True, capture_output=True)
        sbc = Path(cls.tmp.name) / "LaunchScreen.storyboardc"
        cls.view = values(sbc / "01J-lp-oVM-view-Ze5-6b-2t3.nib")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def get(self, key):
        return [v for k, v in self.view if k == key]

    def test_minimum_font_sizes(self):
        self.assertEqual(self.get("UIMinimumFontSize"), ["float 18.0", "float 9.0"])
        # minimumFontSize / pointSize, as a float: 18/36 and 9/17
        self.assertEqual(self.get("UIMinimumScaleFactor"),
                         ["float 0.5", "float 0.529411792755127"])

    def test_middle_truncation(self):
        self.assertEqual(self.get("UILineBreakMode"), ["int 5"])

    def test_bold_system_font(self):
        names = self.get("UIFontName")
        self.assertTrue(names[0].startswith("string '.SFUI-Bold'"), names)
        self.assertTrue(names[1].startswith("string '.SFUI-Regular'"), names)
        self.assertEqual(self.get("UIFontTraits"), ["int 2", "int 0"])
        self.assertIn("string 'CTFontBoldUsage'", " ".join(v for _, v in self.view))

    def test_multiplier(self):
        # 1/3 as a float, widened to a double (Apple's golden)
        self.assertEqual(self.get("NSMultiplier"), ["double 0.3333333432674408"])


if __name__ == "__main__":
    unittest.main()
