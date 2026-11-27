"""tools/asc.py make_test_profile: the TEST identity profile grants the capabilities the app
requests (ASC_ENTITLEMENTS_PATH), as an App Store profile for a bundle id with those
capabilities does, so the offline validation of an app with push, Sign in with Apple or
Associated Domains reaches the validator instead of stopping in capability_entitlements.
The functions under test are taken from asc.py with ast and run offline; the CMS signature
is a stub that returns the payload.

Rows (expected results written before the code):
  1  nothing requested: only the base entitlements, no capability keys
  2  Sign in with Apple requested: granted ["Default"], capability_entitlements accepts it
  3  push requested (development): granted "production", signed as production
  4  Associated Domains requested: granted "*", the requested domains are allowed
Mutant (checked by hand when the test was written):
  M1  drop the grant block from make_test_profile -> rows 2-4
"""
import ast
import datetime
import os
import plistlib
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

NAMES = {"make_test_profile", "requested_capabilities", "requested_associated_domains",
         "associated_domains_allowed", "capability_entitlements", "profile_payload"}
SIWA = "com.apple.developer.applesignin"
APS = "aps-environment"
DOMAINS = "com.apple.developer.associated-domains"


class _Builder:
    def set_data(self, data):
        self.data = data
        return self

    def add_signer(self, *_):
        return self

    def sign(self, *_):
        return b"CMS" + self.data + b"END"


def namespace():
    source = (Path(__file__).resolve().parents[1] / "tools/asc.py").read_text()
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    if {n.name for n in tree.body} != NAMES:
        raise AssertionError("asc.py must contain the functions under test")
    ns = dict(os=os, Path=Path, plistlib=plistlib, uuid=uuid, APP_GROUPS=[], TEST_TEAM="TEST000000",
              APS_KEY=APS, SIWA_KEY=SIWA,
              pkcs7=SimpleNamespace(PKCS7SignatureBuilder=_Builder),
              hashes=SimpleNamespace(SHA256=lambda: None),
              serialization=SimpleNamespace(Encoding=SimpleNamespace(DER=None)),
              cert_path_bytes=lambda: b"cert")

    def die(message):
        raise SystemExit(message)
    ns["die"] = die
    exec(compile(tree, "asc.py", "exec"), ns)
    return ns


class TestIdentityCapabilities(unittest.TestCase):
    def setUp(self):
        self.ns = namespace()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cert = SimpleNamespace(not_valid_after_utc=datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc))
        self.now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    def granted(self, requested):
        env = {}
        if requested is not None:
            path = Path(self.tmp.name) / "Runner.entitlements"
            path.write_bytes(plistlib.dumps(requested))
            env["ASC_ENTITLEMENTS_PATH"] = str(path)
        with patch.dict(os.environ, env, clear=False):
            if requested is None:
                os.environ.pop("ASC_ENTITLEMENTS_PATH", None)
            prov = self.ns["make_test_profile"]("com.example.app", None, self.cert, self.now)
            return self.ns["profile_payload"](prov)["Entitlements"], self.ns["requested_capabilities"]()

    def test_row1_nothing_requested(self):
        ents, _ = self.granted(None)
        self.assertEqual(ents["application-identifier"], "TEST000000.com.example.app")
        for key in (SIWA, APS, DOMAINS):
            self.assertNotIn(key, ents)

    def test_row2_sign_in_with_apple(self):
        ents, requested = self.granted({SIWA: ["Default"]})
        self.assertEqual(ents[SIWA], ["Default"])
        self.assertEqual(self.ns["capability_entitlements"](requested, ents, "com.example.app"),
                         {SIWA: ["Default"]})

    def test_row3_push(self):
        ents, requested = self.granted({APS: "development"})
        self.assertEqual(ents[APS], "production")
        self.assertEqual(self.ns["capability_entitlements"](requested, ents, "com.example.app"),
                         {APS: "production"})

    def test_row4_associated_domains(self):
        domains = ["applinks:example.com", "webcredentials:example.com"]
        ents, _ = self.granted({DOMAINS: domains})
        self.assertEqual(ents[DOMAINS], "*")
        self.assertTrue(self.ns["associated_domains_allowed"](domains, ents[DOMAINS]))


if __name__ == "__main__":
    unittest.main()
