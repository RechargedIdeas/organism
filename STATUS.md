# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.8.1 — Organism generative polish**  
**Corpus:** closed v0.1–v1.8.0 + v1.8.1 badge/path/soak  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.8.1](https://github.com/RechargedIdeas/organism/releases/tag/v1.8.1)

## Verdict

**v1.8.1** polishes the Organism generative Desktop surfaces: visible bundle
export/import path feedback, Active Organism badge in the shell header, and a
generative evolve→promote→rollback soak (no registry leak). Bio/wet-lab
actuation remains hard-refused. CPU Everywhere holds. Hybrid Studio still not
imported. Naming is **Organism** only.

Meaningful *software* gaps from the generative/Desktop wave are closed for that wave's scope. A fuller residual software backlog (CI, docs drift, generative production bar, Desktop/SDK depth) is in [docs/AUDIT_v1.8.md](docs/AUDIT_v1.8.md). Remaining **hard external** deps stay silicon / wet-lab HW / production WAN.

## v1.8.1 phase table

| Phase | Status | Notes |
|---|---|---|
| **P0** Bundle round-trip Desktop path feedback | **green** | path edit + feedback label |
| **P1** Active Organism shell badge | **green** | `shell_organism_badge` |
| **P2** Generative soak (evolve/promote/rollback) | **green** | offscreen + service |
| **P3** Tests + docs | **green** | SDK + Desktop suites |
| **P4** Release | **green** | tag **v1.8.1** |

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only |
| Production WAN BFT + TPM | multi-process / multi-node software stubs only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling — **not** imported |
| Hosted LLM provider | optional; default backends are offline stubs |

**Default pytest:** **334 passed**, 0 skipped, 2 slow deselected.

## Tooling

```bash
PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  .venv/bin/python -m organism_desktop --smoke
organism-desktop
```
