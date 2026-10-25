#!/usr/bin/env bash
# Organism single-device entrypoint (CPU-only default).
set -euo pipefail
ROOT="${ORGANISM_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/sdk/python:${ROOT}/modules:${ROOT}"
CONFIG="${ORGANISM_CONFIG:-${ROOT}/deploy/config/cpu_only.yaml}"
cd "$ROOT"
exec python -m organism_sdk serve --config "$CONFIG" "$@"
