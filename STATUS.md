# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.4.0 — Ops Completeness**  
**Corpus:** closed v0.1–v1.3 + v1.4 ops  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.4.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.4.0)

## Verdict

Software Organism complete through CPU Everywhere (v1.3). **v1.4** ships every
software-possible ops item: single-device deploy, soak runbook, optional torch
policy, wet-lab HAL stub with deny-by-default SafetyPolicy.

## v1.4 phase table

| Phase | Status | Notes |
|---|---|---|
| **P1** Deploy profile | **green** | `deploy/`, CLI serve/status, `v14:deploy` |
| **P2** Soak ops | **green** | SOAK_RUNBOOK + `soak_target.sh`, `v14:soak_ops` |
| **P3** Torch optional | **green** | CUDA only when opted in; `ORGANISM_TORCH=0` |
| **P4** Wet-lab stub | **green** | SafetyPolicy + sim loop; no real GPIO required |
| **P5** Release | **green** | tag **v1.4.0** |

**Default pytest:** **209 passed**, 0 skipped, 2 slow deselected.

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Real bioreactor GPIO / wet-lab hardware | Stub + policy only; needs silicon + certified policy |
| Production WAN BFT + TPM | multi-process software only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling (VENDOR.md) |
| CUDA / ROCm / Metal | **optional prefer**; CPU always works |

## Tooling

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk serve \
  -c deploy/config/cpu_only.yaml --dry-run
./scripts/soak_target.sh
```

## Prior lines

v1.3.0 CPU Everywhere. v1.2.0 live Hybrid. v1.1.0 Hybrid mapping. v1.0.0 A–H.
