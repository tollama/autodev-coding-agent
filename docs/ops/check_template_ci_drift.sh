#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-$(pwd)}"
CONTRACT="${2:-$ROOT_DIR/docs/ops/template-validation-contract.json}"
shift || true
WORKFLOWS=("$@")
if [ ${#WORKFLOWS[@]} -eq 0 ]; then
  WORKFLOWS=(
    "$ROOT_DIR/templates/python_fastapi/.github/workflows/ci.yml"
    "$ROOT_DIR/templates/python_cli/.github/workflows/ci.yml"
  )
fi

python3 - "$CONTRACT" "${WORKFLOWS[@]}" <<'PY'
import json
import pathlib
import sys

contract = json.loads(pathlib.Path(sys.argv[1]).read_text())
workflows = [pathlib.Path(p) for p in sys.argv[2:]]
errors = False

required = contract["required_commands"]
python_version = contract["python_version"]
tool_versions = contract["tool_versions"]
env_names = contract.get("tool_version_env", {})

for wf in workflows:
    text = wf.read_text()
    name = wf.as_posix()

    if f'python-version: "{python_version}"' not in text and f"python-version: '{python_version}'" not in text:
        print(f"[ERROR] {name}: python-version {python_version} not configured")
        errors = True

    for cmd in required:
        if cmd not in text:
            print(f"[ERROR] {name}: missing required command: {cmd}")
            errors = True

    for tool, version in tool_versions.items():
        env_name = env_names.get(tool)
        if env_name:
            marker = f"{env_name}: \"{version}\""
            if marker not in text:
                print(f"[ERROR] {name}: missing pinned tool env var {env_name}={version}")
                errors = True
        else:
            pattern = f'"{tool}=={version}"'
            if pattern not in text:
                print(f"[ERROR] {name}: missing pinned tool dependency {pattern}")
                errors = True

if errors:
    sys.exit(1)
print("Template CI workflows match validation contract.")
PY
