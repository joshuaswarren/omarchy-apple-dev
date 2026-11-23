#!/usr/bin/env bash
set -euo pipefail
B=~/scratch/w7Q/411-carry-patch
O=~/scratch/w7Q/omarchy-mlx-g515
BUNDLE=~/scratch/w7Q/omarchy-mlx-g515/.work-w7c5e/mlx/tools/mlx-omarchy-parakeet/share/mlx-omarchy/parakeet-1/bundles/parakeet-encoder-whole
mkdir -p "$B/overlay/mlx/backend/omarchy/shaders"
cp -f "$B/qmm_vec.comp" "$B/overlay/mlx/backend/omarchy/shaders/qmm_vec.comp"
export MLX_OMARCHY_WHOLE_BUNDLE_DIR="$BUNDLE"
export MLX_OMARCHY_WORK_DIR="$O/.work-w7c5diag"
CMAKE_BUILD_PARALLEL_LEVEL=6 bash "$O/scripts/build-wheel.sh" --diagnostics > /tmp/w7c-qmm320-wheel5diag.log 2>&1
echo wheel5diag_exit=$? >> /tmp/w7c-qmm320-wheel5diag.log
