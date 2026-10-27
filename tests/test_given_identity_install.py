"""tools/asc.py given-identity with the REAL installer: the key and certificate it links into ship-signing.

tests/test_given_identity.py stubs install_all_bundles, so it cannot see what the installer does to
the files it is given. This one imports tools/asc.py and runs given_identity, install_all_bundles,
profile_payload, check_named_profile and key_matches_certificate for real, on a real RSA key and a
real self-signed certificate. Only the app and the profile are synthetic (a bundle with an
Info.plist; a plist where Apple's profile would be a CMS wrapper around the same plist).

Rows (expected results written before the code):
  1  key, certificate and profile elsewhere, absolute paths -> ship-signing/key.pem and cert.der are
     links that read back the original bytes
  2  ASC_SIGNING_KEY and ASC_SIGNING_CERT name the files already in ship-signing (real files) ->
     their bytes survive, still real files, and signing inputs read back
  3  the same, run twice (the second time they are links the first run made) -> still readable
  4  relative paths (key.pem, cert.der in the working directory) -> links that read back the originals
  5  ship-signing already holds a regular file that is not the given key -> refused, the file untouched
  6  a stale link in ship-signing that points elsewhere -> replaced by a link to the given file
Mutants (each must fail its row; checked by hand when the test was written):
  M1  link to the path as given, not made absolute -> row 4
  M2  unlink the destination without comparing it with the source -> rows 2 and 3
  M3  drop the refusal of a regular file -> row 5
"""
import datetime
import importlib.util
import os
import plistlib
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:  # pragma: no cover - the pymobile3 venv and CI have it
    x509 = None

TOOLS = Path(__file__).resolve().parents[1] / "tools"
TEAM, IDENT = "TEAM123456", "com.example.app"


def load_asc():
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("asc_under_test", TOOLS / "asc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(x509 is None, "needs cryptography (the pymobile3 venv has it)")
class GivenIdentityInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asc = load_asc()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Apple Distribution: Test")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(1)
                .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
                .sign(key, hashes.SHA256()))
        cls.key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
        cls.cert_der = cert.public_bytes(serialization.Encoding.DER)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.keep = self.root / "keep"  # where the credentials live
        self.keep.mkdir()
        self.app = self.root / "Runner.app"
        self.app.mkdir()
        (self.app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": IDENT}))
        profile = {"UUID": str(uuid.uuid4()), "TeamIdentifier": [TEAM],
                   "ExpirationDate": datetime.datetime.now() + datetime.timedelta(days=30),
                   "Entitlements": {"application-identifier": f"{TEAM}.{IDENT}",
                                    "com.apple.developer.team-identifier": TEAM},
                   "DeveloperCertificates": [self.cert_der]}
        self.profile = self.keep / "app.mobileprovision"
        self.profile.write_bytes(b"CMS-WRAPPER" + plistlib.dumps(profile) + b"CMS-TRAILER")
        self.out = self.root / "ship-signing"
        for var in ("ASC_EXPORT_OPTIONS", "ASC_ENTITLEMENTS_PATH"):
            self.addCleanup(os.environ.pop, var, None) if var in os.environ else None
            os.environ.pop(var, None)

    def place(self, directory, key="key.pem", cert="cert.der"):
        k, c = Path(directory) / key, Path(directory) / cert
        k.write_bytes(self.key_pem)
        c.write_bytes(self.cert_der)
        return k, c

    def run_given(self, key, cert):
        env = {"ASC_SIGNING_KEY": str(key), "ASC_SIGNING_CERT": str(cert), "ASC_PROFILE": str(self.profile)}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])
        self.asc.given_identity(str(self.app), str(self.out))

    def assertSigningInputs(self):
        """What rcodesign reads: ship-signing/key.pem and cert.der must give the original bytes."""
        self.assertEqual((self.out / "key.pem").read_bytes(), self.key_pem)
        self.assertEqual((self.out / "cert.der").read_bytes(), self.cert_der)
        self.assertTrue((self.out / "entitlements.plist").is_file())

    def test_row1_absolute_paths_elsewhere(self):
        key, cert = self.place(self.keep)
        self.run_given(key, cert)
        self.assertSigningInputs()
        self.assertTrue((self.out / "key.pem").is_symlink())
        self.assertEqual(key.read_bytes(), self.key_pem)

    def test_row2_files_already_in_ship_signing_survive(self):
        self.out.mkdir()
        key, cert = self.place(self.out)
        self.run_given(key, cert)
        self.assertSigningInputs()
        self.assertFalse(key.is_symlink(), "the given key was replaced by a link")
        self.assertFalse(cert.is_symlink(), "the given certificate was replaced by a link")

    def test_row3_second_run_over_the_links_of_the_first(self):
        key, cert = self.place(self.keep)
        self.run_given(key, cert)
        self.run_given(self.out / "key.pem", self.out / "cert.der")
        self.assertSigningInputs()
        self.assertEqual(key.read_bytes(), self.key_pem)

    def test_row4_relative_paths(self):
        self.place(self.keep)
        os.chdir(self.keep)
        self.run_given("key.pem", "cert.der")
        self.assertSigningInputs()
        self.assertEqual((self.out / "key.pem").resolve(), self.keep / "key.pem")

    def test_row5_a_regular_file_that_is_not_the_key_is_refused(self):
        key, cert = self.place(self.keep)
        self.out.mkdir()
        other = self.out / "key.pem"
        other.write_bytes(b"somebody else's key")
        with self.assertRaises(SystemExit) as refused:
            self.run_given(key, cert)
        self.assertIn("key.pem", str(refused.exception.code))
        self.assertEqual(other.read_bytes(), b"somebody else's key")
        self.assertFalse(other.is_symlink())
        self.assertEqual(key.read_bytes(), self.key_pem)

    def test_row6_a_stale_link_is_replaced(self):
        key, cert = self.place(self.keep)
        self.out.mkdir()
        (self.out / "key.pem").symlink_to(self.root / "gone.pem")
        (self.out / "cert.der").symlink_to(self.root / "gone.der")
        self.run_given(key, cert)
        self.assertSigningInputs()


if __name__ == "__main__":
    unittest.main()
