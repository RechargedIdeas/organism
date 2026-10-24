# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Corpus:** closed v0.1 + biological extension (Artifacts G–J / F J–O)  
**Repo:** https://github.com/RechargedIdeas/organism (private)

## Milestone summary

| Milestone | Status | Notes |
|---|---|---|
| Batch 1 / Proto | **green** | Additive v0.2 lifecycle enums in `common.proto` |
| **M1–M7** (v0.1) | **green** | Unchanged; suite still green |
| Wall-clock fast / `perf:slo` | **green** | Opt-in full 480s unchanged |
| **v0.2 G** HormoneBus + ISE | **green** | Workspace SoT; bus mirror; `emit_hormone` real |
| **v0.2 H** ImmuneLayer | **green** | FULL/affects_control bindings only; `emit_immune` |
| **v0.2 I** Autonomic + Apoptosis | **green** | Param modulation; SELF_TERMINATING/SUCCEEDED/DEVELOPMENT |
| **v0.2 J** Circadian / morphogenesis / metabolism | **green** | Stubs + rest-cycle exploration gate |
| **F J–O subset** | **green** | J1,K1,L1,M1,N2,O1,O4 runnable |

**Full suite (default):** `PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q tests/contract sdk/python/tests modules/*/tests tests/integration -m 'not slow'` → **73 passed** (1 slow deselected).

---

## v0.2 — Biological extension (runtime)

Structural answers from `docs/v0.2/STRUCTURAL_ANSWERS.md` adopted exactly.

| Organ | Module | Trace |
|---|---|---|
| HormoneBus | `organism_sdk/hormone.py` | `emit_hormone` + Decision Trace `rationale.hormone` |
| ISE | `organism_sdk/interoceptive.py` | workspace `interoceptive_state` |
| ImmuneLayer | `organism_sdk/immune.py` | `emit_immune` + `immune_decision` bindings |
| AutonomicController | `organism_sdk/autonomic.py` | `emit_autonomic`; router `set_autonomic_params` |
| Apoptosis | `organism_sdk/apoptosis.py` | DeathCertificate bindings; AP-1..5 |
| CircadianClock | `organism_sdk/circadian.py` | exploration_budget gate |
| Morphogenesis | `organism_sdk/morphogenesis.py` | DEVELOPMENT ⊂ EXPLORATION |
| Kleiber share | `kleiber_declared_share` | O5 inefficiency flag |

### Invariants enforced in tests
- G/K: SoT write → mirror consistency; staleness_ms; workspace fallback; shield non-override
- H/L: FULL + affects_control; no `deregister`; memory hit; cortisol → quarantine
- I/M/N: router sole dispatcher; T0 never self-terminates; control-affecting needs successor
- J/O: stage fail retains prior; rest suppressed in crisis; circadian scales exploration

### Proto (additive)
`ModuleLifecycleState` += `SELF_TERMINATING`, `SUCCEEDED`, `DEVELOPMENT`, `DEGRADED` (values 8–11). Proto regen green (`grpc_tools.protoc` + `cargo build -p organism-proto`; `make` optional when available).

### Amendments (IMP-*)
| ID | Topic | Resolution |
|---|---|---|
| IMP-5..7 | Wall-clock | Prior (v0.1) |
| IMP-8 | BindingRecord payload / affects_control | Additive fields for hormone/immune/death cert payloads; snapshot serialize |
| IMP-9 | `Lifecycle.self_termination_permitted` | Python contract field; proto Lifecycle message unchanged this cut |
| IMP-10 | `Hypervector.random(seed=)` | Deterministic HV for organs/tests |

### Gates
`ci/gates.yaml`: `v02:hormone`, `v02:immune`, `v02:autonomic_apoptosis`, `v02:morphogenesis_circadian`, `v02:harness_jo` — **blocking: true**, status green. `category_bio` J1/K1/L1/M1/N2/O1/O4 green.

### Remaining gaps (clean boundaries)
- Full Category K3–K6 / L3–L6 / M2–M4 / N1/N4/N5 / O2–O5 beyond subset (partially covered in unit tests; not all harness IDs)
- Hormone consensus / federated oxytocin
- Learned ISE / RL-DCA
- Full HormoneBus multi-node mirror lag simulation
- DeathCertificate successor shadow-validate promotion path (API present; limited scenarios)
- Metamodel developmental synthesizer (tracker only)
- Distributed / SNN hardware paths still E.8 out of scope

### Tooling
```bash
PYTHON=.venv/bin/python
make proto PYTHON=.venv/bin/python
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  tests/contract sdk/python/tests modules/deterministic_engine/tests \
  modules/learned_module/tests tests/integration -m 'not slow'
```
