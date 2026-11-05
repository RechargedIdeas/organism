#!/bin/sh
# Shared by the git hooks. Finds the project interpreter and runs the pipeline for one tier.
# Usage: _resolve.sh <tier> <hook-name>
# Git's own hook arguments (pre-push gets the remote name and URL) are dropped: run.py takes none.
set -u

ROOT="$(git rev-parse --show-toplevel)" || exit 2
TIER="$1"
HOOK="$2"
shift 2

for PY in "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python"; do
  if [ -x "$PY" ]; then
    exec "$PY" "$ROOT/ci/run.py" run --tier "$TIER" --hook "$HOOK"
  fi
done

echo "ci: no project venv at .venv; create it first (see ci/README.md)" >&2
exit 2
