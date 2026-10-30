#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

msg="${1:-update humanoid_chat plugin}"

./scripts/check.sh

git add -A
if git diff --cached --quiet; then
  echo "nothing to commit"
  exit 0
fi

git commit -m "$msg"
git push origin HEAD
