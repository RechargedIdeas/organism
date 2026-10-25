# Organism v1.4 — Ops Completeness

**Date:** 2026-10-24 (America/New_York)  
**Goal:** Ship everything software-possible after v1.3: deploy profile, soak
runbook, optional torch accelerator clarity, wet-lab HAL stub + safety policy.
**Tag target:** `v1.4.0`

## Order (blocking)

| Phase | Deliverable | Gate |
|---|---|---|
| **P1** | Single-device CPU-only deploy (`deploy/`, CLI `serve`/`status`) | `v14:deploy` |
| **P2** | Soak / target-box runbook + `scripts/soak_target.sh` | `v14:soak_ops` |
| **P3** | Torch as optional accelerator (CUDA prefer + opt-in; CPU default) | `cpu:everywhere` + docs |
| **P4** | Wet-lab HAL stub + SafetyPolicy (no real GPIO in default) | `v14:wetlab` |
| **P5** | Docs / CHANGELOG / STATUS / tag **v1.4.0** | release |

## Explicitly out of scope

- PySide6 studio / OpenGL editor into Organism
- Claiming real neuromorphic silicon
- Real bioreactor GPIO as a dependency of the default suite

## Success

Default pytest ≥ 182 passed (grow suite). Push after each phase. Never force-push.
