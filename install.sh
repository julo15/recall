#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.local/share/recall/venv"
BIN_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIN_PYTHON_VERSION="3.10"

# Find a suitable Python 3.10+
check_python() {
  local cmd="$1"
  version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || return 1
  major="${version%%.*}"
  minor="${version#*.}"
  if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
    echo "$cmd"
    return 0
  fi
  return 1
}

find_python() {
  # Check PATH first (works for brew, system python, etc.)
  for cmd in python3 python; do
    if check_python "$cmd" 2>/dev/null; then return 0; fi
  done

  # Check version managers (asdf, pyenv) directly, bypassing shims
  for dir in "$HOME/.asdf/installs/python"/*/bin "$HOME/.pyenv/versions"/*/bin; do
    if [ -x "$dir/python3" ]; then
      if check_python "$dir/python3" 2>/dev/null; then return 0; fi
    fi
  done

  # Check common system locations
  for cmd in /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
    if [ -x "$cmd" ]; then
      if check_python "$cmd" 2>/dev/null; then return 0; fi
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
