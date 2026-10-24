# Organism API Freeze — v0.4.0

**Date:** 2026-10-24 (America/New_York)  
**Release:** `v0.4.0`  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**HEAD at freeze:** see git tag `v0.4.0`

This document freezes the **public API surface** for the v0.4.0 release. SemVer applies to the stable surface below. Breaking changes to frozen symbols require a major bump (or an explicit deprecation window documented in CHANGELOG).

## Version alignment

| Artifact | Version |
|---|---|
| Python package `organism` (root `pyproject.toml`) | `0.4.0` |
| Python package `organism-sdk` (`sdk/python/pyproject.toml`) | `0.4.0` |
| `organism_sdk.__version__` | `0.4.0` |
| Rust workspace `workspace.package.version` | `0.4.0` |
| Git tag | `v0.4.0` |

## Stability promises

1. **Additive-only on frozen symbols** within `0.4.x`: new optional fields, new enum values, and new modules may land; renames/removals of frozen exports do not.
2. **Proto package `organism.v1`** remains the wire source of truth. Field numbers and existing enum values are immutable; new fields/enums are additive only.
3. **Default single-box control path** (registry → workspace → router → degradation → deterministic/learned modules) stays green under the default pytest suite (`-m 'not slow'`).
4. **Experimental APIs** (biology, multi-node sim, SNN, learned ISE/metamodel) may change shape in `0.5+` without a major bump, but must remain fail-closed when disabled.
5. **CI gates** listed as `blocking: true` in `ci/gates.yaml` for v0.1–v0.4 remain blocking on this release line.

## Frozen: proto `organism.v1`

Nine proto sources under `proto/organism/v1/`:

| File | Package |
|---|---|
| `common.proto`, `contract.proto` | `organism.v1` |
| `registry.proto` | `organism.v1.registry` |
| `workspace.proto` | `organism.v1.workspace` |
| `router.proto` | `organism.v1.router` |
| `trace.proto` | `organism.v1.trace` |
| `rule.proto` | `organism.v1.rule` |
| `calibration.proto` | `organism.v1.calibration` |
| `exploration.proto` | `organism.v1.exploration` |

Lifecycle enum extensions (`SELF_TERMINATING`, `SUCCEEDED`, `DEVELOPMENT`, `DEGRADED`) are part of the frozen additive surface.

## Frozen: public Python SDK (`organism_sdk`)

Symbols re-exported from `organism_sdk` / listed in `__all__` that constitute the **stable authoring + runtime core** (A3.1 + v0.1 amendments + degradation):

### Contract & identity
`CapabilityScopes`, `EmissionSignature`, `FailureSignature`, `HealthEscalationPolicy`, `HealthHttp`, `HealthProbe`, `Identity`, `JustificationKind`, `JustificationSpec`, `Lifecycle`, `MetabolicProfile`, `ModuleRole`, `PerceptionSignature`, `ReliabilityTier`, `SafetyDeclaration`, `Shape`, `SubstrateContract`, `ValidationIssue`

### Errors
`JustificationMissing`, `ModalityUnavailable`, `RegistrationRejected`, `SDKInvariantViolation`, `TraceUnavailable`

### Authoring / IO
`OrganismModule`, `run_handle`, `ModalityPayload`, `PerceptionInput`, `TaskDescriptor`, `Emission`, `JustificationToken`, `VerificationResult`, `HealthReport`, `HealthServer`

### Runtime clients
`RegistryClient`, `CapabilityFilter`, `WorkspaceClient`, `BindingRecord`, `TraceEmitter`, `Hypervector`, `DIM`

### Degradation (v0.1 M6)
`DegradationMachine`, `FaultInjector`, `HealthSignals`

### Version
`__version__`

## Experimental (not SemVer-frozen; may change in 0.5+)

These are shipped and tested, but **not** part of the v0.4 SemVer freeze. Prefer them behind feature flags / exploration roles. Production control actuation through experimental paths remains gated (promotion, FULL/affects_control, hardware, federation opt-in).

### v0.2 biological organs (exported in `__all__`)
`HormoneBus`, `HormoneLevels`, `InteroceptiveStateEstimator`, `HealthVector`, `ImmuneLayer`, `AutonomicController`, `RouterExposedParams`, `ApoptosisService`, `MemoryExport`, `CircadianClock`, `kleiber_declared_share`, `MorphogenesisTracker`, `DevelopmentalGenome`, `DevelopmentalStage`

Related submodule APIs (importable, not all in `__all__`): `organism_sdk.hormone`, `.interoceptive`, `.immune`, `.autonomic`, `.apoptosis`, `.circadian`, `.morphogenesis`, `.federation`

### v0.3 E.8 lifts (submodules / modules)
| Area | Location | Notes |
|---|---|---|
| Learned ISE + RL-DCA | `organism_sdk.learned_ise` | Shadow until promote; not control-path by default |
| Metamodel synthesizer | `organism_sdk.metamodel` | Exploration only until promote; `MetamodelDisabled` when off |
| Multi-node + oxytocin | `organism_sdk.multinode`, federation opt-in | **In-process simulation only** — not BFT |
| SNN sentinel | `modules/snn_sentinel` | Registers; no production control dispatch without neuromorphic HW |

### Still intentionally out of scope (E.8 / research-tier)
Real neuromorphic silicon, full BFT cluster / clock sync, live NAS / heavy hypernetwork training, molecular / physical substrates on the control path.

## Rust crates

Workspace members under `runtime/`, `sdk/rust/`, `modules/`, `harness/` share `workspace.package.version = 0.4.0`. Public crate APIs beyond proto bindings are **pre-1.0 / internal** for this freeze: treat them as unstable unless a crate is explicitly documented as public in a later freeze note.

## Test / gate baseline at freeze

- **Default suite:** 115 passed (2 slow deselected via `-m 'not slow'`).
- Plans / budgets: [docs/v0.4/PLAN.md](v0.4/PLAN.md), [docs/v0.4/PERF.md](v0.4/PERF.md), [STATUS.md](../STATUS.md).
- Opt-in: `ORGANISM_WALL_CLOCK_FULL=1`, `ORGANISM_SOAK_FULL=1`.

## Compatibility policy (summary)

| Change type | Allowed in 0.4.x? |
|---|---|
| Bugfix, perf, docs, tests | Yes |
| Additive proto fields / enum values | Yes |
| New experimental submodule / gate | Yes |
| Rename/remove frozen `__all__` symbol | **No** (needs 0.5+ major discussion) |
| Break wire compatibility of existing proto fields | **No** |
| Enable experimental path as default control | **No** without STATUS + CHANGELOG note |

