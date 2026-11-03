# Organism Upgrade and Expansion Plan

- **Status:** Draft for review. Not approved.
- **Date:** 2026-11-03
- **Baseline:** Organism v1.10.0 (see [CHANGELOG.md](../CHANGELOG.md)); 377 tests passing under `-m 'not slow'`.
- **Source:** DeepSeek share `https://chat.deepseek.com/share/06or3m42rv9g0raup0`. 96 messages, 2026-10-31 to 2026-11-03. Archived locally at `chat_archive/Provide_comprehensive_in_depth_and_detailed_suggestions_for.md`. That archive is untracked and not committed.

## 1. Summary

The thread proposes a **mixture-of-SLMs layer built on Organism**, not beside it. Each purpose-built small model becomes an Organism module. A capability-aware routing stage sits on top of the existing structural router. Expert outputs are aggregated in the VSA workspace instead of by an LLM. Degradation tiers map onto the existing `DegradationMachine`. Every change to an expert or router goes through the existing promote gate.

Organism already has most of the substrate the thread needs. The new work is:

1. Capability-aware routing.
2. VSA-based aggregation.
3. MoA-specific degradation tiers.
4. A judge and guardrail module family.
5. Promote-gated evolution of experts and routers.

The second half of the thread (about 40 continuation turns) moves into governance, legal, lifecycle, and philosophical topics. Little of it has a code-level hook in the repo. Treat it as a backlog of design notes, not as roadmap (see section 5).

**Recommended scope:** Phases 0 to 5 in section 3. The thread's timeline is about 16 weeks, but it is an estimate and has not been validated.

## 2. Current state

### 2.1 Primitives that already exist

| Capability | Where it lives | Relevance to the thread |
|---|---|---|
| Module contract | `sdk/python/organism_sdk/contract.py` (`SubstrateContract`) | The integration point for each SLM. Part of the API freeze. |
| Structural router | `sdk/python/organism_sdk/router.py`; `runtime/router/` (Rust) | Stage 1 pre-filter. Deterministic. |
| Shared workspace | `runtime/workspace/`; `sdk/python/organism_sdk/workspace.py`; `hypervector.py` | Aggregation substrate and routing-trace store. |
| Degradation | `sdk/python/organism_sdk/degradation.py` (`DegradationMachine`); `runtime/degradation/` | Basis for tiers T0 to T4. |
| Promote gate and rollback | `sdk/python/organism_sdk/generative/stages.py` (`PromoteGate`, default shadow minimum 0.9); `generative/code_pipeline.py` (`rollback_last_promote`) | Governs every expert and router revision. |
| Probabilistic module template | `modules/learned_module/` (T2, conformal intervals, `may_actuate=false`) | Template for SLM expert modules. |
| Deterministic fallback | `modules/deterministic_engine/` | Basis for tier T4. |
| Hosted LLM backend | `sdk/python/organism_sdk/generative/backends.py` (`HostedLLMBackend`) | Optional. Off by default (`ORGANISM_LLM_ENABLED`). |

### 2.2 Constraints that apply

- **CPU Everywhere.** Every SLM needs a CPU path. See `docs/CPU_EVERYWHERE.md`.
- **Actuation.** Bio and wet-lab actuation is hard-refused. See `docs/ops/WETLAB_SAFETY_POLICY.md`.
- **Hot-registered capabilities** start at EXPLORATION with `may_actuate=False`.
- **Docker is optional.** Bare metal is the primary target.

### 2.3 Not present yet

No directory or module exists yet for any of the following (checked against `modules/` and `sdk/python/organism_sdk/` at the time of writing):

- SLM expert modules
- A capability-scoring stage in the router
- VSA role-binding aggregation
- A judge or guardrail module family
- A red-team module family
- MoA tier-transition gates in `ci/gates.yaml`

### 2.4 Corrections to the thread

- The thread's paths use `sdk/python/organism/`. The real package is `sdk/python/organism_sdk/`.
- The thread refers to a "Module ABC". The real contract type is `SubstrateContract` in `contract.py`.
- The thread's `[reference:N]` citations were not checked and are not relied on here.

## 3. Phased plan

Week numbers are the thread's estimates. They are not validated.

### Phase 0: Lock interfaces (week 0 to 1)

- Freeze the module contract (`SubstrateContract`), the routing-trace schema, and the degradation-tier semantics.
- Write a short architecture decision record for the MoA layer.
- **Exit:** `tests/contract` green. No changes to frozen symbols.

### Phase 1: Two SLM experts as modules (weeks 1 to 3)

- Build two experts on disjoint domains. The thread names Phi-4-Mini and Qwen3-1.7B as examples only (decision D1).
- Implement each as a module modeled on `learned_module`. Each exposes a capability descriptor, confidence signals, a resource profile, and degradation metadata.
- Each expert needs a CPU path.
- **Exit:** Both register, pass health checks, and stay at EXPLORATION until promoted.

### Phase 2: Capability routing in shadow (weeks 3 to 6)

- Add a Stage 2 scorer: a frozen sentence encoder plus a small learned projection. It outputs an enum over the experts plus `unsure` and `llm_fallback`.
- Run it in shadow beside the structural router. Log every decision to the workspace as a routing trace.
- **Gate:** at least 90% per-domain routing precision, and no regression in `sdk/python/tests/test_router_m3.py` or the `router:determinism` gate.
- **Data:** 200 to 500 labeled query–domain pairs (thread estimate). Use synthetic or user-owned examples. Do not commit real chat content.

### Phase 3: VSA aggregation and tiers T0 to T4 (weeks 6 to 10)

- Encode each expert output as a role-bound hypervector. Start with the simplest rule: pick the highest-confidence schema-valid binding by role cue. No generative synthesis yet.
- Map tiers T0 to T4 onto `DegradationMachine`, with hysteresis so the tier does not oscillate.
- Run fault-injection drills: kill an expert, corrupt routing scores, remove workspace bindings. Verify tier transitions and trace completeness. Update `docs/ops/DEGRADATION_DRILLBOOK.md`.
- Add MoA tier-transition budgets to `ci/gates.yaml` as blocking gates.
- **Exit:** Every tier is exercised by the harness and every transition leaves a complete trace.

| Tier | Condition | Metabolism |
|---|---|---|
| T0 Full MoA | All experts healthy, workspace available, latency budget met | Capability routing, parallel experts, VSA aggregation |
| T1 Reduced MoA | One or more experts unhealthy or over budget | Healthy experts only; missing-role tolerance |
| T2 Single expert | One healthy expert within budget | Highest-confidence expert; no VSA aggregation; schema check still enforced |
| T3 CPU fallback | GPU unavailable or throttled | Quantized expert on CPU; relaxed latency SLO |
| T4 Deterministic | No expert can serve within constraints | `deterministic_engine`; `llm_fallback` only if generation is required |

### Phase 4: Synthesizer and router evolution (weeks 10 to 16)

- Add a lightweight synthesizer SLM for the case where VSA aggregation is insufficient (strong disagreement on open-ended tasks). Gate its use behind a disagreement threshold and a latency check.
- Extend the generative pipeline to propose router-policy revisions. Run them in shadow.
- Promote a revision only after it beats the hand-tuned baseline in shadow for a sustained window. Use the soak cadence in `docs/ops/SOAK_RUNBOOK.md`.
- Rollback uses the existing `rollback_last_promote`.
- **Exit:** At least one evolved router revision promoted through the gate, with a tested rollback.

### Phase 5: Judge, guardrails, red team (after Phase 3; can overlap Phase 4)

- **Judge:** a distinct expert family. Calibration matters more than size, so measure calibration first.
- **Guardrails:** pre-generation jailbreak and prompt filtering, plus schema and groundedness checks. Each is a module with a declared contract.
- **Red team:** a module family that attacks the router as well as the experts.
- **Exit:** False-positive and false-negative rates documented for each guardrail. Red-team suite runs in CI as non-blocking first, then blocking.

### Phase 6: Lifecycle and provenance (optional; scope decision D4)

- Provenance and an AI bill of materials for each expert artifact, using the existing artifact store and promotion history.
- Migration cost as a promote-gate metric. Decommission steps for retired experts.
- Include only items that map onto existing artifacts and gates.

## 4. Gates and metrics

| Gate | Threshold | Source |
|---|---|---|
| Expert promotion | Shadow score ≥ 0.9, plus per-domain metrics | `PromoteGate` default |
| Router promotion | ≥ 90% per-domain precision; no structural regression | Thread, Phase 2 |
| Tier transitions | Blocking budgets in `ci/gates.yaml` | Phase 3 |
| Production outcomes | Fallback rate, cost per successful query, user acceptance | Thread, section 6 risks |
| Adaptation speed | Time from new expert to promoted expert | Thread's "time-to-adapt" metric |

## 5. Backlog: parked, not roadmap

These chapters have no implementation hook in the repo, or conflict with current policy. Keep them as design notes. Do not schedule them.

- **Embodiment and physical actuation** (control-path boundary, latent world-action models, runtime assurance shield). Conflicts with the actuation refusal policy. Revisit only with a separate safety case.
- **Legal and regulatory routes** (conformity attestation, liability, insurance, certification bodies, resolution planning). Needs legal review, not code.
- **Long-horizon custodianship and inheritance** (succession runbooks, bequest, terminal states, seven-generation framing). No measurable acceptance criteria in the thread.
- **Legitimacy, dissent, ownership, forgetting, meaning, repair, exit, and constitution chapters.** Philosophical framing. No testable criteria.
- **Engine landscape** (photonic, DNA, quantum, neuromorphic silicon). Research. Organism's stance is RESEARCH_SIM only.
- **Carbon-aware scheduling, multi-tenant isolation, federation.** Plausible later. No current requirement.

Some chapters are written in Chinese. Translate before any of them is used as a reference.

## 6. Risks

| Risk | Why it matters here | Mitigation |
|---|---|---|
| Router promote gate never clears | Aggregate accuracy may stay below the bar with many experts | Gate on per-domain precision and coverage. Promote one domain at a time. |
| VSA capacity | Superposing many bindings degrades retrieval | Cap simultaneous bindings. Use clean-up memory and role-cue unbinding. |
| Tier thrashing | Physiological routing and MoA routing can interact | Hysteresis. Require a sustained condition before a tier change. |
| Contract explosion | Every expert and router revision adds surface | Freeze the contract. Version capability descriptors, not contracts. |
| Evolution drift | Routers may optimize shadow metrics that diverge from production value | Put production-outcome metrics into the promote gate. |

## 7. Decisions needed from you

- **D1.** Which domains and base models for the first two experts?
- **D2.** Is CPU-only the first target? (Current default under CPU Everywhere.)
- **D3.** May a hosted LLM serve as `llm_fallback`? It is off by default.
- **D4.** Include Phase 6 (lifecycle and provenance) in scope?
- **D5.** Should `chat_archive/` be committed, gitignored, or moved out of the repo? It holds the full chat text.

## 8. What was checked and what was not

- **Checked:** The Organism identifiers in section 2 exist in the repo. Organism's status, baseline, and constraints come from `STATUS.md`, `README.md`, and `CHANGELOG.md`.
- **Read in full:** The thread's Organism-specific section (its section 1 to 6, roughly lines 386 to 512 of the archive).
- **Read by heading only:** The first-four-weeks implementation section and the later governance chapters.
- **Not checked:** The thread's timelines, numeric thresholds (200 to 500 examples, 90% precision, 0.9 shadow), and external citations.
- **No tests were run.** This is a documentation change only.
