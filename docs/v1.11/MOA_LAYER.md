# MoA Layer: Design Record (v1.11)

Status: Phases 0 to 3 implemented and tested. Phases 4 (synthesizer and router
evolution) and 5 (judge and guardrails) are not started. Covers the plan in
[docs/UPGRADE_AND_EXPANSION_PLAN.md](../UPGRADE_AND_EXPANSION_PLAN.md).

Code: `sdk/python/organism_sdk/moa/`. Tests: `sdk/python/tests/test_v111_moa_*.py`.
Gates: `v111:*` entries in `ci/gates.yaml`.

## 1. What it does

A mixture-of-experts layer on top of the existing substrate:

- **Experts** are in-process modules with a capability descriptor, a health report,
  and a declared resource profile. They register in the existing registry as
  `SubstrateContract`s with `may_actuate=False` and reliability tier T0.
- **Capability scorer** routes a query to experts by keyword match.
- **Shadow gate** measures the scorer against a labeled set before it is allowed to route.
- **Aggregation** picks the highest-confidence schema-valid output. It records every
  output in a VSA composite that can be queried back by role.
- **Tiers T0 to T4** decide how much of the expert set serves a request, with
  hysteresis on recovery.

## 2. Corrections to the upgrade plan

Found while building. These change the plan in
[docs/UPGRADE_AND_EXPANSION_PLAN.md](../UPGRADE_AND_EXPANSION_PLAN.md).

1. **Tiers are not the `DegradationMachine`.** The machine tracks global levels L1 to L4
   over time. MoA tiers are chosen per request from expert health, latency budget, GPU
   availability, and the global level. The global level enters as an input: L4 forces T4.
2. **"Module ABC" is `OrganismModule`.** The experts implement the registry's health
   protocol but do not implement `OrganismModule.handle`. They are routed by the MoA
   pipeline, not by the structural router's dispatch path.
3. **Paths use the real package name `organism_sdk`.**
4. **The contract has no text output form.** Text-producing experts declare
   `SYMBOLIC_TRIPLE` for now. Adding a text form is a contract and proto change.
5. **The contract has no GPU requirement enum.** `HardwareRequirement` has no GPU value.
   `CapabilityDescriptor.requires_gpu` is the source of truth for the MoA tier logic,
   and the contract declares `NONE`.
6. **The generative pipeline does not evolve routing policies.** It evolves code and skill
   bundles. Router evolution (Phase 4) needs a new policy artifact type.
7. **Workspace integration is in-process.** The aggregation composite is not written to
   `WorkspaceClient`. Connecting the two needs roles, tags, and registry wiring.
8. **VSA capacity is not the binding limit at these sizes.** The plan assumed a finite
   capacity that would constrain experts per request. Measured recovery holds up to 64
   experts (8 random trials per count). `MAX_EXPERTS_PER_REQUEST = 8` is a latency
   policy, not a capacity limit.

## 3. Experts (Phase 1)

- `CapabilityDescriptor`: expert id, domain, task forms, keywords, role, declared latency,
  GPU requirement. Task forms and roles are validated against `DEFAULT_FORM_TO_ROLES`.
- `Expert` protocol: `descriptor`, `health()`, `answer(query, form)`.
- `ExpertOutput`: expert id, payload (text), confidence in [0, 1], schema validity.
- Reference experts (`reference.py`), both rule-based, CPU-only, deterministic:
  - `intent_classifier`: domain `intent`, form `pattern_recognition`, role PREDICTION.
    Confidence is the share of matched keyword evidence that supports the best intent.
    This is a rule margin, not a calibrated probability.
  - `extractor`: domain `extraction`, form `feature_extraction`, role FEATURE_EXTRACTOR.
    Extracts ISO dates, email addresses, and numbers. Confidence is 1.0 when anything is found.
- `register_experts` registers each contract in `EXPLORATION` state. The registry's
  `health()` reports each expert's live status.

## 4. Capability scoring and the shadow gate (Phase 2)

- `LexicalScorer`: an expert's score is its matched keyword count divided by a saturation
  value (default 2), capped at 1. Saturation stops a long keyword list from being penalized.
  Phrases match on word boundaries.
- Routes:
  - `expert` when the top score clears `min_score` (0.5) and leads the runner-up by `min_margin` (0.25).
  - `unsure` when no expert clears `min_score`, or the top two are too close.
  - `llm_fallback` only when no expert clears `min_score` and fallback is enabled.
    Off by default (decision D3).
- `shadow.evaluate` runs the scorer over a labeled set and reports per-domain precision.
  The gate: precision ≥ 0.90 in every domain with at least 5 predictions, and no regression
  in the structural baseline on form-given items.

**Result on the synthetic set** (`sdk/python/tests/data/moa_routing_synthetic.json`, 35 items):

| Measure | Result |
|---|---|
| Intent precision | 17 / 17 (1.00) |
| Extraction precision | 12 / 13 (0.92) |
| Unsure correct | 5 / 6 |
| Structural baseline | 16 / 16 (1.00) |
| Gate | passes |

Known weakness: the bare verb "find" routes a generic query ("Find the best coffee shop
nearby") to the extractor. One more such false positive would drop extraction below 0.90.
The gate passes today by one item. The set is synthetic. Passing it does not establish
precision on real traffic. Options for the weakness: require two keyword matches for
generic verbs, or add a stop-keyword list.

## 5. Aggregation (Phase 3)

- **Selection:** the highest-confidence schema-valid output. Ties break on expert id.
  No generative synthesis.
- **VSA composite:** each output contributes three role-bound facts,
  `expert ⊗ payload`, `confidence ⊗ level`, and `schema ⊗ flag`, all bundled into one
  hypervector. A clean-up memory of this request's candidates recovers each fact.
- **Cap:** `MAX_EXPERTS_PER_REQUEST = 8`. The pipeline raises `top_k` no higher than this.

## 6. Tiers (Phase 3)

| Tier | Condition | Executed path |
|---|---|---|
| T0 full | Every active expert healthy and within budget | Run all healthy experts; aggregate |
| T1 reduced | Some active experts unhealthy; two or more healthy | Run healthy experts; aggregate |
| T2 single | Reduced to one healthy expert | Run that expert alone; no aggregation; schema check still applies |
| T3 CPU | An active expert needs a GPU and none is available | Skip GPU experts; run the rest on CPU; aggregate |
| T4 deterministic | No healthy expert, global level L4, or no schema-valid output | Deterministic fallback |

- **Active set:** the top-k experts with any keyword evidence. A query that only one
  expert is relevant to is not a degradation: it is T0.
- **Hysteresis:** demotion takes effect immediately. Promotion needs `recover_after`
  (default 3) consecutive observations of the better tier. A different better target
  restarts the streak. An observation at the current tier clears it.
- **Failed experts stay in the active set.** They count against the healthy total, so a
  failure shows up as a tier change.

## 7. Verification

- Fast suite: 447 passed, 4 skipped, 4 failed. The 78 new v1.11 tests pass. The four
  failures existed before this work and share one cause. See section 8.
- `ruff check` is clean on the new code.
- Rust workspace: not run. `organism-proto` needs `protoc`, which is not installed here.

## 8. Known issues

- **Evolve wall-clock budget fails on this Windows machine.** Four tests:
  `test_v17_generative::test_evolution_runtime_hot_register`,
  `test_v17_generative::test_wall_clock_budgets_recorded`, and two desktop evolution tests.
  All four check `within_wall_clock_budgets()`. `evolve_ms` measures about 434 ms against a 250 ms budget. The sandbox runs its child with the `spawn` start method,
  which costs about 100 ms per child on Windows before any imports. The budget was set for
  a platform where `fork` is cheap. Budgets are unchanged. A per-platform budget is a
  decision for the maintainer (see the upgrade plan).
- **Soak executable-bit test** is skipped on Windows. It still runs on Linux, and the
  git index records mode `100755` for `scripts/soak_target.sh`.
- **Rust workspace tests** need `protoc` on `PATH`, or `PROTOC` set to its path.

## 9. Not started

- **Phase 4:** synthesizer SLM, and router-policy evolution through the promote gate.
  Needs a routing-policy artifact type and a learned backend.
- **Phase 5:** judge, guardrail, and red-team module families.
- **Learned backends:** the thread's Phi-4-Mini and Qwen3-1.7B. Decision D1 is still open.
  The `Expert` protocol is the place they plug in.
- **Phase 6:** lifecycle and provenance. Optional (decision D4).
