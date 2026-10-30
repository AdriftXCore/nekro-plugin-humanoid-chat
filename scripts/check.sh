#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m py_compile humanoid_chat.py
echo "python syntax: ok"

python3 - <<'PY'
import glob
import yaml

for path in sorted(glob.glob("examples/*.yaml")):
    with open(path, encoding="utf-8") as f:
        yaml.safe_load(f)
    print("yaml: ok", path)
PY
