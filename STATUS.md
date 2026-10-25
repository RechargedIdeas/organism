# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.7.2 — Generative Runtime Integration**  
**Corpus:** closed v0.1–v1.7.1 + v1.7.2 runtime wiring  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.7.2](https://github.com/RechargedIdeas/organism/releases/tag/v1.7.2)

## Verdict

**v1.7.2** integrates Organism generative evolution into the live runtime:
CodePipeline promote hot-registers generated skill/code modules into
`ModuleRegistry` through a shadow gate; evolution events emit
`EvolutionTraceEntry`; optional hormone pulse on promote; ImmuneLayer
quarantine demotes drafts that fail contracts; wall-clock budgets gate the
pipeline; Desktop e2e covers evolve → improve-from-trace → promote → catalog.
Bio/wet-lab actuation remains hard-refused. CPU Everywhere holds. Hybrid Studio
still not imported. Naming is **Organism** only.

## v1.7.2 phase table

| Phase | Status | Notes |
|---|---|---|
| **R0** Promote → ModuleRegistry hot-register | **green** | shadow gate SANDBOXED→SHADOW_VALIDATED→EXPLORATION |
| **R1** Evolution traces + hormone pulse | **green** | `EvolutionTraceEntry` · optional dopamine/oxytocin |
| **R2** Immune quarantine demote | **green** | failed contracts → QUARANTINE → demote |
| **R3** Desktop e2e catalog | **green** | evolve → improve → promote → dynamic catalog |
| **R4** Wall-clock budgets | **green** | evolve/promote/hot-register/quarantine P95 |
| **R5** Release | **green** | tag **v1.7.2** |

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only |
| Production WAN BFT + TPM | multi-process / multi-node software stubs only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling — **not** imported |
| Hosted LLM provider | optional; default backends are offline stubs |

**Default pytest:** **319 passed**, 0 skipped, 2 slow deselected.

## Tooling

```bash
PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  .venv/bin/python -m organism_desktop --smoke
organism-desktop
```
