#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' 'Create the environment first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt'
  exit 1
fi
exec .venv/bin/python -m uvicorn dreamtales.app:app --host 127.0.0.1 --port "${DREAMTALES_PORT:-8765}"
