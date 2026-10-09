#!/usr/bin/env bash
# Host side: bundle JS with Metro, compile to Hermes bytecode, run RN codegen.
# Outputs go to local disk (per Main 2026-10-09: no small-file writes to QNAP).
#   rn-js.sh <RNProbe dir> <OUT dir>
set -euo pipefail
APP=${1:?RNProbe dir}
OUT=${2:?local out dir}
mkdir -p "$OUT"
cd "$APP"

echo "== metro bundle"
ionice -c3 nice -n 19 npx react-native bundle \
  --platform ios --dev false --entry-file index.js \
  --bundle-output "$OUT/main.jsbundle" \
  --assets-dest "$OUT/assets" 2>&1 | tail -3

echo "== hermes bytecode"
HERMESC=${HERMESC:-/mnt/qnap-public/omp-studio-offload/apple-dev/flutter-work/rn/artifacts/package/hermesc/linux64-bin/hermesc}
"$HERMESC" -O -emit-binary -out "$OUT/main.hbc" "$OUT/main.jsbundle"

echo "== codegen"
ionice -c3 nice -n 19 node node_modules/react-native/scripts/generate-codegen-artifacts.js \
  -p . -o "$OUT/codegen" --platform ios 2>&1 | tail -3
echo done
