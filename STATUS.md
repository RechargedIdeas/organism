# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.8.0 — Organism generative surfaces**  
**Corpus:** closed v0.1–v1.7.2 + v1.8.0 theme/multi/bundle/rollback  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.8.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.8.0)

## Verdict

**v1.8.0** adds production Organism self-evolution surfaces on top of the v1.7
generative stack: Desktop theme apply from looks, ModuleRegistry deregister on
code rollback, multi-Organism create/switch, and export/import bundles
(JSON+assets zip). Bio/wet-lab actuation remains hard-refused. CPU Everywhere
holds. Hybrid Studio still not imported. Naming is **Organism** only.

## v1.8.0 phase table

| Phase | Status | Notes |
|---|---|---|
| **S0** Looks promote → Desktop theme apply | **green** | shell accents via QSS; offscreen CI safe |
| **S1** Rollback deregisters GeneratedSkillModule | **green** | after_rollback → ModuleRegistry.deregister |
| **S2** Multi-Organism store + Evolution panel | **green** | create/switch + `_active.json` |
| **S3** Export/import Organism bundle | **green** | organism_bundle_v1 zip |
| **S4** Tests + docs | **green** | SDK + Desktop suites |
| **S5** Release | **green** | tag **v1.8.0** |

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only |
| Production WAN BFT + TPM | multi-process / multi-node software stubs only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling — **not** imported |
| Hosted LLM provider | optional; default backends are offline stubs |

**Default pytest:** **329 passed**, 0 skipped, 2 slow deselected.

## Tooling

```bash
PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  .venv/bin/python -m organism_desktop --smoke
organism-desktop
```
