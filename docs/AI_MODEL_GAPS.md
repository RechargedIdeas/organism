# Organism gaps for KotMoE, Lightspeed and future AI/ML models

Date: 2026-11-04. Scope: what Organism does not yet provide that the KotMoE agent, the Lightspeed model line and any
later model will need. Each gap cites the file that shows it (repo-relative paths). Nothing here is a bug report
against the current Python reference unless it says so.

Priority:
- **P0** blocks a Lightspeed stage (A to C) or a basic agent path.
- **P1** blocks a later stage (D to F) or a platform (Android, many-core).
- **P2** can wait, but it shapes an interface that is cheaper to get right now.

Consumers: **KotMoE** (the agent and its experts), **LS** (Lightspeed core and system), **All** (any model that is
registered with Organism).

---

## A. Contract and output

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| A1 | No text, token-stream or tool-call output form. A language model cannot declare what it emits | `sdk/python/organism_sdk/contract.py` `OutputForm`; `docs/v1.11/MOA_LAYER.md` section 2, item 4 | KotMoE, LS, All | P0 | New output forms in the contract, proto and Kotlin (K1b) |
| A2 | No tool contract: a module cannot declare a callable tool, its JSON schema, its risk tier, its confirmation rule, or its network and confinement needs | `contract.py` has no tool fields | KotMoE, LS | P0 | Tool contract type in K1b. KotMoE's risk tiers map onto Organism's safety tiers |
| A3 | No human-confirmation justification kind for irreversible actions | `contract.py` `JustificationKind` (NONE, CAUSAL_CERT, KERNEL_BOUND, RULE_TRACE, ENERGY_CERT, SYMBOLIC_PROOF) | KotMoE, LS | P0 | Add `HUMAN_CONFIRMATION` (K1b) |
| A4 | Learned actuation is only a warning. A T2 or T3 module with `may_actuate=true` still registers when cross-check is off | `contract.py` `actuation_without_cross_check` is WARNING; vectors `warn_t3_actuate_no_cross_check` (`conformance/vectors/contract.json`) | All learned experts | P1 | Owner decision: error for T3, warning or error for T2 |
| A5 | Reliability tier is declared. No calibration evidence (ECE, coverage) is checked at registration or promotion | `contract.py` `SafetyDeclaration` has no calibration field | KotMoE (RAMA T2), LS | P1 | Calibration record checked at promotion (K6) |
| A6 | Metabolic profile is declared, not measured. Nothing feeds device measurements back into the contract | `contract.py` `MetabolicProfile`. Lightspeed section 5 requires measured values | LS, KotMoE | P1 | Measurement record type and a declared-versus-measured check |
| A7 | Hardware requirement has no GPU or phone NPU value. `requires_gpu` is a boolean. Enum has NONE, NEUROMORPHIC, EVENT_CAMERA, PHYSICAL_SUBSTRATE, TPU_NPU | `contract.py` `HardwareRequirement`; `MetabolicProfile.requires_gpu` | LS (Android NPU, multi-GPU), All | P1 | Accelerator classes (CPU, GPU vendor-neutral, NPU) in the contract |
| A8 | No model-artifact type. A release needs weights digest, tokenizer, quantisation, adapter lineage, licence, data provenance and gate report. `artifact_digest` is only a field on `Identity`. The artifact store is for generated code and assets | `contract.py` `Identity`; `sdk/python/organism_sdk/generative/artifacts.py` | LS (signed manifest, LIGHTSPEED section 7), All | P0 | `ModelArtifact` manifest type (new item, before LS8) |
| A9 | No signature verification anywhere. `Identity` has `signatures_b64`, and the Python SDK depends on `cryptography`, but no verify or sign code exists | `contract.py` `signatures_b64`; no Ed25519 or verify code under `sdk/python/organism_sdk`; `pyproject.toml` | LS (refuses unsigned adapters), All | P0 | Ed25519 verify in the Kotlin SDK. Android needs a provider that supports Ed25519 (API 33 and later, or a bundled library) |

## B. Registry and lifecycle

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| B1 | Promotion ignores shadow evidence and the approver. `promote()` takes `shadow_records` and `approver_signature` and never uses them | `sdk/python/organism_sdk/registry.py` `promote` | LS ("never serve before shadow"), All learned experts | P0 | K6: make the gate mandatory inside the registry. **Done (K6, `0d38866`):** gated states need evidence over `ShadowThreshold`, and the approver signature covers the evidence |
| B2 | Registry state lives in memory. A restart loses every registration and every lifecycle state | `registry.py` `self._modules` dict | All | P0 | Lifecycle stream on the op log (K4) |
| B3 | Kotlin registry was not synchronized, while the reference holds an RLock | `registry.py` line 122 `RLock`. Fixed in this change: `ModuleRegistry.kt` methods are `@Synchronized` | KotMoE on Android (multi-thread) | P1 | Done in K1 (`Registry.kt`) |
| B4 | The ladder has no transitions for DEVELOPMENT, SELF_TERMINATING, SUCCEEDED or DEGRADED. The Python reference raises `ValueError` for them. Kotlin returns a typed rejection | `registry.py` `_PROMOTE_ORDER` and `_EXTENDED_STATES`; `conformance/vectors/lifecycle.json` (`DEVELOPMENT` rows) | LS (self-termination and degraded experts), KotMoE | P2 | Define the extended transitions in the reference, then vectors |
| B5 | Registering an existing id silently replaces the entry | `registry.py` `register` | All | P2 | Reject, or require an explicit replace call |
| B6 | Health and drain are Python-only. The registry cannot ask a Kotlin module for health or drain it | `registry.py` `health()`, `deregister()` calls `on_drain`; not in Kotlin | KotMoE (experts report health), LS (failure signature) | P1 | Health and drain interfaces in K1 follow-up |
| B7 | Unknown ids raise `KeyError` in the reference (`promote`, `get_contract`, `health`) | `registry.py` | All | P2 | Typed `not_found` everywhere (Kotlin already does this for `promote`) |

## C. Traces, decision records and data handling

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| C1 | Traces are in-memory lists. No persistence, no hash chain, no signed head | `sdk/python/organism_sdk/trace.py` `TraceEmitter._entries` | LS (tamper-evident decision records, LIGHTSPEED section 3), KotMoE | P0 | Op log with digest chain and a signed head (K4) |
| C2 | No redaction or anonymisation hook on traces or workspace content. No PII handling anywhere in the SDK | Searches for redact, anonym and pii return nothing in `sdk/python/organism_sdk` | KotMoE (LS2 anonymiser), LS, All | P0 | A redaction hook in the trace sink. The anonymiser stays in KotMoE, and Organism only defines the hook |
| C3 | No canonical JSON writer in Kotlin. `Json.kt` only parses | `sdk/kotlin/src/main/kotlin/org/organism/sdk/Json.kt` (`parse` only) | KotMoE (canonical plans, K2), LS (signed manifests), All | P0 | Canonical encoder: sorted keys, fixed number format, with vectors |
| C4 | Kotlin tests read the vectors through the same reader they test. There is no independent check of the reader | `ContractConformanceTest.kt`, `ConformanceTest.kt` | All | P2 | A second check: round-trip the vectors through the canonical encoder once C3 exists |

## D. Routing, eligibility and aggregation

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| D1 | No public eligibility mask. Exclusions exist only inside `decide()` | `sdk/python/organism_sdk/router.py` `excluded` list built inside `decide` | LS (M1), KotMoE (RAMA prompt) | P0 | Eligibility API with typed exclusions (K2). **Done (K2, `c706613`).** |
| D2 | No learned router backend. The policy artifact has no weights type | `docs/v1.11/MOA_LAYER.md` section 9 (Phase 4 not started, learned backends undecided); section 6, item 6 | LS, KotMoE | P0 | Policy artifact type and a learned-backend interface (MoA Phase 4). **Partly done (K2):** the router policy artifact has a digest. The learned-backend interface is open |
| D3 | Aggregation confidence is a rule margin, not a calibrated probability | `docs/v1.11/MOA_LAYER.md` section 3 (intent classifier) | LS (cross-check and abstain), KotMoE | P1 | Calibration service (ECE and isotonic), shared by experts |
| D4 | No synthesis. Aggregation picks one output and never merges text | `docs/v1.11/MOA_LAYER.md` section 5 ("No generative synthesis") | KotMoE (composite answers), LS | P1 | Synthesiser expert (MoA Phase 4) |

## E. Degradation, signals and modulators

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| E1 | Degradation thresholds are constants, not a level table | `sdk/kotlin/src/main/kotlin/org/organism/sdk/Degradation.kt` `Hysteresis.DEFAULT`; Python `degradation.py` constants | LS (phone and desktop tuning), KotMoE | P1 | Level table as data (K3) |
| E2 | No signal sources. Battery, thermal, memory, network, idle and charging are inputs only. No rest-window concept exists | `HealthSignals` is input-only. No rest, charging or idle term found in `sdk/python/organism_sdk` | LS (stage C), KotMoE (Android) | P0 | Signal-source interface and a rest-window type (K3). Platform adapters stay in KotMoE |
| E3 | Modulators have hormone names only | `sdk/python/organism_sdk/hormone.py`; `docs/KOTLIN_PARITY_PLAN.md` gap G12 | KotMoE (UI and API naming), LS | P2 | Plain-name alias layer (K3) |

## F. Memory and retrieval

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| F1 | Workspace similarity is hypervector-only. No dense-embedding index and no vector-store interface | `sdk/python/organism_sdk/workspace.py` `read_similar` over hypervectors; no embedding code | LS (M4 retrieval), KotMoE (RAG, memory) | P0 | Index interface with a pluggable embedding source. KotMoE supplies the embedding model. Hypervectors stay as a trace index |

## G. Execution and confinement

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| G1 | No tool runtime, no tool-calling loop, no conversation memory, no prompt handling. The only LLM path is an env-gated hosted draft generator | `docs/KOTMOE_SUBSTRATE.md` section 0 ("What it is not"); `generative/backends.py` | KotMoE, LS, All agents | P0 | Owner decision: Organism defines the tool contract (A2) and a ToolHost interface. The loop stays in KotMoE |
| G2 | Confinement exists only as Linux rlimits and optional `unshare`. No Windows, macOS or Android provider | `sdk/python/organism_sdk/sandbox/`; `docs/v1.10/BARE_METAL_AND_SANDBOX.md` | KotMoE (rule: workers confined before real tasks), LS | P0 | Confinement types in Organism (K5). Enforcement per platform in KotMoE |

## H. Learning, evaluation and evolution

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| H1 | No shadow runner on live traffic. Shadow exists only as labelled-set evaluation and generative code metrics | `sdk/python/organism_sdk/moa/shadow.py` (labelled set); `generative/code_pipeline.py` `ShadowMetrics` | LS (stage E), KotMoE (learning loop) | P0 | `ShadowRunner` with a traffic callback (K6). **Done (K6, `0d38866`):** `shadow_runner.py` and `Shadow.kt` |
| H2 | The promote gate is tied to generative shadow metrics. No per-track model gate, and no gates-as-data per model | `generative/stages.py`; `ci/gates.yaml` is for pipeline gates only | LS (LS-Bench tracks), KotMoE | P1 | Gate file per model in the gates format, read by the promote gate |
| H3 | No model-quality record. The harness checks faults, soak and performance, not accuracy, calibration or energy per task | `harness/scenarios/` (faults, soak, performance) | LS (scorecard), KotMoE | P1 | Metric record type that the gate reads (LS-Bench keeps the suite in KotMoE) |
| H4 | No evolution proposals (spawn, retire, merge). The metamodel is a hypernetwork stub | `docs/KOTMOE_SUBSTRATE.md` section 2.6; `sdk/python/organism_sdk/metamodel.py` | KotMoE (Agents page owner queue), LS | P2 | Propose-only evolution (K7) |
| H5 | No provenance or AI bill of materials. MoA Phase 6 is optional and undecided | `docs/UPGRADE_AND_EXPANSION_PLAN.md` Phase 6 and decision D4 | LS (supply chain), All | P2 | Owner decision D4, then the manifest from A8 |

## I. Kotlin parity, interfaces and footprint

| ID | Gap | Evidence | Consumers | Priority | Planned fix |
|---|---|---|---|---|---|
| I1 | The Kotlin SDK covers hypervectors, degradation, contracts and the registry. No plan, router, workspace, op log, MoA, shadow or sandbox types | `sdk/kotlin/src/main/kotlin/org/organism/sdk/` | KotMoE on Android | P1 | K2 (routing) and K6 (shadow) **done**. K3 to K5 open |
| I2 | No MCP, ACP or OpenAI-compatible gateway. Nothing exposes the registry over HTTP | `docs/KOTMOE_SUBSTRATE.md` section 2.7; `docs/KOTLIN_PARITY_PLAN.md` K8 | KotMoE tools and editors | P1 | Gateway (K8) |
| I3 | The Python dependency set is heavy for small hosts (protobuf, grpcio, numpy, pydantic, cryptography, structlog) | `pyproject.toml` | Phones and small hosts running the Python reference | P2 | Keep the core importable without them (plan G14) |
| I4 | Conformance vectors cover hypervectors, degradation, contracts and the lifecycle. None yet for routing plans, workspace or the op log | `conformance/generate.py` | KotMoE (K2), All | P1 | Vectors added with each K-phase. **Partly done:** `router.json` (K2) and `shadow.json` (K6), plus the K1b vectors. Workspace, op log, trace persistence and sandbox are open |
| I5 | No CI check that the checked-in vectors match a fresh run of the Python generator. The only conformance gate is `conformance:kotlin` (`ci/gates.yaml`), so a stale vector would pass | `ci/gates.yaml` (only `conformance:kotlin`) | KotMoE, All | P1 | Regenerate-and-diff gate. Not added yet: it touches the pipeline, so it needs the owner's go |

---

## Cross-cutting notes

- **Naming.** Organism's Python reference names are kept in Kotlin (`SubstrateContract`, `ModuleRegistry`,
  `LifecycleState`). The Lightspeed design used `ModuleContract`. Pick one name before KotMoE code depends on it.
  Keeping the reference name is the recommendation, because the vectors use it.
- **Declared versus measured.** Several gaps (A5, A6, H3) share one cause: Organism records what a module claims and
  never checks it against measurements. A single measured-evidence record would close all three.
- **Where the line is.** Organism should own contracts, lifecycle, eligibility, traces and gates. KotMoE should own
  experts, tools, platform adapters, data handling and the user interface. Gaps A2, B6, C2, E2 and G1 sit on that
  boundary, and each one needs an owner decision.
- **Fixed in K1:** B3 (Kotlin registry synchronized, commit `34c25a2`). Everything else is still open.
- **Fixed in K1b (`38d5fdd`):** A1 (output forms TEXT, TOKEN_STREAM, TOOL_CALL, with a warning for a
  tool call that names no action class), A2 (`ToolContract`), A3 (`HUMAN_CONFIRMATION`), A8 (`ModelArtifact`), A9 (the
  Python verify is `signing.verify`; Kotlin has a pure verify), C3 (canonical JSON, `docs/INTEROP.md`). Vectors:
  `canonical.json`, `signature.json`, `tool.json`, `model_artifact.json`, and 5 new cases in `contract.json`. Still open
  from K1b: B6, A5, A6, A7 (K1b task 7, deferred).
- **Fixed in K2 and K6:** D1 (`c706613`), B1 and H1 (`0d38866`). D2, I1 and I4 are partly done. The owner review items
  from these phases are in `docs/HANDOVER.md`.
- **Status 2026-11-05:** `docs/HANDOVER.md` has the working order for these gaps. This file has no separate status
  column, so status is recorded in the Planned fix column and in these notes.
