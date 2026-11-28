import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "sdk-free/swift/features.py"
APINOTES = ROOT / "sdk-free/swift/overlay-apinotes.py"
FIXHDR = ROOT / "sdk-free/swift/overlay-fix-headers.py"
MKAPP = ROOT / "tools/mkapp.py"


def run(tool, *args):
    return subprocess.run([sys.executable, str(tool), *args],
                          capture_output=True, text=True)


class Features(unittest.TestCase):
    def test_flags_from_fixture_cmake(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdlib = Path(tmp) / "stdlib"
            stdlib.mkdir()
            (stdlib / "a.cmake").write_text(
                'list(APPEND X "-enable-experimental-feature" "Embedded")\n'
                'list(APPEND X "-enable-experimental-feature" "Lifetimes")\n'
                'list(APPEND X "-enable-upcoming-feature" "ConciseMagicFile")\n')
            (stdlib / "b.cmake").write_text(
                '"-enable-experimental-feature" "Lifetimes"\n')
            r = run(FEATURES, tmp, "a.cmake", "b.cmake")
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            # Embedded excluded, Lifetimes deduped
            self.assertEqual(lines, ["-enable-experimental-feature", "Lifetimes",
                                     "-enable-upcoming-feature", "ConciseMagicFile"])


class Apinotes(unittest.TestCase):
    def test_bridging_entries_installed_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            mock = Path(tmp) / "mock"
            mock.mkdir()
            (mock / "Foundation.apinotes").write_text("Classes:\nTags:\nOther: x\n")
            (mock / "CoreGraphics.apinotes").write_text("cg-body\n")
            fw, res = Path(tmp) / "FW", Path(tmp) / "RES"
            r = run(APINOTES, str(mock), str(fw), str(res))
            self.assertEqual(r.returncode, 0, r.stderr)
            got = (fw / "Foundation.framework/Headers/Foundation.apinotes").read_text()
            self.assertIn("SwiftBridge: Data", got)
            self.assertIn("SwiftName: NSData.ReadingOptions", got)
            self.assertIn("Other: x", got)  # untouched content survives
            for d in ("Modules/Foundation.apinotes", "Foundation.apinotes"):
                self.assertTrue((fw / "Foundation.framework" / d).is_file(), d)
            self.assertEqual((res / "Foundation.apinotes").read_text(), got)
            self.assertEqual((res / "CoreGraphics.apinotes").read_text(), "cg-body\n")

    def test_missing_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            mock = Path(tmp) / "mock"
            mock.mkdir()
            (mock / "Foundation.apinotes").write_text("Classes:\n")  # no Tags:
            r = run(APINOTES, str(mock), str(Path(tmp) / "FW"), str(Path(tmp) / "RES"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("drifted", r.stderr)


FOUNDATION = """#import <objc/NSObject.h>
#import <objc/NSObjCRuntime.h>
#define NS_ENUM(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)
#define NS_OPTIONS(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)
typedef int32_t OSStatus; typedef unsigned char Boolean;
typedef NSString *NSErrorDomain __attribute__((swift_wrapper(struct)));
typedef NSString *NSErrorUserInfoKey __attribute__((swift_wrapper(struct)));
typedef NS_OPTIONS(NSUInteger, NSStringCompareOptions) { A = 1 };
@interface NSBundle :
@interface NSThread :
@interface NSUserDefaults :
@interface NSFileManager :
@interface NSProcessInfo :
@interface NSNotificationCenter :
@interface NSOperationQueue :
@interface NSRunLoop :
@interface NSTimer :
@interface NSJSONSerialization :
@interface NSDateFormatter :
@interface NSNumberFormatter :
@interface NSOperation :
@interface NSStream :
@interface NSInputStream :
@interface NSOutputStream :
- (void)setObject:(nullable id)value forKey:(NSString *)defaultName;
- (void)setBool:(BOOL)value forKey:(NSString *)defaultName;
- (instancetype)initWithBytes:(nullable const void *)bytes length:(NSUInteger)length;
@property(readonly) NSUInteger length;
typedef struct _NSRange { NSUInteger location; NSUInteger length; } NSRange;
static inline NSRange NSMakeRange(NSUInteger loc, NSUInteger len)
- (NSUInteger)countByEnumeratingWithState:(NSFastEnumerationState *)state objects:(id __unsafe_unretained _Nullable[_Nullable])buffer count:(NSUInteger)len;
@interface NSString : NSObject <NSCopying, NSMutableCopying, NSSecureCoding>
@property(readonly) NSUInteger length;
+ (instancetype)dataWithBytes:(nullable const void *)bytes length:(NSUInteger)length;
+ (instancetype)dataWithBytesNoCopy:(void *)bytes length:(NSUInteger)length freeWhenDone:(BOOL)b;
- (void)getBytes:(void *)buffer length:(NSUInteger)length;
@property NSUInteger length;
+ (nullable instancetype)dataWithLength:(NSUInteger)length;
- (void)appendBytes:(const void *)bytes length:(NSUInteger)length;
- (void)replaceBytesInRange:(NSRange)range withBytes:(const void *)bytes length:(NSUInteger)replacementLength;
- (void)setLength:(NSUInteger)length;
+ (instancetype)dictionaryWithObjects:(const ObjectType _Nonnull[_Nonnull])objects forKeys:(const KeyType<NSCopying> _Nonnull[_Nonnull])keys count:(NSUInteger)cnt;
@property(readonly) NSUInteger count;
@property(readonly) NSUInteger count;
@property(readonly) NSUInteger count;
typedef NS_ENUM(NSUInteger, NSStringEncoding) {
@property(readonly, copy) NSString *absoluteString;
- (NSURL *)URLByAppendingPathComponent:(NSString *)pathComponent;
"""

UIKIT = """typedef NSString *UIApplicationOpenURLOptionsKey __attribute__((swift_wrapper(struct)));
typedef NSString *UIApplicationOpenExternalURLOptionsKey __attribute__((swift_wrapper(struct)));
- (BOOL)canOpenURL:(NSURL *)url;
- (void)openURL:(NSURL *)url options:(NSDictionary<UIApplicationOpenExternalURLOptionsKey, id> *)options completionHandler:(void (^_Nullable)(BOOL success))completion;
UIKIT_EXTERN NSString *const UIApplicationLaunchOptionsURLKey;
"""


class FixHeaders(unittest.TestCase):
    def test_foundation_applies_every_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Path(tmp) / "Foundation.h"
            h.write_text(FOUNDATION)
            r = run(FIXHDR, "foundation", str(h))
            self.assertEqual(r.returncode, 0, r.stderr)
            got = h.read_text()
            self.assertIn('swift_name("Bundle")', got)
            self.assertIn('swift_name("set(_:forKey:)")', got)
            self.assertIn("CF_ENUM(_type, _name)", got)
            self.assertIn("swift_bridged_typedef", got)
            self.assertIn('swift_name("NSString.CompareOptions")', got)
            self.assertIn("typedef _Bool Boolean;", got)
            self.assertIn("@import ObjectiveC;", got)
            self.assertEqual(got.count("NSInteger count;"), 3)

    def test_uikit_and_cf(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Path(tmp) / "UIKit.h"
            h.write_text(UIKIT)
            r = run(FIXHDR, "uikit", str(h))
            self.assertEqual(r.returncode, 0, r.stderr)
            got = h.read_text()
            self.assertIn('swift_name("UIApplication.OpenURLOptionsKey")', got)
            self.assertIn('swift_name("canOpenURL(_:)")', got)
            self.assertIn("UIApplicationOpenURLOptionUniversalLinksOnly", got)
            cf = Path(tmp) / "CF.h"
            cf.write_text("typedef unsigned char Boolean;\n")
            r = run(FIXHDR, "cf", str(cf))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("typedef _Bool Boolean;", cf.read_text())

    def test_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Path(tmp) / "Foundation.h"
            h.write_text("// nothing the tool needs\n")
            r = run(FIXHDR, "foundation", str(h))
            self.assertEqual(r.returncode, 1)
            self.assertIn("header drifted", r.stderr)
            bad = Path(tmp) / "CF.h"
            bad.write_text("typedef int Boolean;\n")
            r = run(FIXHDR, "cf", str(bad))
            self.assertEqual(r.returncode, 1)


class Mkapp(unittest.TestCase):
    def test_bundle_layout_and_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "hello"
            binary.write_bytes(b"\xcf\xfa" + b"\0" * 32)
            out = Path(tmp) / "Out.app"
            r = run(MKAPP, str(binary), str(out), "com.example.hello", "Hello")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((out / "Hello").read_bytes(), binary.read_bytes())
            self.assertEqual((out / "PkgInfo").read_bytes(), b"APPL????")
            with open(out / "Info.plist", "rb") as f:
                info = plistlib.load(f)
            self.assertEqual(info["CFBundleExecutable"], "Hello")
            self.assertEqual(info["CFBundleIdentifier"], "com.example.hello")
            self.assertEqual(info["CFBundlePackageType"], "APPL")
            r = run(MKAPP, str(binary), str(Path(tmp) / "D.app"), "com.example.d")
            with open(Path(tmp) / "D.app/Info.plist", "rb") as f:
                info = plistlib.load(f)
            self.assertEqual(info["CFBundleExecutable"], "HelloNoSDK")  # default name


if __name__ == "__main__":
    unittest.main()
