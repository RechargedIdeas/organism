#!/usr/bin/env bash
# Target-box soak runner (v1.4). Fast path always; full soak when FULL=1 (default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/sdk/python:${ROOT}/modules:${ROOT}"
PY="${ORGANISM_PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

FULL="${ORGANISM_SOAK_FULL:-1}"
WALL="${ORGANISM_WALL_CLOCK_FULL:-0}"

echo "== Organism soak_target =="
echo "root=$ROOT python=$PY FULL=$FULL WALL=$WALL"

echo "-- fast soak (CI path) --"
"$PY" -m pytest -q sdk/python/tests/test_v04_soak.py -m 'not slow'

if [[ "$FULL" == "1" ]]; then
  echo "-- full soak (ORGANISM_SOAK_FULL=1) --"
  ORGANISM_SOAK_FULL=1 "$PY" -m pytest -q sdk/python/tests/test_v04_soak.py
fi

echo "-- perf budgets (retune source for PERF.md) --"
"$PY" -m pytest -q sdk/python/tests/test_v04_perf.py

if [[ "$WALL" == "1" ]]; then
  echo "-- wall-clock full (ORGANISM_WALL_CLOCK_FULL=1) --"
  ORGANISM_WALL_CLOCK_FULL=1 "$PY" -m pytest -q sdk/python/tests/test_wall_clock_slo.py
else
  echo "-- wall-clock fast only --"
  "$PY" -m pytest -q sdk/python/tests/test_wall_clock_slo.py -m 'not slow'
fi

echo "OK — see docs/ops/SOAK_RUNBOOK.md to retune docs/v0.4/PERF.md"
