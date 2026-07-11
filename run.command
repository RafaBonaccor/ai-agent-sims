#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_ROOT/.venv"
PYTHON="$VENV/bin/python"
SETUP="$PROJECT_ROOT/scripts/setup_macos.sh"
HOST="${AGENT_LAB_HOST:-127.0.0.1}"
PORT="${AGENT_LAB_PORT:-8000}"
URL="http://$HOST:$PORT/"
OPEN_BROWSER=1
RUN_SETUP=1
SETUP_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --no-browser)
      OPEN_BROWSER=0
      ;;
    --skip-install)
      SETUP_ARGS+=("--skip-install")
      ;;
    --skip-setup)
      RUN_SETUP=0
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./run.command [--no-browser] [--skip-install] [--skip-setup]

Options:
  --no-browser    Start the server without opening the browser.
  --skip-install  Run setup checks and config generation without pip install.
  --skip-setup    Skip macOS setup entirely and start with the existing .venv.

Environment:
  AGENT_LAB_HOST  Bind host, default 127.0.0.1.
  AGENT_LAB_PORT  Bind port, default 8000.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

cd "$PROJECT_ROOT"

if [ "$RUN_SETUP" -eq 1 ]; then
  if [ ! -x "$SETUP" ]; then
    echo "Setup script is missing or not executable: $SETUP" >&2
    exit 1
  fi

  echo "Preparing macOS runtime and scraper environment..."
  "$SETUP" "${SETUP_ARGS[@]}"
fi

if [ ! -x "$PYTHON" ]; then
  echo "Runtime Python not found: $PYTHON" >&2
  echo "Run scripts/setup_macos.sh, then try again." >&2
  exit 1
fi

echo "Starting Agent Protocol Lab at $URL"
echo "Press Control-C to stop the server."
if [ "$OPEN_BROWSER" -eq 1 ]; then
  (sleep 1; open "$URL") &
else
  echo "Open manually: $URL"
fi

exec env AGENT_LAB_HOST="$HOST" AGENT_LAB_PORT="$PORT" "$PYTHON" -m agent_runtime.server
