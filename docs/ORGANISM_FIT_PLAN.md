# Where Organism fits: superagent mapping + pure-Kotlin agent loop + KotMoE

> **Status (2026-11-04):** the dependency model in section 3 is confirmed: KotMoE depends on `org.organism:organism-kotlin`,
> published to a private repository. Organism does not reimplement the concepts in KotMoE. Current state and next steps are
> in `HANDOVER.md`.

Date: 2026-11-01. Plan only. No KotMoE repo edits. Inputs: `KOTMOE_MAPPING.md` (D1-D27), `KOTMOE_AGENT_LOOP_PLAN.md` (phases A-H),
`KOTMOE_SUBSTRATE.md` (Organism analysis), and the live Organism fork at this repository
(branch `feat/kotlin-parity`, K0 done: Kotlin SDK with hypervector + degradation machine bit-exact against Python vectors;
plans in `docs/KOTLIN_PARITY_PLAN.md` and `docs/INTEROP.md`).

## 1. One-paragraph answer

Layering, bottom to top: **Organism (substrate)** gives KotMoE the generic runtime pieces that are not specific to an
assistant: contracts, lifecycle ladder, eligibility masks, degradation levels, op log/snapshots/replay, modulators,
confinement policy shape, evolution proposals. **The agent loop (phases A-H)** is KotMoE's own, runs on top and calls
Organism for the cross-cutting parts. **The superagent items (D1-D27)** are the organisation layer (work items, mandates,
attention, effects) and mostly stay KotMoE-owned, except where they are the same thing Organism already defines (store,
health, replay, shadow/observe). Organism never depends on KotMoE; KotMoE depends on `org.organism:organism-kotlin`
(pure Kotlin, stdlib only, JVM 11), which is why it is safe for Android and for the self-independence rule.

```
 KotMoE product layer   Tauri Assistant page · Android UI · /v1/agent/* · MCP/ACP
 ------------------------------------------------------------------------------
 KotMoE agent layer     AgentLoop (A) · ToolHost+Tiers (B) · Mandate/Policy/Trust (B) · PlanTemplates (E)
                        WorkItem/Attention (D2,D9) · Sources/Triggers (D11) · RAMA router + Experts
 ------------------------------------------------------------------------------
 Organism (substrate)   ModuleContract · Lifecycle ladder · Eligibility mask · DispatchPlan · Degradation L0-L4
                        OpLog/Snapshot/Replay · Modulators · ShadowRunner · Evolution proposals · Confinement policy
 ------------------------------------------------------------------------------
 Platform adapters      Desktop JVM: process confinement, power/thermal   Android: BatteryManager, isolated process
```

## 2. Ownership table (D-items and loop phases)

Legend: **OWN** Organism builds it, KotMoE consumes; **SUPPLY** Organism supplies a primitive, KotMoE builds the product piece on it;
**KEEP** stays purely KotMoE (Organism has no business there); **REPLACE** Organism's version supersedes the planned one.

| Item | Owner | Detail |
|---|---|---|
| D1 EffectQueue | SUPPLY | Organism op log gives append-only JSONL, digest chain, torn-tail repair, snapshots. KotMoE builds `EffectQueue` (idempotency keys, ordering per key, 2 s to 60 s backoff) as a *stream* on it. Delivery semantics stay KotMoE's (Organism's `AT_LEAST_ONCE` channel has nothing durable). |
| D2 WorkItem / WorkStore | SUPPLY | WorkStore = op log stream + snapshot. Stage derived, as designed. |
| D3 / Phase A AgentLoop | KEEP | Organism has no agent loop. Each loop step becomes a `TaskDescriptor` into Organism's dispatch, so the loop inherits eligibility, degradation and tracing. |
| D4 Gate / Assessor | SUPPLY | Gate = Eligibility mask (hard) + mandate check; Assessor stays RAMA-based. Organism supplies typed exclusion reasons. |
| D5 Mandate / Policy | SUPPLY | Organism owns tiers (SafetyTier, ReliabilityTier, `may_actuate`) and the "restrict, never grant" shield; KotMoE owns Mandate (who asked, scope, tool allow-list). Rule: call allowed iff `mandate.scope contains tool.risk` AND module tier eligible. One lexicon, see §4.3. |
| D6 / Phase B ToolHost, RiskTier | SUPPLY | Organism supplies `ConfinementPolicy` + `ConfinementProvider` interface and capability reporting. `RiskTier` (READ, LOCAL_WRITE, DEVICE_STATE, LEAVES_DEVICE, SPEND) stays KotMoE's and maps to SafetyTier for eligibility. |
| D7 Accept modes off/observe/auto | REPLACE | Same thing as the lifecycle ladder: observe = SHADOW stage, auto = DELIBERATION. One implementation (Organism lifecycle) serves both rules and Experts. |
| D8 Outcome to learning | SUPPLY | Organism's reward modulator, shadow results and trace-with-reasons are the data; KotMoE's `LearningLoop` consumes them. |
| D9 Attention / Ask | KEEP | Human-facing; not substrate. |
| D10 Trust labels | SUPPLY | Organism's anomaly guard (immune-style, propose-only quarantine) adds known-bad pattern memory; label propagation itself is KotMoE's. |
| D11, D12 Sources, subscriptions | KEEP | A Source can be modelled as an Organism module with role FRONTEND, but routing of conversations is product logic. |
| D13 Pause / E-stop | SUPPLY | Degradation machine L4 plus human ack is the system-wide analogue; per-item pause stays KotMoE's. |
| D14 Slots | SUPPLY | Concurrency budget comes from degradation level and modulators (Android N=1). |
| D15 Jobs | KEEP | Reuse `JobRunner`. |
| D16-D18 Prompts, skills, versioned settings | KEEP | Organism's artifact store with version history and rollback may back `VersionedStore` later (optional). |
| D19 Health model | REPLACE | Organism `HealthProbe` + escalation + recovery procedure + degradation. The 3-strike rule is its default. |
| D20 Panel | KEEP | New "Substrate" page (levels, lifecycle, modulators, shadow results) is additive. |
| D21 Replay / shadow review | OWN | OpLog + `toCanonicalBytes()` plans + replay runner. Built once in Organism K2/K4, used by KotMoE as the gate before any rule goes to `auto`. |
| D22 MCP/ACP | SUPPLY | Organism gateway (K8) can host substrate tools; KotMoE's existing server stays the single surface (see decision 8). |
| D24 Coding executor | KEEP | Needs the confined runner (G). |
| D27 Desktop/Android handoff | SUPPLY | Op-log stream sync with per-stream ownership. |
| Phase E plan templates | SUPPLY | Masked catalogue and `<plan>` rows: templates are Organism "modules" with contracts; eligibility removes templates the level or mandate forbids. |
| Phase F free planning flag | SUPPLY | Reliability tier T3 for free-planned steps; HIGH tier tasks exclude T3 by the eligibility table. |
| Phase G confined runner | SUPPLY (policy) / KEEP (implementation) | Organism defines policy fields and capability report; per-platform enforcement is KotMoE-implemented (Organism's Linux jail is not enough; Windows AppContainer/Job and Android isolated process needed). |
| Phase H retire TS agent | KEEP | Organism not involved; its scenario list is the parity input. |

Net new from Organism for KotMoE: degradation levels, lifecycle/shadow, eligibility with exclusions, canonical plans and
replay, modulators, evolution proposals. Nothing in the loop's control flow moves into Organism.

## 3. Interfaces between Organism and KotMoE

All are Kotlin interfaces in `org.organism.sdk`; KotMoE adapts its existing types (no KotMoE type leaks into Organism).

### 3.1 ToolHost
```kotlin
// KotMoE side (phase B), Organism-aware
interface ToolHost { specs(); validate(call); summarize(call); suspend run(call, ctx) }
// Organism side: each tool is advertised as a module contract so eligibility can mask it
data class ToolContract(val name: String, val riskTier: RiskTier /*mapped*/, val safetyTier: SafetyTier,
                        val confinement: ConfinementRequirement, val needsNetwork: Boolean, val onDevice: Boolean)
interface ConfinementProvider { fun capabilities(): ConfinementCaps; fun launch(cmd, policy): ConfinedProcess }
```
Rule: if `capabilities()` cannot satisfy a tool's requirement, Eligibility excludes it with `confinement_insufficient`.
There is no silent downgrade, which is how "no unconfined execution" becomes mechanical rather than conventional.

### 3.2 WorkItem / EffectQueue
```kotlin
interface OpLog { fun append(stream: String, op: Op): Seq; fun read(stream: String, from: Seq): Sequence<Op>; fun head(stream: String): Digest }
interface SnapshotStore { fun put(stream: String, upTo: Seq, bytes: ByteArray): Digest; fun latest(stream: String): Snapshot? }
```
Streams: `work/<id>`, `effects`, `lifecycle`, `health`, `evolution`, `route`. KotMoE's `WorkStore`/`EffectQueue` are thin
state machines folding these ops; `AtomicFile` backs the default file implementation, Room may back it on Android.
Language-neutral JSONL so desktop and phone exchange streams by `(stream, seq, digest)`.

### 3.3 Policy / Mandate
```kotlin
// KotMoE
data class Mandate(scope, allowedTiers: Set<RiskTier>, toolAllow: Set<String>, network: Boolean, policyVersion: Int)
// Organism
data class TaskDescriptor(id, capability, safetyTier, deadlineMs, needsDeterminism, needsUncertainty, mandate: MandateRef?, trust: TrustLabel, source: SourceKind)
interface Eligibility { fun mask(task, all: List<ModuleHandle>, signals: HealthSignals, level: Level, mods: Modulators): MaskedCatalogue }
```
`MandateRef` is an opaque id plus the tier set; Organism does not interpret scope text. Mandate stays immutable; widening is
a new run, as the loop plan already requires.

### 3.4 Learning outcomes
Organism emits typed trace entries (route plan with `excluded[reason]`, lifecycle, degradation, modulators, shadow result).
KotMoE joins them to `Outcome(score)` by trace id. Consumers: `LearningLoop` (batches), `rama-kt.datagen` (hard-negative rows
from exclusions, real catalogue twins), `PromotionGate` (adds the SHADOW stage). Modulators: `reward` and `stress` throttle
learning; they cannot override the gate.

### 3.5 Signals
`SignalSource` per platform feeds `HealthSignals` into the degradation machine; level table is data (JSON), proven by
vectors. KotMoE decides what each level removes (Android table in §5).

## 4. Ordering against phases A-H

Principle: A and B do not wait for Organism; Organism pieces slot in behind interfaces KotMoE already needs.

| Order | KotMoE phase | Organism phase | Why this pairing |
|---|---|---|---|
| 1 | A (loop core, fake tools) | K1 (contract, lifecycle) | independent; A uses an in-memory store behind `OpLog` |
| 2 | B (ToolHost, tiers, Mandate, trust) | K2 (eligibility, canonical plan, trace) | tiers and the eligibility table must be one table; decide §4.3 before either lands |
| 3 | C (Android adapter, WorkStore, EffectQueue, resume) | K4 (op log, snapshots, replay) + K3 (degradation signals on Android) | C needs a durable store; build it once |
| 4 | D (SSE routes, ModelSource.runAgent) | none | plain KotMoE work |
| 5 | E (plan templates, `<plan>` rows) | K2 done; trace-with-reasons feeds data | wait for RAMA v4 data work, as already planned |
| 6 | F (free planning) | K6 (shadow runner) | observe new rules and free-planned steps in shadow before `auto` |
| 7 | G (confined runner) | K5 (confinement policy + providers) | one design, implemented per platform; owner approves test results |
| 8 | H (retire TS) | none | |
| after | | K7 (spawn/retire/merge proposals), K8 (gateway) | needs outcomes and the Agents page |

### 4.3 The shared lexicon (must be fixed before B/K2)
| KotMoE | Organism | Rule |
|---|---|---|
| RiskTier READ | SafetyTier LOW | no confinement beyond path allow-list |
| LOCAL_WRITE | MEDIUM | confined runner required |
| DEVICE_STATE | MEDIUM | human confirm on Android |
| LEAVES_DEVICE | HIGH | trust must be TRUSTED, else human confirm |
| SPEND | CRITICAL | T0/T1 verifier justification + human confirm; learned modules excluded |
| Expert STATIC/SELF_LEARNING/TAUGHT/COMPOSITE | ReliabilityTier T0-T1 / T2 / T2-T3 / derived | HIGH and CRITICAL tasks exclude T3 |

## 5. Android versus desktop

| Capability | Android (fully on device) | Desktop |
|---|---|---|
| Substrate library | same jar, in `kotmoe-core` | same |
| Signals | BatteryManager, thermal status, memory, charging/idle | process load, hardware guard, power |
| Degradation levels | L0 all; L1 drop MoA and learning adapters; L2 RAMA + RAG + tools only; L3 rules router + deterministic tools; L4 canned floor (alarms/timers/calls) | L0-L2 normally, shown in the Substrate page |
| Store | file op log or Room behind `OpLog` | files |
| Tools | `DeviceTool` set behind ToolHost, intents + confirm | READ tools first, then confined LOCAL_WRITE/shell |
| Confinement | app sandbox + `isolatedProcess` for untrusted parsing | AppContainer/Job (Windows), namespaces (Linux), sandbox-exec (macOS) |
| Shadow and learning | only inside the rest window (charging + idle), sample rate setting | on schedule, hardware-guarded |
| Evolution proposals | observed, executed on desktop only | proposals generated and approved here |
| Sync | optional op-log stream exchange with desktop | desktop as optional source (a module with `needsNetwork=true`) |
| Network required | never | never (bridges stay opt-in) |

## 6. Risks

1. **Two lexicons / double stores** if A-C proceed alone. Mitigation: fix §4.3 and the `OpLog` interface first (decisions 1-2).
2. **Dependency direction slip.** If Organism ever needs a KotMoE type, self-independence is lost. Mitigation: Organism ships no KotMoE import; adapters live in KotMoE; CI check on the dependency graph.
3. **Premature substrate** slowing the loop. Mitigation: loop A-B ship with identity behaviour (mask = all, level = L0); each Organism layer starts in observe mode.
4. **Public/private split.** Organism is private, KotMoE public. Consuming the jar from a public build either publishes source or requires a private artifact. Needs decision 3.
5. **Catalogue and prompt budget** for the 121M router: mask then top-K before the prompt; plan templates count as catalogue entries.
6. **Confinement is the long pole** (G/K5) and owner-approved; nothing above READ runs on desktop until then.
7. **Battery cost** of shadow runs on Android: rest window only, off by default.
8. **Parity drift** between Python and Kotlin Organism: conformance vectors are a CI gate; reference stays Python until the owner says otherwise (decision 4).
9. **Effort concentration**: one person across KotMoE, Organism and RAMA v4. The ordering in §4 keeps the first four steps independent.

## 7. Owner decisions needed

1. Approve the unified tier table (§4.3) as the single risk lexicon for ToolHost, eligibility and Mandate.
2. Approve `OpLog`/`SnapshotStore` as the one durable store for WorkStore, EffectQueue, route trace and lifecycle (file-based default, Room optional on Android).
3. How KotMoE (public) consumes Organism (private): vendored jar built privately, Maven artifact in a private registry, or publish `sdk/kotlin` as its own public repo (concepts-only sources). Also whether Organism's Kotlin SDK may itself become public.
4. Is Python the permanent reference with Kotlin as a conformant port, or should Kotlin become the reference once K3 is done?
5. Observe/shadow on live conversations: allowed? where is the log kept, how long, is conversation content stored.
6. Android degradation levels: confirm what disappears at each level and whether the owner may force a level.
7. Confinement: platforms in order (Windows AppContainer/Job vs WSL2 VM first) and who signs off the confinement tests that unlock G.
8. Single API surface: should Organism's gateway (K8) exist at all, or does KotMoE's server remain the only HTTP/MCP/ACP surface that exposes substrate routes?
9. Evolution autonomy: observe, propose with approval, or limited auto for memory/adapter Experts; retirement rules for built-ins versus auto-spawned.
10. Pace: continue Organism K1 (contract + lifecycle Kotlin) in parallel with loop phase A now, or sequence Organism after loop B?

## 8. Immediate next steps (no KotMoE edits)

- Organism: K1 in the fork (Kotlin contract, validator, lifecycle ladder, vectors), then K2.
- Hand the interface sketches in §3 to the loop plan so A/B code against `OpLog`, `Eligibility`, `ConfinementProvider` as local interfaces first.
- Keep this file and the Organism docs (`docs/KOTLIN_PARITY_PLAN.md`) in step as decisions arrive.
