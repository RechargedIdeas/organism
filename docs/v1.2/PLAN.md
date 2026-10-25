# v1.2 — Live Hybrid path + telemetry + hypervisor drill + GPU twin

**Date:** 2026-10-24 (America/New_York)  
**Status:** complete (P1–P4)  
**Repo:** https://github.com/RechargedIdeas/organism

| Phase | Scope | Exit |
|---|---|---|
| **P1** Live Hybrid import | `BIO_DIGITAL_HYBRID_ROOT` → real HAL/slime/mycelium; stub fallback | `vendor_loader` + tests both paths |
| **P2** Telemetry bridge | NodeStatus / EnvironmentState / metrics → HealthReport probes + hormone stress | probes `affects_control=False` |
| **P3** Hypervisor drill | Active/Standby drain → promote; kill ACTIVE mid-flight | `v12:hypervisor_drill` gate |
| **P4** Optional GPU twin | torch multi-GPU/CPU behind RESEARCH_SIM + `ORGANISM_BIO_GPU_TWIN`; else CPU HAL | default suite never requires torch |

Bio modules remain exploration-only (`may_actuate=False`). Studio / OpenGL / wet-lab GPIO stay external.
