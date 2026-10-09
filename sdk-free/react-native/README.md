# React Native (0.87.x) iOS app without Xcode

A React Native iOS release app builds and signs on Linux. The app target
(compiled here) is a few files; everything heavy ships as Meta's own prebuilt
artifacts, downloaded by version from Maven Central like the pods do.

## Route

1. `npx @react-native-community/cli init RNProbe` (any Linux with node).
2. Download the prebuilt artifacts for the RN version (`rn-build.sh` prints the
   URLs): `react-native-artifacts-<v>-reactnative-core-release.tar.gz`,
   `-reactnative-dependencies-release.tar.gz` (Maven, `com/facebook/react`),
   `hermes-ios-<hermesv>-hermes-ios-release.tar.gz` (`com/facebook/hermes`),
   plus the matching `hermes-compiler` npm package for the Linux `hermesc`.
   Keep only the `ios-arm64` slice of each xcframework.
3. Bundle the JS with Metro (`rn-js.sh`) and compile it to Hermes bytecode with
   the Linux `hermesc` (same version as the runtime).
4. Generate the codegen providers with `generate-codegen-artifacts.js`.
5. Compile the app target with `rncc.sh` (ObjC++ + libc++ headers from the
   host, RN prebuilt headers, the shim headers in `headers/`).
6. Link with `ld64.lld` against the three dynamic frameworks and embed them.
7. Assemble `RNProbe.app`, sign with `tools/provision-dev.py` +
   `tools/sign-dev.sh` (sign-dev already signs embedded frameworks).

`RNProbe.app` is 9 MB; `macho-lint.py` reports the executable and all three
embedded frameworks clean.

## Status

- Verified on Linux for RN 0.87.1, arm64 iPhone, iOS 17.0 deployment target:
  app target compiles, links, bundles, signs (`receipts/2026-10-09-rn.md`).
- JS runs as Hermes bytecode compiled by the version-matched Linux `hermesc`.
- The template's third-party Fabric pod (`react-native-safe-area-context`)
  still needs its generated C++ headers; the probe ships without it. More
  pods are buildable the same way — `headers/` grows per missing SDK type.

## Header shims

`headers/` holds hand-written minimal Foundation/UIKit/QuartzCore surfaces
written for this repo (no SDK files): variadic `NS_ENUM` (RN 0.87 headers use
anonymous `NS_ENUM(NSInteger){...}`), `NSProxy`/`NSAssertionHandler` stubs,
`CATransform3D`, `CADisplayLink`, geometry inline functions, and the text
enums RN converters use. `rncc.sh` puts them before the sysroot copies.
