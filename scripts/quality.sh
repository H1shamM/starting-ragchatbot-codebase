#!/bin/bash
# Run code quality checks from the repo root.
# Usage:
#   bash scripts/quality.sh          # check formatting + run tests
#   bash scripts/quality.sh --fix    # auto-format then run tests

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FIX=false
if [[ "$1" == "--fix" ]]; then
    FIX=true
fi

echo "=== Formatting (black) ==="
if $FIX; then
    uv run black backend/ main.py
    echo "Files formatted."
else
    uv run black --check backend/ main.py
    echo "Formatting OK."
fi

echo ""
echo "=== Tests (pytest) ==="
cd backend && uv run pytest tests/ -v
