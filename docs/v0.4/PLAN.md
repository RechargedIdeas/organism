# Organism v0.4 — Hardening Plan

**Date:** 2026-10-24 (America/New_York)  
**Corpus base:** closed v0.1 + v0.2 biological + v0.3 E.8 lifts (M0–M4)  
**Repo:** https://github.com/RechargedIdeas/organism  
**Prior HEAD at open:** `df38255` (~101 tests green)

## Goal

Production-grade **hardening** of the single-box Organism stack: soak/stability, measured perf budgets, and security fuzz against the trust model and fault matrix — without lifting remaining E.8 hardware/cluster research items onto the control path.

## Optimal dependency order (do not reorder)

| ID | Milestone | Depends on | Exit criteria |
|---|---|---|---|
| **M0** | Plan + STATUS | — | This document + STATUS.md v0.4 section |
| **v0.4-M1** | Soak harness | M0 | Multi-window control loop (register → route → hormone → degrade → GC); no flapping; workspace queryable; binding-count/GC proxy bounded; decision traces reconstructible; fast CI soak + `@pytest.mark.slow` opt-in |
| **v0.4-M2** | Perf budgets | M1 | Router p50/p95, workspace bind/unbind/query, hormone window publish, degradation transition confirm under virtual clock; `docs/v0.4/PERF.md` + `ci/gates.yaml` `perf:*` entries |
| **v0.4-M3** | Security fuzz | M2 | Malformed contracts rejected; untrusted learned control_actuation without justification rejected; Byzantine → L3–L4 / cross-check path; capability-scope violations; immune quarantine forgery fails without FULL/affects_control; fixed-seed fuzz for CI |

## Explicitly still out of scope (unless thin-tested)

| Topic | v0.4 status |
|---|---|
| Real neuromorphic silicon | **OOS** — SNN sentinel remains hardware-gated (v0.3-M4) |
| Full BFT cluster / clock sync | **OOS** — multi-node stays in-process simulation |
| Live NAS / heavy hypernetwork training | **OOS** — metamodel stub + shadow only |
| Molecular / physical substrates | **Research-tier docs only** — never on control path |

Thin tests that *assert* these remain gated/fail-closed are allowed; implementing them is not.

## Design constraints (carry forward)

1. Workspace remains SoT; HormoneBus is mirror.
2. T0 never self-terminates; router is sole dispatcher.
3. Prefer thin vertical slices; keep prior 101+ tests green.
4. Never force-push; `git pull --rebase` before each push to `main`.
5. Virtual clock OK for CI soak/perf; wall soak via env flag only.

## Gates (additive)

| Gate id | Blocking | Milestone |
|---|---|---|
| `v04:plan` | docs | M0 |
| `v04:soak` | true | M1 |
| `perf:router` / `perf:workspace` / `perf:hormone` / `perf:degradation` | blocking where stable on this box; else non-blocking + baseline | M2 |
| `v04:security_fuzz` | true | M3 |

## Tooling

```bash
PYTHON=.venv/bin/python
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  tests/contract sdk/python/tests modules/deterministic_engine/tests \
  modules/learned_module/tests tests/integration -m 'not slow'
# Opt-in longer soak:
ORGANISM_SOAK_FULL=1 PYTHONPATH=... .venv/bin/python -m pytest -q -m slow sdk/python/tests/test_v04_soak.py
```
