#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.local/share/recall/venv"
BIN_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIN_PYTHON_VERSION="3.10"

# Find a suitable Python 3.10+
find_python() {
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
      major="${version%%.*}"
      minor="${version#*.}"
      if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
        command -v "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON=$(find_python) || {
  echo "Error: Python >=${MIN_PYTHON_VERSION} is required but not found on PATH."
  echo "Install Python from https://www.python.org/downloads/ and try again."
  exit 1
}

echo "Using $PYTHON ($($PYTHON --version 2>&1))"

# Create or update venv
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR..."
  "$PYTHON" -m venv "$VENV_DIR"
else
  echo "Virtual environment already exists at $VENV_DIR"
fi

echo "Installing recall..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR" -q

# Symlink the recall binary onto PATH
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/recall" "$BIN_DIR/recall"

# Check if BIN_DIR is on PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  echo ""
  echo "NOTE: $BIN_DIR is not on your PATH."
  echo "Add this to your shell profile (~/.zshrc or ~/.bashrc):"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo ""
echo "Done! Run 'recall --help' to get started."
echo "On first search, the embedding model (~80MB) will be downloaded."
