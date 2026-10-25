# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.3.0 — CPU Everywhere**  
**Corpus:** closed v0.1–v1.2 + v1.3 CPU guarantee  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.3.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.3.0)

## Verdict

Software Organism complete (v1.0). Bio-Digital mapping (v1.1–v1.2). **v1.3** makes
CPU the universal minimum: every RESEARCH_SIM / GPU-labelled workload has a CPU
fallback that is default or auto-selected when accelerators are absent.

## v1.3 phase table

| Phase | Status | Notes |
|---|---|---|
| **D1** Device selection | **green** | `organism_sdk.device`; never hard-fail missing GPU |
| **D2** Bio wave twin NumPy | **green** | same diffusion math; no torch skip |
| **D3** SNN CPU RESEARCH_SIM | **green** | `neuromorphic_cpu_backend` |
| **D4** `cpu:everywhere` gate | **green** | blocking in `ci/gates.yaml` |
| **D5** Docs / release | **green** | `docs/CPU_EVERYWHERE.md` |

**Default pytest:** **182 passed**, 0 skipped, 2 slow deselected.

## What was CPU-gated before (v1.2)

| Path | Before | After (v1.3) |
|---|---|---|
| Bio GPU twin without torch | `pytest.skip` / cpu_hal stub only | **numpy_cpu** same wave math, always |
| `ORGANISM_BIO_GPU_TWIN=1` no CUDA | torch_cpu if torch else skip risk | torch_cpu or **numpy_cpu** fallback |
| Neuromorphic | RESEARCH_SIM CPU (ok) | Confirmed + `neuromorphic_cpu_backend` |
| `requires_gpu` | Declared, unused crash path | `resolve_requires_gpu()` soft CPU |

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` (CPU) |
| Wet-lab / bioreactor GPIO | bio_digital + physical_research exploration only |
| Production WAN BFT + TPM | multi-process software only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling (VENDOR.md) |
| CUDA / ROCm / Metal | **optional prefer**; CPU always works |

## Tooling

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
# CPU-everywhere gate:
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q sdk/python/tests/test_cpu_everywhere.py modules/bio_digital/tests/test_gpu_twin.py
# Prefer GPU when present (CPU fallback automatic):
ORGANISM_BIO_GPU_TWIN=1 ORGANISM_BIO_DIGITAL_SIM=1 ...
ORGANISM_NEURO_SIM=1 ...
```

## Prior lines

v1.2.0 live Hybrid + telemetry + hypervisor + optional GPU twin.  
v1.1.0 Hybrid mapping. v1.0.0 software-complete A–H.
