# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.6.0 — Desktop explorer / inspector / multi-profile / catalog / contracts**  
**Corpus:** closed v0.1–v1.5 + v1.6 desktop surfaces  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.6.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.6.0)

## Verdict

**v1.6.0** deepens Organism Desktop into an operator control plane: filterable
**trace explorer** (export + jump), **router/plan inspector**, **multi-profile
deploy** (`cpu_only` ↔ `default`), **module catalog** with RESEARCH_TIER badges,
and a **contracts/assert** panel. Bio/wet-lab actuation remains hard-refused.
CPU Everywhere holds.

## v1.6 phase table

| Phase | Status | Notes |
|---|---|---|
| **E0** Trace explorer | **green** | table · export JSON · jump |
| **E1** Plan inspector | **green** | ranking_trace structured |
| **E2** Multi-profile | **green** | default.yaml + Ops switch |
| **E3** Module catalog | **green** | RESEARCH_TIER + register |
| **E4** Contracts panel | **green** | validate() last results |
| **E5** Packaging docs | **green** | PACKAGING.md · entry point |
| **E6** Release | **green** | tag **v1.6.0** |

Prior v1.5 D0–D7 remain green (see git history / CHANGELOG).

**Stack:** PySide6 (primary). NiceGUI documented as fallback only.

**Default pytest:** **269 passed**, 0 skipped, 2 slow deselected.

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only |
| Production WAN BFT + TPM | multi-process software only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling (VENDOR.md) — **not** imported |
| CUDA / ROCm / Metal | optional prefer; CPU always works |

## Tooling

```bash
PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  .venv/bin/python -m organism_desktop --smoke
organism status -c deploy/config/cpu_only.yaml
organism status -c deploy/config/default.yaml
organism-desktop
```
