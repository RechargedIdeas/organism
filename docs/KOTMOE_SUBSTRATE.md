# organism as a substrate for the next-generation KotMoE agent framework and RAMA

Date: 2026-11-01. Analysis only. Nothing in the KotMoE repo was edited, and nothing from organism was run or installed.
Sources: a shallow clone of `RechargedIdeas/organism` at a local clone (336 tracked files, 1 commit, v1.10.0),
the KotMoE repository on `p0-stabilise` (read-only), and the sibling report the KotMoE mapping report.
This file lives outside the (public) KotMoE repo on purpose.

---------------------------------------------------------------------------------------------------------------

## 0. Summary (read this first)

**What organism is.** A Python 3.11 + thin-Rust "substrate" for heterogeneous *modules*. Each module declares a four-part
**SubstrateContract** (identity, perception, emission, safety, plus failure, metabolic, capability and lifecycle parts). A
**deterministic structural router** picks a module per task from the contracts, filtered by safety tier, reliability tier,
health, hardware and a **graded degradation level L0..L4**. Modules talk through a **capability-scoped shared workspace**
(binary 10,000-bit hypervectors, ops log + content-addressed snapshots). A "physiology" layer (hormone bus, autonomic modes,
circadian clock, immune layer, interoception, apoptosis, morphogenesis) modulates the router's *exposed parameters* but can
never grant permissions. Anything new (a synthesised organ, generated code, a skill) walks a **promotion ladder**
`PROPOSED → SANDBOXED → SHADOW_VALIDATED → EXPLORATION → DELIBERATION → DEPRECATED → RETIRED` with a shadow floor of 0.9 and
rollback. Docker is optional; a native process sandbox exists.

**What it is not.** It is not an LLM agent framework. There is no agent loop, no tool calling, no conversation memory, no
planner, no prompt handling (one env-gated hosted-LLM *draft generator* aside). Its tasks are sensor-style forms
(`temporal_prediction`, `anomaly_detection`, `constrained_allocation`...). Large parts are deliberately simulated
(`RESEARCH_SIM`: neuromorphic, bio-digital, wet-lab, "instant hypernetwork stub", in-process "multi-node", BFT stubs). The
Rust runtime is ~1,400 lines in total. The design corpus that defines it (Artifacts A–F, addenda, "organism-handoff.txt")
is **not in the repo**; `docs/architecture/README.md` is a two-line pointer to a file outside it.

**Verdict.** Use organism as a **source of mature design patterns and invariants, reimplemented in Kotlin**, not as code,
not as a dependency, not as a runtime. The five ideas worth taking, in order of value for RAMA and the agent framework:

1. **Contract-first modules + lifecycle ladder with shadow validation on live traffic** (generalises `PromotionGate`).
2. **Eligibility-then-choice routing**: hard constraints (safety/reliability tier, health, hardware, degradation level, mandate)
   produce a *masked catalogue*; the learned RAMA head only chooses inside it; a deterministic fallback chain always exists.
3. **Graded degradation (L0..L4) with hysteresis**, fed by battery/thermal/RAM/queue/error signals. This is exactly what
   an Android-on-device assistant needs, and KotMoE has nothing like it.
4. **Typed trace + byte-stable plan serialisation + ops log/snapshot/replay**: golden-plan regression tests, shadow replay,
   and route labels that carry *reasons* (why an expert was excluded), which feeds RAMA's contrastive training rows.
5. **Modulators that tune but never authorise** (cortisol/dopamine/oxytocin/melatonin as plain-named signals: stress,
   reward, trust, rest) used to schedule learning, exploration and cross-checking, plus a **safety shield list**.

Do not take: HDC workspace as the first memory, any hormone/organ vocabulary in user-facing names, the Python/gRPC/proto
stack, the Linux-only sandbox as KotMoE's confinement, neuromorphic/bio/physical modules, generated-code evolution.

### Architecture diagram (proposed, text)

```
                         ┌──────────────────────── Interfaces ─────────────────────────┐
                         │ Tauri app · Android app · HTTP /v1 · CLI · MCP · ACP · voice │
                         └──────────────────────────────┬───────────────────────────────┘
 L6 Interfaces                                          │ Trigger / Task
 ─────────────────────────────────────────────────────────────────────────────────────────────
 L5 Evolution (propose-only)   Spawner · Specialiser · Retirer · Merger · TeachingLoop · LearningLoop
                               ShadowRunner · EvolutionPolicy(off|observe|auto) · owner approval queue
 ─────────────────────────────────────────────────────────────────────────────────────────────
 L4 Agent framework            AgentLoop (route→act→observe) · WorkItem/Mandate · ToolHost · Attention
                               (sibling report items 1–10); each loop step is a TaskDescriptor into L3
 ─────────────────────────────────────────────────────────────────────────────────────────────
 L3 Dispatch                   Eligibility(mask) ─► RAMA head (learned, inside the mask) ─► DispatchPlan
                               fallbacks: rules router → SELF → deterministic floor      (plan is byte-stable)
 ─────────────────────────────────────────────────────────────────────────────────────────────
 L2 Modules                    Expert = Module with ExpertContract (Static · SelfLearning · Taught · Composite
                               · Tool · Source(remote desktop) · Sensor/STT/TTS) — existing Experts keep their code
 ─────────────────────────────────────────────────────────────────────────────────────────────
 L1 Substrate (new, pure Kotlin, no platform API, Android-safe)
    contract/  registry+lifecycle/  health+degradation/  signals+modulators/  workspace/  store(oplog,snapshot)/
    trace/  policy(safety tiers, shield, mandate)/  confine(interface)/
 ─────────────────────────────────────────────────────────────────────────────────────────────
 L0 Platform adapters          Desktop JVM: process confinement, power/thermal, files · Android: isolated
                               process, BatteryManager/Thermal API, Room-or-file store · both: clock, storage root
```

Runs identically on desktop host, Android on-device and "desktop as optional source" (a remote Module whose contract says
`network=true, onDevice=false` and whose health probe is a loopback/LAN reachability check).

---------------------------------------------------------------------------------------------------------------

## 1. Overlaps and conflicts with the dsh-superagent mapping

The superagent report designs an **organisation layer** (WorkItem, Mandate, EffectQueue, Gate/Assessor, Attention, ToolHost,
AgentLoop) at `com.kotmoe.engine.{work,policy,source,agent}`. Organism designs the **runtime layer underneath**. They mostly
stack; four places need one decision each.

| Topic | superagent report | organism | Resolution proposed |
|---|---|---|---|
| Risk/authority vocabulary | Mandate "strength" (explicit/inferred), accept modes off/observe/auto, tool tiers | `MaxSafetyTier` (research/low/medium/high/critical), `ReliabilityTier` T0–T3, `may_actuate`, lifecycle shadow | **One lexicon.** Keep organism's tiers for *modules*, superagent's strength for *who asked*. A call is allowed iff `mandate.scope ⊇ tool.risk` AND the module tier is eligible. `observe` mode = the SHADOW_VALIDATED lifecycle stage; `auto` = DELIBERATION. Same code path for both reports (#7 and lifecycle). |
| Health model | "system problem only after 3 consecutive failures" (#19) | `HealthProbe` + `HealthEscalationPolicy` (consecutive failures, duration, timeout) + `RecoveryProcedure` with backoff | Take organism's (already generalised). The 3-strike rule is its default. |
| Replay/shadow review | `ReplayRunner` over RouteTrace + WorkItem journal (#21) | OpsLog + snapshot + `query_digest`, byte-stable `DispatchPlan`, `DraftReplayLog` | Same component. Build once in `substrate.store`/`trace`; the WorkItem journal is just another ops-log stream. |
| Durable stores | `WorkStore` JSONL+snapshot, `EffectQueue` JSONL | SQLite-WAL ops log + content-addressed snapshots | **One store abstraction** (`OpLog`, `SnapshotStore`) over `AtomicFile`; WorkStore and EffectQueue become streams on it. No SQLite in core (core is file-based; Android may use Room behind the same interface). |
| Delivery semantics | EffectQueue: persist-then-do, idempotency keys, ordering per key | `Channel.delivery = AT_LEAST_ONCE`, no durable outbox | Superagent wins (organism has nothing durable here). |
| Agent loop | wanted, harness-owned in the source | none | Superagent's #3 stands; make each step a `TaskDescriptor` through L3 so the loop inherits eligibility, degradation and tracing. |
| Sandbox/confinement | ToolHost + OS confinement (#6) | `ProcessJail` (rlimits + optional Linux `unshare`), degrades to "rlimits only" elsewhere | Organism's jail **does not satisfy** KotMoE's "OS-confined before real tasks" rule on Windows/macOS/Android. Keep only its *policy shape*; see §5.6. |
| Source/Trigger/Thread (#11) | new | none | Superagent only; a Source is a Module with role FRONTEND. |
| Subscriptions/Attention (#9, #12) | new | `Channel` + workspace tags are the nearest concept | Keep superagent's; do not invent a second pub/sub. Workspace tags are for *module-to-module* data, Threads for *human-facing* conversations. |

Directly conflicting package plans: both reports propose a root under `com.kotmoe.engine.*` with their own persistence and
policy classes. Settle by putting the shared, lower-level pieces in `substrate` and having `work`/`policy` depend on it
(layer diagram above). No other conflict found.

---------------------------------------------------------------------------------------------------------------

## 2. Organism inventory

### 2.1 Purpose and shape
- `README.md`: "production-grade AI/ML substrate: runtime, contract system, orchestration layer that hosts heterogeneous
  computational modules, couples them through a shared vector-symbolic workspace, routes work by task structure and
  physiological state, and degrades through graded alternative metabolisms rather than crashing. Organism is not a model."
- v1.10.0 (2026-10-25), single commit, 336 tracked files, Apache-2.0, repo marked private. 77 test files; CHANGELOG states
  377 tests pass (`-m 'not slow'`). Python is canonical; Rust is a thin parity layer (registry, workspace, router, degradation,
  control_loop: 1,133 lines in `runtime/*/src/lib.rs`, plus ~250 in `sdk/rust`, `modules/hdc`, `modules/kernel`).

| Path | What |
|---|---|
| `proto/organism/v1/*.proto` | schema source of truth: `contract`, `registry`, `router`, `workspace`, `trace`, `calibration`, `rule`, `exploration`, `common` |
| `sdk/python/organism_sdk/` (6.5k lines) | authoring SDK and the reference implementation of everything |
| `modules/*/module.py` (10 reference modules, ~2,000 lines) | deterministic_engine, learned_module (T2 + conformal calibration), kernel_module, hdc_module, reservoir, energy_hopfield, spectral, neurosymbolic, snn_sentinel, physical_research, bio_digital, generative |
| `runtime/{registry,workspace,router,degradation,control_loop}` | Rust ports |
| `harness/` | fault injector, observer, assertions, scenarios (soak, faults, security fuzz, perf, wall-clock SLO) |
| `ci/gates.yaml`, `.github/workflows` | declarative gate list; blocking vs non-blocking; perf budgets |
| `desktop/` | PySide6 control plane (13 panels) |
| `deploy/` | bare-metal install, systemd unit, container example, profiles `bare_metal|vm|container_generic|cpu_only` |
| `docs/` | per-version plans, audits, ops runbooks; architecture corpus is external |

### 2.2 Core abstractions
- **Module** (`organism_sdk/module.py`): ABC with `declare_contract()`, `handle(PerceptionInput) -> Emission`, `health()`,
  optional `justify(emission)` and `on_drain(deadline)`. `run_handle` enforces: an emission whose `action_class` is in
  `contract.emission.requires_justification_for` must carry a justification token of the declared kind, else
  `JustificationMissing`.
- **SubstrateContract** (`contract.py`, 697 lines): `Identity` (module_id, version, author, license, role, artifact digest,
  signatures), `PerceptionSignature` (modalities, shapes, sampling), `EmissionSignature` (output form, uncertainty kind,
  determinism, justification list), `MetabolicProfile` (energy J/inference, memory footprint/peak, GPU need, budget class
  LEAN..RESEARCH, `declared_share` ResourceVector), `FailureSignature` (failure modes + observable signal + detection latency
  budget, `HealthProbe` http/rpc/stream, `RecoveryProcedure` with attempts and backoff, `HealthEscalationPolicy`),
  `SafetyDeclaration` (reliability tier T0..T3, `may_actuate`, cross-check requirements, `max_safety_tier`),
  `CapabilityScopes` (read/write roles and tags, allowed channels, trace-sink overrides), `Channel`, `JustificationSpec`,
  `Lifecycle`. Validation yields `ValidationIssue(severity, code, field_path, ...)`; `RegistrationRejected` on errors.
- **Roles**: PERCEPTION, PREDICTION, SENTINEL, SOLVER, VERIFIER, GOVERNANCE, FEATURE_EXTRACTOR, MEMORY, ACTUATOR, FRONTEND.
- **Reliability tiers**: T0 deterministic, T1 calibrated non-learned, T2 learned calibrated, T3 learned uncalibrated.

### 2.3 Runtime and lifecycle
- **Registry** (`registry.py`): `register`, `deregister(drain, timeout)`, `query(CapabilityFilter)`, `promote(from, to)`,
  `hot_swap`. Ladder `PROPOSED, SANDBOXED, SHADOW_VALIDATED, EXPLORATION, DELIBERATION, DEPRECATED, RETIRED`; extended
  states `DEVELOPMENT, SELF_TERMINATING, SUCCEEDED, DEGRADED` (`apoptosis.py`). Promotion must step in order and from the
  recorded state. The router only sees `DELIBERATION`. Every transition emits a `LifecycleTraceEntry`.
- **Degradation machine** (`degradation.py`): levels L0..L4 driven by `HealthSignals` (per-module health, confidence,
  thermal, power, memory, queue p95, GC, Byzantine count, trace/determinism/causal OK). Entering a lower level requires the
  condition to hold for `t_down[level]`; recovering requires `t_up` plus (at the deepest level) a human ack. Deterministic
  with a virtual clock, plus a wall-clock mode for SLO tests. Thresholds are constants (`THERMAL_L1 0.20`, `GC_L4 0.85`,
  `Q_P95_L3 50`...). L4 = "deterministic engine only".
- **Autonomic controller** (`autonomic.py`): modes PARASYMPATHETIC, SYMPATHETIC, CRISIS, RECOVERY chosen from viability and
  cortisol; they set only four router-exposed knobs (`preemption_class`, `cross_check_frequency`, `exploration_budget`,
  `metabolic_multiplier`).
- **Control loop**: Rust `runtime/control_loop` minimal tick loop; Python `deploy/serve.py`, `deploy/stack.py` assemble a stack.

### 2.4 Units and routing
Units are **modules** (not agent "cells"), registered with contracts. Router (`router.py`, 488 lines), a stateless evaluator:
1. Step 0 validate the task and require `policy.lifecycle_state == DELIBERATION`.
2. Map `task.form → roles` (`DEFAULT_FORM_TO_ROLES`, 13 forms).
3. Filter by level (`LEVEL_ELIGIBILITY`) and safety tier (`TIER_ELIGIBILITY`; critical never gets learned modules; control
   actuation forces T0/T1), health, hardware requirement, interpretability and determinism flags.
4. Rank the remainder (hormone and autonomic parameters feed the ranking), produce `DispatchPlan` = primary + fallbacks +
   `constraints_applied` + `excluded[(module, reason_code, params)]` + `ranking_trace` + optional cross-check module +
   required justification kind. `to_canonical_bytes()` is byte-stable JSON, and a CI gate asserts byte-identical re-runs.
5. Unknown form, bad descriptor or non-deliberation policy produce a `HOLD` disposition, never a guess.

### 2.5 Communication and memory
- **Workspace** (`workspace.py`, `hypervector.py`, `snapshot.py`): bindings = `(role ⊗ filler)` binary hypervectors
  (DIM 10,000, packed as 157 u64) with tags, salience, fidelity, optional semantic `payload`, `affects_control`, checksum.
  Reads are scoped by the reader's `CapabilityScopes` (`CapabilityScopeMissing` otherwise). `read_similar(hv, k)` is a
  similarity lookup. `DurableWorkspace` persists an ops log (SQLite WAL) and content-addressed snapshots with replay.
- **Hormone bus** (`hormone.py`): four levels with half-lives (cortisol 30 s, dopamine 10 s, oxytocin 20 s, melatonin 60 s),
  declared (not learned) release functions from stress, viability, crisis precursors, mean reward, adapter acceptance and
  circadian phase. The workspace `hormone_state` binding is the single source of truth; the bus is a mirror and consumers
  emit a staleness-annotated trace. Receptors map a hormone to a *module parameter* (threshold gate, binary switch,
  continuous gain). `SAFETY_SHIELD_PARAMS` (`bypass_safety`, `permit_forbidden_actuation`, ...) can never be targeted.
- **Immune layer** (`immune.py`): antigen scoring of module outputs against thresholds, memory cells keyed by hypervector
  signature (response history), decisions written as FULL / `affects_control` workspace bindings only.
- **Interoception** (`interoceptive.py`, `learned_ise.py`): a viability function over a health vector with allostatic
  setpoints and predicted trajectory; a learned estimator (RL-DCA-style) runs in shadow and may only emit *signals*
  until promoted by `PromotionGate`.
- **Circadian clock + Kleiber scaling** (`circadian.py`): phase, sleep pressure, rest; `kleiber_declared_share` (declared
  resource share ∝ complexity^0.75) and `metabolic_inefficiency(measured, predicted)` flag modules that burn more than their share.

### 2.6 Learning and evolution
- **Metamodel** (`metamodel.py`): reproductive path `REQUESTED → SYNTHESIZED → SANDBOXED → SHADOW_VALIDATED → PROMOTED|REJECTED`.
  A four-part contract check must pass, the new organ has `may_actuate=False` and never T0, default `enabled=False`
  (fail-closed), `min_shadow_pass_rate 0.9`. The "hypernetwork" is a deterministic stub from the spec digest.
- **Apoptosis** (`apoptosis.py`): `begin_self_terminate` drains work, writes a `DeathCertificate` and a `MemoryExport`,
  records synthetic lifecycle; `assert_self_termination_allowed(contract)` guards who may die; `shadow_validate` and
  `promote` for successors.
- **Morphogenesis**: developmental stage genome tracker (stub, 74 lines).
- **Generative evolution** (`generative/`, `modules/generative`): code, assets ("looks") and skills pipelines. Intent →
  draft (template library of ~10, pluggable `GeneratorBackend`, env-gated `HostedLLMBackend`) → AST static check → contract
  validate → sandbox exec → shadow metrics (≥0.9) → promote/demote/**rollback last promote**. Drafts are replayable
  (`DraftReplayLog`), artifacts content-hashed (`ArtifactStore`), skills carry a version history and a dependency DAG
  and can `improve_from_trace`. Hot-registered modules are capped at EXPLORATION, `may_actuate=False`.
- There is **no gradient learning of the router**; the router policy is a versioned, digest-identified artifact.

### 2.7 Persistence, interfaces, config, ops
- Persistence: SQLite WAL ops log + snapshot files (workspace), JSON artifact stores under `organism_data/`.
- Interfaces: gRPC/proto3 `organism.v1` (generated into Python and Rust), a `HealthServer` (HTTP, `/health`), a CLI
  (`organism_sdk/cli.py`: `serve`, `status`, `validate-config`, `sandbox`, `evolve-*`, `promote-*`, `rollback-code`, `bundle-*`).
  No MCP, ACP or OpenAI-compatible API.
- Config: YAML deploy profiles (`deploy/config/*.yaml`), env flags (`ORGANISM_LLM_ENABLED`, `ORGANISM_NEURO_SIM`,
  `ORGANISM_SANDBOX_*`), `host.detect_host()`.
- Sandbox (`sandbox/`): `SandboxPolicy` (cpu, rss, time, fds, nproc, network allowlist, namespaces, shell-escape deny, env
  scrub, workdir, self-containment), `ProcessJail` (subprocess + rlimits + best-effort `unshare`), audit log to a typed trace.
- Tests: contract validation, registry/workspace, router determinism, degradation transitions, trace replay, e2e bootstrap,
  perf budgets (router/workspace/hormone), soak, fault injection, security fuzz, wall-clock SLO, deploy config,
  desktop smoke. Gates are data in `ci/gates.yaml`.

### 2.8 Honest quality read
Strengths: invariants are explicit and tested (determinism, fail-closed defaults, ladder ordering, shield list), consistent
trace schema, good CI-as-data. Weaknesses for our purpose: sensor-oriented task taxonomy, many simulated parts, thin Rust,
spec corpus missing from the repo, Python-only reference, the "physiology" naming is heavy, `LEVEL_ELIGIBILITY` and the
degradation thresholds are hard-coded constants, router ranking is not learned, workspace similarity is hypervector-only.

---------------------------------------------------------------------------------------------------------------

## 3. KotMoE baseline (what the substrate has to sit under)

Verified on `p0-stabilise` (docs + code):

- **Core** `kotmoe-core/.../engine/`: `rama/` (`Rama.kt` orchestration, `Router` interface + `RamaRouter` rules,
  `LearnedRouter` head, `CascadeRouter`, `RouteGrammar` constrained decoding, `RouteFormat`, `RouteTrace` JSONL,
  `RouteCalibration`), `experts/` (`Expert` = `descriptor` + `isAvailable()` + `suspend run(req)`; `ExpertClass` STATIC /
  SELF_LEARNING / TAUGHT / COMPOSITE; `ExpertRegistry` with file manifests; `LearningExpert`/`TeachableExpert`/
  `VersionedExpert` with `promote`/`rollback`; `PromotionGate`, `HeldOut`, `LearningLoop` 536 lines, `ExemplarMemory`,
  `JobRunner`; concrete `GeneralExpert`, `RagExpert`, `FileModelExpert`, `MemoryExpert`, `AdapterExpert`, `DistilledExpert`,
  `CompositeExpert` PARALLEL/MOA), `agent/KotMoEAgent.kt` (single-shot `chat`, `queryKnowledge`, `feedback`, `ingest`),
  `rag/`, `embed/`, `general/`, `gguf/`, `bridge/`, `json/`.
- **Server** `kotmoe-server`: OpenAI-style `/v1/chat/completions`, `/v1/rag/*`, `/v1/experts`, `/v1/bridges`,
  `/v1/learning/*`, `/v1/training/*`; `server/training/` supervisor (watchdog, self-recovery, pipeline, preflight,
  `RunStore`) and `training/client/` CLI + MCP + ACP (training surface only).
- **Training**: `rama-train/` (Python/JAX today; gate thresholds 0.85/0.90/0.90/0.85; v3 rejected at 0.805), `rama-kt/` is the
  Kotlin replacement (K0–K5 in `docs/KOTLIN_RUNTIME.md`). v4 plan includes **contrastive catalogue twins** (a gold expert
  removed from the catalogue, label changed to SELF or the rest).
- **Apps**: Tauri (pages Chat, Agents, Knowledge, Models, Settings, Toolkit, Training; a separate TS `agent-core` loop),
  Android (`ModelSource` on-device/desktop/auto, `assist/` role + voice + `RamaBrain` + device tools with confirmation).
- Facts that bind the design: `kotmoe-core` is shared by desktop and Android; core is file-based (no SQLite);
  RAMA is 121M parameters (prompt budget is small); the route format is `<route>{"experts":[..],"mode":..,"conf":x}</route>`;
  new Experts reach routing through a fallback embedding match until RAMA's next training; bridges are off by default.

What KotMoE lacks that organism supplies: contracts richer than `ExpertDescriptor`, a lifecycle with live-traffic shadowing,
any notion of a degradation level, eligibility constraints separate from the learned choice, a byte-stable plan record,
a modulator concept, retirement/merging, and a general ops log.

---------------------------------------------------------------------------------------------------------------

## 4. Concept mapping

Legend: **SUB** = becomes substrate (L1), **EXT** = extends an existing KotMoE piece, **REP** = replaces/supersedes,
**NO** = does not fit.

| organism concept | Verdict | KotMoE target | Notes |
|---|---|---|---|
| SubstrateContract (4-part + failure, metabolic, scopes, lifecycle) | SUB + EXT | `substrate.contract.ModuleContract`; `ExpertDescriptor` becomes a projection of it | Keep `ExpertDescriptor` JSON manifests readable (versioned field `contract`). Add fields: `reliabilityTier`, `maxSafetyTier`, `mayActuate`, `hardware`, `metabolic`, `failure`, `scopes`, `justification`. |
| Module `handle/health/justify/on_drain` | EXT | `Expert.run` stays; add `health()`, `drain()` with defaults | Default impls keep every current Expert source-compatible. |
| Roles | EXT | `ExpertRole` (CHAT, RETRIEVER, VERIFIER, TOOL, ACTUATOR, SENSOR, SOURCE, GOVERNANCE) | Not the sensor list; derived from KotMoE capabilities. |
| Reliability tiers T0–T3 | SUB | static=T0/T1, adapter/distilled=T2/T3 | Drives who may be routed for critical/actuating tasks. |
| Safety tier of a task, `TIER_ELIGIBILITY` | SUB | `TaskDescriptor.safetyTier`; tool risk tier from sibling #6 | Replaces ad-hoc "needs confirmation" with one table. |
| Registry + lifecycle ladder | REP/EXT | `ExpertRegistry` gains `LifecycleState`; `PromotionGate` becomes the SANDBOXED→SHADOW→DELIBERATION edge | Today an Expert is either registered or not; add the in-between states. |
| Shadow validation on mirrored traffic | SUB (new) | `ShadowRunner` | KotMoE only has held-out evaluation. Add: candidate receives a copy of real requests (sampled, off by default), result never served. |
| Hot swap / rollback last promote | EXT | `VersionedExpert.promote/rollback` already; add promote stack with provenance | Already close. |
| Router: eligibility then rank, `excluded` reasons | SUB + EXT | `dispatch.Eligibility` before `Rama.decide`; reasons recorded in `RouteTrace` | See §6.1, the biggest RAMA win. |
| Byte-stable `DispatchPlan` | SUB | `DispatchPlan.toCanonicalBytes()`; golden-plan tests | A *learned* head is deterministic at temp 0 with a fixed seed; canonicalise the plan, not the logits. |
| Router policy as digest-identified artifact | EXT | route policy (rules + head hash + catalogue hash + level) recorded in each trace | Gives exact reproducibility of a past decision. |
| Degradation L0..L4 + hysteresis | SUB (new) | `substrate.health.DegradationMachine` | See §5.3. |
| Autonomic modes, exposed router params | SUB | `Modulators` | Four knobs map to KotMoE: preemption → queue priority, cross-check frequency → MoA/verification rate, exploration budget → shadow/learning rate, metabolic multiplier → cost weight in routing. |
| Hormone bus (4 levels, half-lives, receptors) | SUB (lite) | `ModulatorBus` with plain names `stress`, `reward`, `trust`, `rest` | Keep decay + receptor mapping + safety shield. Do not ship the hormone names in UI or API. |
| Immune layer (antigen score, memory cells) | EXT | `AnomalyGuard` for tool args/outputs and untrusted text; propose-only quarantine | Pairs with sibling #10 trust labels. Memory cells = known-bad patterns (embedding signature) with response history. |
| Interoception / viability | SUB (lite) | `Viability` score from signals, feeds Degradation and Modulators | Skip the learned ISE at first. |
| Circadian / rest | SUB (small) | `RestWindow` (idle + charging + night) gates learning, shadowing, consolidation | Directly useful on a phone. |
| Kleiber share, metabolic inefficiency | SUB | per-Expert resource share; retire/merge trigger | Cost accounting KotMoE does not have. |
| Workspace (capability-scoped blackboard) | SUB | `substrate.workspace.Workspace` | Keep tags, salience, scopes, `affects_control`, checksum. **Defer** HDC; use embeddings (MiniLM already present) for `readSimilar`. |
| Hypervector (10k-bit) binding/bundling | NO (now) | optional later module for tiny devices | 1,250 B per vector and popcount similarity is attractive on phones, but there is no evidence it beats MiniLM+BM25 for text. Make `readSimilar` an interface; HDC can be added later. |
| OpsLog + snapshots + replay | SUB | `substrate.store` over `AtomicFile` | Shared with sibling WorkStore/EffectQueue. |
| Typed trace entries, `TraceEmitter` | EXT | `RouteTrace` becomes one of several typed entries (route, lifecycle, degradation, modulator, evolution, sandbox) | Same JSONL file family and viewer. |
| Federation / multi-node | NO (now) | desktop↔phone sync is a separate, simpler design (§7) | Organism's is an in-process simulation. |
| Metamodel (spawn path) | EXT | `Spawner` | The *ladder* and four-part gate matter; the hypernetwork stub does not. |
| Apoptosis (DeathCertificate, MemoryExport) | SUB/EXT | `Retirer` | Add certificate + exemplar hand-over. |
| Morphogenesis genome | NO | — | Stub. |
| Generative code pipeline (AST sandbox) | NO | — | Generating and running code is outside KotMoE's safety posture. Use declarative skills instead. |
| Generative skills (version history, DAG, improve-from-trace) | EXT | skills = Knowledge Modules + tool recipes with version history and promotion | Fits `docs/kms`; no code generation. |
| Generative assets/looks | NO | — | Cosmetic; not part of the goal. |
| `HostedLLMBackend` | NO | KotMoE bridges already cover optional remote models | Same rule: off by default, never gets tool schemas. |
| Sandbox policy shape | EXT | `ConfinementPolicy` interface | Implementation is KotMoE's own per platform (§5.6). |
| `ci/gates.yaml`, fault injector, wall-clock SLO | EXT | `substrate/gates.yaml` + a small chaos harness | Gates as data is a good habit; reuse for promotion gates. |
| Deploy profiles | EXT | `desktop-host`, `android-device`, `desktop-source` profiles | |
| gRPC + proto3 | NO | KotMoE speaks HTTP/JSON + MCP + ACP | A `.proto` is only worth it if a second language needs the schema; JSON schema suffices. |
| Neuromorphic, SNN sentinel, bio-digital, wet-lab, physical, Hopfield, reservoir, spectral | NO | — | Domain modules for a different problem. (SNN-style "sentinel wake" is the same idea as a cheap always-on trigger; for KotMoE that is the wake-word/keyword detector, a different component.) |
| PySide6 Desktop | NO | Tauri app already exists | A "Substrate" page (levels, lifecycle, modulators, shadow results) is new UI, not a port. |
| Python SDK, Rust crates | NO | — | Reimplement in Kotlin; Rust adds nothing. |

---------------------------------------------------------------------------------------------------------------

## 5. Proposed next-generation architecture

### 5.1 Principles
1. Pure Kotlin/JVM in `substrate`, no platform imports (Android-safe), file-based atomic stores, no network, no cloud.
2. Everything new is **off or observe-only by default**, GUI-toggleable (owner rule: every setting has a control).
3. **Propose-only for anything durable.** Evolution produces proposals; promotion needs the gate and, for new or retired
   Experts, the owner's approval (setting: `evolution.mode = off | observe | propose | auto-safe`, default `observe`;
   `auto-safe` limited to adapter/memory Experts that beat the gate, never builtins).
4. Modulators and degradation can **restrict, never grant**. The shield list is enforced in code, not config.
5. Existing Experts and routes keep working unchanged (adapter layer), no feature removal.

### 5.2 Module / package layout

Phase 1 inside `kotmoe-core` (no Gradle churn); extract `kotmoe-substrate` when it stabilises (it has no dependencies, so
extraction is mechanical).

```
com.kotmoe.engine.substrate
  contract/    ModuleContract, Identity, Perception, Emission, SafetyDeclaration, Metabolic, FailureSignature,
               CapabilityScopes, JustificationSpec, ContractValidator, ValidationIssue
  registry/    LifecycleState, ModuleRegistry (wraps ExpertRegistry), LifecycleEvent, PromotionPolicy
  health/      HealthReport, HealthProbe, EscalationPolicy, RecoveryProcedure, HealthSignals,
               DegradationLevel, DegradationMachine
  signals/     SignalSource (battery, thermal, memory, queue, error rate, idle, charging), ModulatorBus,
               Modulators(stress, reward, trust, rest), Receptor, SafetyShield, RestWindow, Viability
  workspace/   Workspace, Binding, ReaderView(scoped), SimilarityIndex(interface; Embedding impl)
  store/       OpLog (append-only JSONL, seq + prev-digest chain), SnapshotStore (content-addressed), Replay
  trace/       TraceEntry (sealed: Route, Lifecycle, Degradation, Modulator, Evolution, Confinement, Guard), TraceSink
  policy/      SafetyTier, ReliabilityTier, Eligibility rules table (data, not code), Mandate hook (sibling)
  confine/     ConfinementPolicy, ConfinementProvider (interface only)
com.kotmoe.engine.dispatch
  TaskDescriptor, Eligibility, MaskedCatalogue, DispatchPlan, PlanningRouter (wraps Router: mask -> head -> fallbacks)
com.kotmoe.engine.evolution
  EvolutionPolicy, ShadowRunner, Spawner, Specialiser, Retirer, Merger, Proposal, ProposalStore, ApprovalQueue
com.kotmoe.engine.experts   (existing; gains health(), drain(), contract())
com.kotmoe.engine.rama      (existing; Rama.decide consumes MaskedCatalogue)
com.kotmoe.engine.agent / work / policy / tools   (sibling report; built on substrate)
kotmoe-server/.../substrate  routes /v1/substrate/{levels,modules,lifecycle,proposals,modulators,trace}; MCP+ACP tools
platform adapters: desktop (JVM) ConfinementProvider, power/thermal; android-app/.../platform  Battery/Thermal/Isolated process
```

### 5.3 Key interfaces (signatures, sketch)

```kotlin
// ---- contract ----
enum class ReliabilityTier { T0_DETERMINISTIC, T1_CALIBRATED, T2_LEARNED_CALIBRATED, T3_LEARNED_UNCALIBRATED }
enum class SafetyTier { RESEARCH, LOW, MEDIUM, HIGH, CRITICAL }
enum class LifecycleState { PROPOSED, SANDBOXED, SHADOW, EXPLORATION, DELIBERATION, DEPRECATED, RETIRED }
enum class DegradationLevel { L0, L1, L2, L3, L4 }

data class ModuleContract(
    val identity: Identity,                 // id, version, role, artifactDigest, author, license
    val perception: Perception,             // capabilities consumed, modalities, size limits
    val emission: Emission,                 // output form, uncertainty kind, determinism, requiresJustificationFor
    val safety: SafetyDeclaration,          // reliability tier, maxSafetyTier, mayActuate, needsCrossCheck
    val metabolic: Metabolic,               // latency p50/p95, RAM peak, energy hint, onDevice, needsNetwork, hardware
    val failure: FailureSignature,          // modes, probe, recovery, escalation
    val scopes: CapabilityScopes,           // workspace read/write tags
    val lifecycle: LifecyclePolicy,         // hotSwap, drainTimeout, retirementAllowed
)
interface Module { // Expert extends this with defaults
    fun contract(): ModuleContract
    fun health(): HealthReport = HealthReport.Healthy
    suspend fun drain(deadlineMs: Long) {}
    suspend fun run(req: ExpertRequest): ExpertResult
}

// ---- registry / lifecycle ----
interface ModuleRegistry {
    fun register(m: Module, initial: LifecycleState = PROPOSED): RegisterResult
    fun state(id: String): LifecycleState?
    fun promote(id: String, from: LifecycleState, to: LifecycleState, evidence: Evidence): PromoteResult  // ordered, from must match
    fun query(filter: CapabilityFilter): List<ModuleHandle>
    suspend fun retire(id: String, reason: String): DeathCertificate        // drain + certificate + exemplar export
}

// ---- degradation ----
data class HealthSignals(val moduleHealth: Map<String, Health>, val battery: Float, val charging: Boolean,
    val thermal: Float, val memFree: Float, val queueP95Ms: Long, val errorRate: Float, val idle: Boolean)
class DegradationMachine(private val table: LevelTable, private val clock: Clock) {
    val level: DegradationLevel
    fun update(s: HealthSignals): LevelChange?     // hysteresis: tDown to enter, tUp to leave, ack at L4 (setting)
}
data class LevelTable(val eligibleRoles: Map<DegradationLevel, Set<ExpertRole>>, val tDown: Map<..>, val tUp: Map<..>) // data, loaded from JSON

// ---- modulators (restrict, never grant) ----
data class Modulators(val stress: Float, val reward: Float, val trust: Float, val rest: Float)
interface ModulatorBus { fun read(consumer: String): Modulators; fun publish(signal: ModulatorSignal) }
object SafetyShield { val forbiddenTargets: Set<String>; fun assertNotTargeted(param: String) }

// ---- dispatch ----
data class TaskDescriptor(val id: String, val capability: String?, val safetyTier: SafetyTier,
    val deadlineMs: Long, val needsDeterminism: Boolean, val needsUncertainty: Boolean,
    val mandate: MandateRef?, val trust: TrustLabel, val source: SourceKind)
data class Exclusion(val moduleId: String, val reason: String, val params: Map<String, String> = emptyMap())
data class MaskedCatalogue(val candidates: List<ModuleHandle>, val excluded: List<Exclusion>, val level: DegradationLevel)
interface Eligibility { fun mask(task: TaskDescriptor, all: List<ModuleHandle>, signals: HealthSignals,
                                 level: DegradationLevel, mods: Modulators): MaskedCatalogue }
data class DispatchPlan(val taskId: String, val policyDigest: String, val level: DegradationLevel,
    val primary: ModuleHandle?, val team: List<ModuleHandle>, val mode: RouteMode, val fallbacks: List<ModuleHandle>,
    val excluded: List<Exclusion>, val conf: Float, val crossCheck: ModuleHandle?, val justification: JustificationKind,
    val disposition: Disposition /* DISPATCH | HOLD */) { fun toCanonicalBytes(): ByteArray }
class PlanningRouter(val eligibility: Eligibility, val head: Router /*RAMA*/, val rules: Router, val registry: ModuleRegistry) {
    suspend fun plan(task: TaskDescriptor, query: String, ctx: ConversationContext): DispatchPlan
}

// ---- workspace + store ----
interface Workspace { fun write(b: Binding, writer: ScopeId): WriteResult; fun view(scope: CapabilityScopes): ReaderView }
interface ReaderView { fun byTag(tags: List<String>): List<Binding>; fun similar(text: String, k: Int): List<Pair<Binding, Float>> }
interface OpLog { fun append(stream: String, op: Op): Seq; fun read(stream: String, from: Seq): Sequence<Op>; fun head(stream: String): Digest }
interface SnapshotStore { fun put(stream: String, upTo: Seq, bytes: ByteArray): Digest; fun latest(stream: String): Snapshot? }

// ---- evolution (propose-only) ----
sealed interface Proposal { val id: String; val evidence: Evidence; val reversible: Boolean }
data class SpawnProposal(...) : Proposal; data class RetireProposal(...) : Proposal
data class SpecialiseProposal(...) : Proposal; data class MergeProposal(...) : Proposal
interface Evolver { suspend fun propose(window: TraceWindow): List<Proposal> }          // never mutates the registry
interface ApprovalQueue { fun submit(p: Proposal); fun decide(id: String, approve: Boolean, by: String) }
class ShadowRunner(registry: ModuleRegistry, gate: PromotionGate, sample: SamplePolicy, rest: RestWindow)

// ---- confinement (platform implemented) ----
data class ConfinementPolicy(val fsRead: List<Path>, val fsWrite: List<Path>, val network: NetPolicy, val cpuMs: Long,
    val memMb: Int, val procs: Int, val env: Map<String,String>)
interface ConfinementProvider { fun capabilities(): ConfinementCaps; fun launch(cmd: List<String>, p: ConfinementPolicy): ConfinedProcess }
```

### 5.4 Data and state model

| State | Where | Format | Notes |
|---|---|---|---|
| Module contracts | `<data>/experts/<id>.json` (existing manifest dir) | JSON, `schema:2`, old manifests load with defaults | |
| Lifecycle + promote stack | OpLog stream `lifecycle` | JSONL ops, snapshot every N | rollback = previous stack entry |
| Degradation level + signals | OpLog `health` (sampled, 1 per transition) | JSONL | level history for the UI and for training labels |
| Route trace | existing `RouteTrace` JSONL, extended with plan fields | JSONL | adds `level`, `excluded[]`, `policyDigest`, `modulators`, `lifecycle` of chosen expert |
| Workspace | OpLog `ws/<name>` + snapshots | JSONL + content-addressed blobs | scoped by tags |
| Evolution proposals + approvals | OpLog `evolution` | JSONL | owner decisions are first-class records |
| Shadow results | `<data>/shadow/<expert>/<ver>.jsonl` | JSONL | request hash, served result id, shadow result, score |
| Death certificates + exemplar export | `<data>/graveyard/<id>/` | JSON + JSONL | kept; delete only by owner |
| Policy digest | derived: sha256 over (rules, head weights hash, catalogue hash, level table) | string | stored on every trace |

All writes use `AtomicFile` (tmp + replace) or append + fsync with the digest chain; torn tails are detected and truncated at open.

### 5.5 Desktop, Android, desktop-as-source

- **One code path.** `substrate` and `dispatch` live in `kotmoe-core` and run in-process on both. Only the `SignalSource`s
  and `ConfinementProvider` differ.
- **Android on device (fully standalone).** Signals: `BatteryManager`, `PowerManager` thermal status, `ActivityManager`
  memory, charging/idle/doze. Typical level table: L0 all; L1 drop SELF_LEARNING/TAUGHT adapters and MoA; L2 RAMA + RAG + tools
  only, no general GGUF generation; L3 rules router + deterministic tools + memory lookup; L4 canned/rules floor (alarms, timers,
  calls still work). Shadow runs, learning and consolidation only inside `RestWindow` (charging + idle). All of it works with
  no network.
- **Desktop as optional source.** The desktop is a `SourceModule` on the phone with `needsNetwork=true`, `onDevice=false`,
  health = reachability probe (LAN/Tailscale), so `Eligibility` excludes it automatically when unreachable or when the phone's
  level forbids network use. This replaces today's special-cased `AutoSource` heuristic with the same mask used for every Expert.
- **Sync.** Optional and off by default: exchange OpLog streams (`evolution`, `lifecycle`, exemplars) by `(stream, seq, digest)`
  with an append-only merge; conflicts resolved by per-stream owner (the device that holds the Expert's weights owns its
  lifecycle). No quorum or hormone mirror lag needed.
- **Build target.** The same `substrate` jar goes into the Tauri sidecar (`kotmoe-server`) and the Android app.

### 5.6 Confinement (hard rule)

Organism's `ProcessJail` is Linux-first; on macOS/Windows/nested containers it falls back to rlimits ("namespaces marked
degraded"). That is **not** acceptable for KotMoE. Required instead:

| Platform | Mechanism (KotMoE-implemented behind `ConfinementProvider`) |
|---|---|
| Windows desktop | AppContainer or restricted token + Job Object (CPU, memory, process count, no child escape), deny-by-default filesystem via ACL on a per-task directory, no network capability; a WSL2-VM option for heavier tools. (AgenticBotPlatform already has design material for appcontainer and a VM; reuse the *ideas*, not code, to keep KotMoE self-independent.) |
| Linux desktop | user + mount + pid + net namespaces, seccomp, cgroup limits |
| macOS | sandbox-exec profile (deprecated but working) or App Sandbox helper |
| Android | tools are in-process intents with user confirmation, plus an `isolatedProcess` service for any untrusted parsing |
| Contract | `capabilities()` reports what is really enforced. `ModuleContract.metabolic` and the task's tier require a minimum; if the platform cannot provide it, the module is *excluded* by `Eligibility` (reason `confinement_insufficient`), never silently downgraded. |

Take from organism only: the policy fields, the env-scrub list idea, the shell-escape deny, and the audit-to-trace habit.

---------------------------------------------------------------------------------------------------------------

## 6. What organism changes for RAMA

### 6.1 Routing: eligibility-then-choice (highest value)
- Today `Rama.decide` hands the whole catalogue to the head or the rules router. New flow:
  1. `Eligibility.mask(...)` removes experts that are unavailable, not in DELIBERATION (or SHADOW for the shadow tap),
     above the degradation level's role set, over the task's safety tier, not on-device when offline, lacking confinement,
     out of mandate, or over the cost/latency budget (modulated by `stress`). Each removal is a typed `Exclusion`.
  2. The **masked catalogue** is what RAMA's prompt shows. This fits the v4 training plan exactly: the head already trains on
     *contrastive catalogue twins* (gold expert removed, label changed), so it is taught to read the catalogue rather than
     the query. Eligibility makes that distribution real at run time.
  3. The head picks `{experts, mode, conf}` inside the mask. The grammar-constrained decoder only allows ids in the mask,
     so an illegal route is impossible by construction (`RouteGrammar` already constrains ids).
  4. `conf` below a threshold, a HOLD, or a head failure falls through the chain: rules router → `SELF` → deterministic floor.
     `modulators.stress` raises the cross-check rate (a second Expert verifies or MoA is forced for HIGH-tier tasks).
- **Prompt budget risk:** a 121M model has a short context. The catalogue shown must be top-K (use the embedding match that
  already exists as the fallback to pre-select ~8–12 candidates) after the mask, not the full registry.
- **Determinism:** plan serialised canonically; policy digest in every trace; golden-plan tests per router version.

### 6.2 Expert lifecycle (spawn, specialise, retire, merge). All propose-only.

| Operation | Trigger (from the trace) | Mechanism | Gate |
|---|---|---|---|
| **Spawn** | cluster of queries where RAMA chose SELF or an expert later scored low; or "absent expert" rows (the 0.56 absent case in the v3 error analysis) | first a `MemoryExpert` seeded from the cluster's best outcomes (cheapest); then `AdapterExpert` LoRA; or `DistilledExpert` from a teacher; or a `Composite` of existing Experts | contract four-part check → SANDBOXED (confined) → SHADOW on mirrored traffic (rest window only) → held-out win via `PromotionGate` → EXPLORATION (served only when RAMA's fallback embedding match picks it, capped share of traffic) → DELIBERATION after the next RAMA training includes it |
| **Specialise** | one Expert's per-capability `evalScore` diverges (strong on A, weak on B) or its latency/cost is dominated by a sub-capability | clone + narrow `capabilities`, train/curate on the sub-slice; parent keeps the rest | same ladder; parent version untouched, rollback by retiring the child |
| **Retire** | win rate below threshold over N days *and* a better expert exists; or metabolic inefficiency (measured cost > declared share × margin); or superseded by a merge | `retire()`: DEPRECATED (routes only as fallback), drain, `DeathCertificate` (reason, last version, final scores), `MemoryExport` (exemplars handed to successor/RAG), weights kept N days | **Auto-spawned Experts only.** Built-ins and anything the owner added need an explicit owner decision (no feature removal). |
| **Merge** | a Composite whose members are nearly always called together (cost high, results stable); or two adapters on near-identical capabilities | distil the composite into one Expert (TAUGHT with the composite as teacher), or LoRA weight-merge for adapters | held-out win vs the composite/both parents; parents DEPRECATED, not deleted |

The catalogue grows only through this ladder, so RAMA's prompt never meets an unvalidated Expert, and a new Expert is
usable before retraining via the embedding fallback (as `RAMA_PLAN.md` already specifies).

### 6.3 Self-learning and teaching loops
- Keep `LearningLoop`, `PromotionGate`, `HeldOut`, `JobRunner`. Add **ShadowRunner** as the first stage of every candidate.
- Modulators schedule and throttle (they cannot override the gate):
  - `reward` (mean recent outcome score) raises learning eagerness (smaller min batch), `stress` (error/timeout/rejected
    promotions) freezes learning and shadowing; `trust` (teacher acceptance rate, from `TeachableExpert` outcomes) weights
    teacher curricula; `rest` (idle + charging + night) opens the window for jobs. Half-lives are settings.
- Immune-style **negative memory**: outcomes that were scored near 0 or that a user reversed are stored as known-bad
  signatures (embedding of query + chosen expert); the router penalises repeating them and the trainer uses them as hard
  negatives.
- **Teaching**: organism has no teacher/student notion; keep KotMoE's `TeachableExpert`. Add the organism rule that a
  *student never serves* before shadow ≥ floor, and that `justify()` for high-tier actions must come from a T0/T1 verifier.

### 6.4 Training and evaluation pipeline
1. **Trace → dataset with reasons.** The enriched trace records `candidates`, `excluded[reason]`, chosen route, level,
   outcome score. `rama-kt.datagen` can emit, from real traces: positive rows, **hard-negative rows from `excluded` reasons**,
   and the contrastive twins the v4 plan wants, with real catalogues instead of synthetic ones.
2. **Golden-plan regression.** Fixed task set → `DispatchPlan` canonical bytes per (head hash, level). Run on every export; any
   diff must be explained. This complements the existing parity fixtures (`parity_expected.json`) and the Kotlin parity
   harness, and catches eligibility changes as well as weights.
3. **Replay as eval.** Re-run a trace window through a candidate head with stub tools; compare plans and outcome-weighted
   scores. This is the superagent's "replay" (#21) on organism's OpLog.
4. **Gates as data.** Promotion thresholds (0.85/0.90/0.90/0.85) move to a `gates.json` next to the head (one source for
   `eval.py`, `rama-kt.eval` and the UI); add degradation-level cases (route exactness at L1..L3 catalogues) and a
   shadow-validity gate for live promotion. The PARALLEL-order question stays with the owner (decision 9).
5. **Chaos tests.** A tiny fault injector (timeouts, crashes, slow experts, signal spikes) driving `DegradationMachine` and the
   chain, modelled on organism's `harness/` scenarios; includes a "no network, low battery" scenario for Android.
6. **Training scheduling.** The Training supervisor consults `RestWindow` and `stress` before starting a run on a laptop;
   unchanged on the dedicated machine (setting).

---------------------------------------------------------------------------------------------------------------

## 7. Migration path from today's code

Order chosen so every step is mergeable alone, gated by tests, default behaviour unchanged.

| Phase | Content | Effort | Risk |
|---|---|---|---|
| **S0 Decisions & vocabulary** | owner answers §9 (names, tiers, scope); one glossary; JSON schema for `ModuleContract` v2 | S | wrong names are costly later |
| **S1 Contract + lifecycle** | `ModuleContract`, validator, `LifecycleState` in `ExpertRegistry`, adapter that derives a contract from every existing `ExpertDescriptor` (defaults), manifests `schema:2`, lifecycle events in the trace | M | manifest compatibility; mitigate with default projection and loader tests |
| **S2 Eligibility + plan** | `Eligibility`, `MaskedCatalogue`, `DispatchPlan`, `PlanningRouter` wrapping `Rama.decide`; `RouteTrace` extension; golden-plan tests; off by default (mask = identity) | M | catalogue prompt budget; extra latency (kept sub-ms, it is table logic) |
| **S3 Signals + degradation** | `HealthSignals`, `DegradationMachine`, level table JSON; desktop + Android `SignalSource`s; `/v1/substrate/levels`; UI badge | M | thresholds need field tuning on a real phone; ship observe-only first |
| **S4 Store** | `OpLog`, `SnapshotStore`, replay; move `RouteTrace` writes behind it (keeps file format readable) | M | disk growth on phone; rotation and snapshot cadence |
| **S5 ShadowRunner + generalised promotion** | shadow tap on live traffic, `PromotionGate` gains the SHADOW stage and promote stack; rest-window scheduling | M | battery/CPU; run only on rest, sample rate setting |
| **S6 Modulators + rest window** | `ModulatorBus`, shield, `LearningLoop` throttling; GUI controls | S | name bloat; plain names only |
| **S7 Confinement + ToolHost** | `ConfinementProvider` per platform, with the superagent ToolHost/Mandate (#5, #6) | L | hardest platform work (Windows AppContainer/Job, Android isolated process); shared with the sibling plan |
| **S8 Workspace blackboard** | scoped workspace for Composite teams and the agent loop's working memory | M | do not build before the AgentLoop needs it |
| **S9 Evolution proposals** | Spawner (memory/adapter first), Retirer, then Specialiser and Merger; approval queue + GUI; observe mode first | L | proposal quality; unbounded Expert count; cap and rank by value |
| **S10 Training integration** | trace→dataset with reasons, golden-plan gate, gates.json, replay eval in `rama-kt` | M | v4 data plan is in flight; add after v4, do not mix |
| **S11 Device sync** | OpLog sync phone↔desktop with ownership rules | M | conflict semantics; start read-only |

Rough total ≈ 3 L + 7 M + 3 S, about 12–16 engineer-weeks if serial; S1–S6 (the part that changes RAMA behaviour) ≈ 5–6
weeks. Quick-win order if time is short: S1 → S2 → S3 (these give eligibility + degradation, the most distinctive benefits).

Interaction with the in-flight work: do **not** touch the v4 data/training path before the v4 run lands; S2 only needs the
trace shape. The `rama-kt` Kotlin trainer (K0–K5) is independent. The sibling items #1–#3 (EffectQueue, WorkItem,
AgentLoop) can start in parallel if they target the `OpLog` interface from S4 (an in-memory stub meanwhile).

---------------------------------------------------------------------------------------------------------------

## 8. Risks and mitigations

1. **Organism is partly simulation and its spec is missing.** Adopt concepts and invariants only; write our own tests per
   concept (ladder order, shield, determinism) so we do not depend on unseen documents.
2. **Over-engineering for a 121M model on a phone.** Keep each layer table-driven and optional; ship with identity behaviour
   (mask = all, level = L0) until a layer proves value in observe mode.
3. **Catalogue length vs RAMA context.** Mask then top-K retrieval before the prompt; cap Expert count; spawn-rate limit.
4. **Learned head vs hard constraints.** Constrained decoding over the masked ids; the mask is always final authority.
5. **Shadow cost on battery.** Rest window only, sample rate, hard CPU budget, off by default.
6. **Confinement honesty.** `ConfinementCaps` are reported truthfully; insufficient = excluded, never degraded silently.
7. **Evolution runaway** (too many Experts, thrash). Proposal budget per day, hysteresis on retire/merge, owner approval for
   non-auto-spawned Experts, DEPRECATED before RETIRED, weights retained.
8. **Vocabulary leak.** Organism's biological names are an internal metaphor; do not expose them, and avoid copying
   organism's identifiers wholesale (see licence/privacy below).
9. **Drift between two reports.** Single `substrate` lexicon and one store (§1); review the sibling designs against §5 before
   either is built.
10. **Mobile persistence.** OpLog growth, torn writes. Digest chain with tail repair, rotation, snapshots, and a size cap setting.
11. **Safety posture of "auto-safe" evolution.** Default `observe`; `auto-safe` is limited, reversible, logged, and its scope
    is the owner's call (decision 4).

---------------------------------------------------------------------------------------------------------------

## 9. Licence and reuse

- `LICENSE` in the clone is **Apache-2.0** (full standard text; pyproject says `Apache-2.0`, authors "Organism Contributors"). No
  `NOTICE` file. The repo is the owner's own (`RechargedIdeas/organism`), marked **private** in `README.md`.
- Apache-2.0 allows copying, modifying and redistributing with: the licence text kept, a notice of changes, existing
  copyright/attribution notices retained, and an express patent grant. Not legal advice.
- Because the owner holds the copyright (subject to anything an AI-assisted commit might complicate), they can also relicense
  or contribute code to KotMoE without outside permission. Two practical points remain:
  - **Privacy:** KotMoE is public and organism is private. Pasting organism code, docs or its distinctive identifiers into the
    public repo discloses it. That is the owner's choice (decision 8); the report assumes **concepts only**.
  - **Third-party deps:** nothing in organism's concepts depends on its Python deps (protobuf, grpcio, numpy, blake3,
    cryptography, structlog, pydantic); none would be carried over.
- **May reuse (if the owner decides to publish it):** the contract field set, the lifecycle ladder and level eligibility tables,
  the default thresholds, the shield list, the `ci/gates.yaml` pattern, the test scenarios as specs. Port by hand to Kotlin
  with an attribution comment and a `THIRD_PARTY_NOTICES.md` line (KotMoE already keeps one for `needle/`, Apache-2.0).
- **Reimplement, do not carry over:** all Python code, the proto files, the Rust crates, the PySide6 desktop, the bio/neuro/
  physical modules, the generative code/asset pipelines, and the Linux sandbox (insufficient for KotMoE's rule).
- **Names:** use none of organism's product names, "hormone/immune/organ" terms or the term "Sophont" (organism itself retired
  it) in KotMoE's public API.

---------------------------------------------------------------------------------------------------------------

## 10. Top 10 decisions for the owner

1. **Adopt organism as "concepts, reimplemented in Kotlin"** (recommended), or as a dependency/runtime? (Recommendation: concepts
   only; the Python/Rust code is not usable on Android and breaks self-independence.)
2. **Public vs private:** may organism's design material (contract fields, tables, names) appear in the public KotMoE repo, or
   must the substrate be described only in generic terms (it is generic enough that this is workable)?
3. **Scope of the first slice:** S1–S3 (contract, eligibility, degradation) only, or include shadowing and evolution
   proposals before the next RAMA retrain? (Recommendation: S1–S3, then S5.)
4. **Autonomy of evolution:** `observe` only, `propose` (owner approves each spawn/retire/merge), or `auto-safe` for
   memory/adapter Experts that pass the gate? (Recommendation: observe by default, propose when enabled.)
5. **One risk lexicon:** unify organism tiers (safety/reliability) with the superagent report's mandate strength and tool
   tiers into a single table. Approve the unified table before either S2 or the ToolHost is built.
6. **Eligibility is final authority over RAMA:** confirm that a learned route can never override the mask, and that unmasked
   behaviour exists only as a debug setting.
7. **Degradation levels on Android:** approve the L0..L4 meaning (what disappears at each level) and whether the user may
   override a level ("I'm plugged in, use everything").
8. **Shadow on live traffic:** allowed at all? If yes, only on the desktop, only on the phone while charging, sample rate, and
   whether the content of a real conversation may be copied into a shadow log on disk (privacy).
9. **Confinement targets and the gate itself:** which platforms must be OS-confined first (Windows AppContainer/Job vs WSL2 VM),
   and the open v4 question: score PARALLEL routes by expert set instead of order (worth ~1.3 points, changes the gate).
10. **Retirement policy:** may auto-spawned Experts be retired automatically, may built-ins ever be, and how long are
    weights and certificates kept? (Recommendation: auto-spawned only, DEPRECATED then RETIRED after 30 days, nothing deleted
    without the owner.) Also decide whether to keep a workspace/HDC memory on the roadmap at all or leave it at embeddings.

---------------------------------------------------------------------------------------------------------------

## Appendix A. Organism file index used

`README.md`, `STATUS.md`, `CHANGELOG.md`, `LICENSE`, `pyproject.toml`, `Cargo.toml`, `ci/gates.yaml`,
`docs/architecture/README.md`, `docs/v1.7/ORGANISM_GENERATIVE_EVOLUTION.md`, `docs/v1.10/BARE_METAL_AND_SANDBOX.md`,
`proto/organism/v1/router.proto`, `sdk/python/organism_sdk/{module,contract,registry,router,workspace,hypervector,snapshot,
degradation,autonomic,hormone,immune,interoceptive,learned_ise,circadian,apoptosis,morphogenesis,metamodel,federation,
multinode,trace,device,health}.py`, `sdk/python/organism_sdk/sandbox/policy.py`, `sdk/python/organism_sdk/generative/*`,
`modules/*/module.py` (headers), `runtime/*/src/lib.rs` (sizes only).

## Appendix B. KotMoE file index used

`docs/RAMA_PLAN.md`, `docs/KOTLIN_RUNTIME.md`, `docs/TRAINING_DASHBOARD.md` (head), `kotmoe-core/.../engine/experts/{Expert,
Learning,ExpertRegistry,PromotionGate}.kt`, `engine/rama/{Rama,Router,RouteTrace}.kt`, `engine/agent/KotMoEAgent.kt`,
directory inventory of `kotmoe-core`, `kotmoe-server/.../server/training/**`, and the sibling report
the KotMoE mapping report. Items I did not read line by line: `tauri-app/`, `android-app/` sources
(taken from the docs and the sibling report), `rama-train/` code, `rama-kt/`.
