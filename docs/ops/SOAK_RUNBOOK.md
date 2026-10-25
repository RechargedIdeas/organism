# Organism soak / target-box runbook (v1.4)

**Purpose:** Prove stability and retune `docs/v0.4/PERF.md` budgets on the
machine you actually deploy to. CI keeps the **fast** soak path; full soak is
opt-in.

## Fast path (CI / every PR)

```bash
cd /path/to/organism
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  sdk/python/tests/test_v04_soak.py -m 'not slow'
```

- Virtual clock, ~24–40 windows, GC-bounded bindings, reconstructible routing
  traces, no flapping assertion.
- Gate: `v04:soak` (blocking).

## Full soak (target box)

```bash
./scripts/soak_target.sh           # default: fast + full soak markers
# or:
ORGANISM_SOAK_FULL=1 ORGANISM_WALL_CLOCK_FULL=1 \
  PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  sdk/python/tests/test_v04_soak.py sdk/python/tests/test_wall_clock_slo.py
```

| Env | Effect |
|---|---|
| `ORGANISM_SOAK_FULL=1` | Enables `@pytest.mark.slow` extended soak (240 windows) |
| `ORGANISM_WALL_CLOCK_FULL=1` | Enables ~480s Category I wall-clock physiology |
| `ORGANISM_SOAK_WINDOWS=N` | Override extended window count (harness reads if set) |
| `ORGANISM_SOAK_MAX_BINDINGS=N` | Override GC binding cap |

## What “green” means

1. No degradation flapping (L0↔L1 flip-flops ≤ 2).
2. `binding_count_final ≤ max_bindings + slack`.
3. Routing + degradation traces reconstructible (`routing_trace_count ≥ plans`).
4. `hormone_state` remains queryable after every window.
5. Fast wall-clock gates still pass; full 480s is opt-in evidence only.

## Retuning PERF.md

1. On the target box, run:

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  sdk/python/tests/test_v04_perf.py -s
```

2. Record p50/p95 from the test output / logs into a dated row under
   **Measured baseline** in `docs/v0.4/PERF.md`.
3. Budgets should stay ~50–100× above measured p95 so CI noise does not flake.
4. Only tighten budgets after ≥3 consecutive target-box runs agree.
5. Never raise budgets silently — document the box ID / CPU model in PERF.md.

## Memory / reconstructibility

The soak harness (`harness/scenarios/v04_soak.py`):

- Caps ephemeral bindings via `WorkspaceClient.gc_ephemeral(max_bindings=…)`.
- Emits routing + degradation traces for every plan / transition.
- Returns `SoakResult` with peak/final binding counts and flap detection.

Gate for this runbook’s ops script: `v14:soak_ops`.
