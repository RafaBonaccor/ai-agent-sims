#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_VENV="$PROJECT_ROOT/.venv"
RUNTIME_PYTHON="$RUNTIME_VENV/bin/python"
SCRAPER_ROOT="$PROJECT_ROOT/projects/main-scraper"
SCRAPER_VENV="$SCRAPER_ROOT/.venv"
SCRAPER_PYTHON="$SCRAPER_VENV/bin/python"
SCRAPER_REQUIREMENTS="$PROJECT_ROOT/integrations/main-scraper/requirements.txt"
PROJECTS_LOCAL="$PROJECT_ROOT/config/projects.local.json"

SKIP_INSTALL=0
SKIP_SUBMODULE=0
SKIP_CONFIG=0
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

for arg in "$@"; do
  case "$arg" in
    --skip-install)
      SKIP_INSTALL=1
      ;;
    --skip-submodule)
      SKIP_SUBMODULE=1
      ;;
    --skip-config)
      SKIP_CONFIG=1
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/setup_macos.sh [--skip-install] [--skip-submodule] [--skip-config]

Creates a reproducible local macOS setup:
  - runtime .venv
  - The Main Scraper submodule checkout
  - projects/main-scraper/.venv
  - scraper dependencies from integrations/main-scraper/requirements.txt
  - config/projects.local.json pointing to the scraper venv Python

Options:
  --skip-install    Create venv/config only; do not run pip install.
  --skip-submodule  Do not run git submodule update.
  --skip-config     Do not write config/projects.local.json.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

find_python() {
  if [ -n "${PYTHON_BIN:-}" ]; then
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      local configured
      configured="$(command -v "$PYTHON_BIN")"
      if python_version_ok "$configured"; then
        echo "$configured"
        return 0
      fi
      echo "PYTHON_BIN must point to Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+; got $("$configured" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" >&2
      return 1
    fi
    echo "PYTHON_BIN is set but not executable: $PYTHON_BIN" >&2
    return 1
  fi

  for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      local resolved
      resolved="$(command -v "$candidate")"
      if python_version_ok "$resolved"; then
        echo "$resolved"
        return 0
      fi
    fi
  done

  echo "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required. Current macOS /usr/bin/python3 is too old for The Main Scraper." >&2
  if command -v brew >/dev/null 2>&1; then
    echo "Recommended install: brew install python@3.12" >&2
    echo "Then re-run: scripts/setup_macos.sh" >&2
  else
    echo "Install Python 3.12 from https://www.python.org/downloads/macos/ and re-run this script." >&2
  fi
  return 1
}

python_version_ok() {
  local python_bin="$1"
  "$python_bin" - "$MIN_PYTHON_MAJOR" "$MIN_PYTHON_MINOR" <<'PY'
import sys

required = (int(sys.argv[1]), int(sys.argv[2]))
raise SystemExit(0 if sys.version_info[:2] >= required else 1)
PY
}

create_venv() {
  local python_bin="$1"
  local venv_dir="$2"
  local label="$3"

  if [ -x "$venv_dir/bin/python" ]; then
    if python_version_ok "$venv_dir/bin/python"; then
      echo "$label venv already exists: $venv_dir"
      return 0
    fi
    echo "$label venv uses Python older than ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}; recreating: $venv_dir"
    rm -rf "$venv_dir"
  fi

  if [ -x "$venv_dir/bin/python" ]; then
    echo "$label venv already exists: $venv_dir"
    return 0
  fi

  echo "Creating $label venv: $venv_dir"
  "$python_bin" -m venv "$venv_dir"
}

install_requirements() {
  local python_bin="$1"
  local requirements="$2"
  local label="$3"

  if [ "$SKIP_INSTALL" -eq 1 ]; then
    echo "Skipping $label dependency install."
    return 0
  fi

  echo "Installing $label requirements: $requirements"
  "$python_bin" -m pip install --disable-pip-version-check -r "$requirements"
}

write_projects_local() {
  if [ "$SKIP_CONFIG" -eq 1 ]; then
    echo "Skipping config/projects.local.json update."
    return 0
  fi

  echo "Writing scraper Python path to config/projects.local.json"
  "$RUNTIME_PYTHON" - "$PROJECT_ROOT" "$SCRAPER_PYTHON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
scraper_python = Path(sys.argv[2]).expanduser()
if not scraper_python.is_absolute():
    scraper_python = root / scraper_python
path = root / "config" / "projects.local.json"

if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {}

projects = data.setdefault("projects", {})
main_scraper = projects.setdefault("main-scraper", {})
main_scraper["pythonExecutable"] = str(scraper_python)

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

check_import() {
  local python_bin="$1"
  local module="$2"
  local label="$3"

  "$python_bin" - "$module" "$label" <<'PY'
import importlib.util
import sys

module = sys.argv[1]
label = sys.argv[2]
available = importlib.util.find_spec(module) is not None
status = "ok" if available else "missing"
print(f"{label}: {module} {status}")
raise SystemExit(0 if available else 1)
PY
}

cd "$PROJECT_ROOT"

PYTHON="$(find_python)"
echo "Using Python: $PYTHON"

create_venv "$PYTHON" "$RUNTIME_VENV" "runtime"
install_requirements "$RUNTIME_PYTHON" "$PROJECT_ROOT/requirements.txt" "runtime"

if [ "$SKIP_SUBMODULE" -eq 0 ] && [ ! -f "$SCRAPER_ROOT/main.py" ]; then
  echo "Initializing The Main Scraper submodule..."
  git submodule update --init --recursive projects/main-scraper
fi

if [ ! -f "$SCRAPER_ROOT/main.py" ]; then
  echo "The Main Scraper is missing at $SCRAPER_ROOT" >&2
  echo "Run: git submodule update --init --recursive projects/main-scraper" >&2
  exit 1
fi

create_venv "$PYTHON" "$SCRAPER_VENV" "main-scraper"
install_requirements "$SCRAPER_PYTHON" "$SCRAPER_REQUIREMENTS" "main-scraper"
write_projects_local

echo
echo "Setup summary"
echo "-------------"
echo "Runtime Python: $RUNTIME_PYTHON"
echo "Scraper Python: $SCRAPER_PYTHON"
echo "Projects local: $PROJECTS_LOCAL"

if check_import "$SCRAPER_PYTHON" botasaurus "main-scraper"; then
  echo "Botasaurus bridge is ready."
else
  echo "Botasaurus is not installed yet. Re-run without --skip-install when network is available." >&2
  if [ "$SKIP_INSTALL" -eq 0 ]; then
    exit 1
  fi
fi

if check_import "$SCRAPER_PYTHON" tkinter "main-scraper"; then
  echo "Tkinter is ready."
else
  echo "Tkinter is missing for Python 3.12. Install it with: brew install python-tk@3.12" >&2
  exit 1
fi
