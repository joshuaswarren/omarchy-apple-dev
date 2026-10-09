#pragma once
// Omarchy SDK-free Foundation subset: written from the public behaviour and names of the classes, not copied
// from any SDK. Grows as builds fail.
#import <objc/NSObject.h>
#import <objc/NSObjCRuntime.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreFoundation/CoreFoundation.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <sys/cdefs.h>
#include <assert.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <sys/param.h>
#include <os/log.h>
#include <time.h>

#define NS_ASSUME_NONNULL_BEGIN _Pragma("clang assume_nonnull begin")
#define NS_ASSUME_NONNULL_END _Pragma("clang assume_nonnull end")
/* Anonymous and named enums: RN 0.87 headers use `NS_ENUM(NSInteger){...}`. */
#define _NSEO_PICK(_1, _2, _3, ...) _3
#define _NSEO_1(_type) enum : _type
#define _NSEO_2(_type, _name) enum _name : _type _name; enum _name : _type
#define NS_ENUM(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)
#define NS_OPTIONS(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)
#define NS_CLOSED_ENUM(...) _NSEO_PICK(__VA_ARGS__, _NSEO_2, _NSEO_1)(__VA_ARGS__)
#define NS_TYPED_ENUM
#define NS_TYPED_EXTENSIBLE_ENUM
#define NS_STRING_ENUM
#define NS_EXTENSIBLE_STRING_ENUM
#define NS_SWIFT_NAME(x) __attribute__((swift_name(#x)))
#define NS_REFINED_FOR_SWIFT __attribute__((swift_private))
#define NS_SWIFT_UNAVAILABLE(msg) __attribute__((availability(swift, unavailable, message = msg)))
#define NS_NOESCAPE __attribute__((noescape))
#define NS_REQUIRES_SUPER __attribute__((objc_requires_super))
#define NS_REQUIRES_NIL_TERMINATION __attribute__((sentinel(0, 1)))
#define NS_SWIFT_SENDABLE
#define NS_SWIFT_UI_ACTOR
#define NS_SWIFT_NONISOLATED
#define NS_EXTENSION_UNAVAILABLE(msg)
#define NS_EXTENSION_UNAVAILABLE_IOS(msg)
#define NS_UNAVAILABLE __attribute__((unavailable))
#define NS_DEPRECATED_IOS(...)
#define NS_FORMAT_FUNCTION(F, A) __attribute__((format(__NSString__, F, A)))
#define NS_FORMAT_ARGUMENT(A) __attribute__((format_arg(A)))
#define FOUNDATION_EXPORT extern
#define FOUNDATION_EXTERN extern
#define NS_INLINE static inline
#define NS_RETURNS_RETAINED __attribute__((ns_returns_retained))
#define NS_RETURNS_NOT_RETAINED __attribute__((ns_returns_not_retained))
#define NS_RETURNS_INNER_POINTER __attribute__((objc_returns_inner_pointer))
#define NS_VALID_UNTIL_END_OF_SCOPE __attribute__((objc_precise_lifetime))

@class NSString, NSData, NSArray<ObjectType>, NSDictionary<KeyType, ObjectType>, NSSet<ObjectType>, NSURL, NSError,
    NSNumber, NSBundle, NSCoder, NSDate, NSLocale, NSTimeZone, NSUUID, NSNotification, NSOperationQueue,
    NSURLSession, NSURLRequest, NSThread, NSRunLoop, NSIndexSet, NSIndexPath, NSCharacterSet, NSAttributedString,
    NSMutableString, NSMutableData, NSMutableArray<ObjectType>, NSMutableDictionary<KeyType, ObjectType>,
    NSMutableSet<ObjectType>, NSFileManager, NSLock, NSException, NSURLQueryItem;

/* Minimal containers for RCTLayoutContext fields. */
#ifndef ABS
#define ABS(a) ((a) < 0 ? -(a) : (a))
#endif
@interface NSHashTable<__covariant ObjectType> : NSObject
@property(readonly) NSUInteger count;
- (BOOL)containsObject:(nullable ObjectType)anObject;
- (void)addObject:(nullable ObjectType)anObject;
- (void)removeObject:(nullable ObjectType)anObject;
@end
@interface NSPointerArray : NSObject
@property(readonly) NSUInteger count;
- (void)addPointer:(nullable void *)pointer;
- (void)removePointer:(nullable void *)pointer;
- (nullable void *)pointerAtIndex:(NSUInteger)index;
@end

/* NSProxy surface for RCTBridgeProxy; the class comes from the device runtime. */
#define CF_RETURNS_NOT_RETAINED __attribute__((cf_returns_not_retained))
#define CF_RETURNS_RETAINED __attribute__((cf_returns_retained))
#define CF_IMPLICIT_BRIDGING_ENABLED _Pragma("clang arc_cf_code_audited begin")
#define CF_IMPLICIT_BRIDGING_DISABLED _Pragma("clang arc_cf_code_audited end")
/* NSAssertionHandler surface for NSAssert-style macros in pod sources. */
@interface NSAssertionHandler : NSObject
@property (class, nonatomic, readonly) NSAssertionHandler *currentHandler;
- (void)handleFailureInMethod:(SEL)selector object:(id)object file:(NSString *)fileName
                   lineNumber:(NSInteger)line description:(NSString *)format, ... NS_FORMAT_FUNCTION(5, 6);
- (void)handleFailureInFunction:(NSString *)functionName file:(NSString *)fileName
                     lineNumber:(NSInteger)line description:(NSString *)format, ... NS_FORMAT_FUNCTION(4, 5);
@end
@interface NSProxy <NSObject>
+ (id)alloc;
+ (id)allocWithZone:(struct _NSZone *)zone;
- (void)forwardInvocation:(NSInvocation *)anInvocation;
@end

/* RN 0.87 headers expect these from a full SDK; values from the public names. */
typedef NS_ENUM(NSUInteger, NSURLRequestCachePolicy) {
  NSURLRequestUseProtocolCachePolicy = 0, NSURLRequestReloadIgnoringLocalCacheData = 1,
  NSURLRequestReturnCacheDataElseLoad = 2, NSURLRequestReturnCacheDataDontLoad = 4
};
typedef NS_ENUM(NSInteger, NSTextAlignment) {
  NSTextAlignmentLeft = 0, NSTextAlignmentCenter = 1, NSTextAlignmentRight = 2,
  NSTextAlignmentJustified = 3, NSTextAlignmentNatural = 4
};
typedef NS_ENUM(NSInteger, NSLineBreakMode) {
  NSLineBreakByWordWrapping = 0, NSLineBreakByCharWrapping = 1, NSLineBreakByClipping = 2,
  NSLineBreakByTruncatingHead = 3, NSLineBreakByTruncatingTail = 4, NSLineBreakByTruncatingMiddle = 5
};
typedef NS_ENUM(NSInteger, NSUnderlineStyle) {
  NSUnderlineStyleNone = 0, NSUnderlineStyleSingle = 1, NSUnderlineStyleThick = 2, NSUnderlineStyleDouble = 9
};
typedef NS_ENUM(NSInteger, NSWritingDirection) {
  NSWritingDirectionNatural = -1, NSWritingDirectionLeftToRight = 0, NSWritingDirectionRightToLeft = 1
};
typedef NS_ENUM(NSInteger, NSLineBreakStrategy) {
  NSLineBreakStrategyNone = 0, NSLineBreakStrategyStandard = 1, NSLineBreakStrategyHangulWordWrap = 2,
  NSLineBreakStrategyPushOut = 3
};

typedef NSString *NSNotificationName __attribute__((swift_wrapper(struct)));
typedef NSString *NSErrorDomain __attribute__((swift_wrapper(struct)));
typedef NSString *NSRunLoopMode __attribute__((swift_wrapper(struct)));
typedef NSString *NSErrorUserInfoKey __attribute__((swift_wrapper(struct)));
typedef double NSTimeInterval;
typedef uint8_t UInt8; typedef int8_t SInt8; typedef uint16_t UInt16; typedef int16_t SInt16;
typedef uint32_t UInt32; typedef int32_t SInt32; typedef uint64_t UInt64; typedef int64_t SInt64;
typedef int32_t OSStatus; typedef unsigned char Boolean;
typedef struct _NSRange { NSUInteger location; NSUInteger length; } NSRange;
typedef NSRange *NSRangePointer;
typedef struct { NSInteger majorVersion; NSInteger minorVersion; NSInteger patchVersion; } NSOperatingSystemVersion;
typedef NS_ENUM(NSInteger, NSComparisonResult) { NSOrderedAscending = -1L, NSOrderedSame, NSOrderedDescending };
typedef NS_OPTIONS(NSUInteger, NSStringCompareOptions) {
  NSCaseInsensitiveSearch = 1, NSLiteralSearch = 2, NSBackwardsSearch = 4, NSAnchoredSearch = 8,
  NSNumericSearch = 64
};
typedef NS_ENUM(NSUInteger, NSStringEncoding) {
  NSASCIIStringEncoding = 1, NSUTF8StringEncoding = 4, NSUnicodeStringEncoding = 10, NSUTF16StringEncoding = 10,
  NSUTF32StringEncoding = 0x8c000100
};
typedef unsigned short unichar;
enum { NSNotFound = NSIntegerMax };
static inline NSRange NSMakeRange(NSUInteger loc, NSUInteger len) { NSRange r; r.location = loc; r.length = len; return r; }

#ifdef __cplusplus
extern "C" {
#endif
FOUNDATION_EXPORT NSString *NSStringFromClass(Class aClass);
FOUNDATION_EXPORT Class NSClassFromString(NSString *aClassName);
FOUNDATION_EXPORT NSString *NSStringFromSelector(SEL aSelector);
FOUNDATION_EXPORT SEL NSSelectorFromString(NSString *aSelectorName);
FOUNDATION_EXPORT void NSLog(NSString *format, ...) NS_FORMAT_FUNCTION(1, 2);
FOUNDATION_EXPORT void NSLogv(NSString *format, va_list args);
#ifdef __cplusplus
}
#endif
#define NSAssert(condition, desc, ...) assert(condition)
#define NSCAssert(condition, desc, ...) assert(condition)
#define NSParameterAssert(condition) assert(condition)
#define NSCParameterAssert(condition) assert(condition)

typedef struct NSFastEnumerationState {
  unsigned long state;
  id __unsafe_unretained _Nullable *_Nullable itemsPtr;
  unsigned long *_Nullable mutationsPtr;
  unsigned long extra[5];
} NSFastEnumerationState;
@protocol NSCopying
- (id)copyWithZone:(nullable struct _NSZone *)zone;
@end
@protocol NSMutableCopying
- (id)mutableCopyWithZone:(nullable struct _NSZone *)zone;
@end
@protocol NSCoding
- (void)encodeWithCoder:(NSCoder *)coder;
- (nullable instancetype)initWithCoder:(NSCoder *)coder;
@end
@protocol NSSecureCoding <NSCoding>
@property(class, readonly) BOOL supportsSecureCoding;
@end
@protocol NSFastEnumeration
- (NSUInteger)countByEnumeratingWithState:(NSFastEnumerationState *)state objects:(id __unsafe_unretained _Nullable[_Nullable])buffer count:(NSUInteger)len;
@end


NS_ASSUME_NONNULL_BEGIN

@interface NSObject (NSObjectFoundationAdditions)
- (NSString *)description;
- (void)performSelectorOnMainThread:(SEL)aSelector withObject:(nullable id)arg waitUntilDone:(BOOL)wait;
- (void)setValue:(nullable id)value forKey:(NSString *)key;
- (nullable id)valueForKey:(NSString *)key;
- (Class)classForCoder;
- (id)copy;
- (id)mutableCopy;
@end

@interface NSString : NSObject <NSCopying, NSMutableCopying, NSSecureCoding>
@property(readonly) NSUInteger length;
@property(readonly, copy) NSString *description;
@property(readonly) NSUInteger hash;
- (unichar)characterAtIndex:(NSUInteger)index;
- (NSString *)substringFromIndex:(NSUInteger)from;
- (NSString *)substringToIndex:(NSUInteger)to;
- (NSString *)substringWithRange:(NSRange)range;
- (BOOL)isEqualToString:(NSString *)aString;
- (BOOL)hasPrefix:(NSString *)str;
- (BOOL)hasSuffix:(NSString *)str;
- (NSRange)rangeOfString:(NSString *)searchString;
- (NSComparisonResult)compare:(NSString *)string;
- (NSString *)stringByAppendingString:(NSString *)aString;
- (NSString *)stringByAppendingFormat:(NSString *)format, ... NS_FORMAT_FUNCTION(1, 2);
- (NSString *)lowercaseString;
- (NSString *)uppercaseString;
- (nullable const char *)UTF8String NS_RETURNS_INNER_POINTER;
- (nullable NSData *)dataUsingEncoding:(NSStringEncoding)encoding;
- (NSArray<NSString *> *)componentsSeparatedByString:(NSString *)separator;
- (NSString *)stringByReplacingOccurrencesOfString:(NSString *)target withString:(NSString *)replacement;
@property(readonly) const char *fileSystemRepresentation NS_RETURNS_INNER_POINTER;
- (NSString *)stringByTrimmingCharactersInSet:(NSCharacterSet *)set;
@property(readonly) NSInteger integerValue;
@property(readonly) double doubleValue;
@property(readonly) BOOL boolValue;
+ (instancetype)string;
+ (instancetype)stringWithString:(NSString *)string;
+ (instancetype)stringWithUTF8String:(const char *)nullTerminatedCString;
+ (instancetype)stringWithFormat:(NSString *)format, ... NS_FORMAT_FUNCTION(1, 2);
+ (nullable instancetype)stringWithContentsOfFile:(NSString *)path encoding:(NSStringEncoding)enc error:(NSError **)error;
- (instancetype)init;
- (nullable instancetype)initWithData:(NSData *)data encoding:(NSStringEncoding)encoding;
- (instancetype)initWithUTF8String:(const char *)nullTerminatedCString;
- (instancetype)initWithFormat:(NSString *)format, ... NS_FORMAT_FUNCTION(1, 2);
@end

@interface NSMutableString : NSString
+ (instancetype)stringWithCapacity:(NSUInteger)capacity;
- (instancetype)initWithCapacity:(NSUInteger)capacity;
- (void)appendString:(NSString *)aString;
- (void)appendFormat:(NSString *)format, ... NS_FORMAT_FUNCTION(1, 2);
@end

@interface NSValue : NSObject <NSCopying, NSSecureCoding>
@property(readonly) const char *objCType NS_RETURNS_INNER_POINTER;
@property(readonly) void *pointerValue;
@property(nonatomic, readonly, nullable) id nonretainedObjectValue;
+ (NSValue *)valueWithPointer:(nullable const void *)pointer;
+ (NSValue *)valueWithNonretainedObject:(nullable id)anObject;
@end

@interface NSNumber : NSValue
@property(readonly) char charValue;
@property(readonly) unsigned char unsignedCharValue;
@property(readonly) short shortValue;
@property(readonly) unsigned short unsignedShortValue;
@property(readonly) int intValue;
@property(readonly) unsigned int unsignedIntValue;
@property(readonly) long longValue;
@property(readonly) unsigned long unsignedLongValue;
@property(readonly) long long longLongValue;
@property(readonly) unsigned long long unsignedLongLongValue;
@property(readonly) float floatValue;
@property(readonly) double doubleValue;
@property(readonly) BOOL boolValue;
@property(readonly) NSInteger integerValue;
@property(readonly) NSUInteger unsignedIntegerValue;
@property(readonly, copy) NSString *stringValue;
- (BOOL)isEqualToNumber:(NSNumber *)number;
+ (NSNumber *)numberWithChar:(char)value;
+ (NSNumber *)numberWithUnsignedChar:(unsigned char)value;
+ (NSNumber *)numberWithShort:(short)value;
+ (NSNumber *)numberWithUnsignedShort:(unsigned short)value;
+ (NSNumber *)numberWithInt:(int)value;
+ (NSNumber *)numberWithUnsignedInt:(unsigned int)value;
+ (NSNumber *)numberWithLong:(long)value;
+ (NSNumber *)numberWithUnsignedLong:(unsigned long)value;
+ (NSNumber *)numberWithLongLong:(long long)value;
+ (NSNumber *)numberWithUnsignedLongLong:(unsigned long long)value;
+ (NSNumber *)numberWithFloat:(float)value;
+ (NSNumber *)numberWithDouble:(double)value;
+ (NSNumber *)numberWithBool:(BOOL)value;
+ (NSNumber *)numberWithInteger:(NSInteger)value;
+ (NSNumber *)numberWithUnsignedInteger:(NSUInteger)value;
@end

@interface NSEnumerator<ObjectType> : NSObject <NSFastEnumeration>
- (nullable ObjectType)nextObject;
@property(readonly, copy) NSArray<ObjectType> *allObjects;
@end

@interface NSData : NSObject <NSCopying, NSMutableCopying, NSSecureCoding>
- (instancetype)initWithBytes:(nullable const void *)bytes length:(NSUInteger)length;
@property(readonly) NSUInteger length;
@property(readonly) const void *bytes NS_RETURNS_INNER_POINTER;
+ (instancetype)data;
+ (instancetype)dataWithBytes:(nullable const void *)bytes length:(NSUInteger)length;
+ (instancetype)dataWithBytesNoCopy:(void *)bytes length:(NSUInteger)length freeWhenDone:(BOOL)b;
+ (nullable instancetype)dataWithContentsOfFile:(NSString *)path;
- (void)getBytes:(void *)buffer length:(NSUInteger)length;
- (void)getBytes:(void *)buffer range:(NSRange)range;
- (NSData *)subdataWithRange:(NSRange)range;
- (BOOL)isEqualToData:(NSData *)other;
- (BOOL)writeToFile:(NSString *)path atomically:(BOOL)useAuxiliaryFile;
@end

@interface NSMutableData : NSData
@property(readonly) void *mutableBytes NS_RETURNS_INNER_POINTER;
@property NSUInteger length;
+ (nullable instancetype)dataWithCapacity:(NSUInteger)aNumItems;
+ (nullable instancetype)dataWithLength:(NSUInteger)length;
- (void)appendBytes:(const void *)bytes length:(NSUInteger)length;
- (void)appendData:(NSData *)other;
- (void)replaceBytesInRange:(NSRange)range withBytes:(const void *)bytes length:(NSUInteger)replacementLength;
- (void)setLength:(NSUInteger)length;
@end

@interface NSArray<__covariant ObjectType> : NSObject <NSCopying, NSMutableCopying, NSSecureCoding, NSFastEnumeration>
@property(readonly) NSUInteger count;
@property(readonly, nullable) ObjectType firstObject;
@property(readonly, nullable) ObjectType lastObject;
- (ObjectType)objectAtIndex:(NSUInteger)index;
- (ObjectType)objectAtIndexedSubscript:(NSUInteger)idx;
- (BOOL)containsObject:(ObjectType)anObject;
- (NSUInteger)indexOfObject:(ObjectType)anObject;
- (NSArray<ObjectType> *)arrayByAddingObject:(ObjectType)anObject;
- (NSString *)componentsJoinedByString:(NSString *)separator;
- (void)enumerateObjectsUsingBlock:(void (^NS_NOESCAPE)(ObjectType obj, NSUInteger idx, BOOL *stop))block;
+ (instancetype)array;
+ (instancetype)arrayWithObject:(ObjectType)anObject;
+ (instancetype)arrayWithObjects:(const ObjectType _Nonnull[_Nonnull])objects count:(NSUInteger)cnt;
+ (instancetype)arrayWithArray:(NSArray<ObjectType> *)array;
- (instancetype)initWithArray:(NSArray<ObjectType> *)array;
@end

@interface NSMutableArray<ObjectType> : NSArray<ObjectType>
- (void)addObject:(ObjectType)anObject;
- (void)insertObject:(ObjectType)anObject atIndex:(NSUInteger)index;
- (void)removeObjectAtIndex:(NSUInteger)index;
- (void)removeObject:(ObjectType)anObject;
- (void)removeAllObjects;
- (void)addObjectsFromArray:(NSArray<ObjectType> *)otherArray;
+ (instancetype)arrayWithCapacity:(NSUInteger)numItems;
@end

@interface NSDictionary<__covariant KeyType, __covariant ObjectType> : NSObject <NSCopying, NSMutableCopying, NSSecureCoding, NSFastEnumeration>
@property(readonly) NSUInteger count;
@property(readonly, copy) NSArray<KeyType> *allKeys;
@property(readonly, copy) NSArray<ObjectType> *allValues;
- (nullable ObjectType)objectForKey:(KeyType)aKey;
- (nullable ObjectType)objectForKeyedSubscript:(KeyType)key;
- (NSEnumerator<KeyType> *)keyEnumerator;
- (NSEnumerator<ObjectType> *)objectEnumerator;
- (void)enumerateKeysAndObjectsUsingBlock:(void (^NS_NOESCAPE)(KeyType key, ObjectType obj, BOOL *stop))block;
+ (instancetype)dictionary;
+ (instancetype)dictionaryWithObject:(ObjectType)object forKey:(KeyType<NSCopying>)key;
+ (instancetype)dictionaryWithObjects:(const ObjectType _Nonnull[_Nonnull])objects forKeys:(const KeyType<NSCopying> _Nonnull[_Nonnull])keys count:(NSUInteger)cnt;
+ (instancetype)dictionaryWithDictionary:(NSDictionary<KeyType, ObjectType> *)dict;
- (instancetype)initWithDictionary:(NSDictionary<KeyType, ObjectType> *)otherDictionary;
@end

@interface NSMutableDictionary<KeyType, ObjectType> : NSDictionary<KeyType, ObjectType>
- (void)setObject:(ObjectType)anObject forKey:(KeyType<NSCopying>)aKey;
- (void)setObject:(nullable ObjectType)obj forKeyedSubscript:(KeyType<NSCopying>)key;
- (void)removeObjectForKey:(KeyType)aKey;
- (void)removeAllObjects;
- (void)addEntriesFromDictionary:(NSDictionary<KeyType, ObjectType> *)otherDictionary;
+ (instancetype)dictionaryWithCapacity:(NSUInteger)numItems;
- (instancetype)initWithCapacity:(NSUInteger)numItems;
@end

@interface NSSet<__covariant ObjectType> : NSObject <NSCopying, NSMutableCopying, NSSecureCoding, NSFastEnumeration>
@property(readonly) NSUInteger count;
@property(readonly, copy) NSArray<ObjectType> *allObjects;
- (nullable ObjectType)anyObject;
- (BOOL)containsObject:(ObjectType)anObject;
+ (instancetype)set;
+ (instancetype)setWithObject:(ObjectType)object;
+ (instancetype)setWithArray:(NSArray<ObjectType> *)array;
- (NSSet<ObjectType> *)objectsPassingTest:(BOOL (^NS_NOESCAPE)(ObjectType obj, BOOL *stop))predicate;
@end

@interface NSMutableSet<ObjectType> : NSSet<ObjectType>
- (void)addObject:(ObjectType)object;
- (void)removeObject:(ObjectType)object;
- (void)removeAllObjects;
- (NSSet<ObjectType> *)objectsPassingTest:(BOOL (^NS_NOESCAPE)(ObjectType obj, BOOL *stop))predicate;
@end

@interface NSURL : NSObject <NSSecureCoding, NSCopying>
@property(readonly, copy, nullable) NSString *scheme;
@property(readonly, copy, nullable) NSString *host;
@property(readonly, copy, nullable) NSString *path;
@property(readonly, copy, nullable) NSString *query;
@property(readonly, copy, nullable) NSString *fragment;
@property(readonly, copy) NSString *absoluteString;
@property(readonly, getter=isFileURL) BOOL fileURL;
+ (nullable instancetype)URLWithString:(NSString *)URLString;
+ (instancetype)fileURLWithPath:(NSString *)path;
- (nullable instancetype)initWithString:(NSString *)URLString;
- (NSURL *)URLByAppendingPathComponent:(NSString *)pathComponent;
@end

@interface NSBundle : NSObject
@property(class, readonly, strong) NSBundle *mainBundle;
@property(readonly, copy) NSString *bundlePath;
@property(readonly, copy, nullable) NSString *bundleIdentifier;
@property(readonly, copy, nullable) NSDictionary<NSString *, id> *infoDictionary;
+ (nullable NSBundle *)bundleWithPath:(NSString *)path;
+ (nullable NSBundle *)bundleForClass:(Class)aClass;
+ (nullable NSBundle *)bundleWithIdentifier:(NSString *)identifier;
- (nullable NSString *)pathForResource:(nullable NSString *)name ofType:(nullable NSString *)ext;
- (nullable NSURL *)URLForResource:(nullable NSString *)name withExtension:(nullable NSString *)ext;
- (nullable id)objectForInfoDictionaryKey:(NSString *)key;
@end

@interface NSError : NSObject <NSCopying, NSSecureCoding>
@property(readonly, copy) NSErrorDomain domain;
@property(readonly) NSInteger code;
@property(readonly, copy) NSDictionary<NSErrorUserInfoKey, id> *userInfo;
@property(readonly, copy) NSString *localizedDescription;
+ (instancetype)errorWithDomain:(NSErrorDomain)domain code:(NSInteger)code userInfo:(nullable NSDictionary<NSErrorUserInfoKey, id> *)dict;
@end

@interface NSUserActivity : NSObject
@property(copy, nullable) NSString *title;
@property(copy, readonly) NSString *activityType;
@property(copy, nullable) NSURL *webpageURL;
@property(copy, nullable) NSDictionary *userInfo;
- (instancetype)initWithActivityType:(NSString *)activityType;
@end

@interface NSCoder : NSObject
@end

@interface NSNotification : NSObject
@property(readonly, copy) NSNotificationName name;
@property(readonly, strong, nullable) id object;
@property(readonly, copy, nullable) NSDictionary *userInfo;
@end

@interface NSNotificationCenter : NSObject
@property(class, readonly, strong) NSNotificationCenter *defaultCenter;
- (void)addObserver:(id)observer selector:(SEL)aSelector name:(nullable NSNotificationName)aName object:(nullable id)anObject;
- (void)removeObserver:(id)observer;
- (void)removeObserver:(id)observer name:(nullable NSNotificationName)aName object:(nullable id)anObject;
- (void)postNotificationName:(NSNotificationName)aName object:(nullable id)anObject;
- (void)postNotificationName:(NSNotificationName)aName object:(nullable id)anObject userInfo:(nullable NSDictionary *)aUserInfo;
- (void)addObserverForName:(nullable NSNotificationName)name object:(nullable id)obj queue:(nullable NSOperationQueue *)queue usingBlock:(void (^)(NSNotification *note))block API_AVAILABLE(macos(10.6), ios(4.0));
@end

@interface NSUUID : NSObject
+ (instancetype)UUID;
@property(readonly, copy) NSString *UUIDString;
@end

@interface NSDate : NSObject
+ (instancetype)date;
+ (NSTimeInterval)timeIntervalSinceReferenceDate;
+ (instancetype)dateWithTimeIntervalSince1970:(NSTimeInterval)secs;
- (instancetype)initWithTimeIntervalSince1970:(NSTimeInterval)secs;
@property(readonly) NSTimeInterval timeIntervalSince1970;
@property(readonly) NSTimeInterval timeIntervalSinceReferenceDate;
@end

@interface NSProcessInfo : NSObject
@property(class, readonly, strong) NSProcessInfo *processInfo;
@property(readonly, copy) NSDictionary<NSString *, NSString *> *environment;
@property(readonly, copy) NSArray<NSString *> *arguments;
@property(readonly) NSOperatingSystemVersion operatingSystemVersion;
@end

@interface NSUserDefaults : NSObject
@property(class, readonly, strong) NSUserDefaults *standardUserDefaults;
- (nullable id)objectForKey:(NSString *)defaultName;
- (void)setObject:(nullable id)value forKey:(NSString *)defaultName;
- (BOOL)boolForKey:(NSString *)defaultName;
- (void)setBool:(BOOL)value forKey:(NSString *)defaultName;
@end

@interface NSNull : NSObject <NSCopying, NSSecureCoding>
+ (NSNull *)null;
@end

typedef NS_ENUM(NSUInteger, NSSearchPathDirectory) { NSDocumentDirectory = 9, NSCachesDirectory = 13, NSApplicationSupportDirectory = 14, NSLibraryDirectory = 5 };
typedef NS_OPTIONS(NSUInteger, NSSearchPathDomainMask) { NSUserDomainMask = 1, NSLocalDomainMask = 2, NSAllDomainsMask = 0x0ffff };
typedef NSString *NSFileAttributeKey __attribute__((swift_wrapper(struct)));
typedef NSString *NSFileProtectionType __attribute__((swift_wrapper(struct)));
FOUNDATION_EXPORT NSFileAttributeKey const NSFileProtectionKey;
FOUNDATION_EXPORT NSErrorDomain const NSCocoaErrorDomain;
FOUNDATION_EXPORT NSFileProtectionType const NSFileProtectionNone;
FOUNDATION_EXPORT NSErrorUserInfoKey const NSLocalizedDescriptionKey;
FOUNDATION_EXPORT NSErrorUserInfoKey const NSUnderlyingErrorKey;
FOUNDATION_EXPORT NSErrorUserInfoKey const NSLocalizedFailureReasonErrorKey;
FOUNDATION_EXPORT NSArray<NSString *> *NSSearchPathForDirectoriesInDomains(NSSearchPathDirectory directory, NSSearchPathDomainMask domainMask, BOOL expandTilde);
FOUNDATION_EXPORT NSString *NSTemporaryDirectory(void);

@interface NSFileManager : NSObject
@property(class, readonly, strong) NSFileManager *defaultManager;
- (BOOL)fileExistsAtPath:(NSString *)path;
- (BOOL)fileExistsAtPath:(NSString *)path isDirectory:(nullable BOOL *)isDirectory;
- (BOOL)createDirectoryAtPath:(NSString *)path withIntermediateDirectories:(BOOL)createIntermediates attributes:(nullable NSDictionary<NSFileAttributeKey, id> *)attributes error:(NSError **)error;
- (BOOL)removeItemAtPath:(NSString *)path error:(NSError **)error;
- (BOOL)copyItemAtPath:(NSString *)srcPath toPath:(NSString *)dstPath error:(NSError **)error;
- (nullable NSArray<NSString *> *)contentsOfDirectoryAtPath:(NSString *)path error:(NSError **)error;
@end

@interface NSString (NSStringPathExtensions)
@property(readonly, copy) NSString *lastPathComponent;
@property(readonly, copy) NSString *pathExtension;
@property(readonly, copy) NSString *stringByDeletingLastPathComponent;
@property(readonly, copy) NSString *stringByDeletingPathExtension;
- (NSString *)stringByAppendingPathComponent:(NSString *)str;
@end

@interface NSLocale : NSObject <NSCopying, NSSecureCoding>
+ (NSLocale *)localeWithLocaleIdentifier:(NSString *)string;
- (instancetype)initWithLocaleIdentifier:(NSString *)string;
@property(class, readonly, copy) NSLocale *currentLocale;
@end
@interface NSTimeZone : NSObject <NSCopying, NSSecureCoding>
+ (nullable NSTimeZone *)timeZoneForSecondsFromGMT:(NSInteger)seconds;
+ (nullable NSTimeZone *)timeZoneWithName:(NSString *)tzName;
@property(class, readonly, copy) NSTimeZone *localTimeZone;
@end
@interface NSCharacterSet : NSObject <NSCopying, NSSecureCoding>
@property(class, readonly, strong) NSCharacterSet *whitespaceCharacterSet;
@property(class, readonly, strong) NSCharacterSet *whitespaceAndNewlineCharacterSet;
@end
@interface NSDateFormatter : NSObject
@property(nullable, copy) NSString *dateFormat;
@property(nullable, copy) NSLocale *locale;
@property(nullable, copy) NSTimeZone *timeZone;
- (NSString *)stringFromDate:(NSDate *)date;
- (nullable NSDate *)dateFromString:(NSString *)string;
@end

typedef NS_OPTIONS(NSUInteger, NSKeyValueObservingOptions) { NSKeyValueObservingOptionNew = 1, NSKeyValueObservingOptionOld = 2, NSKeyValueObservingOptionInitial = 4, NSKeyValueObservingOptionPrior = 8 };
typedef NSString *NSKeyValueChangeKey __attribute__((swift_wrapper(struct)));
typedef NS_ENUM(NSUInteger, NSStreamStatus) {
  NSStreamStatusNotOpen = 0, NSStreamStatusOpening = 1, NSStreamStatusOpen = 2, NSStreamStatusReading = 3,
  NSStreamStatusWriting = 4, NSStreamStatusAtEnd = 5, NSStreamStatusClosed = 6, NSStreamStatusError = 7
};
typedef NS_OPTIONS(NSUInteger, NSStreamEvent) {
  NSStreamEventNone = 0, NSStreamEventOpenCompleted = 1 << 0, NSStreamEventHasBytesAvailable = 1 << 1,
  NSStreamEventHasSpaceAvailable = 1 << 2, NSStreamEventErrorOccurred = 1 << 3, NSStreamEventEndEncountered = 1 << 4
};
typedef NSString *NSStreamPropertyKey __attribute__((swift_wrapper(struct)));
@class NSStream;
@protocol NSStreamDelegate <NSObject>
@optional
- (void)stream:(NSStream *)aStream handleEvent:(NSStreamEvent)eventCode;
@end
@interface NSStream : NSObject
@property(nullable, assign) id<NSStreamDelegate> delegate;
@property(readonly) NSStreamStatus streamStatus;
@property(nullable, readonly, copy) NSError *streamError;
- (void)open;
- (void)close;
- (void)scheduleInRunLoop:(NSRunLoop *)aRunLoop forMode:(NSRunLoopMode)mode;
- (void)removeFromRunLoop:(NSRunLoop *)aRunLoop forMode:(NSRunLoopMode)mode;
- (nullable id)propertyForKey:(NSStreamPropertyKey)key;
@end
@interface NSInputStream : NSStream
- (NSInteger)read:(uint8_t *)buffer maxLength:(NSUInteger)len;
@property(readonly) BOOL hasBytesAvailable;
- (instancetype)initWithData:(NSData *)data;
@end
@interface NSRunLoop : NSObject
@property(class, readonly, strong) NSRunLoop *currentRunLoop;
@property(class, readonly, strong) NSRunLoop *mainRunLoop;
- (void)run;
@end
@interface NSCondition : NSObject
- (void)lock;
- (void)unlock;
- (void)wait;
- (void)signal;
- (void)broadcast;
@end
@interface NSMethodSignature : NSObject
+ (nullable NSMethodSignature *)signatureWithObjCTypes:(const char *)types;
@property(readonly) NSUInteger numberOfArguments;
@property(readonly) const char *methodReturnType NS_RETURNS_INNER_POINTER;
- (const char *)getArgumentTypeAtIndex:(NSUInteger)idx NS_RETURNS_INNER_POINTER;
@end
typedef NS_ENUM(NSInteger, NSItemProviderRepresentationVisibility) {
  NSItemProviderRepresentationVisibilityAll = 0, NSItemProviderRepresentationVisibilityTeam = 1,
  NSItemProviderRepresentationVisibilityGroup = 2, NSItemProviderRepresentationVisibilityOwnProcess = 3
};
@interface NSObject (NSKeyValueObserving)
- (void)observeValueForKeyPath:(nullable NSString *)keyPath ofObject:(nullable id)object change:(nullable NSDictionary<NSKeyValueChangeKey, id> *)change context:(nullable void *)context;
- (void)addObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath options:(NSKeyValueObservingOptions)options context:(nullable void *)context;
- (void)removeObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath;
@end
@protocol NSItemProviderReading <NSObject>
@end
@protocol NSItemProviderWriting <NSObject>
@end
@protocol NSPortDelegate <NSObject>
@end
@interface NSObject (NSKeyValueObservingContext)
- (void)removeObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath context:(nullable void *)context;
@end
@interface NSThread : NSObject
@property(class, readonly) BOOL isMainThread;
@end

NS_ASSUME_NONNULL_END

#include <dispatch/dispatch.h>
