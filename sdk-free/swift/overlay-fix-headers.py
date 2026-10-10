#!/usr/bin/env python3
"""Module-clean fixes on the sdkm framework header copies, which the Swift importer reads.
  overlay-fix-headers.py foundation <Foundation.framework>/Headers/Foundation.h
  overlay-fix-headers.py uikit     <UIKit.framework>/Headers/UIKit.h
Every replacement must apply; a miss means the header drifted and the build stops."""
import re
import sys


def must(s, old, new):
    if new in s:
        return s
    if old not in s:
        sys.exit("overlay-fix-headers: header drifted, missing: " + old[:70])
    return s.replace(old, new)


def foundation(p):
    with open(p) as f:
        s = f.read()
    RENAMES = ["Bundle", "Thread", "UserDefaults", "FileManager", "ProcessInfo", "NotificationCenter", "OperationQueue", "RunLoop", "Timer",
               "JSONSerialization", "DateFormatter", "NumberFormatter", "Operation", "Stream", "InputStream", "OutputStream"]
    n = 0
    for r in RENAMES:
        pat = re.compile("^@interface NS" + r + r"( *):", re.M)
        s, k = pat.subn('__attribute__((swift_name("' + r + '"))) @interface NS' + r + " :", s)
        n += k
    s = must(s, "- (void)setObject:(nullable id)value forKey:(NSString *)defaultName;", "- (void)setObject:(nullable id)value forKey:(NSString *)defaultName __attribute__((swift_name(\"set(_:forKey:)\")));")
    s = must(s, "- (void)setBool:(BOOL)value forKey:(NSString *)defaultName;", "- (void)setBool:(BOOL)value forKey:(NSString *)defaultName __attribute__((swift_name(\"set(_:forKey:)\")));")
    s = must(s, "#define NS_ENUM(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)", "#include <CoreFoundation/CFAvailability.h>\n#define NS_ENUM(_type, _name) CF_ENUM(_type, _name)")
    s = must(s, "#define NS_OPTIONS(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)", "#define NS_OPTIONS(_type, _name) CF_OPTIONS(_type, _name)")
    s = must(s, "typedef NSString *NSErrorDomain __attribute__((swift_wrapper(struct)));", "typedef NSString *NSErrorDomain __attribute__((swift_bridged_typedef));")
    s = must(s, "typedef NSString *NSErrorUserInfoKey __attribute__((swift_wrapper(struct)));", "typedef NSString *NSErrorUserInfoKey __attribute__((swift_bridged_typedef));")
    if 'swift_name("NSString.CompareOptions")' not in s:
        s2 = re.sub(r"(typedef NS_OPTIONS\(NSUInteger, NSStringCompareOptions\) \{[^}]*\})(;)", r'\1 __attribute__((swift_name("NSString.CompareOptions")))\2', s)
        if s2 == s:
            sys.exit("overlay-fix-headers: header drifted, missing: NSStringCompareOptions typedef")
        s = s2
    s = must(s, "- (instancetype)initWithBytes:(nullable const void *)bytes length:(NSUInteger)length;\n@property(readonly) NSUInteger length;",
             "- (instancetype)initWithBytes:(nullable const void *)bytes length:(NSInteger)length;\n@property(readonly) NSInteger length; /* NSInteger: the Swift importer must see Int, as on Apple's SDK; the overlay's NSData subclass overrides it with Int (same ABI) */")
    # The 6.x importer maps NSUInteger members to UInt; the 5.3 overlay (and Apple's SDK apinotes) expect Int
    # for the size/count members below. The sysroot copies keep NSUInteger; only the Swift view changes.
    for old, new in [
        ("typedef struct _NSRange { NSUInteger location; NSUInteger length; } NSRange;",
         "typedef struct _NSRange { NSInteger location; NSInteger length; } NSRange;"),
        ("static inline NSRange NSMakeRange(NSUInteger loc, NSUInteger len)",
         "static inline NSRange NSMakeRange(NSInteger loc, NSInteger len)"),
        ("- (NSUInteger)countByEnumeratingWithState:(NSFastEnumerationState *)state objects:(id __unsafe_unretained _Nullable[_Nullable])buffer count:(NSUInteger)len;",
         "- (NSInteger)countByEnumeratingWithState:(NSFastEnumerationState *)state objects:(id __unsafe_unretained _Nullable[_Nullable])buffer count:(NSInteger)len;"),
        ("@interface NSString : NSObject <NSCopying, NSMutableCopying, NSSecureCoding>\n@property(readonly) NSUInteger length;",
         "@interface NSString : NSObject <NSCopying, NSMutableCopying, NSSecureCoding>\n@property(readonly) NSInteger length;"),
        ("+ (instancetype)dataWithBytes:(nullable const void *)bytes length:(NSUInteger)length;",
         "+ (instancetype)dataWithBytes:(nullable const void *)bytes length:(NSInteger)length;"),
        ("+ (instancetype)dataWithBytesNoCopy:(void *)bytes length:(NSUInteger)length freeWhenDone:(BOOL)b;",
         "+ (instancetype)dataWithBytesNoCopy:(void *)bytes length:(NSInteger)length freeWhenDone:(BOOL)b;"),
        ("- (void)getBytes:(void *)buffer length:(NSUInteger)length;",
         "- (void)getBytes:(void *)buffer length:(NSInteger)length;"),
        ("@property NSUInteger length;",
         "@property NSInteger length;"),
        ("+ (nullable instancetype)dataWithLength:(NSUInteger)length;",
         "+ (nullable instancetype)dataWithLength:(NSInteger)length;"),
        ("- (void)appendBytes:(const void *)bytes length:(NSUInteger)length;",
         "- (void)appendBytes:(const void *)bytes length:(NSInteger)length;"),
        ("- (void)replaceBytesInRange:(NSRange)range withBytes:(const void *)bytes length:(NSUInteger)replacementLength;",
         "- (void)replaceBytesInRange:(NSRange)range withBytes:(const void *)bytes length:(NSInteger)replacementLength;"),
        ("- (void)setLength:(NSUInteger)length;",
         "- (void)setLength:(NSInteger)length;"),
        ("+ (instancetype)dictionaryWithObjects:(const ObjectType _Nonnull[_Nonnull])objects forKeys:(const KeyType<NSCopying> _Nonnull[_Nonnull])keys count:(NSUInteger)cnt;",
         "+ (instancetype)dictionaryWithObjects:(const ObjectType _Nonnull[_Nonnull])objects forKeys:(const KeyType<NSCopying> _Nonnull[_Nonnull])keys count:(NSInteger)cnt;"),
        ("typedef int32_t OSStatus; typedef unsigned char Boolean;",
         "typedef int32_t OSStatus; typedef _Bool Boolean; /* imports as Swift Bool, as on Apple's SDK */"),
    ]:
        s = must(s, old, new)
    n = s.count("@property(readonly) NSUInteger count;")
    if n != 3:
        sys.exit("overlay-fix-headers: header drifted, expected 3 count properties, found " + str(n))
    s = s.replace("@property(readonly) NSUInteger count;", "@property(readonly) NSInteger count;")
    s = must(s, "#import <objc/NSObject.h>\n#import <objc/NSObjCRuntime.h>", "#if __has_feature(modules)\n@import ObjectiveC;\n#else\n#import <objc/NSObject.h>\n#import <objc/NSObjCRuntime.h>\n#endif")
    s = must(s, "typedef NS_ENUM(NSUInteger, NSStringEncoding) {", "typedef NSUInteger NSStringEncoding;\nenum {")
    s = must(s, "@property(readonly, copy) NSString *absoluteString;", "@property(readonly, copy, nullable) NSString *absoluteString;")
    s = must(s, "- (NSURL *)URLByAppendingPathComponent:(NSString *)pathComponent;", "- (nullable NSURL *)URLByAppendingPathComponent:(NSString *)pathComponent;")
    with open(p, "w") as f:
        f.write(s)
    print("renamed", n, "of", len(RENAMES), file=sys.stderr)


def cf(p):
    with open(p) as f:
        s = f.read()
    if "typedef _Bool Boolean;" not in s:
        s, n = re.subn(r"typedef unsigned char\s+Boolean;", "typedef _Bool Boolean; /* imports as Swift Bool, as on Apple's SDK */", s, count=1)
        if n != 1:
            sys.exit("overlay-fix-headers: header drifted, missing Boolean typedef")
        with open(p, "w") as f:
            f.write(s)
    print("cf patched", file=sys.stderr)


def uikit(p):
    with open(p) as f:
        s = f.read()
    subs = [
        ('typedef NSString *UIApplicationOpenURLOptionsKey __attribute__((swift_wrapper(struct)));',
         'typedef NSString *UIApplicationOpenURLOptionsKey __attribute__((swift_wrapper(struct))) __attribute__((swift_name("UIApplication.OpenURLOptionsKey")));'),
        ('typedef NSString *UIApplicationOpenExternalURLOptionsKey __attribute__((swift_wrapper(struct)));',
         'typedef NSString *UIApplicationOpenExternalURLOptionsKey __attribute__((swift_wrapper(struct))) __attribute__((swift_name("UIApplication.OpenExternalURLOptionsKey")));'),
        ('- (BOOL)canOpenURL:(NSURL *)url;',
         '- (BOOL)canOpenURL:(NSURL *)url __attribute__((swift_name("canOpenURL(_:)")));'),
        ('- (void)openURL:(NSURL *)url options:(NSDictionary<UIApplicationOpenExternalURLOptionsKey, id> *)options completionHandler:(void (^_Nullable)(BOOL success))completion;',
         '- (void)openURL:(NSURL *)url options:(NSDictionary<UIApplicationOpenExternalURLOptionsKey, id> *)options completionHandler:(void (^_Nullable)(BOOL success))completion __attribute__((swift_name("open(_:options:completionHandler:)")));'),
    ]
    for old, new in subs:
        s = must(s, old, new)
    add = 'UIKIT_EXTERN UIApplicationOpenExternalURLOptionsKey const UIApplicationOpenURLOptionUniversalLinksOnly __attribute__((swift_name("UIApplicationOpenExternalURLOptionsKey.universalLinksOnly")));'
    if 'UIApplicationOpenURLOptionUniversalLinksOnly' not in s:
        s = s.replace('UIKIT_EXTERN NSString *const UIApplicationLaunchOptionsURLKey;', add + '\nUIKIT_EXTERN NSString *const UIApplicationLaunchOptionsURLKey;', 1)
    with open(p, "w") as f:
        f.write(s)
    print("uikit patched", file=sys.stderr)


mode = sys.argv[1] if len(sys.argv) > 1 else ""
{"foundation": foundation, "uikit": uikit, "cf": cf}.get(mode, lambda p: sys.exit("usage: overlay-fix-headers.py foundation|uikit|cf <header>"))(sys.argv[2])
