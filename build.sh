#!/usr/bin/env bash
# Build the OST single-file binary on Linux and macOS.
#
# Usage:   ./build.sh [PYTHON_EXECUTABLE]
# Output:  dist/ost
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${1:-python3}"
VENV=".build-venv"

if [ ! -d "$VENV" ]; then
  echo ">> creating venv ($PYTHON)"
  "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo ">> installing project + build deps"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[all]" pyinstaller

echo ">> building binary"
python -m PyInstaller --noconfirm --clean ost.spec

echo
echo ">> DONE: $(pwd)/dist/ost"
echo "   try it:     ./dist/ost list"
echo "   launch TUI: ./dist/ost"