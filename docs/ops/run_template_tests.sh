#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

templates=(python_fastapi python_cli python_library)

for template in "${templates[@]}"; do
  echo "[template-test] ===== ${template} ====="
  tdir="$ROOT_DIR/templates/$template"
  if [ ! -d "$tdir/tests" ]; then
    echo "[skip] tests directory not found: $tdir/tests"
    continue
  fi

  (cd "$tdir" && PYTHONPATH="$tdir/src:${PYTHONPATH-}" python3 -m pytest -q tests)
done
