#!/usr/bin/env bash
# like sdk-free/cc.sh but with libc++ headers first (RN app sources are ObjC++)
#   rncc.sh [-c] file.mm -o out.o    extra RN include/framework paths pass via args
set -euo pipefail
SDKFREE_HOME=${SDKFREE_HOME:-/qwork/sdkfree-swift}
SR=${NOSDK_SYSROOT:-$SDKFREE_HOME/iPhoneOS.sdk}
CLANG=${SDKFREE_CLANG:-$(dirname "$(readlink -f "$(command -v swift)")")/clang}
MIN=${NOSDK_MIN:-17.0}
exec "$CLANG" -target "arm64-apple-ios$MIN" -isysroot "$SR" -nostdinc \
  -I /usr/include/c++/v1 \
  -I "$SDKFREE_HOME/swift/darwin/usr/include" \
  -I "${NOSDK_SHIM:-/home/builder/rnbuild/inc}" \
  -isystem "$SR/usr/include" \
  -isystem "$("$CLANG" -print-resource-dir)/include" \
  -iframework "$SR/System/Library/Frameworks" \
  -fobjc-arc -fobjc-runtime="ios-$MIN" -fno-modules "$@"
