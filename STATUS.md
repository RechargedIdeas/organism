# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.7.0 — Organism Generative Evolution**  
**Corpus:** closed v0.1–v1.6.1 + v1.7 generative code/assets/skills  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.7.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.7.0)

## Verdict

**v1.7.0** ships production-grade **generative code**, **asset (looks)**, and
**skills** pipelines so **Organisms** can self-evolve under Learned-ISE-style
promote gates. Desktop adds **Organism Evolution** (skills / looks / code
promotions / evolution log). Bio/wet-lab actuation remains hard-refused. CPU
Everywhere holds. Hybrid Studio still not imported.

## v1.7 phase table

| Phase | Status | Notes |
|---|---|---|
| **G0** Generative code pipeline | **green** | intent→draft→static→contract→sandbox→shadow→promote |
| **G1** Artifact store + provenance | **green** | `organism_data/artifacts/` |
| **G2** Asset / looks pipeline | **green** | avatar/skin/icon/theme + manifests |
| **G3** Skills registry | **green** | generate/improve/promote + metamodel hook |
| **G4** OrganismProfile identity | **green** | skills · appearance · revisions · log |
| **G5** Desktop Organism Evolution | **green** | 13 panels |
| **G6** Release | **green** | tag **v1.7.0** |

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only |
| Production WAN BFT + TPM | multi-process / multi-node software stubs only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling — **not** imported |
| Hosted LLM provider | optional; default backends are offline stubs |

**Default pytest:** **296 passed**, 0 skipped, 2 slow deselected.

## Tooling

```bash
PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  .venv/bin/python -m organism_desktop --smoke
organism-desktop
```
