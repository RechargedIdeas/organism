# Bio-Digital Hybrid Cluster → Organism Mapping

**Date:** 2026-10-24 (America/New_York)  
**Source:** [Recharged-Ideas/Bio-Digital_Hybrid_Cluster](https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster) (private)  
**Target:** [RechargedIdeas/organism](https://github.com/RechargedIdeas/organism) ≥ v1.1.0  
**Local clones:** `/workspace/Bio-Digital_Hybrid_Cluster`, `/workspace/organism`  
**Status:** Adopted — adapters under `modules/bio_digital/` (RESEARCH_TIER / exploration-only)

This document maps every Hybrid module onto Organism layers without violating Organism axioms (esp. Axiom 2 declared channels + VSA workspace SoT, Axiom 6 reconstructibility, T0 non-self-termination, physical/molecular never on control actuation).

---

## 1. Component-by-component map

| Hybrid component | Path | Organism layer / binding | Notes |
|---|---|---|---|
| Shared domain models | `src/shared/models.py` | `SubstrateContract` nested types + `bio_digital.limits` / message DTOs | `BioLimits`, `EnvironmentState`, `ClusterMessage`, `NodeStatus`, `ActuatorCommand`, `TelemetryPayload`, `SimulationResult` |
| Substrate enums | `SubstrateType` | Module IDs `bio_digital.slime_mold` / `bio_digital.mycelium` + `HardwareRequirement.PHYSICAL_SUBSTRATE` | Species-specific RESEARCH_TIER modules |
| Port / graph models | `PortModel`, `NodeGraphModel` | Metamodel / morphogenesis exploration graph (optional); not control path | GUI editor stays external |
| Async IPC bus | `src/core/bus.py` `BioClusterBus` | Declared `Channel`s + workspace bindings (Axiom 2) | Heartbeats/role cmds → typed channel; spike/spatial results → VSA workspace |
| BioNode base | `src/core/node.py` | `OrganismModule` + health probe + life-support → failure modes | Thermal/desiccation → `FailureSignature` + immune/hormone stress signals |
| Slime mold (Physarum) | `src/core/slime_mold.py` | `bio_digital.slime_mold` module | Pathfinding / XOR-style spatial solver; **exploration only** |
| Mycelium (Pleurotus) | `src/core/mycelium.py` | `bio_digital.mycelium` module | Spike-train / network memory substrate; **exploration only** |
| HAL sensors/actuators | `src/core/hal.py` | HAL facade + `HardwareRequirement.PHYSICAL_SUBSTRATE` + `RuntimeId=RESEARCH_SIM` | Simulated by default; never wires real GPIO into control_actuation |
| Multi-GPU sim twin | `src/sim/engine.py` | Digital-twin bridge → workspace tags `bio_twin` + Decision Trace | Optional torch; CPU stub always available |
| Hypervisor Active/Standby | `src/hypervisor/` | Registry `hot_swap` + `DrainPolicy` + apoptosis successor | Standby = shadow successor; Active fail → promote after drain |
| FastAPI telemetry | `src/api/` | Health probes + `hormone_state` windows + TraceEmitter | REST/WS stay optional external; metrics mapped inward |
| Metrics counters/gauges | `src/api/metrics.py` | Trace / health / twin payload fields | No second SoT |
| Digital twin visualizer | `src/twin/` | External tooling | Consumes twin bindings; not in Organism runtime |
| Studio GUI (PySide6) | `src/studio/`, `src/nodes/` | **Non-map** — external toolbox | Never imported by Organism adapters |
| Installer Blue/Green | `src/installer/` | Deployment ops outside runtime; maps conceptually to hot-swap + rollback digest | Not vendored |
| Build / CI scripts | `scripts/`, `ci/` | Organism `ci/gates.yaml` + pytest | Separate repos keep their CI |
| Shared exceptions | `DesiccationRiskError`, `ThermalBreachError` | Failure modes `thermal_breach`, `desiccation_risk` | Escalate via health / immune Danger |

---

## 2. Species / substrates (RESEARCH_TIER)

| Species | Hybrid | Organism module | Safety |
|---|---|---|---|
| *Physarum polycephalum* | `SlimeMoldNode` | `bio_digital.slime_mold` | `MaxSafetyTier.RESEARCH`, `may_actuate=False`, refuses `control_actuation` |
| *Pleurotus ostreatus* | `MyceliumNode` | `bio_digital.mycelium` | Same |
| Generic wetware twin | (HAL+sim) | Extends / coexists with `physical_research` | Same axioms as `docs/v0.3/HARDWARE.md` + v1.0-E |

**Hard rule (Organism axioms + STRUCTURAL_ANSWERS):** physical/molecular/wetware substrates are **exploration-only**. They must **never** be selected as primary on `task.form == "control_actuation"`. Adapters hard-refuse that form and set `may_actuate=False`.

`ORGANISM_BIO_DIGITAL_SIM=1` (default on when unset for unit tests that opt in) marks the HAL/sim facade as `RuntimeId=RESEARCH_SIM`. Real bioreactor GPIO is out of scope for software Organism (same class as wet-lab external dep in STATUS).

---

## 3. HAL / sim → HardwareRequirement / RuntimeId / twin

| Hybrid | Organism |
|---|---|
| `SensorInterface.read_telemetry` | Health probe sample + twin payload `env` |
| `ActuatorInterface.apply_potential` | **Exploration electrode stim only** inside module handle; never router ACTUATOR role |
| `SimulatedSensorSubsystem` / `SimulatedGalvanicActuator` | Default HAL when `RuntimeId=RESEARCH_SIM` |
| `BiologicalTensorSimulator` | Twin density/latency fields written to workspace `bio_twin` |
| Voltage clamp (`BioLimits.max_voltage`) | Enforced in HAL facade; breach → failure mode, not silent clamp on control path (there is no control path) |

`HardwareRequirement.PHYSICAL_SUBSTRATE` is declared on both species modules. Router `available_hardware` without `PHYSICAL_SUBSTRATE` excludes them from production dispatch (same pattern as SNN ↔ `NEUROMORPHIC`).

---

## 4. Async IPC bus → Channels + workspace (Axiom 2)

| `ClusterMessage.payload_type` / IPC | Stays typed **Channel** | Must hit **VSA workspace** |
|---|---|---|
| `HEARTBEAT` | Yes — `bio_digital.ipc.heartbeat` | Optional mirror tag `bio_node_alive` for reconstructibility |
| `STATE_UPDATE` / `PROMOTE` / `DEMOTE` / `SHUTDOWN` | Yes — `bio_digital.ipc.lifecycle` | Lifecycle also traced (`LifecycleTraceEntry` / apoptosis) |
| `EXECUTE_WORKLOAD` | Channel request | Result binding required before any consumer decision |
| `SPIKE_TRAIN` → slime mold ALU | Channel delivers request | **Result** → workspace binding tags `bio_slime_result` |
| `SPATIAL_GRAPH` → mycelium | Channel delivers request | **Result** → workspace binding tags `bio_mycelium_result` |
| Environment / impedance telemetry | — | Workspace `bio_twin` + optional contribution to `hormone_state` window (stress ↔ cortisol coefficient input) |

**Axiom 2:** no undeclared buses. Hybrid’s `asyncio.Queue` is reified as declared `Channel` records on the SubstrateContract.  
**Axiom 6:** any consumer that reads the channel mirror records staleness in the Decision Trace (same HormoneBus pattern in STRUCTURAL_ANSWERS §1).

---

## 5. Hypervisor Active/Standby → hot-swap / DrainPolicy / apoptosis

| Hybrid | Organism |
|---|---|
| `NodeRole.ACTIVE` | Module in `DELIBERATION` (or active runtime slot) |
| `NodeRole.STANDBY` | Shadow / successor candidate (`EXPLORATION` → `SHADOW_VALIDATED`) |
| Heartbeat timeout / crash | Failure mode → drain → `hot_swap` or apoptosis with successor |
| `PROMOTE` | `RegistryClient.hot_swap` **or** `ApoptosisController.promote_successor` after shadow-validate |
| Shared `mp.Array` state blob | Workspace snapshot / binding export before drain (not a second SoT) |
| Spawn replacement Standby | Morphogenesis / registry register of successor |

`DrainPolicy` (adapter): `{ drain_timeout_s, abandon_in_flight: bool }` maps to `OrganismModule.on_drain(deadline)` + registry `hot_swap(..., drain_timeout_s=...)`.

Control-affecting modules still obey T0 non-self-termination; bio_digital modules are research/exploration so they may self-terminate with successor under apoptosis rules, but they never hold control actuation.

---

## 6. Telemetry API / metrics → Trace + health + hormone_state

| Hybrid | Organism |
|---|---|
| FastAPI `/health` | `HealthProbe` / `HealthReport` |
| WebSocket telemetry stream | TraceEmitter + workspace twin writes each window |
| `counter` / `gauge` / `histogram` | Fields inside twin payload + optional Trace metadata |
| Node temp/humidity/CO₂/impedance | `bio_twin` binding; out-of-range → Danger-class immune signal + cortisol-raising interoception input |
| GPU util | Metabolic / resource vector observation only |

`hormone_state` remains the SoT for endocrine; bio twin may **feed coefficients** (stress from thermal breach rate) but does not bypass HormoneBus attestation.

---

## 7. Gaps and non-maps

| Item | Disposition |
|---|---|
| PySide6 Studio / OpenGL node editor / twin canvas | **External tooling** — do not import into Organism |
| Real I2C/GPIO/SPI bioreactor | External wet-lab; RESEARCH_SIM only in software |
| Torch multi-GPU wave sim | Optional dependency; CPU stub in adapter |
| FastAPI process + WS broker | Optional sidecar; Organism consumes mapped metrics/traces |
| Blue/Green installer | Ops concern; conceptual map only |
| Full copy of Hybrid repo into Organism | **Forbidden** — adapter + documented dependency / path note |
| Hybrid bus as unaudited side channel | **Forbidden** — must declare Channel + workspace SoT |

**Vendor note:** Adapters prefer importing from `BIO_DIGITAL_HYBRID_ROOT` (env) or documented path `/workspace/Bio-Digital_Hybrid_Cluster` when present; otherwise pure Organism RESEARCH_SIM stubs (no Hybrid import required for tests).

---

## 8. Phased integration plan

| Phase | Scope | Exit criteria |
|---|---|---|
| **I1** | Mapping doc (this file) | Reviewed against Hybrid README + `docs/architecture.md` + Organism HARDWARE / STRUCTURAL_ANSWERS |
| **I2** | HAL facade + limits + RESEARCH_SIM RuntimeId | Contract validate; voltage clamp; twin sample |
| **I3** | `slime_mold` + `mycelium` modules behind SubstrateContract | `may_actuate=False`; refuse `control_actuation`; exploration emit |
| **I4** | Bus adapter: ClusterMessage → Channel + workspace | Tests: spike/spatial → bindings; heartbeat channel-only |
| **I5** | Twin bridge → workspace + trace (+ optional hormone window feed) | Twin write reconstructible; no control dispatch |
| **I6** | Hypervisor map: DrainPolicy + hot-swap / successor helpers | Unit tests for promote-after-drain |
| **I7** | Registry wiring + router exclusion without PHYSICAL_SUBSTRATE | Plan excludes bio modules on control_actuation |
| **I8** | STATUS + CHANGELOG + tag `v1.1.0` | Default suite green; push `main` (no force) |

Phases I1–I8 are implemented in this release line.

---

## 9. Axiom checklist (must stay green)

1. No undeclared Hybrid bus reads that affect decisions.  
2. Physical modules never `may_actuate` / never win `control_actuation`.  
3. Twin + channel mirrors attested in Trace with enough data for replay.  
4. GUI / installer / real wetware remain outside the control plane.  
5. T0 deterministic engine remains the L4 refuge (bio modules are not T0).
