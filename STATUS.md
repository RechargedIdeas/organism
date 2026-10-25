# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.5.2 — Desktop polish + CLI parity**  
**Corpus:** closed v0.1–v1.4 + v1.5 desktop  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.5.2](https://github.com/RechargedIdeas/organism/releases/tag/v1.5.2)

## Verdict

**v1.5.2** polishes Organism Desktop and locks **CLI ↔ Desktop status parity**:
Home/Ops show live CPU Everywhere + deploy/soak facts; shortcuts and toasts;
e2e + refresh soak tests. Bio/wet-lab actuation remains hard-refused.

## v1.5 phase table

| Phase | Status | Notes |
|---|---|---|
| **D0** Design | **green** | `docs/v1.5/DESKTOP.md`, `PLAN.md` |
| **D1** DesktopService | **green** | headless SDK façade |
| **D2** PySide6 shell + 10 panels | **green** | offscreen smoke |
| **D3** Pipeline + bio refuse | **green** | `v15:desktop` |
| **D4** Packaging | **green** | `[desktop]` extra, `organism-desktop` |
| **D5** Release | **green** | tag **v1.5.0** |
| **D6** Panel deepen + tests | **green** | tag **v1.5.1** |
| **D7** Polish + CLI parity | **green** | tag **v1.5.2** |

**Stack:** PySide6 6.12 (primary). NiceGUI documented as fallback only.

**Default pytest:** **249 passed**, 0 skipped, 2 slow deselected.

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
organism-desktop
```
