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
| Extraction precision | 10 / 10 (1.00) |
| Unsure correct | 6 / 6 |
| Structural baseline | 16 / 16 (1.00) |
| Gate | passes |

**Result on the held-out set** (`sdk/python/tests/data/moa_routing_heldout.json`, 24 items). Labels were fixed from each query's meaning before any scorer change was measured.

| Measure | Result |
|---|---|
| Intent precision | 8 / 8 (1.00) |
| Extraction precision | 7 / 7 (1.00) |
| Unsure correct | 8 / 8 |
| Structural baseline | 3 / 3 (1.00) |
| Gate | passes |

**Fixed weakness.** The bare verb "find" routed generic queries ("Find a good recipe for dinner") to the extractor. Held-out extraction precision was 0.78. The verb is no longer an extractor keyword; its targets ("dates", "numbers", "emails") carry the signal. The held-out set exposed this flaw, so it is no longer an untouched holdout. Measure any further change on a new labeled set.

**Known recall gap.** The noun "email" is not an extractor keyword, so extraction queries built around "email address" go unsure. The strict `xfail` test in `test_v111_moa_routing.py` pins one case. Adding "email address" and "email addresses" as keywords was measured and rejected. On the fresh set `sdk/python/tests/data/moa_routing_email_recall.json` (13 items, labels fixed before the trial), recall rose from 1/7 to 7/7, but the four negatives such as "Set up a new email address for the new hire" also routed to the extractor. Extraction precision fell to 7/11, below the 0.90 gate. Closing the gap needs a context rule: a keyword that counts only when a source reference such as "in this" or "out of" is present. That is a scorer design change, not a keyword edit. `sdk/python/tests/test_v111_moa_email_routing.py` keeps the four negatives unsure in the meantime. The fresh set has now been used for one measurement, so it is no longer untouched.

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

- Fast tier (`python ci/run.py run --tier fast`): 58 of 58 gates pass in 166 s. This includes
  `suite:fast`, the `v17:*` budgets, `v18:desktop_polish`, `v10:rust` and `rust:clippy`.
- `suite:fast` (`pytest -m 'not slow'`): 510 passed, 4 skipped, 1 xfailed, 0 failed.
- `tests/ci` (the local pipeline's own tests): 57 passed.
- `ruff` and `mypy` pass their ratchets against the recorded baselines. `rustfmt` and `clippy`
  report zero findings.
- Nightly tier, run before the Rust clean-up: 60 of 60 pass in 589 s. `slow:wall_clock_full`
  takes 462 s. `slow:soak_full` runs the extended 240-window soak and passes.

## 8. Known issues

- **Evolve wall-clock budget is now per platform.** Four tests failed on Windows:
  `test_v17_generative::test_evolution_runtime_hot_register`,
  `test_v17_generative::test_wall_clock_budgets_recorded`, and two desktop evolution tests.
  They checked `within_wall_clock_budgets()` against 250 ms, but `evolve_ms` measured about 434 ms.
  The sandbox runs its child with the `spawn` start method, which costs about 100 ms per child on
  Windows before any imports. `EVOLVE_BUDGET_MS` in `sdk/python/organism_sdk/generative/budgets.py`
  is 1000 ms on Windows and 250 ms elsewhere. Windows measured median 440 ms, p95 452 ms, max 501 ms
  over 15 runs. Linux has not been measured and keeps 250 ms. All four tests pass in the fast tier.
- **Soak executable-bit test** is skipped on Windows. It still runs on Linux, and the
  git index records mode `100755` for `scripts/soak_target.sh`.
- **Rust workspace tests** need `protoc`. The local pipeline resolves it from the `PROTOC` variable, then `.venv/Scripts/protoc.exe`, then `PATH`.

## 9. Not started

- **Phase 4:** synthesizer SLM, and router-policy evolution through the promote gate.
  Needs a routing-policy artifact type and a learned backend.
- **Phase 5:** judge, guardrail, and red-team module families.
- **Learned backends:** the thread's Phi-4-Mini and Qwen3-1.7B. Decision D1 is still open.
  The `Expert` protocol is the place they plug in.
- **Phase 6:** lifecycle and provenance. Optional (decision D4).
