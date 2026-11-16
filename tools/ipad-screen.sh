#!/usr/bin/env bash
# Mirror/control only. Never builds, installs packages system-wide, or uses sudo.
set -euo pipefail
root=$(cd -- "$(dirname -- "$(readlink -f -- "$0")")" && pwd)
if [[ -n ${IPAD_SCREEN_PYTHON:-} ]]; then
  py=$IPAD_SCREEN_PYTHON
elif [[ -x $HOME/pymobile3-venv/bin/python ]]; then
  py=$HOME/pymobile3-venv/bin/python
elif [[ -x $HOME/.local/share/pipx/venvs/pymobiledevice3/bin/python ]]; then
  py=$HOME/.local/share/pipx/venvs/pymobiledevice3/bin/python
else
  echo 'ipad-screen: need the installer venv (~/pymobile3-venv) or pymobiledevice3 pipx environment' >&2
  exit 1
fi
exec "$py" "$root/ipad-screen.py" "$@"
