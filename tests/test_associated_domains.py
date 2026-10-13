import ast
import datetime
import hashlib
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def signer_namespace():
    # Test the signer offline without importing API/cryptography dependencies.
    source = (Path(__file__).resolve().parents[1] / "tools/asc.py").read_text()
    names = {'associated_domains_allowed', 'requested_associated_domains',
             'requested_capabilities', 'capability_entitlements',
             'install_all_bundles', '_check_signature_seals'}
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in tree.body} != names:
        raise AssertionError('signer patch must contain the complete functions under test')
    namespace = dict(os=os, Path=Path, plistlib=plistlib, hashlib=hashlib, APP_GROUPS=[],
                     APS_KEY='aps-environment', SIWA_KEY='com.apple.developer.applesignin')
    def die(message):
        raise SystemExit(message)
    namespace['die'] = die
    exec(compile(tree, 'patched-asc.py', 'exec'), namespace)
    return namespace


class SignerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.root / 'Fake.app'
        self.app.mkdir()
        self.out = self.root / 'signing'
        self.domains = ['applinks:courses.example.test', 'webcredentials:courses.example.test']
        self.request = self.root / 'requested.entitlements'
        self.request.write_bytes(plistlib.dumps({'com.apple.developer.associated-domains': self.domains}))
        self.environment = patch.dict(os.environ, ASC_ENTITLEMENTS_PATH=str(self.request))
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.signer = signer_namespace()
        self.granted = {'application-identifier': 'FAKE000000.com.example.fake',
                        'com.apple.developer.team-identifier': 'FAKE000000',
                        'get-task-allow': False, 'beta-reports-active': True,
                        'keychain-access-groups': ['FAKE000000.com.example.fake'],
                        'com.apple.security.application-groups': ['group.com.example.fake'],
                        'com.apple.developer.associated-domains': ['*']}
        self.profile = {'Entitlements': self.granted, 'UUID': 'FAKE-PROFILE',
                        'ExpirationDate': datetime.datetime(2099, 1, 1),
                        'DeveloperCertificates': [b'FAKE-CERTIFICATE']}
        self.signer.update(bundles=lambda app: [(Path(app), 'com.example.fake')],
                           profile_payload=lambda raw: self.profile)

    def install(self):
        self.signer['install_all_bundles'](self.app, self.out, lambda ident: b'FAKE-PROFILE',
                                           self.root / 'fake.key', self.root / 'fake.cert')
        return plistlib.loads((self.out / 'entitlements.plist').read_bytes())

    def test_exact_requested_domains_are_preserved(self):
        signed = self.install()
        self.assertEqual(signed['com.apple.developer.associated-domains'], self.domains)
        self.assertNotIn('*', signed['com.apple.developer.associated-domains'])

    def test_missing_or_mismatched_profile_grant_fails(self):
        for value in (None, [], ['applinks:other.example.test']):
            with self.subTest(grant=value):
                self.granted.pop('com.apple.developer.associated-domains', None)
                if value is not None:
                    self.granted['com.apple.developer.associated-domains'] = value
                with self.assertRaisesRegex(SystemExit, 'does not grant.*Associated Domains'):
                    self.install()

    def test_existing_entitlements_remain_unchanged(self):
        expected = dict(self.granted)
        expected.pop('com.apple.developer.associated-domains')
        signed = self.install()
        signed.pop('com.apple.developer.associated-domains')
        self.assertEqual(signed, expected)
        self.request.write_bytes(plistlib.dumps({}))
        self.assertEqual(self.install(), expected)

    def test_post_sign_verification_accepts_only_concrete_granted_domains(self):
        import re
        self.signer['re'] = re
        info = self.app / 'Info.plist'
        info.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.example.fake'}))
        seal = self.app / '_CodeSignature/CodeResources'
        seal.parent.mkdir()
        seal.write_bytes(plistlib.dumps({'files2': {}}))
        cd = ('team_name: Some("FAKE000000")\nInfo (1): ' + hashlib.sha256(info.read_bytes()).hexdigest()
              + '\nResources (3): ' + hashlib.sha256(seal.read_bytes()).hexdigest())
        self.signer['subprocess'] = SimpleNamespace(run=lambda args, **kwargs:
            SimpleNamespace(returncode=0, stderr='', stdout=cd if 'code-directory' in args else b'FAKE-CMS'))
        self.signer['serialization'] = SimpleNamespace(Encoding=SimpleNamespace(DER=None))
        self.signer['pkcs7'] = SimpleNamespace(load_pem_pkcs7_certificates=lambda cms:
            [SimpleNamespace(public_bytes=lambda encoding: b'FAKE-CERTIFICATE')])
        for domains, allowed in ((self.domains, True), (None, True), ([], True),
                                 (['applinks:other.example.test'], True), (['*'], False),
                                 (['activitycontinuation:courses.example.test'], False), (['applinks:'], False)):
            with self.subTest(domains=domains):
                signed = dict(self.granted, **{'com.apple.developer.associated-domains': domains})
                if domains is None:
                    signed.pop('com.apple.developer.associated-domains')
                self.signer['signature_blob'] = lambda *args: plistlib.dumps(signed)
                results = {}
                self.signer['_check_signature_seals'](lambda ok, msg: results.update({msg: bool(ok)}),
                    self.app, self.app / 'Fake', 'fake-rcodesign', self.profile, 'FAKE000000',
                    'FAKE000000.com.example.fake')
                self.assertEqual(results.get('signed Associated Domains match the profile grant', True), allowed)
                self.assertEqual(results['signed Associated Domains match the app request'], domains == self.domains)
                self.assertEqual(all(results.values()), domains == self.domains)
        self.granted['com.apple.developer.associated-domains'] = ['applinks:other.example.test']
        self.assertFalse(self.signer['associated_domains_allowed'](self.domains, self.granted['com.apple.developer.associated-domains']))


class CapabilityTests(SignerTests):
    """Push and Sign in with Apple requested through ASC_ENTITLEMENTS_PATH."""

    def request_caps(self, **caps):
        self.request.write_bytes(plistlib.dumps({'com.apple.developer.associated-domains': self.domains, **caps}))

    def test_push_takes_the_profile_environment(self):
        self.granted['aps-environment'] = 'production'
        self.request_caps(**{'aps-environment': 'development'})
        self.assertEqual(self.install()['aps-environment'], 'production')

    def test_push_without_a_profile_grant_fails(self):
        self.request_caps(**{'aps-environment': 'development'})
        with self.assertRaisesRegex(SystemExit, 'does not grant aps-environment'):
            self.install()

    def test_push_request_must_name_an_environment(self):
        self.granted['aps-environment'] = 'production'
        self.request_caps(**{'aps-environment': 'staging'})
        with self.assertRaisesRegex(SystemExit, 'development or production'):
            self.install()

    def test_sign_in_with_apple_is_signed_when_granted(self):
        self.granted['com.apple.developer.applesignin'] = ['Default']
        self.request_caps(**{'com.apple.developer.applesignin': ['Default']})
        self.assertEqual(self.install()['com.apple.developer.applesignin'], ['Default'])

    def test_sign_in_with_apple_without_a_grant_fails(self):
        self.request_caps(**{'com.apple.developer.applesignin': ['Default']})
        with self.assertRaisesRegex(SystemExit, 'does not grant Sign in with Apple'):
            self.install()

    def test_sign_in_with_apple_request_must_be_default(self):
        self.granted['com.apple.developer.applesignin'] = ['Default']
        self.request_caps(**{'com.apple.developer.applesignin': ['Other']})
        with self.assertRaisesRegex(SystemExit, r'must be \["Default"\]'):
            self.install()

    def test_sign_in_with_apple_string_grant_is_compared_whole(self):
        # "Default" must not match inside "NotDefault": a string grant is one value, not a substring test.
        self.request_caps(**{'com.apple.developer.applesignin': ['Default']})
        self.granted['com.apple.developer.applesignin'] = 'Default'
        self.assertEqual(self.install()['com.apple.developer.applesignin'], ['Default'])
        self.granted['com.apple.developer.applesignin'] = 'NotDefault'
        with self.assertRaisesRegex(SystemExit, 'does not grant Sign in with Apple'):
            self.install()

    def test_post_sign_sign_in_with_apple_compares_the_grant_whole(self):
        import re
        self.signer['re'] = re
        info = self.app / 'Info.plist'
        info.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.example.fake'}))
        seal = self.app / '_CodeSignature/CodeResources'
        seal.parent.mkdir()
        seal.write_bytes(plistlib.dumps({'files2': {}}))
        cd = ('team_name: Some("FAKE000000")\nInfo (1): ' + hashlib.sha256(info.read_bytes()).hexdigest()
              + '\nResources (3): ' + hashlib.sha256(seal.read_bytes()).hexdigest())
        self.signer['subprocess'] = SimpleNamespace(run=lambda args, **kwargs:
            SimpleNamespace(returncode=0, stderr='', stdout=cd if 'code-directory' in args else b'FAKE-CMS'))
        self.signer['serialization'] = SimpleNamespace(Encoding=SimpleNamespace(DER=None))
        self.signer['pkcs7'] = SimpleNamespace(load_pem_pkcs7_certificates=lambda cms:
            [SimpleNamespace(public_bytes=lambda encoding: b'FAKE-CERTIFICATE')])
        self.request_caps(**{'com.apple.developer.applesignin': ['Default']})
        key = 'com.apple.developer.applesignin'
        for grant, matches in ((['Default'], True), ('Default', True), ('NotDefault', False),
                               (['NotDefault'], False), ([], False), (None, False)):
            with self.subTest(grant=grant):
                self.granted[key] = grant
                if grant is None:
                    self.granted.pop(key)
                signed = dict(self.granted, **{key: ['Default']})
                self.signer['signature_blob'] = lambda *args, signed=signed: plistlib.dumps(signed)
                results = {}
                self.signer['_check_signature_seals'](lambda ok, msg: results.update({msg: bool(ok)}),
                    self.app, self.app / 'Fake', 'fake-rcodesign', self.profile, 'FAKE000000',
                    'FAKE000000.com.example.fake')
                self.assertEqual(results['signed Sign in with Apple matches the app request'], matches)

    def test_unrequested_capabilities_are_not_signed(self):
        self.granted['aps-environment'] = 'production'
        self.granted['com.apple.developer.applesignin'] = ['Default']
        signed = self.install()
        self.assertNotIn('aps-environment', signed)
        self.assertNotIn('com.apple.developer.applesignin', signed)


if __name__ == '__main__':
    unittest.main()
