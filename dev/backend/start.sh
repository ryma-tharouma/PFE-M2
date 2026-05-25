#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR"
PROD_DIR="$PROJECT_ROOT/prod"
VENV_DIR="$BACKEND_DIR/venv"

cd "$BACKEND_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip >/dev/null
pip install -r "$BACKEND_DIR/requirements.txt"
pip install -r "$PROD_DIR/requirements.txt"

export PYTHONPATH="$PROD_DIR:${PYTHONPATH:-}"

if [ ! -f "$BACKEND_DIR/.env" ] && [ -f "$BACKEND_DIR/.env.example" ]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
fi

echo "Starting Flask API from $BACKEND_DIR"
python "$BACKEND_DIR/main.py"
