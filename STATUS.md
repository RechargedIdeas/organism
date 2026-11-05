# Organism — Implementation Status

**Date:** 2026-11-04 (America/New_York)  
**Release:** **v1.10.0 — Bare metal first + native sandbox** (latest tag). v1.11 is in progress and unreleased.  
**Corpus:** closed v0.1–v1.9.0 + v1.10.0 host portability / native sandbox  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.10.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.10.0)  
**Gap review:** [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md) lists what is fixed, what is open, and the decisions still needed.

## Verdict

**v1.10.0** makes Organism **first-class on bare metal and VMs**. Docker is
**optional** (one backend under `container_generic`); main CI gates never need
it. A **native Organism sandbox** (`organism_sdk.sandbox`) jails child work and
supports self-containment for workers / generative / soak / federation children.
Bio/wet-lab actuation remains hard-refused. CPU Everywhere holds. Naming is
**Organism** only.

See [docs/v1.10/BARE_METAL_AND_SANDBOX.md](docs/v1.10/BARE_METAL_AND_SANDBOX.md).

## v1.11 in progress: MoA layer

Phases 0 to 3 of the [upgrade plan](docs/UPGRADE_AND_EXPANSION_PLAN.md) are implemented
and tested, and Phase 5 has its rule-based part. See [docs/v1.11/MOA_LAYER.md](docs/v1.11/MOA_LAYER.md).

| Phase | Status | Notes |
|---|---|---|
| 0 Design record | done | Corrections to the plan recorded |
| 1 Experts and registration | done | Two reference experts; registry health works |
| 2 Capability scorer and shadow gate | done | Gate passes on the synthetic set (extraction 12/13, one known false positive) |
| 3 VSA aggregation, tiers T0 to T4, drills | done | Hysteresis and failure drills tested |
| 4 Synthesizer and router evolution | not started | Needs a routing-policy artifact and a learned backend (D1) |
| 5 Judge | not started | Needs a calibrated learned backend (D1) |
| 5 Guardrails and red team | done (rule-based) | Input and output guardrails with measured error rates. Red-team suite runs non-blocking, with three known misses |
| 6 Lifecycle and provenance | optional | Decision D4 |

Signed registration is available. Pass a `TrustStore` to `RegistryClient` to require an author
signature on registration and an approver signature on promotion. Without one, signatures are not
checked, which is the default. Production keys live with the approver, never in the repo or the agent's environment (decision S1, adopted 2026-11-04). Wiring the trust store into the deploy stack and the desktop app is still to do.

## Soak / wall-clock cadence

- Default CI / pytest: `-m 'not slow'` (fast soak + budgets).
- Full soak: `ORGANISM_SOAK_FULL=1` on a target box per [docs/ops/SOAK_RUNBOOK.md](docs/ops/SOAK_RUNBOOK.md).
- Category I ~480s: `ORGANISM_WALL_CLOCK_FULL=1` (opt-in only).
- Nightly: the local `nightly` tier (Windows Task Scheduler, 02:00), and a scheduled
  [`nightly.yml`](.github/workflows/nightly.yml) workflow on GitHub with an advisory dependency audit.

## Quality ratchets

| Ratchet | Count | Baseline |
|---|---|---|
| ruff | 1 | `ci/baselines/ruff.json` (intentional `exec` in the generative sandbox) |
| mypy (hand-written) | 59 | `ci/baselines/mypy.json` (breakdown in [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md)) |
| rustfmt | 0 | enforced |

`pytest -m 'not slow'` collects 591 tests. The pre-push fast tier runs 60 gates.

## v1.10.0 phase table

| Phase | Status | Notes |
|---|---|---|
| **A** Host portability (bare/vm/container_generic) | **green** | Docker optional |
| **B** Native sandbox runtime | **green** | rlimits + optional ns |
| **C** CLI / Desktop / CI / docs | **green** | `sandbox *`, Ops badges |
| **D** Release | **green** | tag **v1.10.0** |

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only |
| Production WAN BFT + TPM | multi-process / multi-node software stubs only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling — **not** imported |
| Hosted LLM provider account/network | optional client; default backends offline |

**NiceGUI** remote status page: explicitly out of scope (use `organism serve` or Desktop Ops).

## Tooling

```bash
PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  .venv/bin/python -m organism_desktop --smoke
organism sandbox self-check
organism-desktop
```

## Prior

v1.9.0 closed the software audit backlog (see
[docs/v1.9/AUDIT_CLOSURE.md](docs/v1.9/AUDIT_CLOSURE.md) and
[docs/AUDIT_v1.8.md](docs/AUDIT_v1.8.md)).
