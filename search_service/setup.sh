#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

PYTHON="${PYTHON:-python3.13}"
CAMOUFOX_BROWSER="${CAMOUFOX_BROWSER:-official/stable/152.0.4-beta.29}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON was not found." >&2
    echo "Install Python 3.13 or set PYTHON to a Python 3.13 executable." >&2
    exit 1
fi

"$PYTHON" -m venv "$VENV_DIR"

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

"$VENV_DIR/bin/camoufox" set "$CAMOUFOX_BROWSER"

echo
echo "Search service environment ready."
echo "Python:"
"$VENV_DIR/bin/python" --version
echo "Camoufox:"
"$VENV_DIR/bin/camoufox" version
