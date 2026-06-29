#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_ROOT/.venv"
PYTHON="$VENV/bin/python"
URL="http://127.0.0.1:8000/"
OPEN_BROWSER=1

if [ "${1:-}" = "--no-browser" ]; then
  OPEN_BROWSER=0
fi

cd "$PROJECT_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it and run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x "$PYTHON" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$VENV"
fi

echo "Installing requirements..."
"$PYTHON" -m pip install --disable-pip-version-check -r "$PROJECT_ROOT/requirements.txt"

echo "Starting Agent Protocol Lab at $URL"
echo "Press Control-C to stop the server."
if [ "$OPEN_BROWSER" -eq 1 ]; then
  (sleep 1; open "$URL") &
else
  echo "Open manually: $URL"
fi

exec "$PYTHON" -m agent_runtime.server
