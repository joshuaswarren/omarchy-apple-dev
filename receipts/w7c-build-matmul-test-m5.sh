#!/usr/bin/env bash
set -euo pipefail
O=~/scratch/w7Q/omarchy-mlx-g515
LOG=/tmp/w7c-matmul-family-build.log
echo "restart $(date -u +%FT%TZ)" >>"$LOG"
cd "$O"
export MLX_OMARCHY_WORK_DIR="$O/.work-w7ctest"
B="$MLX_OMARCHY_WORK_DIR/build-doctest"
LAPACK_INC=/usr/include/openblas
CMAKE_EXTRA=()
[[ -f $LAPACK_INC/lapacke.h ]] && CMAKE_EXTRA+=(-DLAPACK_INCLUDE_DIRS="$LAPACK_INC")
[[ -f /usr/include/openblas/cblas.h ]] && CMAKE_EXTRA+=(-DBLAS_INCLUDE_DIRS="$LAPACK_INC")
rm -rf "$B"
echo "== cmake configure (lapack fix) ==" >>"$LOG"
cmake -S "$MLX_OMARCHY_WORK_DIR/mlx" -B "$B" -G Ninja \
  -DMLX_BUILD_OMARCHY=ON -DMLX_BUILD_CPU=ON \
  -DMLX_BUILD_METAL=OFF -DMLX_BUILD_CUDA=OFF \
  -DMLX_BUILD_TESTS=ON -DMLX_BUILD_EXAMPLES=OFF \
  -DMLX_BUILD_BENCHMARKS=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_EXTRA[@]}" >>"$LOG" 2>&1
cp -f "$O/overlay/tests/omarchy/test_matmul_family.cpp" \
  "$MLX_OMARCHY_WORK_DIR/mlx/tests/omarchy/test_matmul_family.cpp"
echo "== build target ==" >>"$LOG"
cmake --build "$B" --target omarchy_matmul_family_tests -j"$(nproc)" >>"$LOG" 2>&1
BIN=$(find "$B" -name omarchy_matmul_family_tests -type f | head -1)
echo "BUILT $BIN" >>"$LOG"
export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/asahi_icd.aarch64.json
"$BIN" -tc="qwen3 decode q4 gemv k2560 n320 bandwidth floor on G17C" >>"$LOG" 2>&1 || echo "doctest_exit=$?" >>"$LOG"
echo "done $(date -u +%FT%TZ)" >>"$LOG"
