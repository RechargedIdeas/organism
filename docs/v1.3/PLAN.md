# v1.3 — CPU Everywhere

**Goal:** Product guarantee that every aspect of Organism (including GPU-labelled
workloads) runs on CPU on any box. Tag **v1.3.0**.

| Phase | Deliverable | Status |
|---|---|---|
| D1 | `organism_sdk.device` selection + CPU_HOSTABLE_HARDWARE | green |
| D2 | Bio wave twin NumPy parity; remove torch skip | green |
| D3 | SNN / neuro_sim CPU RESEARCH_SIM harden | green |
| D4 | Tests + blocking `cpu:everywhere` gate | green |
| D5 | `docs/CPU_EVERYWHERE.md`, STATUS, CHANGELOG, release | green |

Bio `may_actuate=False` unchanged. No wet-lab GPIO on control path.
