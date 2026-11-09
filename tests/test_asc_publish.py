"""tools/asc.py publish(): the post-upload release steps as an opt-in command.
Runs asc.py with `call` replaced by a canned responder, so nothing touches the
network and the real exit codes are asserted (a frozen state must stop
non-zero, never read as success).

Rows (expected results written before the code):
  1  happy path: no version -> one is created (releaseType MANUAL), the VALID
     build is attached, whatsNew is filled per locale through the mapping
     (he<-iw, zh-Hans<-zh-CN, nl-NL<-nl, ko<-en-US), emoji are stripped, no
     reviewSubmissions call happens and the last line says submission is
     manual; exit 0
  2  the mapping tail: base-language match (nl-NL<-nl), a store locale with no
     fitting notes is reported and left empty (ko), a notes locale with no
     store localization is reported (ja); exit 0
  3  a notes entry that is emoji-only: dies "release notes are empty once
     emoji are stripped"; exit non-zero, nothing patched
  4  version IN_REVIEW: dies "already exists but is not editable (state:
     IN_REVIEW)"; exit 1 (die is sys.exit, so a script cannot read the stop as
     success); no version created, no write call
  5  re-run, version WAITING_FOR_REVIEW: "leaving whatsNew untouched"; exit 0;
     only GETs
  6  re-run, editable version with the same build attached and whatsNew
     already equal: "already attached: ok", "whatsNew already up to date"; no
     write call; exit 0
  7  attached build with a different number: MISMATCH then die; exit 1
  8  a bad command prints the usage line naming publish; exit non-zero
Mutants (each must fail its row; checked by hand when the test was written):
  M1  note_for skips the alias step -> rows 1, 2
  M2  strip_emoji returns the empty text instead of dying -> row 3
  M3  editable_version returns a frozen version instead of dying -> row 4
      (exit code 0)
  M4  publish re-attaches the build when one is attached -> row 6
  M5  the WAITING_FOR_REVIEW early return dropped -> row 5 (PATCHes on a
      version in review)
  M6  publish ends with a review submission PATCH -> rows 1, 4 (a
      reviewSubmissions call or the missing manual-step line)
"""
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ASC = Path(__file__).resolve().parents[1] / "tools" / "asc.py"

try:
    import cryptography  # asc.py imports it at module level
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False

# Runs the real asc.py command line: module head with `call` swapped for the
# canned responder, then the untouched __main__ block (real commands table).
DRIVER = r"""
import json, sys
from pathlib import Path

asc_path, canned_path, log_path, target, notes = sys.argv[1:6]
canned = {}
for key, value in json.loads(Path(canned_path).read_text(encoding="utf-8")).items():
    method, path = key.split(" ", 1)
    canned[method, path] = value
log = []


def call(method, path, body=None):
    log.append({"method": method, "path": path, "body": body})
    try:
        return canned[method, path.split("?")[0]]
    except KeyError:
        print(f"fake call: no canned response for {method} {path} (call #{len(log)})", file=sys.stderr)
        sys.exit(3)


source = Path(asc_path).read_text(encoding="utf-8")
cut = source.index('if __name__ == "__main__":')
namespace = {"__name__": "asc_publish_setup", "__file__": asc_path}
exec(compile(source[:cut], asc_path, "exec"), namespace)
namespace["call"] = call
namespace["__name__"] = "__main__"
sys.argv = ["asc.py", "publish", target, notes]
try:
    exec(compile(source[cut:], asc_path, "exec"), namespace)
finally:
    Path(log_path).write_text(json.dumps(log), encoding="utf-8")
"""

APP = {"data": [{"id": "100", "attributes": {"name": "Fixture", "bundleId": "dev.omarchy.fixture"}}]}
CREATED = {"data": {"id": "200", "attributes": {"appStoreState": "PREPARE_FOR_SUBMISSION", "versionString": "1.2"}}}
BUILD_NONE = {"data": None}
BUILD_3 = {"data": {"id": "300", "attributes": {"version": 3}}}
BUILD_9 = {"data": {"id": "999", "attributes": {"version": 9}}}
BUILDS_VALID = {"data": [{"id": "300", "attributes": {"processingState": "VALID", "expired": False}}]}
PATCHED = {"data": {}}


def versions(state):
    return {"data": [{"id": "200", "attributes": {"appStoreState": state, "versionString": "1.2"}}]}


def localizations(*specs):
    """(id, locale, whatsNew) tuples -> the appStoreVersionLocalizations list."""
    return {"data": [{"id": loc_id, "attributes": {"locale": locale, "whatsNew": whats_new}}
                     for loc_id, locale, whats_new in specs]}


def run_row(tmp, canned, notes_entries):
    ipa = tmp / "Fixture.ipa"
    notes = tmp / "release_notes.json"
    canned_path = tmp / "canned.json"
    log_path = tmp / "calls.json"
    info = {"CFBundleIdentifier": "dev.omarchy.fixture", "CFBundleShortVersionString": "1.2",
            "CFBundleVersion": "3"}
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/Fixture.app/Info.plist", plistlib.dumps(info))
    notes.write_text(json.dumps(notes_entries), encoding="utf-8")
    canned_path.write_text(json.dumps({f"{method} {path}": value for (method, path), value in canned.items()}),
                           encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", DRIVER, str(ASC), str(canned_path), str(log_path),
                           str(ipa), str(notes)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, cwd=tmp,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    return done, log


def whats_new(log, loc_id):
    """The whatsNew attribute of the PATCH a localization received, or None."""
    for item in log:
        if item["method"] == "PATCH" and item["path"] == f"/v1/appStoreVersionLocalizations/{loc_id}":
            return item["body"]["data"]["attributes"]["whatsNew"]
    return None


@unittest.skipUnless(CRYPTO_OK, "needs cryptography to import tools/asc.py")
class AscPublish(unittest.TestCase):
    def row(self, canned, notes_entries):
        with tempfile.TemporaryDirectory(prefix="asc-publish-") as tmp:
            return run_row(Path(tmp), canned, notes_entries)

    def test_row_1_happy_path_creates_attaches_fills(self):
        clean_en = "What's new\n- Faster sync\n- Dark mode"  # emoji and double spaces gone
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): {"data": []},
            ("POST", "/v1/appStoreVersions"): CREATED,
            ("GET", "/v1/appStoreVersions/200/build"): BUILD_NONE,
            ("GET", "/v1/builds"): BUILDS_VALID,
            ("PATCH", "/v1/appStoreVersions/200"): PATCHED,
            ("GET", "/v1/appStoreVersions/200/appStoreVersionLocalizations"): localizations(
                ("201", "en-US", "old text"), ("202", "he", None), ("203", "zh-Hans", None),
                ("204", "nl-NL", None), ("205", "ko", None)),
            ("PATCH", "/v1/appStoreVersionLocalizations/201"): PATCHED,
            ("PATCH", "/v1/appStoreVersionLocalizations/202"): PATCHED,
            ("PATCH", "/v1/appStoreVersionLocalizations/203"): PATCHED,
            ("PATCH", "/v1/appStoreVersionLocalizations/204"): PATCHED,
            ("PATCH", "/v1/appStoreVersionLocalizations/205"): PATCHED,
        }
        notes = [
            {"language": "en-US", "text": "What's new ✨\n- Faster sync  \n- Dark mode 🎉"},
            {"language": "iw", "text": "Fixes and speed-ups 🚀"},
            {"language": "zh-CN", "text": "修复了若干问题"},
            {"language": "nl", "text": "Stabiele  release ⭐"},
        ]
        done, log = self.row(canned, notes)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("no editable version 1.2; creating one", done.stdout)
        self.assertIn("build 300 #3 attached", done.stdout)
        self.assertIn("publish stops here: review submission is a manual step", done.stdout)
        # the mapping: exact, Play alias, alias, base language, en-US fallback
        self.assertEqual(whats_new(log, "201"), clean_en)
        self.assertEqual(whats_new(log, "202"), "Fixes and speed-ups")
        self.assertEqual(whats_new(log, "203"), "修复了若干问题")
        self.assertEqual(whats_new(log, "204"), "Stabiele release")
        self.assertEqual(whats_new(log, "205"), clean_en)
        post = next(item for item in log if item["method"] == "POST")
        self.assertEqual(post["body"]["data"]["attributes"]["releaseType"], "MANUAL")
        attach = next(item for item in log
                      if item["method"] == "PATCH" and item["path"] == "/v1/appStoreVersions/200")
        self.assertEqual(attach["body"]["data"]["relationships"]["build"]["data"]["id"], "300")
        self.assertIn("en-US: stripped 2 symbol kind(s)", done.stdout)
        self.assertNotIn("no notes text", done.stdout)
        self.assertNotIn("no store localization", done.stdout)
        # the maintainer's condition: no review submission call, ever
        self.assertFalse([item for item in log if "reviewSubmission" in item["path"]])

    def test_row_2_mapping_tail_missing_and_unused(self):
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): versions("PREPARE_FOR_SUBMISSION"),
            ("GET", "/v1/appStoreVersions/200/build"): BUILD_3,
            ("GET", "/v1/appStoreVersions/200/appStoreVersionLocalizations"): localizations(
                ("201", "nl-NL", None), ("202", "he", None), ("203", "ko", None)),
            ("PATCH", "/v1/appStoreVersionLocalizations/201"): PATCHED,
            ("PATCH", "/v1/appStoreVersionLocalizations/202"): PATCHED,
        }
        notes = [
            {"language": "nl", "text": "Stabiel ⭐"},
            {"language": "iw", "text": "Fixes 🚀"},
            {"language": "ja", "text": "既定の変更"},
        ]
        done, log = self.row(canned, notes)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(whats_new(log, "201"), "Stabiel")   # base language
        self.assertEqual(whats_new(log, "202"), "Fixes")     # he -> iw
        self.assertIsNone(whats_new(log, "203"), "ko must stay empty")
        self.assertIn("store locales with no notes text, left empty: ko", done.stdout)
        self.assertIn("notes locales with no store localization: ja", done.stdout)
        self.assertIn("nl-NL: stripped 1 symbol kind(s)", done.stdout)

    def test_row_3_emoji_only_notes_die(self):
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): versions("PREPARE_FOR_SUBMISSION"),
            ("GET", "/v1/appStoreVersions/200/build"): BUILD_3,
            ("GET", "/v1/appStoreVersions/200/appStoreVersionLocalizations"): localizations(
                ("201", "en-US", None)),
        }
        done, log = self.row(canned, [{"language": "en-US", "text": "🎉✨⭐"}])
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("en-US: release notes are empty once emoji are stripped", done.stderr)
        self.assertFalse([item for item in log if item["method"] == "PATCH"])

    def test_row_4_frozen_version_stops_non_zero(self):
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): versions("IN_REVIEW"),
        }
        done, log = self.row(canned, [{"language": "en-US", "text": "Fresh fixes"}])
        self.assertEqual(done.returncode, 1, "the frozen-state stop must exit non-zero")
        self.assertIn("version 1.2 already exists but is not editable (state: IN_REVIEW)", done.stderr)
        self.assertEqual([item["method"] for item in log], ["GET", "GET"], "nothing may be written")

    def test_row_5_rerun_version_waiting_for_review(self):
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): versions("WAITING_FOR_REVIEW"),
        }
        done, log = self.row(canned, [{"language": "en-US", "text": "Fresh fixes"}])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("version is already waiting for review; leaving whatsNew untouched", done.stdout)
        self.assertEqual([item["method"] for item in log], ["GET", "GET"], "only lookups, no writes")

    def test_row_6_rerun_changes_nothing(self):
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): versions("PREPARE_FOR_SUBMISSION"),
            ("GET", "/v1/appStoreVersions/200/build"): BUILD_3,
            ("GET", "/v1/appStoreVersions/200/appStoreVersionLocalizations"): localizations(
                ("201", "en-US", "Fresh fixes")),
        }
        done, log = self.row(canned, [{"language": "en-US", "text": "Fresh fixes"}])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("build 300 #3 already attached: ok", done.stdout)
        self.assertIn("en-US: whatsNew already up to date", done.stdout)
        self.assertEqual([item["method"] for item in log], ["GET", "GET", "GET", "GET"],
                         "a matching build is not re-attached, equal text is not re-set")

    def test_row_7_attached_build_mismatch_dies(self):
        canned = {
            ("GET", "/v1/apps"): APP,
            ("GET", "/v1/apps/100/appStoreVersions"): versions("PREPARE_FOR_SUBMISSION"),
            ("GET", "/v1/appStoreVersions/200/build"): BUILD_9,
        }
        done, log = self.row(canned, [{"language": "en-US", "text": "Fresh fixes"}])
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("MISMATCH (version wants 3)", done.stdout)
        self.assertIn("attached build #9 does not match the bundle's 3", done.stderr)

    def test_row_8_usage_line_names_publish(self):
        done = subprocess.run([sys.executable, str(ASC), "no-such-command"],
                              capture_output=True, text=True, check=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("publish IPA|APP NOTES_JSON", done.stderr)


if __name__ == "__main__":
    unittest.main()
