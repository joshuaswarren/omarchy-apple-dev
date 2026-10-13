import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from xcstrings_symbols import identifier, swift_symbols  # noqa: E402


def catalog(*keys):
    return {"sourceLanguage": "en",
            "strings": {key: {"extractionState": "manual"} for key in keys}}


class SymbolNameTests(unittest.TestCase):
    def test_swift_keywords_are_escaped(self):
        self.assertEqual(identifier("CONTINUE"), "`continue`")
        self.assertEqual(identifier("WHERE"), "`where`")
        self.assertEqual(identifier("For %@."), "`for`")
        self.assertEqual(identifier("Self"), "`self`")

    def test_ordinary_names_are_unchanged(self):
        self.assertEqual(identifier("Add someone"), "addSomeone")
        self.assertEqual(identifier("3 friends"), "_3Friends")

    def test_keyword_symbols_are_declared_escaped(self):
        out = swift_symbols(catalog("CONTINUE", "Done"), "Localizable.xcstrings", "Localizable")
        self.assertIn("static var `continue`: LocalizedStringResource", out)
        self.assertIn("static var done: LocalizedStringResource", out)

    def test_colliding_keys_get_no_symbol_and_a_warning(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = swift_symbols(catalog("Cancel", "CANCEL", "Done"), "Localizable.xcstrings", "Localizable")
        self.assertNotIn("static var cancel", out)
        self.assertIn("static var done", out)
        self.assertIn("no symbol 'cancel'", err.getvalue())

    def test_a_catalog_of_only_collisions_yields_no_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(swift_symbols(catalog("All even", "ALL EVEN"), "Localizable.xcstrings",
                                           "Localizable"), "")


if __name__ == "__main__":
    unittest.main()
