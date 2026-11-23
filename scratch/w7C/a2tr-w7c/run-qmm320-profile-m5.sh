#!/usr/bin/env bash
set -euo pipefail
V=~/scratch/w7Q/omarchy-mlx-g515/.work-w7c5diag/venv-build
WHL=$(ls -t ~/scratch/w7Q/omarchy-mlx-g515/dist/*diag*.whl 2>/dev/null | head -1)
test -n "$WHL"
"$V/bin/pip" install -q --force-reinstall "$WHL"
export PATH="$V/bin:$PATH"
PROF=/tmp/w7c-qmm320-word-profile.jsonl
rm -f "$PROF"
export MLX_DISABLE_COMPILE=1 VK_DRIVER_FILES=/usr/share/vulkan/icd.d/asahi_icd.aarch64.json
export MLX_OMARCHY_GPU_PROFILE="$PROF"
export MLX_OMARCHY_GPU_PROFILE_LABEL=qmm320-k2560-n320-wheel5e
export MLX_OMARCHY_GPU_PROFILE_DISPATCH=1
python3 /var/tmp/qmm320_profile_once.py default | tee /var/tmp/qmm320_profile_once.out
python3 /var/tmp/summarize-qmm320-profile.py "$PROF"
