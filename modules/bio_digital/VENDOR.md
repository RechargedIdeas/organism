# Bio-Digital Hybrid Cluster — vendor / dependency note

**Upstream (private):** https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster  
**Organism adapters:** `modules/bio_digital/` (this package)  
**Mapping:** `docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md`

## What is vendored

Nothing from Hybrid GUI (`src/studio`, `src/nodes`, `src/twin` OpenGL canvas) or installer is copied into Organism.

Adapters re-implement the **domain contracts** (limits, HAL sim, slime/mycelium exploration solvers, bus routing semantics, hypervisor Active/Standby) as Organism modules so the default suite has zero mandatory Hybrid checkout.

## Optional live import

If a Hybrid checkout is available:

```bash
export BIO_DIGITAL_HYBRID_ROOT=/workspace/Bio-Digital_Hybrid_Cluster
# PYTHONPATH may include that root for optional comparison tests (not required).
```

Organism tests must pass with Hybrid **absent**. RESEARCH_SIM HAL is the default.

## Do not

- Import PySide6 / Hybrid studio into Organism runtime.
- Place bio-digital modules on `control_actuation` dispatch.
- Treat Hybrid `BioClusterBus` as an undeclared side channel.
