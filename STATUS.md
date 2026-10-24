# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.0.0 — software Organism COMPLETE**  
**Corpus:** closed v0.1–v0.4 + v1.0 completion (Phases A–H)  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.0.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.0.0)

## Verdict

**COMPLETE** for the software Organism. Remaining gaps require **real silicon / wet lab / WAN-BFT infrastructure** (external). Faithful simulators ship as `RESEARCH_SIM`.

## v1.0 phase table

| Phase | Status | SHA / notes |
|---|---|---|
| **A** Plan | **green** | `docs/v1.0/PLAN.md` |
| **B** Substrate ecology | **green** | kernel, hdc, reservoir, energy_hopfield, spectral, neurosymbolic |
| **C** Learned control | **green** | RL-DCA loop; ISE promote+revoke; live NAS |
| **D** Distributed | **green** | multi-process; oxytocin ≥3; BFT f=1 N=4; clock skew |
| **E** Hardware sims | **green** | `ORGANISM_NEURO_SIM=1`; physical_research non-actuation |
| **F** Rust parity | **green** | router + degradation; cargo test --workspace |
| **G** Hardening docs | **green** | API_FREEZE_v1.0, HARDENING, CHANGELOG, gates, versions 1.0.0 |
| **H** Release | **green** | annotated tag `v1.0.0` + GitHub Release |

**Default pytest:** 135 passed (2 slow deselected).  
**Rust:** `cargo test --workspace` green.

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon (Loihi-class) | No HW on box; RESEARCH_SIM via env |
| Wet-lab / molecular physical substrates | Exploration module only; never control path |
| Production WAN BFT + TPM attestation | In-process/multi-process software BFT-ish only |

## Amendments (IMP-*)

| ID | Topic | Resolution |
|---|---|---|
| IMP-22 | contract_factory | Shared helper for reference substrates |
| IMP-23 | neuro_sim | `ORGANISM_NEURO_SIM` merges NEUROMORPHIC caps |
| IMP-24 | ProcessCluster | OS processes + lag SLO; not WAN |
| IMP-25 | Rust router/degradation | Core path parity; Python remains primary authoring surface |

## Tooling

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
cargo test --workspace
# Opt-in: ORGANISM_WALL_CLOCK_FULL=1 | ORGANISM_SOAK_FULL=1 | ORGANISM_NEURO_SIM=1
```

## Prior lines (summary)

v0.1 M1–M7, v0.2 G–J + F J–O, v0.3 M0–M4, v0.4 soak/perf/security + freeze — all remain green under the v1.0 suite. See git history and `docs/v0.*/`.
