#!/usr/bin/env bash
# Build the release packages for this OS (see packaging/build.py) using the project's .venv.
#   packaging/build.sh   -> dist/release/*.deb, *.tar.gz (Linux) / *.dmg (macOS)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -e . "pyinstaller>=6"
.venv/bin/python packaging/build.py
