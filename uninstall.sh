#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.local/share/recall/venv"
BIN_LINK="$HOME/.local/bin/recall"

removed=false

if [ -L "$BIN_LINK" ]; then
  rm "$BIN_LINK"
  echo "Removed $BIN_LINK"
  removed=true
fi

if [ -d "$VENV_DIR" ]; then
  rm -rf "$VENV_DIR"
  echo "Removed $VENV_DIR"
  removed=true
fi

if [ "$removed" = true ]; then
  echo "Done. recall has been uninstalled."
else
  echo "Nothing to remove — recall does not appear to be installed."
fi
