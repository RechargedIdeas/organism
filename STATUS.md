# Organism — Implementation Status

**Date:** 2026-10-25 (America/New_York)  
**Release:** **v1.9.0 — Audit closure / generative production bar**  
**Corpus:** closed v0.1–v1.8.1 + v1.9.0 audit software items  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.9.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.9.0)  
**Tip:** 

## Verdict

**v1.9.0** closes the software-fixable backlog from
[docs/AUDIT_v1.8.md](docs/AUDIT_v1.8.md) (see
[docs/v1.9/AUDIT_CLOSURE.md](docs/v1.9/AUDIT_CLOSURE.md)): GitHub Actions + v18/v19
gates, HostedLLMBackend (env-gated), sandbox process jail, ImageBackend, generative
CLI, thicker Physiology/ISE/Ops Desktop, Rust control_loop tick, packaging `.spec`,
docs sync. Bio/wet-lab actuation remains hard-refused. CPU Everywhere holds.
Naming is **Organism** only.

Generative/Desktop wave + audit residuals are closed for software. Remaining
**hard external** deps stay silicon / wet-lab HW / production WAN / Hybrid Studio /
hosted LLM provider account.

## Soak / wall-clock cadence

- Default CI / pytest: `-m 'not slow'` (fast soak + budgets).
- Full soak: `ORGANISM_SOAK_FULL=1` on a target box per [docs/ops/SOAK_RUNBOOK.md](docs/ops/SOAK_RUNBOOK.md).
- Category I ~480s: `ORGANISM_WALL_CLOCK_FULL=1` (opt-in only).

## v1.9.0 phase table

| Phase | Status | Notes |
|---|---|---|
| **P0** GitHub Actions + gates | **green** | `.github/workflows/ci.yml` |
| **P1** Generative production bar | **green** | HostedLLM + sandbox jail + CLI |
| **P1** Desktop physiology depth | **green** | immune/autonomic/circadian/apoptosis/ISE |
| **P2** Assets / Rust / packaging / Docker | **green** | ImageBackend, control_loop, `.spec` |
| **P3** Docs / templates / replay / HV | **green** | audit links, 10 templates, Draft Replay |
| **P4** Release | **green** | tag **v1.9.0** |

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
organism-desktop
```
