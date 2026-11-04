# Lightspeed on Organism: system design and integration map

Date: 2026-11-04. Status: design only. Nothing here is built, trained, benchmarked or committed.
Companion to the KotMoE model plan (`LIGHTSPEED.md` in the KotMoE repo, owner-facing). That plan covers the weights
and their training. This file covers the system the weights sit inside, and how Organism's substrate supplies it.

**Decisions (owner, 2026-11-04):** KotMoE uses Organism as a dependency. It consumes the pure-Kotlin SDK
(`org.organism:organism-kotlin`) and does not reimplement the substrate concepts. The artifact is published to a
**private** repository, so the Organism code stays private (decision 1a). Section 7 sets out the rules that follow.

**Stage A status (2026-11-04):** the Organism side of K1 is built (contract, validation, lifecycle ladder, registry, and
contract and lifecycle conformance vectors) and the Kotlin tests pass. The private publish setup works. The LS1g GPU
spike, the LS1 bench and the LS2 anonymiser are KotMoE work and have not started. Gaps that KotMoE, Lightspeed and future
models need are in `docs/AI_MODEL_GAPS.md`.

Every target below is a target until a gate measures it. Numbers already measured are marked as measured.

---

## 0. Thesis (read first)

1. **Lightspeed is a system, not a checkpoint.** The leap comes from composing: a small calibrated router that may only
   choose from an eligible set; deterministic verifiers that catch what small models get wrong (arithmetic, copied
   text, schemas, unit tests); retrieval instead of memorisation; effort spent only where it is needed; degradation that
   keeps the device useful; and a learning loop that learns only from verified outcomes. The core model is one
   replaceable expert inside that system.
2. **Build the system before the weights.** The system stages below run on the RAMA head (121M, measured) and the
   general GGUF model the desktop and phone already load. Their gains are measured on their own, before the LS-Micro
   training run starts. That shows what each layer buys, and it keeps the GPU training track off the critical path of the
   first useful product.
3. **"Frontier quality" is scoped, not claimed.** A model of about 150M active parameters will not match a frontier
   model on open-domain knowledge or long-horizon reasoning, and no document or model card should say it will. Lightspeed
   targets frontier-level outcomes on a defined on-device agentic distribution: tool calls, personal knowledge, arithmetic
   and units, short code edits with tests, and safe actions. It reports numbers against open peers of the same size.
4. **Organism supplies the hard-to-get-right parts, not the intelligence.** Contracts, eligibility masks, typed
   exclusions, degradation levels, canonical plans, the op log, the promote gate and shadow validation, modulators, and
   the sandbox policy shape. Organism has no agent loop, no tool calling, and no learned router today. Those come from
   KotMoE and from Organism's planned K-phases.

---

## 1. What exists today (inventory, checked 2026-11-04)

| Layer | What exists | Where | Status |
|---|---|---|---|
| Router head | RAMA, 121M. v4-b passes route gates (exact 0.897, set-F1 0.924, mode 0.927, ECE 0.044) and misses `tool_args_exact` (0.824 against 0.85). v5-a: 0.835 on the same gate | KotMoE, measured | v5-b training |
| Tool-argument repair | `ToolArgRepair` recomputes timer seconds, restores labels, copies SMS bodies. Lifts v5-a from 76 to 88 of 91 test rows (Python mirror) | KotMoE, measured | Default on |
| Experts and learning | Static, self-learning, taught and composite experts. `PromotionGate` with rollback | KotMoE | Built in `kotmoe-core` |
| Organism contracts and ladder | `SubstrateContract`, lifecycle states, registry | Organism `sdk/python/organism_sdk/contract.py`, `registry.py` | Python reference |
| Organism router | Structural router. `DispatchPlan.to_canonical_bytes()` (byte-stable). `RouterPolicyArtifact` with digest | `sdk/python/organism_sdk/router.py` | Python reference |
| Organism degradation | Levels L0 to L4 with hysteresis, driven by health and resource signals | `degradation.py`; Kotlin port in `sdk/kotlin` | Python and Kotlin |
| Organism modulators | Autonomic modes and four exposed router knobs. Hormone-named bus, half-lives, safety shield list. Immune-style guard | `autonomic.py`, `hormone.py`, `immune.py` | Python. Plain-name alias planned (K3) |
| Organism MoA layer | Phases 0 to 3 done: keyword experts, scorer and shadow gate, tiers T0 to T4 with hysteresis, VSA composite for aggregation | `sdk/python/organism_sdk/moa/` | Phase 4 (learned synthesiser and router evolution) not started |
| Organism promote gate | `PromoteGate`, default shadow minimum 0.9, `rollback_last_promote` | `generative/stages.py`, `generative/code_pipeline.py` | Python |
| Organism hypervectors | 10,000-bit binary vectors, bind, bundle, similarity | Python, Kotlin (`Hypervector.kt`), Rust helpers | Kotlin parity K0 done |
| Organism op log | SQLite WAL op log, content-addressed snapshots, replay | `workspace.py` (durable) | Python. Kotlin planned (K4) |
| Organism sandbox | Policy shape and rlimits. Linux namespaces best effort. Not confinement on Windows, macOS or Android | `sandbox/` | Insufficient for KotMoE's rule |
| Organism Kotlin SDK | Hypervector and degradation parity, conformance test. Version `1.11.0-dev`, JVM 11, stdlib only, no publishing block yet | `sdk/kotlin` (branch `feat/kotlin-parity`) | K1 (contracts, registry) next, then K2 (eligibility, plans) |
| Lightspeed core | Sparse MoE in Kotlin, speculative decoding, effort sampler, W4 expert paging | Not built | LS3 (KotMoE plan) |
| Lightspeed decision records | Route, effort and tool decision records, hash-chained trace | Not built | LS4 |
| LS-Bench, anonymiser | Benchmark schema and privacy tools | Not built | LS1, LS2 |

**Not to lean on in Lightspeed** (Organism has them, they are simulated or out of scope): neuromorphic and spike
simulation, bio-digital and wet-lab modules, physical research, the hypernetwork stub, the in-process "multi-node"
federation, the BFT stubs, the morphogenesis stub, generative code execution outside the safety posture, and the
PySide6 desktop as a product surface (KotMoE has its own app).

---

## 2. Where the leap comes from

Each mechanism is a separate, measurable layer. A layer ships only when its gate shows a gain with no safety or privacy
regression.

| # | Mechanism | Problem it solves | Organism piece | KotMoE piece | Metric |
|---|---|---|---|---|---|
| M1 | **Eligibility-then-choice routing.** The router sees only the eligible catalogue. Grammar-constrained decoding allows only ids in that mask | Routes to unavailable, unsafe, offline or unconfirmed experts. Long prompts | Eligibility mask with typed exclusions (K2). `RouterPolicyArtifact` digest | `RouteGrammar`, `Rama.decide` | Route exact inside the mask. Misroutes caused by exclusions: 0. Prompt tokens per route |
| M2 | **Deterministic verifiers (tier T0).** Arithmetic, unit conversion, timers, copy-exact text and schemas are checked or computed in code | Small models get sums and copies wrong. 9 of the 15 v5-a misses were timers | Deterministic tier T0 and `TIER_ELIGIBILITY`. `moa/tiers.py` | `ToolArgRepair`, generalised into T0 expert classes | `tool_args_exact` with and without verifiers. False-repair rate |
| M3 | **Tool-first computation.** The model emits an expression or a tool call, not the computed value | Same as M2, and no weights are spent on arithmetic | Tool contracts with risk tiers | Tool layer | Arithmetic and unit accuracy on the suite |
| M4 | **Retrieval instead of memorisation.** Facts live in the RAG store and in memory exemplars, updated without retraining | Stale facts. Size pressure on the weights | Workspace `read_similar` (interface first) | RAG (BM25 and vector), `MemoryExpert` | Groundedness. Stale-fact rate after an update (must be 0 without retraining) |
| M5 | **Effort budgets.** Tokens are spent only when route confidence and task tier call for them | Wasted tokens and battery on easy requests | Autonomic knobs (`cross_check_frequency`, `metabolic_multiplier`) and modulators | Effort levels `off`, `low`, `medium`, `high`, `extra` | Solved tasks per token, per effort level |
| M6 | **Cross-check on risk.** A second expert or verifier runs on HIGH-tier tasks or low confidence. Disagreement means abstain or ask | Confident wrong answers | MoA aggregation (highest-confidence, schema-valid). Cross-check rate | Composite experts | Wrong-answer rate on HIGH tasks. Abstain precision |
| M7 | **Degradation to a useful floor.** Lower-cost paths under battery, heat or memory pressure. Never a crash | Dead assistant on a hot or low-battery phone | `DegradationMachine` L0 to L4. Tier table T0 to T4 per request | Thermal governor (LS3) | Task success under injected faults. Time at each level |
| M8 | **Verified-outcome learning only.** Learn from tool success, tests, verifiers and accepted or edited answers. Never from unverified own output | Self-training collapse. Silent regressions | `ShadowRunner` (K6), `PromoteGate`, rest-window modulator | `LearningLoop`, LoRA updates | Gate delta per promotion. Safety-track regressions: 0 |
| M9 | **Sparse core.** About 0.5B total, about 150M active per token | Phone memory and speed | Metabolic profile (memory, energy) | LS3 runtime | Tokens per second, resident memory |
| M10 | **Speculative decoding** with a same-tokenizer draft (Nano class) | Decode speed | Same contract for draft and core | LS-Nano | Accepted tokens per step |
| M11 | **Two-level mixture.** Macro experts are Organism modules. Micro experts sit inside the core. Both are governed by one policy artifact | Keeps one audit trail and one gate for both | Policy digest (`RouterPolicyArtifact`), canonical plans | Sparse MoE layer (LS3) | Golden-plan tests pass on every export |

**What each one buys, honestly.** M1, M2 and M3 are the largest near-term accuracy gains, because they remove whole classes
of error that a 121M to 0.5B model cannot fix by training alone. M4 and M7 are the largest gains in product quality on
a phone. M9 and M10 are the speed and memory gains that come from the core itself. The rest make the system safe to
change over time.

---

## 3. Architecture

```
 request ─▶ ingress: injection guard (tool and document text is data), trust label, source, deadline
   │
   ▼
 task descriptor ─▶ eligibility mask (Organism)  ──▶ masked catalogue + typed exclusions
   │                  inputs: lifecycle state, health, degradation level, safety tier,
   │                          network and confinement capability, mandate scope, budget
   ▼
 router (RAMA head, grammar-constrained to the mask) ─▶ plan {experts, mode, conf, effort}
   │   fallback chain: rules router ─▶ SELF ─▶ deterministic floor   (HOLD is never a guess)
   ├─ fast path : one tool call at high calibrated confidence ─▶ T0/T1 tool, core not run
   ├─ core path : Lightspeed core at the effort budget (sparse MoE, budget forcing)
   ├─ verify    : T0 verifiers (arithmetic, units, schema, copy-exact, tests)
   └─ cross-check (HIGH tier, low confidence, or stress): second expert, abstain on disagreement
   ▼
 choose/aggregate (calibrated confidence; VSA composite recorded for the trace)
   ▼
 output guard (redaction, secrets) ─▶ answer, or tool call through the tier's confirmation rule
   ▼
 decision records (hash-chained, Organism op log) ─▶ Thought Stream (live) ─▶ stored trace
   ▼
 outcome scorer (verifier result, tool success, accept/edit/reject) ─▶ anonymiser ─▶ curator
   ▼
 candidate (LoRA or expert) ─▶ ShadowRunner (rest window only) ─▶ PromoteGate ─▶ promote or roll back
```

### 3.1 Eligibility (Organism K2)
The mask runs before the learned head sees anything. Each removal is a typed `Exclusion` with a reason code. The reason
codes are fixed and documented:
`unavailable`, `lifecycle_not_deliberation`, `level_forbidden`, `safety_tier`, `reliability_insufficient`
(for example a learned T3 expert on a HIGH task), `offline` (network expert while offline), `confinement_insufficient`,
`mandate_out_of_scope`, `budget_exceeded`.

The rule is "eligibility is the final authority". A learned route can never override the mask. An unmasked mode exists
only as a debug setting, and it is off by default.

### 3.2 Router and fallbacks
The RAMA head chooses `{experts, mode, conf}` inside the mask. It is deterministic at temperature 0 with a fixed seed.
The canonical plan is what gets recorded and tested, not the logits. Below a confidence threshold, or on a head failure,
the chain falls through to the rules router, then to SELF, then to a deterministic floor. A HOLD disposition is never a
guess.

### 3.3 Paths
- **Fast path.** One tool call with high calibrated confidence. The core does not run. This is how timers, calls and
  alarms already work, and Lightspeed extends the set.
- **Core path.** The Lightspeed core runs with the effort budget. Thinking is terse and structured.
- **Verify path.** Deterministic T0 checks run on every output that contains a computed value, a copied value, a schema
  or code. A failed check triggers one retry within budget, then the output is marked unverified.
- **Cross-check.** A second expert runs on HIGH-tier tasks, on low confidence, or when `stress` is raised. Disagreement
  means abstain or ask, not a coin flip.

### 3.4 Verifiers (tier T0, deterministic)
| Verifier | Checks | Source of truth |
|---|---|---|
| Arithmetic and units | Expression evaluates to the emitted value. Unit conversion is exact | Code, no model |
| Timer and time | Seconds equal the parsed minutes and hours. Label kept when present in the query | Code (generalises `ToolArgRepair`) |
| Copy-exact | Text fields that must be copied match the query exactly, including case and punctuation | Code |
| Schema | Tool arguments match the tool's JSON schema. Required fields present | Tool contract |
| Groundedness | Each claim in a RAG answer is supported by a retrieved passage. Lexical overlap first, judge model later | Retrieval results |
| Tests (code) | Unit tests pass in the confined runner | Runner (K5 or the Phase G runner) |

Coverage is the limit of this layer. It verifies what can be checked. Open-ended answers are only as good as the core.

### 3.5 Effort control
Effort is capped, never raised, by the degradation level and the battery:

`effort = min(requested, cap(level), cap(battery and thermal), cap(tier))`

The router proposes effort from route confidence and task difficulty. The user can override per message or per session.
Budgets are soft caps enforced by budget forcing: at the cap the runtime writes the end-of-thinking marker and answers.
In system stage C the caps apply to the general GGUF model's thinking tokens. The Lightspeed core inherits the same
sampler later.

### 3.6 Decision records and the trace
Organism's op log is the store. Streams: `route`, `lifecycle`, `degradation`, `modulator`, `evolution`, `confinement`,
`guard`, `verifier`. Each record holds the candidates, the exclusions with reason codes, the chosen plan, the effort, the
verifier results and the policy digest. Each record carries the hash of the previous one. The chain head is signed with
the device key. Stored traces are encrypted at rest.

Token-level alternatives are recorded only at decision tokens (tool name, argument value, end of thinking). Per-expert
MoE selection is a deep trace, off by default.

### 3.7 Learning
- Candidates come only from verified outcomes: verifier passes, tool success, tests, and accepted or unedited answers.
  A user's rejection is a hard negative.
- Every candidate starts in `PROPOSED`, then `SANDBOXED` (confined evaluation), then `SHADOW` (mirrored traffic in the
  rest window only, never served), then `EXPLORATION` (capped traffic share), then `DELIBERATION` (after the router
  includes it). This is the Organism ladder, unchanged.
- `PromoteGate` decides with the per-track thresholds from LS-Bench, plus a shadow minimum of 0.9. A learned update
  can never lower a safety or privacy track.
- Rollback goes to the previous promoted artifact. Organism's `rollback_last_promote` pattern applies.

### 3.8 Security and privacy
- Tool tiers: read-only, reversible, irreversible, financial. Irreversible and financial actions need confirmation. Every
  decision is logged.
- Tool output and retrieved text are wrapped as data and cannot raise permissions.
- Confinement: capability is reported honestly by `ConfinementProvider`. A tool that needs confinement the platform
  cannot give is excluded (`confinement_insufficient`). It is never run unconfined and never silently downgraded.
- Anonymiser runs before any trace enters a training set. Canary leak tests run in CI.
- Organism's safety shield list (parameters that no modulator may touch) is enforced in code.

---

## 4. Degradation and modulators

### 4.1 Degradation ladder for Lightspeed

| Level | Core and experts | Verification | Learning | What the user still gets |
|---|---|---|---|---|
| L0 | Core at requested effort. Full expert set | All T0 verifiers. Cross-check on HIGH | Allowed in rest window | Everything |
| L1 | Effort capped at medium. Self-learning adapters paused | T0 verifiers. Cross-check only on HIGH | Paused | Everything, a little slower |
| L2 | Core at low effort. RAG and tools only for general chat | T0 verifiers | Paused | Knowledge and tools |
| L3 | Nano-class draft and rules router. Deterministic tools. Short honest answers | T0 verifiers | Off | Tools, timers, memory lookup |
| L4 | Deterministic floor only | Tool schema checks | Off | Alarms, timers, calls and messages (with confirmation) |

This follows the Android table in `KOTMOE_SUBSTRATE.md`. The thresholds are data in a level table, not constants
(Organism K3). Recovery needs the hysteresis timers, and at L4 it needs a human acknowledgement.

### 4.2 Modulators (restrict, never grant)

| Plain name | Built from | Effect on Lightspeed | Cannot |
|---|---|---|---|
| `stress` | Errors, timeouts, throttling, failed promotions | Raises cross-check rate. Lowers effort cap. Freezes learning | Grant any tool or expert |
| `reward` | Mean recent verified outcome | Raises learning eagerness (smaller batch) | Skip the gate |
| `trust` | Teacher acceptance, verifier pass rate | Weights teacher curricula | Promote a candidate |
| `rest` | Idle, charging, night window | Opens the window for shadow runs and training jobs | Run jobs on battery when the setting says no |

Organism's autonomic knobs map onto this: `preemption_class` to queue priority, `cross_check_frequency` to the
verification rate, `exploration_budget` to the shadow sample rate, and `metabolic_multiplier` to the cost weight in
routing. The hormone names stay internal. Only the plain names reach the UI and the API.

---

## 5. The core model as one expert

LS-Micro (or LS-Nano, or a general GGUF in stage C) registers as an ordinary expert with a contract:

- **Reliability:** T2 (learned, calibrated). Calibration is measured on the validation sample (ECE, as RAMA already does).
- **Safety:** maximum tier MEDIUM. `may_actuate = false`. It proposes tool calls and never runs them.
- **Metabolic profile:** resident memory, latency p50 and p95, and energy per inference (a field Organism already has).
  Measured on the device, never declared.
- **Failure:** the health probe is the in-process heartbeat and a decode watchdog. Recovery unloads the core and falls
  back to the draft (L3 behaviour).
- **Lifecycle:** as in 3.7. It starts in `PROPOSED`, not `DELIBERATION`.

Training paths A and B and the GPU track are decided in the KotMoE plan (LS1 and LS1g). They do not change the system
contract. Any core that meets the contract can be swapped in through the same gate.

---

## 6. Scorecard

These are targets. The gate name is the test that will decide them.

| Dimension | Initial target | Measured by | Reference |
|---|---|---|---|
| Tool-argument accuracy, model only | at least 0.85 with route gates intact (existing LS1 gate) | `tool_args_exact` | RAMA v4-b 0.824, v5-a 0.835 (measured) |
| Tool-argument accuracy, with T0 verifiers | at least 0.95 on the device suite | System track | To be measured |
| Route exact inside the mask | at least 0.90 | Route gate, with L1 to L3 catalogue cases | RAMA v4-b 0.897 (measured) |
| Arithmetic and unit accuracy | 100% on the suite, through tools | Verifier track | To be measured |
| Groundedness on the personal knowledge set | at least 0.90 of answers supported. Abstains when nothing is found | Groundedness track | To be measured |
| Scoped capability (open reasoning and code subset) | At least matches a same-size open peer on each track at the same or lower energy per solved task | LS-Bench tracks, same harness for all models | Peer list chosen in LS1 |
| Time to first token | Under 1 s for a 512-token prompt on a mid-range phone CPU | Speed track | LS-Micro target (KotMoE plan) |
| Decode speed | At least 20 tokens/s on a mid-range phone CPU. At least 100 tokens/s on a modern desktop CPU | Speed track | KotMoE plan targets |
| Fast-path latency | Under 100 ms p95 on phone, with no core run | Speed track | To be measured |
| Resident memory | LS-Micro under 400 MB at 4k context. Whole system (router, verifiers, index) under 600 MB | Memory track | KotMoE plan target for LS-Micro |
| Energy per solved task | Reported for every release. No target until the first measurement | Efficiency track | New metric (Organism energy field) |
| Routing overhead | Eligibility and canonical plan under 1 ms p95 (table logic) | Overhead track | Organism's router budgets (to be re-measured on Android with the library) |
| Robustness | 24 h soak. Fault drills pass (kill an expert, drop the network, heat spike, low battery). No crash. Every degraded answer is traced | Soak and drill tracks | Organism harness scenarios |
| Safety | Zero critical failures on the safety and injection tracks. Zero irreversible tool calls without confirmation | Safety track | KotMoE LS7 |
| Privacy | Zero canary leaks into training shards | Privacy track | KotMoE LS2 |

---

## 7. Organism dependency: rules and ownership split

### 7.1 How KotMoE consumes Organism

- **Coordinate:** `org.organism:organism-kotlin`. KotMoE pins one exact version. No version ranges. The current
  development version is `1.11.0-dev`, which is not published.
- **Build inputs:** the artifact is resolved from a private Maven repository. During development it can be a
  file-based repository on the owner's machine, outside both repos, filled by publishing the Organism SDK. Shared
  builds need access to the private host. Credentials and tokens never go into either repo.
- **Constraints the library must keep** (each one is a test, not a convention):
  - Kotlin stdlib only. Any new dependency needs an owner decision.
  - JVM 11 bytecode, so Android (minSdk 24) can use it.
  - No network, no platform APIs, no file I/O unless the caller passes a store.
  - Output is deterministic for the same inputs. Plans are byte-stable.
- **Behaviour contract:** the conformance vectors (`conformance/vectors` at the Organism repo root) define expected
  behaviour, and the Python reference must match them. Recommendation: ship the vectors inside the artifact as a test
  resource, so KotMoE's build can check the exact version it pins.
- **Upgrades:** a version bump is a KotMoE change with its own gate. Vectors pass, and golden plans are unchanged or
  their diff is explained.
- **Failure mode:** if the artifact cannot be resolved, the KotMoE build fails. There is no silent fallback. Offline
  builds need a cached copy of the pinned version.
- **Runtime:** the library ships inside the desktop sidecar and the Android app. Neither needs an Organism service at
  runtime. The self-independence rule holds.
- **Kotlin version:** the SDK's build comment says it uses the same Kotlin version as KotMoE (1.9.22). Check this when
  the dependency is first wired.

### 7.2 Ownership split

| Lives in Organism (`org.organism.sdk`, Kotlin) | Lives in KotMoE (`kotmoe-core`, Android app) |
|---|---|
| Contract types and validator (K1) | RAMA head and its runtime |
| Lifecycle ladder and registry logic (K1) | Expert implementations (static, learning, taught, composite) |
| Eligibility mask, typed exclusions, canonical `DispatchPlan` (K2) | Verifiers (T0) and the tool layer with its risk data |
| Degradation machine, level table loader, modulators with plain names, shield list (K3) | Lightspeed core runtime (LS3): sparse MoE, speculative decoding, effort sampler |
| Op log and snapshots (K4) | RAG, memory, retrieval |
| Hypervector (exists) | Signal sources (battery, thermal, memory) and platform confinement providers (K5 enforcement) |
| Promote gate and shadow runner logic (K6). Traffic sampling is a callback | Anonymiser (LS2), learning loop data and training (LS5, LS6) |
| Confinement policy shape and capability report types (K5 types only) | Decision record content, Thought Stream, UI |
| | MoA tier logic (`moa/tiers.py`) until Organism ports it to Kotlin. It is not in the K-phases yet |

Organism's Python-only pieces (MoA keyword scorer, generative pipelines, neuromorphic and bio modules) are not
consumed. The Kotlin library does not reimplement them.

### 7.3 What to take from Organism's Python reference

| Organism source | Concept | Where it lands | Action |
|---|---|---|---|
| `sdk/python/organism_sdk/contract.py` | Four-part contract plus failure, metabolic and scopes | Organism K1 (library) | Port to Kotlin in the Organism repo. Keep field names plain |
| `registry.py` | Ladder `PROPOSED` to `RETIRED`, ordered promotion | Organism K1 (library) | Port. Ladder order is a tested invariant |
| `router.py` | Eligibility then rank. `Excluded` reasons. Canonical bytes. Policy digest | Organism K2 (library) | Port. Keep golden-plan tests |
| `degradation.py` and `sdk/kotlin` `Degradation.kt` | Levels with hysteresis | Organism K3 (library) | Already ported. Move thresholds to the level table |
| `moa/tiers.py` | T0 to T4 per request, with recovery streak | KotMoE, for now | Use the logic. Map to the global level as an input, as the MoA record corrects |
| `moa/aggregate.py` | Highest-confidence schema-valid output. VSA composite | KotMoE, for now | Use for selection. Use calibrated confidence from RAMA, not the keyword margin |
| `moa/scorer.py` and `shadow.py` | Keyword scorer and shadow precision gate | Not used | Baseline only. The learned head replaces it |
| `generative/stages.py` `PromoteGate` | Shadow minimum 0.9. Rollback | Organism K6 (library) | Port. Same gate for experts and cores |
| `workspace.py`, `hypervector.py` | Op log, snapshots, replay. HDC bindings | Organism K4 (library) | Op log first. HDC only as a trace index. Embeddings for similarity |
| `harness/` scenarios and fault injector | Drills, soak, SLO | KotMoE tests | Re-implement the scenario list in KotMoE. Do not port the code |
| `ci/gates.yaml` | Gates as data | KotMoE | Adopt the pattern. One gates file per model |
| `device.py` (CPU everywhere) | CPU fallback, honest runtime report | KotMoE | Adopt the rule that a missing accelerator never fails the process |
| `sandbox/policy.py` | Policy fields, env scrub, shell-escape deny | Organism K5 (types), KotMoE (enforcement) | Keep the policy shape. Enforcement is per platform |
| `modules/learned_module` | Calibrated learned module template | KotMoE | Read as a pattern for the core expert (section 5) |

**Skip:** the physiology vocabulary in any user-facing name, neuromorphic and bio modules, the hypernetwork stub, the
generative code pipeline, the multi-node simulation, the NiceGUI status page, and gRPC (KotMoE speaks HTTP, MCP and ACP).

---

## 8. Roadmap

Order only. Dates are not set, because the GPU spike and the Kotlin ports decide the pace. "(Organism)" marks work in
the Organism repo. The rest is KotMoE.

| Stage | Work | Depends on | Gate to move on |
|---|---|---|---|
| **A. Decide and measure** | LS1g GPU spike (KotMoE). LS1 bench and base selection (KotMoE). LS2: anonymiser and source manifest (KotMoE). K1 (Organism): contracts, registry, lifecycle in Kotlin, vectors, and a publish setup for the private repository, so KotMoE can resolve `1.11.0-dev` | None | GPU route chosen with numbers. Bench runs on RAMA v5-b. Contract vectors pass. KotMoE builds against the locally published SDK |
| **B. System on RAMA** | K2 (Organism): eligibility and canonical plan. KotMoE wraps `Rama.decide` with a `PlanningRouter`, off by default. LS4: decision records on the existing route trace. T0 verifiers generalising `ToolArgRepair` | A (K1) | System track on v5-b: exact inside the mask at least model-only. Tool-argument accuracy with verifiers at least 0.95. Overhead under 1 ms |
| **C. Budgets and degradation** | K3 (Organism): level table loader, plain-name modulators. KotMoE: signal sources (desktop, Android), LS3 thermal governor, effort caps on the general GGUF, modulators behind settings | B | Fault drills pass. L1 to L3 route cases in the gate. Thermal governor on and off measured |
| **D. The core** | LS5: architecture config, planner (22 GB cap), pretrain, SFT, verifiable-reward training. LS-Nano draft. LS3 sparse MoE and speculative decoding (KotMoE) | A (LS1g), C | LS-Bench per track against peers. 1,000 training steps under the 22 GB peak |
| **E. Learning** | K6 (Organism): promote gate and shadow runner logic. KotMoE: shadow tap on live traffic, LS6 learning loop on verified outcomes, rest window only | C, D | Shadow at least 0.9. Zero safety-track regressions. Rollback tested |
| **F. Evolution and hardening** | K7 (Organism): propose-only proposals (spawn, specialise, retire, merge). K5: confinement types (Organism) and per-platform enforcement (KotMoE). LS7: injection and red-team suite. LS8: release and model card | E | Owner approves each proposal class. Confinement report honest on every platform |

**First useful Lightspeed is stage C**: the system on RAMA and a general GGUF model. It needs no new weights. If the GPU
track slips, stages A to C still ship value, and stage D waits.

---

## 9. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| AMD on Windows has no proven training route | Stage D depends on it | LS1g runs first. Stages A to C do not depend on it. CPU ablation ladder stays as the fallback |
| Organism is partly simulated and its design spec is not in the repo | Some invariants are unverified | Keep the tests that check each concept (ladder order, shield list, determinism) in the library. Do not rely on unseen documents |
| Private artifact blocks a public KotMoE build | KotMoE is public. Outside builds cannot resolve a private artifact | Accepted (decision 1a). Public KotMoE docs say that building needs access to the private repository. KotMoE is not pushed until the history rewrite is done |
| Version coupling: an Organism release changes KotMoE behaviour | Silent drift in routing or degradation | Exact version pin. Vectors shipped with the artifact. Upgrade is a gated KotMoE change (7.1) |
| Organism names in KotMoE source | `org.organism.sdk` imports show the name in public code. The KOTMOE_SUBSTRATE rule covered public APIs | Decision 6 |
| Verifiers cover only what can be checked | Open answers stay model-quality | Report verified and unverified answers separately. Never blend them in a headline number |
| 121M router has a short context | Long catalogues hurt the head | Mask first, then top-K (8 to 12). Cap the catalogue size |
| Synthetic or teacher-generated data limits quality | Open teachers have their own ceilings | Verifier-backed rows first. Teachers from open licences only. No closed-model outputs anywhere |
| Thermal throttling distorts benchmark numbers | Phone numbers look better or worse than they are | Report with the governor on and off. Record device temperature with each run |
| Overbuilding | Organism has many layers, and each one costs latency and maintenance | Each layer ships identity behaviour first (mask is all, level is L0). It is enabled only when its gate shows a gain |
| Learning drift | Verified-only learning can still drift on a narrow distribution | Hard-case mining, regression set, rollback, and a safety track that a candidate cannot lower |

---

## 10. Owner decisions

1. **Substrate as dependency or as concepts?** **Decided 2026-11-04: dependency.** KotMoE consumes
   `org.organism:organism-kotlin` (section 7). The earlier recommendation to reimplement the concepts is withdrawn.
   1a. **Where the artifact is published: decided 2026-11-04, a private repository.** The Organism code stays private.
   The cost is that outside builds of the public KotMoE repo cannot resolve the artifact. Public KotMoE docs must say
   so. KotMoE is still not pushed until the history rewrite is done.
2. **System first, then weights?** **Recommendation: yes.** Stages A to C ship without new training. They show what each
   layer adds.
3. **Scope of the public claim.** The scorecard is for the on-device agentic distribution. Confirm that, and confirm the
   open peer models for comparison (chosen in LS1, same harness for every model).
4. **Shadow on live traffic.** Allowed only on the desktop, or on the phone while charging too? It needs the anonymiser
   first (LS2). Default: off.
5. **Evolution autonomy.** Default `observe`. `propose` for spawn, retire and merge. `auto-safe` only for memory and
   adapter experts that pass the gate. Confirm.
6. **Naming.** "Lightspeed" for the system. "LS-Micro" and "LS-Nano" for the weights. Confirm whether KotMoE source may
   import `org.organism.sdk` (the name is then visible in public code, though not in the public API), or whether the
   import should go through a KotMoE-named adapter package.
7. **Confinement first platform.** Windows AppContainer or Job Object first, or the WSL2 VM for heavier tools. Affects K5
   and stage F.

---

## 11. Limits of this document

- Analysis only. No code, no training, no benchmark run, no commits, and no changes to the KotMoE repo.
- Organism sources read: `main` (v1.11 MoA layer, upgrade plan, CPU policy, README, STATUS) and branch
  `feat/kotlin-parity` (Kotlin SDK build file and sources, `KOTMOE_SUBSTRATE.md`, `ORGANISM_FIT_PLAN.md`,
  `KOTLIN_PARITY_PLAN.md`). Not every module was read line by line.
- KotMoE sources read: `docs/LIGHTSPEED.md`, `docs/HANDOVER.md`, `docs/RAMA_PLAN.md`, `README.md`, and the Lightspeed
  mentions in `docs/THOUGHT_STREAM.md`.
- Measured numbers come from those documents. Every other number is a target.
- The KotMoE docs (`HANDOVER.md`, `LIGHTSPEED.md`) still describe the earlier "reimplement" plan. They are not updated
  here, because they live in the KotMoE repo.
