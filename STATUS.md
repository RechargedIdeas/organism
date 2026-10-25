# Organism — Implementation Status

**Date:** 2026-10-25 (America/New_York)  
**Release:** **v1.10.0 — Bare metal first + native sandbox**  
**Corpus:** closed v0.1–v1.9.0 + v1.10.0 host portability / native sandbox  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.10.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.10.0)  

## Verdict

**v1.10.0** makes Organism **first-class on bare metal and VMs**. Docker is
**optional** (one backend under `container_generic`); main CI gates never need
it. A **native Organism sandbox** (`organism_sdk.sandbox`) jails child work and
supports self-containment for workers / generative / soak / federation children.
Bio/wet-lab actuation remains hard-refused. CPU Everywhere holds. Naming is
**Organism** only.

See [docs/v1.10/BARE_METAL_AND_SANDBOX.md](docs/v1.10/BARE_METAL_AND_SANDBOX.md).

## Soak / wall-clock cadence

- Default CI / pytest: `-m 'not slow'` (fast soak + budgets).
- Full soak: `ORGANISM_SOAK_FULL=1` on a target box per [docs/ops/SOAK_RUNBOOK.md](docs/ops/SOAK_RUNBOOK.md).
- Category I ~480s: `ORGANISM_WALL_CLOCK_FULL=1` (opt-in only).

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
