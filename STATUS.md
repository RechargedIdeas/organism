# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Corpus:** closed v0.1 — Artifacts A–F + Addenda A0–A6 + R-amendments (`/workspace/organism-handoff.txt`)  
**Prior projects:** ignored. Working tree only (no commit required).

## Milestone summary

| Milestone | Status | Notes |
|---|---|---|
| Batch 1 / Proto | **green** | `make proto PYTHON=.venv/bin/python`; cargo check |
| **M1** SDK + deterministic_engine | **green** | contract validate; engine registers; health probe |
| **M2** Registry + workspace (in-memory) | **green** | Python + Rust; HV DIM=10000; bind/unbind exactness |
| **M3** Router + DispatchPlan | **green** | form mapping, tier lattice, level gating, determinism |
| **M4** learned_module + cross-check | **green** | T2 + conformal; KERNEL_BOUND for control_actuation/high |
| **M5** Ops log + snapshot + replay | **green** | SQLite WAL + content-addressed snapshots; replay |
| **M6** Degradation + fault injection | **green** | B.6 subset + no-flapping (virtual clock) |
| **M7** Full CI + two-module bootstrap | **green** | gates.yaml; e2e bootstrap; Category I green-pending |

**Full suite:** `PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q tests/contract sdk/python/tests modules/*/tests tests/integration` → **41 passed**.

---

## M1 — green

### Exit criteria
- [x] Contract compiles (`to_proto()` + validate)
- [x] Deterministic engine registers
- [x] Health probe responds
- [x] `contract:validate` green

### Key paths
- `sdk/python/organism_sdk/` — contract, module, inputs, workspace, registry, trace, health, justification, hypervector, errors, snapshot, router, degradation
- `modules/deterministic_engine/engine.py` — T0 / RULE_TRACE
- Tests: `sdk/python/tests/`, `modules/deterministic_engine/tests/`, `tests/contract/`

### Test command
```bash
PYTHONPATH=sdk/python:modules .venv/bin/python -m pytest -q \
  sdk/python/tests modules/deterministic_engine/tests tests/contract
```

### Amendments
| ID | Topic | Resolution |
|---|---|---|
| IMP-1 | OQ-1 vs REG-9 probe timing | T0 uses `probe_interval_ms=1000`, `timeout_ms=400`, `degraded_duration_ms=5000` |
| IMP-2 | TraceEmitter pre-router | Stub emits null policy fields until `attach_router_state`; then SDK-6 strict |
| IMP-3 | Rule-trace signature | SHA-256 placeholder; ed25519 deferred (key registry) |

---

## M2 — green

### Exit criteria
- [x] register / query / promote round-trip
- [x] workspace bind/unbind exactness
- [x] Hypervector binary DIM=10000 (`[u64;157]` packing, LE-per-word — IMP-4)

### Key paths
- Python: `organism_sdk/registry.py`, `workspace.py`, `hypervector.py`
- Rust: `sdk/rust/organism-client`, `runtime/workspace`, `runtime/registry`
- Tests: `sdk/python/tests/test_m2_registry_workspace.py`, `test_hypervector.py`; cargo tests on workspace/registry/client

### Amendments
| ID | Topic | Resolution |
|---|---|---|
| IMP-4 | HV bit packing endianness | BE truncate dropped last-word bits; **LE-per-word** packing in Rust + Python so all 10000 bits round-trip |

---

## M3 — green

### Exit criteria
- [x] form mapping
- [x] tier lattice
- [x] level gating
- [x] determinism for `router:decision`

### Key paths
- `sdk/python/organism_sdk/router.py` — Artifact C decision tree; `RoutingTraceEntry`
- Tests: `sdk/python/tests/test_router_m3.py`

### Notes
Python in-process router for M3 (Rust router crate deferred; exit criteria met). At L2+ emits `DegradedDispatchPlan`.

---

## M4 — green

### Exit criteria
- [x] learned_module registers with conformal calibration
- [x] KERNEL_BOUND justification works for `control_actuation` at high

### Key paths
- `modules/learned_module/module.py` — T2
- Cross-check / KERNEL_BOUND verifier path in SDK justification + module tests
- Tests: `modules/learned_module/tests/`

---

## M5 — green

### Exit criteria
- [x] `workspace:replay` green
- [x] snapshot integrity
- [x] dimension mismatch rejected
- [x] crash recovery via WAL + snapshot replay

### Key paths
- `sdk/python/organism_sdk/snapshot.py` — DurableWorkspace, SQLite WAL ops log, content-addressed snapshots
- Tests: `sdk/python/tests/test_workspace_m5.py`

---

## M6 — green

### Exit criteria
- [x] B.6 matrix subset green (L0→L1 kill, L1→L2 fail, L3→L4 trace/byzantine)
- [x] no-flapping assertion green (T_up hysteresis via virtual clock)

### Key paths
- `sdk/python/organism_sdk/degradation.py` — B.3 + A0.1 (−δ) state machine
- `harness/scenarios/m6_faults.py` — FaultInjector + scenarios
- Tests: `sdk/python/tests/test_degradation_m6.py`

### Amendments
| ID | Topic | Resolution |
|---|---|---|
| IMP-5 | Virtual-clock hysteresis | Wall-clock 480s E-5 1b exercised via virtual clock; `perf:slo` and Category I wall-clock remain **green-pending** |
| IMP-6 | Timer `0.0` falsy | `_cond_since` used `x or now`; `0.0` falsy → never confirmed. Fixed explicit `is None` check |
| IMP-7 | AND/OR short-circuit arming | `_all_sustained` / `_any_confirmed` evaluate all specs before combining so parallel timers arm together |

### A0.1 applied
Calibration triggers use `c_m < 1 − α − δ_k` (not `+ δ`).

---

## M7 — green (Category I: green-pending as specified)

### Exit criteria
- [x] E.5 gates defined in `ci/gates.yaml`
- [x] Two-module bootstrap: `deterministic_engine` + `learned_module_t2`
- [x] e2e replay zero mismatches
- [x] Category I scenarios documented green-pending (wall-clock SLO)

### Key paths
- `ci/gates.yaml`
- `tests/integration/test_e2e_bootstrap_m7.py`
- `harness/scenarios/m6_faults.py`

### Test command
```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q tests/integration
# + degradation:transitions gate
```

### Blocking gates (all runnable locally)
`proto:lint`, `contract:validate`, `registry:api`, `workspace:unit`, `workspace:replay`, `router:decision`, `router:determinism`, `degradation:transitions`, `trace:replay`, `integration:e2e`  
Non-blocking: `perf:slo` (green-pending)

---

## OpenQuestions
- None blocking v0.1 reference path. Wall-clock `perf:slo` deferred (IMP-5).

## E.8 respected
No distributed, metamodel, SNN dispatch, real-valued HV, learned meta-router, federation, graph queries, or concurrent batch writers.

## Tooling
```bash
PYTHON=.venv/bin/python
make proto PYTHON=.venv/bin/python
make python-install PYTHON=.venv/bin/python
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  tests/contract sdk/python/tests modules/deterministic_engine/tests \
  modules/learned_module/tests tests/integration
```
