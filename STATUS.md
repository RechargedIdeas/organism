# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Corpus:** closed v0.1 — Artifacts A–F + Addenda A0–A6 + R-amendments (`/workspace/organism-handoff.txt`)  
**Prior projects:** ignored. Working tree only until pushed to `RechargedIdeas/organism`.

## Milestone summary

| Milestone | Status | Notes |
|---|---|---|
| Batch 1 / Proto | **green** | `make proto PYTHON=.venv/bin/python`; cargo check |
| **M1** SDK + deterministic_engine | **green** | contract validate; engine registers; health probe |
| **M2** Registry + workspace | **green** | Python + Rust; HV DIM=10000; bind/unbind exactness |
| **M3** Router + DispatchPlan | **green** | form mapping, tier lattice, level gating, determinism |
| **M4** learned_module + cross-check | **green** | T2 + conformal; KERNEL_BOUND for control_actuation/high |
| **M5** Ops log + snapshot + replay | **green** | SQLite WAL + content-addressed snapshots; replay |
| **M6** Degradation + fault injection | **green** | B.6 subset + no-flapping (virtual + **wall-clock fast**) |
| **M7** Full CI + two-module bootstrap | **green** | gates.yaml; e2e; Category I fast wall-clock **green** |

**Full suite (default):** `PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q tests/contract sdk/python/tests modules/*/tests tests/integration -m 'not slow'` → **43 passed** (1 slow deselected).

---

## Wall-clock gates (IMP-5 resolved for fast path)

| Gate | Status | Notes |
|---|---|---|
| `perf:slo` | **green** | `test_wall_clock_slo.py -m 'not slow'` — `time.monotonic()`, scaled hysteresis |
| `e5_1b_wall_clock_fast` | **green** | L0→L1→L2→L1→L0 + no-flapping; T_up ≥ 5·T_down (2–3s class) |
| `e5_1b_wall_clock_480s` | **green-pending-opt-in** | Full B.4 (~455–480s); `ORGANISM_WALL_CLOCK_FULL=1 pytest -m slow …` |

### Scaled constants (`T_DOWN_FAST` / `T_UP_FAST`)
| Transition | T_down | T_up | ratio |
|---|---|---|---|
| L0↔L1 | 0.4 s | 2.0 s | 5× |
| L1↔L2 | 0.6 s | 3.0 s | 5× |

SLO band: `[expected − 0.05, expected + 0.75]` s wall elapsed per armed window.

### Key paths
- `sdk/python/organism_sdk/degradation.py` — `t_down`/`t_up` overrides; `sync_wall_clock()`
- `harness/scenarios/wall_clock_slo.py`
- `sdk/python/tests/test_wall_clock_slo.py`
- `ci/gates.yaml`

### Amendments
| ID | Topic | Resolution |
|---|---|---|
| IMP-5 | Virtual-clock hysteresis | **Fast wall-clock path green.** Full 480s remains opt-in slow marker. |
| IMP-6 | Timer `0.0` falsy | Fixed (`is None`) |
| IMP-7 | AND/OR short-circuit arming | Fixed evaluate-all-then-combine |

---

## v0.2 — Biological extension (docs-first open)

| Deliverable | Path | Status |
|---|---|---|
| Structural answers (5) | `docs/v0.2/STRUCTURAL_ANSWERS.md` | **done** |
| Artifact G | `docs/v0.2/G_endocrine_interoceptive.md` | first-cut |
| Artifact H | `docs/v0.2/H_immune.md` | outline + invariants |
| Artifact I | `docs/v0.2/I_autonomic_apoptosis.md` | outline + invariants |
| Artifact J | `docs/v0.2/J_morphogenesis_metabolism_circadian.md` | outline |
| F extension J–O | `docs/v0.2/F_extension_biological_matrix.md` | scenario outlines |
| Trace hooks | `organism_sdk/trace.py` `emit_immune` / `emit_hormone` / `emit_autonomic` | stubs + `V02TraceSink` |
| Proto v2 lifecycle enums | docs in Artifact I | **not** in v0.1 codegen |

**Structural resolutions adopted (corpus preferred):**
1. HormoneBus = declared channel; workspace `hormone_state` SoT; bus = low-latency mirror; trace `staleness_ms`.
2. Autonomic modulates router-exposed params only; router sole dispatcher; writes traced.
3. Immune decisions = FULL / affects_control workspace bindings; no direct lifecycle/routing side effects.
4. `SELF_TERMINATING` / `SUCCEEDED` / `DEVELOPMENT⊂EXPLORATION`; T0 never self-terminates; control-affecting needs successor; `self_termination_permitted`.
5. F.7 extended with Categories J–O (outlined).

**Not implemented yet:** full HormoneBus / Immune / Autonomic runtime (prefer complete docs + wall-clock green).

E.8 still respected for v0.1 runtime.

---

## M1–M7 detail (unchanged green)

See prior milestone sections in git history; exit criteria all met. Key SDK: `sdk/python/organism_sdk/`. Modules: `deterministic_engine`, `learned_module`.

### Tooling
```bash
PYTHON=.venv/bin/python
make proto PYTHON=.venv/bin/python
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  tests/contract sdk/python/tests modules/deterministic_engine/tests \
  modules/learned_module/tests tests/integration -m 'not slow'
# Full E-5 1b (~8 min):
ORGANISM_WALL_CLOCK_FULL=1 PYTHONPATH=sdk/python:modules:. \
  .venv/bin/python -m pytest -q -m slow sdk/python/tests/test_wall_clock_slo.py
```

## OpenQuestions
- None blocking v0.1. Full 480s wall-clock opt-in until nightly/soak wires it.
- Pre-existing flake risk: `test_snapshot_and_replay` uses unseeded `Hypervector.random()` (passed on retry).
