# Organism v1.0 — Hardening & opt-in long runs

**Date:** 2026-10-24 (America/New_York)

## Default CI (blocking)

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
cargo test --workspace
```

Includes Category I **fast** wall-clock / `perf:slo`, soak fast path, security fuzz, biological matrix, v1.0 substrate/distributed/learned-control tests.

## Opt-in full wall-clock (Category I 480s)

```bash
ORGANISM_WALL_CLOCK_FULL=1 PYTHONPATH=sdk/python:modules:. \
  .venv/bin/python -m pytest -q sdk/python/tests/test_wall_clock_slo.py
```

Asserts real hysteresis / physiology windows. Gate id: `e5_1b_wall_clock_480s` (green-pending-opt-in → documented complete).

## Opt-in full soak

```bash
ORGANISM_SOAK_FULL=1 PYTHONPATH=sdk/python:modules:. \
  .venv/bin/python -m pytest -q sdk/python/tests/test_v04_soak.py
```

## Neuromorphic RESEARCH_SIM

```bash
ORGANISM_NEURO_SIM=1  # Router admits NEUROMORPHIC; SNN may dispatch wake path
```

Default without the env var: SNN excluded with `hardware_capability_missing`.

## Category I assertions (summary)

| ID | Default | Full |
|---|---|---|
| Router/workspace/hormone/degradation perf budgets | blocking | — |
| Wall-clock fast hysteresis | blocking | — |
| Wall-clock 480s | deselected | `ORGANISM_WALL_CLOCK_FULL=1` |
| Soak multi-window | blocking (fast) | `ORGANISM_SOAK_FULL=1` |
