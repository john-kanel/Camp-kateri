#!/bin/zsh
set -e

cd "$(dirname "$0")"

PYTHON_BOOTSTRAP="/usr/bin/python3"
if [ ! -d ".venv" ]; then
  "$PYTHON_BOOTSTRAP" -m venv .venv
fi

PYTHON_BIN=".venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Could not find $PYTHON_BIN"
  exit 1
fi

"$PYTHON_BIN" -m pip install --upgrade pip >/dev/null
"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" app_backend.py
