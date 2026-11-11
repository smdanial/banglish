#!/usr/bin/env bash
# Creates .venv/ in the repo folder with everything the laptop scripts need, then checks it.
# Usage (from the repo folder):  ./setup.sh
# Safe to run again: it reuses .venv/ and only installs what is missing.
set -euo pipefail
cd "$(dirname "$0")"

missing=()
command -v python3 >/dev/null || missing+=(python3)
command -v ffmpeg  >/dev/null || missing+=(ffmpeg)
command -v git     >/dev/null || missing+=(git)
if command -v python3 >/dev/null && ! python3 -c "import ensurepip, venv" 2>/dev/null; then
  missing+=(python3-venv)
fi
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing system packages: ${missing[*]}"
  echo "Install them with this command (it asks for your laptop password), then run ./setup.sh again:"
  echo "  sudo apt update && sudo apt install -y git python3 python3-venv python3-pip ffmpeg"
  exit 1
fi

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "Python 3.9 or newer is needed (you have $(python3 --version))."; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi
echo "Installing Python packages (first time: 2-10 minutes, about 600 MB) ..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

.venv/bin/python - <<'PY'
import faster_whisper, jiwer, numpy, psutil, yaml, pytest  # noqa: F401
import sys
print(f"Python {sys.version.split()[0]}, numpy {numpy.__version__}, faster-whisper {faster_whisper.__version__}")
PY
echo "Setup OK. Before running anything, type:  source .venv/bin/activate"
