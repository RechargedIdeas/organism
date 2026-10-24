# v1.1 — Bio-Digital Hybrid Cluster integration

**Date:** 2026-10-24 (America/New_York)  
**Status:** complete (I1–I8)

Map [Bio-Digital_Hybrid_Cluster](https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster) into Organism as RESEARCH_TIER adapters without putting wetware on the control path.

| Phase | Exit |
|---|---|
| I1 Mapping doc | `docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md` |
| I2 HAL + RESEARCH_SIM | `modules/bio_digital/hal.py` |
| I3 slime_mold + mycelium | SubstrateContract, refuse control_actuation |
| I4 Bus adapter | Channel + workspace result bindings |
| I5 Twin bridge | `bio_twin` + optional hormone feed |
| I6 Hypervisor map | DrainPolicy + hot_swap / apoptosis |
| I7 Router gates | No bio primary without PHYSICAL_SUBSTRATE / never control |
| I8 Release | tag `v1.1.0`, suite green |

See mapping doc for component table and non-maps (PySide6 studio stays external).
