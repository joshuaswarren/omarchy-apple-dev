#pragma once
// Omarchy SDK-free UIKit subset, written from public behaviour and names; grows as builds fail.
#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

#define UIKIT_EXTERN extern
#define UIKIT_STATIC_INLINE static inline
#define UI_APPEARANCE_SELECTOR
#define IBOutlet
#define IBAction void
#define IBInspectable
#define IB_DESIGNABLE

typedef NSString *UIApplicationLaunchOptionsKey __attribute__((swift_wrapper(struct)));
typedef NSString *UIApplicationOpenURLOptionsKey __attribute__((swift_wrapper(struct)));
typedef NSString *UIApplicationOpenExternalURLOptionsKey __attribute__((swift_wrapper(struct)));
typedef NSUInteger UIBackgroundTaskIdentifier;
typedef NS_ENUM(NSInteger, UIApplicationState) { UIApplicationStateActive, UIApplicationStateInactive, UIApplicationStateBackground };
typedef NS_ENUM(NSUInteger, UIBackgroundFetchResult) {
  UIBackgroundFetchResultNewData, UIBackgroundFetchResultNoData, UIBackgroundFetchResultFailed
};
typedef NS_OPTIONS(NSUInteger, UIInterfaceOrientationMask) {
  UIInterfaceOrientationMaskPortrait = (1 << 1), UIInterfaceOrientationMaskLandscapeLeft = (1 << 3),
  UIInterfaceOrientationMaskLandscapeRight = (1 << 2), UIInterfaceOrientationMaskPortraitUpsideDown = (1 << 4),
  UIInterfaceOrientationMaskLandscape = (UIInterfaceOrientationMaskLandscapeLeft | UIInterfaceOrientationMaskLandscapeRight),
  UIInterfaceOrientationMaskAll = 30, UIInterfaceOrientationMaskAllButUpsideDown = 26
};
typedef NS_ENUM(NSInteger, UIStatusBarStyle) { UIStatusBarStyleDefault, UIStatusBarStyleLightContent, UIStatusBarStyleDarkContent = 3 };
typedef NS_ENUM(NSInteger, UIUserInterfaceStyle) { UIUserInterfaceStyleUnspecified, UIUserInterfaceStyleLight, UIUserInterfaceStyleDark };
typedef NS_ENUM(NSInteger, UIGestureRecognizerState) {
  UIGestureRecognizerStatePossible, UIGestureRecognizerStateBegan, UIGestureRecognizerStateChanged,
  UIGestureRecognizerStateEnded, UIGestureRecognizerStateCancelled, UIGestureRecognizerStateFailed
};

/* RN 0.87 headers expect these from a full SDK; values from the public names. */
@class UIStatusBarManager;
typedef NS_ENUM(NSInteger, UITextAutocapitalizationType) {
  UITextAutocapitalizationTypeNone = 0, UITextAutocapitalizationTypeWords = 1,
  UITextAutocapitalizationTypeSentences = 2, UITextAutocapitalizationTypeAllCharacters = 3
};
typedef NS_ENUM(NSInteger, UITextFieldViewMode) {
  UITextFieldViewModeNever = 0, UITextFieldViewModeWhileEditing = 1,
  UITextFieldViewModeUnlessEditing = 2, UITextFieldViewModeAlways = 3
};
typedef NS_ENUM(NSInteger, UIKeyboardType) {
  UIKeyboardTypeDefault = 0, UIKeyboardTypeASCIICapable = 1, UIKeyboardTypeNumbersAndPunctuation = 2,
  UIKeyboardTypeURL = 3, UIKeyboardTypeNumberPad = 4, UIKeyboardTypePhonePad = 5,
  UIKeyboardTypeNamePhonePad = 6, UIKeyboardTypeEmailAddress = 7, UIKeyboardTypeDecimalPad = 8,
  UIKeyboardTypeTwitter = 9, UIKeyboardTypeWebSearch = 10
};
typedef NS_ENUM(NSInteger, UIKeyboardAppearance) {
  UIKeyboardAppearanceDefault = 0, UIKeyboardAppearanceDark = 1, UIKeyboardAppearanceLight = 2
};
typedef NS_ENUM(NSInteger, UIReturnKeyType) {
  UIReturnKeyTypeDefault = 0, UIReturnKeyTypeGo = 1, UIReturnKeyTypeGoogle = 2, UIReturnKeyTypeJoin = 3,
  UIReturnKeyTypeNext = 4, UIReturnKeyTypeRoute = 5, UIReturnKeyTypeSearch = 6, UIReturnKeyTypeSend = 7,
  UIReturnKeyTypeYahoo = 8, UIReturnKeyTypeDone = 9, UIReturnKeyTypeEmergencyCall = 10
};
typedef NS_ENUM(NSInteger, UIModalPresentationStyle) {
  UIModalPresentationFullScreen = 0, UIModalPresentationPageSheet = 1, UIModalPresentationFormSheet = 2,
  UIModalPresentationCurrentContext = 3, UIModalPresentationCustom = 4, UIModalPresentationOverFullScreen = 5,
  UIModalPresentationOverCurrentContext = 6, UIModalPresentationPopover = 7, UIModalPresentationBlurOverFullScreen = 8,
  UIModalPresentationNone = -1
};
typedef NS_OPTIONS(NSUInteger, UIDataDetectorTypes) {
  UIDataDetectorTypePhoneNumber = 1 << 0, UIDataDetectorTypeLink = 1 << 1, UIDataDetectorTypeAddress = 1 << 2,
  UIDataDetectorTypeCalendarEvent = 1 << 3, UIDataDetectorTypeAll = NSUIntegerMax
};
typedef NS_ENUM(NSInteger, UIViewContentMode) {
  UIViewContentModeScaleToFill = 0, UIViewContentModeScaleAspectFit = 1, UIViewContentModeScaleAspectFill = 2,
  UIViewContentModeRedraw = 3, UIViewContentModeCenter = 4, UIViewContentModeTop = 5, UIViewContentModeBottom = 6,
  UIViewContentModeLeft = 7, UIViewContentModeRight = 8, UIViewContentModeTopLeft = 9,
  UIViewContentModeTopRight = 10, UIViewContentModeBottomLeft = 11, UIViewContentModeBottomRight = 12
};
typedef struct UIEdgeInsets { CGFloat top, left, bottom, right; } UIEdgeInsets;
typedef NS_ENUM(NSInteger, CGLineCap) { kCGLineCapButt = 0, kCGLineCapRound = 1, kCGLineCapSquare = 2 };
typedef NS_ENUM(NSInteger, CGLineJoin) { kCGLineJoinMiter = 0, kCGLineJoinRound = 1, kCGLineJoinBevel = 2 };
typedef NS_OPTIONS(NSUInteger, UIAccessibilityTraits) {
  UIAccessibilityTraitNone = 0, UIAccessibilityTraitButton = 1, UIAccessibilityTraitLink = 2,
  UIAccessibilityTraitImage = 4, UIAccessibilityTraitSelected = 8, UIAccessibilityTraitPlaysSound = 16,
  UIAccessibilityTraitKeyboardKey = 32, UIAccessibilityTraitStaticText = 64, UIAccessibilityTraitSummaryElement = 128,
  UIAccessibilityTraitNotEnabled = 256, UIAccessibilityTraitUpdatesFrequently = 512, UIAccessibilityTraitSearchField = 1024,
  UIAccessibilityTraitStartsMediaSession = 2048, UIAccessibilityTraitAdjustable = 4096,
  UIAccessibilityTraitAllowsDirectInteraction = 8192, UIAccessibilityTraitCausesPageTurn = 16384,
  UIAccessibilityTraitHeader = 65536, UIAccessibilityTraitTabBar = 0x0000000200000000ULL
};
typedef NS_ENUM(NSInteger, UIUserInterfaceLayoutDirection) {
  UIUserInterfaceLayoutDirectionLeftToRight, UIUserInterfaceLayoutDirectionRightToLeft
};
UIKIT_EXTERN NSString *const UIKeyboardWillShowNotification;
UIKIT_EXTERN NSString *const UIKeyboardDidShowNotification;
UIKIT_EXTERN NSString *const UIKeyboardWillHideNotification;
UIKIT_EXTERN NSString *const UIKeyboardDidHideNotification;
UIKIT_EXTERN NSString *const UIKeyboardDidChangeFrameNotification;
UIKIT_EXTERN NSString *const UIWindowDidBecomeVisibleNotification;
UIKIT_EXTERN NSString *const UIWindowDidBecomeHiddenNotification;
UIKIT_EXTERN NSString *const UIWindowDidBecomeKeyNotification;
UIKIT_EXTERN NSString *const UIWindowDidResignKeyNotification;
@class UIScrollView;
#ifndef CG_BOXABLE
#define CG_BOXABLE __attribute__((objc_boxable))
#endif
static inline BOOL UIEdgeInsetsEqualToEdgeInsets(UIEdgeInsets a, UIEdgeInsets b) { return a.top == b.top && a.left == b.left && a.bottom == b.bottom && a.right == b.right; }
static inline CGRect UIEdgeInsetsInsetRect(CGRect rect, UIEdgeInsets insets) { rect.origin.x += insets.left; rect.origin.y += insets.top; rect.size.width -= insets.left + insets.right; rect.size.height -= insets.top + insets.bottom; return rect; }
UIKIT_EXTERN const UIEdgeInsets UIEdgeInsetsZero;
UIKIT_EXTERN NSString *NSStringFromUIEdgeInsets(UIEdgeInsets insets);
UIKIT_EXTERN NSString *NSStringFromCGPoint(CGPoint point);
UIKIT_EXTERN NSString *NSStringFromCGSize(CGSize size);
UIKIT_EXTERN NSString *NSStringFromCGRect(CGRect rect);
static inline BOOL CGSizeEqualToSize(CGSize a, CGSize b) { return a.width == b.width && a.height == b.height; }
static inline BOOL CGPointEqualToPoint(CGPoint a, CGPoint b) { return a.x == b.x && a.y == b.y; }
static inline BOOL CGRectIsNull(CGRect r) { return r.size.width <= 0 || r.size.height <= 0; }
static inline BOOL CGRectEqualToRect(CGRect a, CGRect b) { return CGPointEqualToPoint(a.origin, b.origin) && CGSizeEqualToSize(a.size, b.size); }
static inline CGRect CGRectInset(CGRect r, CGFloat dx, CGFloat dy) { r.origin.x += dx; r.origin.y += dy; r.size.width -= 2 * dx; r.size.height -= 2 * dy; return r; }
static inline CGRect CGRectOffset(CGRect r, CGFloat dx, CGFloat dy) { r.origin.x += dx; r.origin.y += dy; return r; }
static inline CGRect CGRectUnion(CGRect a, CGRect b) { CGFloat x = MIN(a.origin.x, b.origin.x), y = MIN(a.origin.y, b.origin.y); return CGRectMake(x, y, MAX(a.origin.x + a.size.width, b.origin.x + b.size.width) - x, MAX(a.origin.y + a.size.height, b.origin.y + b.size.height) - y); }
static inline CGRect CGRectIntersection(CGRect a, CGRect b) { CGFloat x = MAX(a.origin.x, b.origin.x), y = MAX(a.origin.y, b.origin.y); CGFloat w = MIN(a.origin.x + a.size.width, b.origin.x + b.size.width) - x, h = MIN(a.origin.y + a.size.height, b.origin.y + b.size.height) - y; return w > 0 && h > 0 ? CGRectMake(x, y, w, h) : CGRectMake(0, 0, 0, 0); }
static inline BOOL CGRectIntersectsRect(CGRect a, CGRect b) { return !CGRectIsNull(CGRectIntersection(a, b)); }

NS_ASSUME_NONNULL_BEGIN

@protocol UIUserActivityRestoring;
@class UISceneConfiguration, UIApplication;
@class UIView, UIViewController, UIWindow, UIScreen, UIEvent, UITouch, UIPress, UIColor, UIImage, UIGestureRecognizer,
    UIScene, UISceneSession, UISceneConnectionOptions, UIOpenURLContext, UIWindowScene, UIApplicationShortcutItem,
    UIUserNotificationSettings, UILocalNotification, UINavigationController, UITraitCollection, UIPresentationController,
    UIStoryboard, UIStoryboardSegue, UIBarButtonItem, UIPasteboard, UIAccessibilityElement, UIOpenURLContext;

@interface UIResponder : NSObject
@property(nonatomic, readonly, nullable) UIResponder *nextResponder;
@property(nonatomic, readonly) BOOL canBecomeFirstResponder;
- (BOOL)becomeFirstResponder;
- (BOOL)resignFirstResponder;
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(nullable UIEvent *)event;
- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(nullable UIEvent *)event;
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(nullable UIEvent *)event;
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(nullable UIEvent *)event;
- (void)pressesBegan:(NSSet<UIPress *> *)presses withEvent:(nullable UIEvent *)event;
- (void)pressesEnded:(NSSet<UIPress *> *)presses withEvent:(nullable UIEvent *)event;
- (void)pressesChanged:(NSSet<UIPress *> *)presses withEvent:(nullable UIEvent *)event;
- (void)pressesCancelled:(NSSet<UIPress *> *)presses withEvent:(nullable UIEvent *)event;
@end

@interface UIColor : NSObject <NSSecureCoding, NSCopying>
@property(class, nonatomic, readonly) UIColor *whiteColor;
@property(class, nonatomic, readonly) UIColor *blackColor;
@property(class, nonatomic, readonly) UIColor *clearColor;
@property(class, nonatomic, readonly) UIColor *systemBackgroundColor;
+ (UIColor *)colorWithRed:(CGFloat)red green:(CGFloat)green blue:(CGFloat)blue alpha:(CGFloat)alpha;
+ (UIColor *)colorWithWhite:(CGFloat)white alpha:(CGFloat)alpha;
@end

@interface UIImage : NSObject <NSSecureCoding>
@property(nonatomic, readonly) CGSize size;
+ (nullable UIImage *)imageNamed:(NSString *)name;
@end

@interface UIDevice : NSObject
@property(class, nonatomic, readonly) UIDevice *currentDevice;
@property(nonatomic, readonly, copy) NSString *systemVersion;
@property(nonatomic, readonly, copy) NSString *model;
@property(nonatomic, readonly, copy) NSString *name;
@end

@interface UIScreen : NSObject
@property(class, nonatomic, readonly) UIScreen *mainScreen;
@property(nonatomic, readonly) CGRect bounds;
@property(nonatomic, readonly) CGFloat scale;
@property(nonatomic, readonly) CGFloat nativeScale;
@end

@interface UITouch : NSObject
@property(nonatomic, readonly) NSTimeInterval timestamp;
@property(nonatomic, readonly, nullable) UIView *view;
- (CGPoint)locationInView:(nullable UIView *)view;
@end

@interface UIEvent : NSObject
@property(nonatomic, readonly) NSTimeInterval timestamp;
@end

@interface UIPress : NSObject
@end

@interface UITraitCollection : NSObject
@property(nonatomic, readonly) UIUserInterfaceStyle userInterfaceStyle;
@property(nonatomic, readonly) CGFloat displayScale;
@end

@interface UIGestureRecognizer : NSObject
@property(nonatomic, readonly) UIGestureRecognizerState state;
@property(nonatomic, getter=isEnabled) BOOL enabled;
@property(nonatomic, readonly, nullable) UIView *view;
@end
@protocol UIGestureRecognizerDelegate <NSObject>
@optional
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer shouldReceiveTouch:(UITouch *)touch;
- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer *)gestureRecognizer;
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)other;
@end

@interface UIView : UIResponder
@property(nonatomic) CGRect frame;
@property(nonatomic) CGRect bounds;
@property(nonatomic, readonly, nullable) UIView *superview;
@property(nonatomic, readonly, copy) NSArray<__kindof UIView *> *subviews;
@property(nonatomic, readonly, nullable) UIWindow *window;
@property(nonatomic, copy, nullable) UIColor *backgroundColor;
@property(nonatomic) CGFloat alpha;
@property(nonatomic, getter=isHidden) BOOL hidden;
@property(nonatomic, getter=isOpaque) BOOL opaque;
@property(nonatomic, getter=isUserInteractionEnabled) BOOL userInteractionEnabled;
@property(nonatomic, getter=isMultipleTouchEnabled) BOOL multipleTouchEnabled;
@property(nonatomic) NSInteger tag;
@property(nonatomic) BOOL clipsToBounds;
@property(nonatomic) BOOL translatesAutoresizingMaskIntoConstraints;
@property(nonatomic, copy, nullable) NSArray<UIGestureRecognizer *> *gestureRecognizers;
- (instancetype)initWithFrame:(CGRect)frame NS_DESIGNATED_INITIALIZER;
- (nullable instancetype)initWithCoder:(NSCoder *)coder NS_DESIGNATED_INITIALIZER;
- (void)addSubview:(UIView *)view;
- (void)removeFromSuperview;
- (void)insertSubview:(UIView *)view atIndex:(NSInteger)index;
- (void)setNeedsLayout;
- (void)layoutSubviews;
- (void)setNeedsDisplay;
- (void)addGestureRecognizer:(UIGestureRecognizer *)gestureRecognizer;
- (void)removeGestureRecognizer:(UIGestureRecognizer *)gestureRecognizer;
- (CGPoint)convertPoint:(CGPoint)point toView:(nullable UIView *)view;
- (CGPoint)convertPoint:(CGPoint)point fromView:(nullable UIView *)view;
- (CGRect)convertRect:(CGRect)rect toView:(nullable UIView *)view;
- (CGRect)convertRect:(CGRect)rect fromView:(nullable UIView *)view;
@property(nonatomic, readonly) UIEdgeInsets safeAreaInsets;
@property(nonatomic, readonly, nonnull) id safeAreaLayoutGuide;
- (void)layoutIfNeeded;
- (CGSize)sizeThatFits:(CGSize)size;
- (void)sizeToFit;
- (nullable UIView *)viewWithTag:(NSInteger)tag;
- (void)setNeedsUpdateConstraints;
- (void)updateConstraintsIfNeeded;
@end


@interface UIScrollView : UIView
@property(nonatomic) CGPoint contentOffset;
@property(nonatomic) UIEdgeInsets contentInset;
@property(nonatomic) CGSize contentSize;
@property(nonatomic, getter=isScrollEnabled) BOOL scrollEnabled;
@property(nonatomic, getter=isPagingEnabled) BOOL pagingEnabled;
@property(nonatomic) BOOL alwaysBounceVertical;
@property(nonatomic, weak, nullable) id<NSObject> delegate;
- (void)setContentOffset:(CGPoint)contentOffset animated:(BOOL)animated;
- (void)scrollRectToVisible:(CGRect)rect animated:(BOOL)animated;
@end
@interface CALayer : NSObject
@property(nonatomic) CGRect frame;
@property(nonatomic) CGRect bounds;
@property(nonatomic) CGPoint position;
@property(nonatomic, strong, nullable) UIColor *backgroundColor;
@property(nonatomic, getter=isHidden) BOOL hidden;
@property(nonatomic, readonly) CALayer *presentationLayer;
@property(nonatomic, strong, nullable) id contents;
@property(nonatomic, readonly, nonnull) id presentationInsets;
@end
@interface UIView (CALayerShim)
@property(nonatomic, readonly, strong) CALayer *layer;
- (void)setNeedsLayout;
@end
@interface UIColor (UIKitShim)
@property(class, nonatomic, readonly) UIColor *systemRedColor;
@property(class, nonatomic, readonly) UIColor *labelColor;
- (UIColor *)colorWithAlphaComponent:(CGFloat)alpha;
- (CGColorRef)CGColor;
@end
typedef NS_ENUM(NSInteger, UIUserInterfaceIdiom) { UIUserInterfaceIdiomUnspecified = -1, UIUserInterfaceIdiomPhone = 1, UIUserInterfaceIdiomPad = 2 };
@interface UIDevice (UIKitShim)
@property(nonatomic, readonly) UIUserInterfaceIdiom userInterfaceIdiom;
- (void)beginGeneratingDeviceOrientationNotifications;
@property(nonatomic, readonly) UIGestureRecognizerState unusedDummy;
@end

@interface UILabel : UIView
@property(nonatomic, copy, nullable) NSString *text;
@property(nonatomic, strong) UIColor *textColor;
@property(nonatomic) NSInteger numberOfLines;
@end

@interface UIWindow : UIView
@property(nonatomic, strong, nullable) UIViewController *rootViewController;
@property(nonatomic, readonly, nullable) UIWindowScene *windowScene;
- (void)makeKeyAndVisible;
- (void)makeKeyWindow;
@end

@interface UIViewController : UIResponder <NSCoding>
@property(null_resettable, nonatomic, strong) UIView *view;
@property(nonatomic, readonly, nullable) UIViewController *parentViewController;
@property(nonatomic, readonly, nullable) UIViewController *presentedViewController;
@property(nonatomic, readonly, copy) NSArray<__kindof UIViewController *> *childViewControllers;
@property(nonatomic, readonly, nullable) UINavigationController *navigationController;
@property(nonatomic, readonly) UITraitCollection *traitCollection;
@property(nonatomic, copy, nullable) NSString *title;
- (instancetype)initWithNibName:(nullable NSString *)nibNameOrNil bundle:(nullable NSBundle *)nibBundleOrNil NS_DESIGNATED_INITIALIZER;
- (nullable instancetype)initWithCoder:(NSCoder *)coder NS_DESIGNATED_INITIALIZER;
- (void)loadView;
- (void)viewDidLoad;
- (void)viewWillAppear:(BOOL)animated;
- (void)viewDidAppear:(BOOL)animated;
- (void)viewWillDisappear:(BOOL)animated;
- (void)viewDidDisappear:(BOOL)animated;
- (void)viewWillLayoutSubviews;
- (void)viewDidLayoutSubviews;
- (void)viewSafeAreaInsetsDidChange;
- (void)viewWillTransitionToSize:(CGSize)size withTransitionCoordinator:(id)coordinator;
- (void)traitCollectionDidChange:(nullable UITraitCollection *)previousTraitCollection;
- (void)didReceiveMemoryWarning;
- (void)presentViewController:(UIViewController *)viewControllerToPresent animated:(BOOL)flag completion:(void (^_Nullable)(void))completion;
- (void)dismissViewControllerAnimated:(BOOL)flag completion:(void (^_Nullable)(void))completion;
- (void)addChildViewController:(UIViewController *)childController;
- (void)didMoveToParentViewController:(nullable UIViewController *)parent;
- (void)willMoveToParentViewController:(nullable UIViewController *)parent;
- (void)removeFromParentViewController;
- (void)setNeedsStatusBarAppearanceUpdate;
- (void)setNeedsUpdateOfScreenEdgesDeferringSystemGestures;
@property(nonatomic, readonly) UIStatusBarStyle preferredStatusBarStyle;
@property(nonatomic, readonly) BOOL prefersStatusBarHidden;
@property(nonatomic, readonly) UIInterfaceOrientationMask supportedInterfaceOrientations;
@property(nonatomic, readonly) BOOL shouldAutorotate;
@end

@interface UIApplicationShortcutItem : NSObject <NSCopying, NSMutableCopying>
@property(nonatomic, copy, readonly) NSString *type;
@end

@interface UIUserNotificationSettings : NSObject
@end
@interface UILocalNotification : NSObject
@end

@interface UIOpenURLContext : NSObject
@property(nonatomic, copy, readonly) NSURL *URL;
@end

@interface UISceneSession : NSObject
@property(nonatomic, readonly, copy) NSString *persistentIdentifier;
@end
@interface UISceneConnectionOptions : NSObject
@property(nonatomic, copy, readonly) NSSet<UIOpenURLContext *> *URLContexts;
@property(nonatomic, copy, readonly) NSSet<NSUserActivity *> *userActivities;
@property(nonatomic, strong, readonly, nullable) UIApplicationShortcutItem *shortcutItem;
@end
@interface UIScene : UIResponder
@property(nonatomic, readonly) UISceneSession *session;
@end
@interface UIWindowScene : UIScene
@property(nonatomic, readonly) NSArray<UIWindow *> *windows;
@property(nonatomic, readonly, nullable) UIWindow *keyWindow;
@end
@protocol UISceneDelegate <NSObject>
@optional
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions;
- (void)sceneDidDisconnect:(UIScene *)scene;
- (void)sceneDidBecomeActive:(UIScene *)scene;
- (void)sceneWillResignActive:(UIScene *)scene;
- (void)sceneWillEnterForeground:(UIScene *)scene;
- (void)sceneDidEnterBackground:(UIScene *)scene;
- (void)scene:(UIScene *)scene openURLContexts:(NSSet<UIOpenURLContext *> *)URLContexts;
- (void)scene:(UIScene *)scene continueUserActivity:(NSUserActivity *)userActivity;
@end
@protocol UIWindowSceneDelegate <UISceneDelegate>
@optional
@property(nonatomic, strong, nullable) UIWindow *window;
- (void)windowScene:(UIWindowScene *)windowScene performActionForShortcutItem:(UIApplicationShortcutItem *)shortcutItem completionHandler:(void (^)(BOOL succeeded))completionHandler;
@end

@protocol UIApplicationDelegate <NSObject>
@optional
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(nullable NSDictionary<UIApplicationLaunchOptionsKey, id> *)launchOptions;
- (BOOL)application:(UIApplication *)application willFinishLaunchingWithOptions:(nullable NSDictionary<UIApplicationLaunchOptionsKey, id> *)launchOptions;
- (void)applicationDidBecomeActive:(UIApplication *)application;
- (void)applicationWillResignActive:(UIApplication *)application;
- (void)applicationDidEnterBackground:(UIApplication *)application;
- (void)applicationWillEnterForeground:(UIApplication *)application;
- (void)applicationWillTerminate:(UIApplication *)application;
- (void)applicationDidReceiveMemoryWarning:(UIApplication *)application;
- (BOOL)application:(UIApplication *)app openURL:(NSURL *)url options:(NSDictionary<UIApplicationOpenURLOptionsKey, id> *)options;
- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)connectingSceneSession options:(UISceneConnectionOptions *)options;
- (void)application:(UIApplication *)application didRegisterForRemoteNotificationsWithDeviceToken:(NSData *)deviceToken;
- (void)application:(UIApplication *)application didFailToRegisterForRemoteNotificationsWithError:(NSError *)error;
- (void)application:(UIApplication *)application didReceiveRemoteNotification:(NSDictionary *)userInfo fetchCompletionHandler:(void (^)(UIBackgroundFetchResult result))completionHandler;
- (void)application:(UIApplication *)application performActionForShortcutItem:(UIApplicationShortcutItem *)shortcutItem completionHandler:(void (^)(BOOL succeeded))completionHandler;
- (void)application:(UIApplication *)application performFetchWithCompletionHandler:(void (^)(UIBackgroundFetchResult result))completionHandler;
- (BOOL)application:(UIApplication *)application continueUserActivity:(NSUserActivity *)userActivity restorationHandler:(void (^)(NSArray<id<UIUserActivityRestoring>> *_Nullable))restorationHandler;
@property(nonatomic, strong, nullable) UIWindow *window;
@end

@interface UISceneConfiguration : NSObject
@property(nonatomic, readonly, nullable) NSString *name;
@property(nonatomic, strong, nullable) Class delegateClass;
+ (instancetype)configurationWithName:(nullable NSString *)name sessionRole:(NSString *)sessionRole;
@end

@interface UIApplication : UIResponder
@property(class, nonatomic, readonly) UIApplication *sharedApplication NS_EXTENSION_UNAVAILABLE_IOS("");
@property(nonatomic, assign, nullable) id<UIApplicationDelegate> delegate;
@property(nonatomic, readonly) UIApplicationState applicationState;
@property(nonatomic, readonly, nullable) UIWindow *keyWindow;
@property(nonatomic, readonly) NSArray<UIWindow *> *windows;
@property(nonatomic, getter=isIdleTimerDisabled) BOOL idleTimerDisabled;
- (BOOL)canOpenURL:(NSURL *)url;
- (void)openURL:(NSURL *)url options:(NSDictionary<UIApplicationOpenExternalURLOptionsKey, id> *)options completionHandler:(void (^_Nullable)(BOOL success))completion;
- (void)registerForRemoteNotifications;
- (UIBackgroundTaskIdentifier)beginBackgroundTaskWithExpirationHandler:(void (^_Nullable)(void))handler;
- (void)endBackgroundTask:(UIBackgroundTaskIdentifier)identifier;
@end

UIKIT_EXTERN int UIApplicationMain(int argc, char *_Nonnull *_Nonnull argv, NSString *_Nullable principalClassName, NSString *_Nullable delegateClassName);
UIKIT_EXTERN NSString *const UIApplicationLaunchOptionsURLKey;
UIKIT_EXTERN UIApplicationOpenURLOptionsKey const UIApplicationOpenURLOptionsSourceApplicationKey;

NS_ASSUME_NONNULL_END
