#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN=${COWPATH_BIN_DIR:-"$HOME/.local/bin"}
mkdir -p "$BIN"
cp "$ROOT/tools/cowpath_mvp.py" "$BIN/cowpath"
chmod +x "$BIN/cowpath"
printf 'Installed cowpath to %s/cowpath\n' "$BIN"
printf 'Run: cowpath --workspace /path/to/workspace\n'
