# Bio-Digital Hybrid Cluster — vendor / dependency note

**Upstream (private):** https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster  
**Organism adapters:** `modules/bio_digital/` (this package)  
**Mapping:** `docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md`

## What is vendored

Nothing from Hybrid GUI (`src/studio`, `src/nodes`, `src/twin` OpenGL canvas) or installer is copied into Organism.

Adapters re-implement the **domain contracts** (limits, HAL sim, slime/mycelium exploration solvers, bus routing semantics, hypervisor Active/Standby) as Organism modules so the default suite has zero mandatory Hybrid checkout.

## Live import (v1.2+)

`bio_digital.vendor_loader` resolves a Hybrid checkout and loads real HAL / slime_mold / mycelium when present:

```bash
# Explicit (recommended in CI with a checkout):
export BIO_DIGITAL_HYBRID_ROOT=/workspace/Bio-Digital_Hybrid_Cluster

# Or omit: if /workspace/Bio-Digital_Hybrid_Cluster exists, it is used automatically.
# If the path is missing, adapters fall back to Organism stubs (tests still pass).
```

| Symbol | Live source | Stub fallback |
|---|---|---|
| HAL sensors/actuators | `src.core.hal.Simulated*` | `BioDigitalHAL` internal |
| Slime mold XOR | `src.core.slime_mold.SlimeMoldNode` | Organism chemotactic XOR |
| Mycelium spikes | `src.core.mycelium.MyceliumNode` | Organism synaptic integrate |
| Models / metrics | `src.shared.models`, `src.api.metrics` | Organism DTOs / telemetry bridge |

Force stub: construct modules with `backend="stub"`. Force live: `backend="live"` (errors → stub if import fails).

**PySide6:** Hybrid `constants.py` imports `QColor` for Studio. Organism never imports Studio; if PySide6 is absent the loader installs a tiny QColor shim so core modules import. Do not import Hybrid studio/UI into Organism.

**Delays:** Hybrid biology sleeps are zeroed unless `ORGANISM_BIO_DIGITAL_REAL_DELAYS=1` (keeps the suite fast under RESEARCH_SIM).

## Do not

- Import PySide6 / Hybrid studio into Organism runtime.
- Place bio-digital modules on `control_actuation` dispatch.
- Treat Hybrid `BioClusterBus` as an undeclared side channel.
