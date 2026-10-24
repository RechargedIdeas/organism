# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v1.1.0 — Bio-Digital Hybrid Cluster integration**  
**Corpus:** closed v0.1–v1.0 + bio-digital mapping (I1–I8)  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Tag:** [v1.1.0](https://github.com/RechargedIdeas/organism/releases/tag/v1.1.0)

## Verdict

Software Organism remains complete (v1.0). **v1.1** adds a proper mapping of [Bio-Digital_Hybrid_Cluster](https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster) as RESEARCH_TIER / exploration-only adapters under `modules/bio_digital/`. Wet-lab GPIO and PySide6 studio stay external.

## v1.1 phase table

| Phase | Status | Notes |
|---|---|---|
| **I1** Mapping doc | **green** | `docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md` |
| **I2** HAL / RESEARCH_SIM | **green** | `BioDigitalHAL`, `ORGANISM_BIO_DIGITAL_SIM` |
| **I3** Species modules | **green** | `slime_mold`, `mycelium` — `may_actuate=False` |
| **I4** Bus → Channel+workspace | **green** | heartbeat channel-only; spike/spatial → bindings |
| **I5** Twin bridge | **green** | `bio_twin` + optional `hormone_state` stress feed |
| **I6** Hypervisor map | **green** | `DrainPolicy` + hot_swap / apoptosis successor |
| **I7** Router invariants | **green** | never control primary; HW gate |
| **I8** Release | **green** | tag `v1.1.0` |

**Default pytest:** 150 passed (2 slow deselected).

## True external deps left

| Dep | Why external |
|---|---|
| Real neuromorphic silicon | RESEARCH_SIM via `ORGANISM_NEURO_SIM` |
| Wet-lab / molecular / bioreactor GPIO | bio_digital + physical_research exploration only |
| Production WAN BFT + TPM | multi-process software only |
| Hybrid PySide6 studio / OpenGL twin UI | external tooling (VENDOR.md) |

## Amendments (IMP-*)

| ID | Topic | Resolution |
|---|---|---|
| IMP-22–25 | (v1.0) | unchanged |
| IMP-26 | bio_digital adapters | Hybrid domain re-implemented as Organism modules; optional `BIO_DIGITAL_HYBRID_ROOT` |

## Tooling

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
# Opt-in: ORGANISM_WALL_CLOCK_FULL=1 | ORGANISM_SOAK_FULL=1 | ORGANISM_NEURO_SIM=1
# Bio-digital RESEARCH_SIM default on; set ORGANISM_BIO_DIGITAL_SIM=0 to mark physical-unavailable
```

## Prior lines

v1.0.0 software-complete (Phases A–H). See git history and `docs/v0.*/` / `docs/v1.0/`.
