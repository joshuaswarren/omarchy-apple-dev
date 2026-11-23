#!/usr/bin/env bash
set -euo pipefail
V=~/scratch/w7Q/omarchy-mlx-g515/.work-w7c5e/venv-build
export PATH="$V/bin:$PATH"
export MLX_DISABLE_COMPILE=1 VK_DRIVER_FILES=/usr/share/vulkan/icd.d/asahi_icd.aarch64.json
exec "$V/bin/python3" /var/tmp/trace_qmm320_counters.py
