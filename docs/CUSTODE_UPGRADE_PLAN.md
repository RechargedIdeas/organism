# Custode Upgrade Plan

- **Status:** Proposed. Phase 0 (interface lock) is documentation only. No code and no proto changes are made in this
  change. Phases 1 to 5 wait for the decisions in section 8.
- **Date:** 2026-11-05
- **Baseline:** Organism v1.10.0 (latest tag, see [CHANGELOG.md](../CHANGELOG.md)). The v1.11 MoA layer is in progress
  (phases 0 to 3, see [v1.11/MOA_LAYER.md](v1.11/MOA_LAYER.md)). The v1.12 work agent has a design record and a pure
  domain layer (see [v1.12/WORK_AGENT.md](v1.12/WORK_AGENT.md)).
- **Source:** the Custode documentation suite and the design thread it summarizes. Both are archived outside this
  repository. No chat content is committed here.
- **Companion:** the Custode repository (`custode`), whose `docs/organism/` folder holds the proposal this plan is
  built from. Organism's `docs/custode/` holds the detailed design.

---

## 1. Summary

Custode is an on-device browser agent. It sees a page, routes a request to narrow experts, proposes an action, and
asks the user before anything writes. It would run as an Organism application.

Organism would gain a browser runtime (a Source), a perception task form, provenance labels on channels and triggers,
and a learning loop in which adapters are artifacts with promote gates. Custode would gain Organism's promote gates,
trust store, sandbox, and audit path, rather than building its own.

The proposal is additive. Every new field and value uses a number after the current maximum, and no existing number is
reused, as the API freeze requires. The first draft of the proposal used numbers that collided with existing values,
and named types that do not exist. Section 3 lists those corrections, and `docs/custode/CONTRACT_EXTENSIONS.md` has
the corrected numbers.

**Recommended scope:** Phase 0 now (this document and the `docs/custode/` package). Phase 1 once decision O-11 is taken.
Phases 2 to 5 are designs first, and each needs its own decision before code.

---

## 2. Current state

Verified on 2026-11-05 in this worktree. Each line names the file.

- **Proto.** Nine files in `proto/organism/v1/`. The API freeze makes field numbers and existing enum values immutable
  (`docs/API_FREEZE_v1.0.md`, and the rule it carries from `docs/API_FREEZE_v0.4.md`).
- **Task forms.** `TaskForm` in `router.proto` has values 0 to 13. `TASK_FORM_CAUSAL_INFERENCE` is 5.
- **Output forms.** `OutputForm` in `contract.proto` has values 0 to 9.
- **Metabolic profile.** `MetabolicProfile` in `contract.proto` (line 123) has `requires_gpu` at 8, memory fields at 5
  and 6, and fields 10 to 12. Its highest field number is 12.
- **Channel.** `Channel` in `contract.proto` (line 299) has fields 1 to 7. Delivery is `AT_MOST_ONCE`,
  `AT_LEAST_ONCE`, `EXACTLY_ONCE`, or `STREAMING`.
- **Trigger.** `Trigger` in `trace.proto` (line 100) has fields 1 to 3.
- **Calibration.** `calibration.proto` has `CalibrationCertificate` (line 34), with `CalibrationDeclaration`,
  `TimeWindow`, and `Split`. Organism has conformal calibration (`UNCERTAINTY_CONFORMAL_INTERVAL`). It has no ECE,
  Brier score, or reliability diagram in proto.
- **Python SDK.** `CapabilityDescriptor` (`sdk/python/organism_sdk/moa/experts.py`, line 77) is a dataclass and has
  `requires_gpu`. `ArtifactKind` (`sdk/python/organism_sdk/generative/artifacts.py`, line 20) is the literal set
  `code`, `asset`, `skill`, `manifest`, `pack`. `ArtifactStore` is in the same file.
- **Promote gates.** The order is contracts, sandbox, shadow, promote, and rollback deregisters
  (`docs/AUDIT_v1.8.md`). `rollback_last_promote` is in `desktop/organism_desktop/service.py`.
- **MoA tiers.** Tiers T0 to T4 are chosen per request. The global `DegradationMachine` (levels L1 to L4) is separate, and
  it enters tier selection as an input (`docs/v1.11/MOA_LAYER.md`, section 6).
- **Guardrails.** A rule-based guardrail and red-team section is in `docs/v1.11/MOA_LAYER.md` (section 10). The code path
  is not verified here.
- **Trust.** An Ed25519 `TrustStore` with separate author and approver keys (`organism_sdk/signing.py`,
  `registry.py`). Decision S1 in the Organism plan covers the approver's role.
- **Sandbox.** `ProcessJail` (`sdk/python/organism_sdk/sandbox/jail.py`) with a network allowlist and shell-escape denial.
- **Work agent.** The chain is Source, Trigger, Eval, Mandate, Ticket, Channel (`docs/v1.12/WORK_AGENT.md`). The first
  Source is GitHub (decision W-D3). The executor is the Claude Code CLI in print mode (W-D1a). The domain types, the
  admission gate, and a versioned `Policy` are in `sdk/python/organism_sdk/work/`.
- **CI gates.** `ci/gates.yaml`. The gates this plan depends on are `hygiene:staged`, `hygiene:tree`, `proto:lint`
  (which regenerates `sdk/python/organism_sdk/_proto` from `proto/`), `contract:validate`, `registry:api`,
  `work:domain`, and `suite:fast`. The API freeze test is `sdk/python/tests/test_api_freeze.py`.

---

## 3. Corrections to the first draft

The first draft of the Custode proposal, and the thread behind it, claimed the following. The repository says otherwise.

| Claim | Correct |
|---|---|
| `TaskForm` has `TASK_FORM_TEXT`, `SYMBOLIC`, `TEMPORAL`, `SPECTRAL`, and `PERCEPTION = 5` | None of the first three exist. 5 is `TASK_FORM_CAUSAL_INFERENCE`. Use `PERCEPTION = 14`. Audio is not part of the browser design, so no value is added for it. |
| `OutputForm` has `OUTPUT_FORM_OBSERVATION = 4` and `OUTPUT_FORM_TOOL_CALL = 5` | The prefix is `OUTPUT_`, and 4 and 5 are taken. Use `OUTPUT_OBSERVATION = 10` and `OUTPUT_TOOL_CALL = 11`. |
| `CapabilityDescriptor` is a proto message, with `requires_gpu = 10` and a new `vram_budget_bytes = 11` | `CapabilityDescriptor` is a Python dataclass. In proto, `MetabolicProfile` has `requires_gpu` at 8 and fields 10 to 12. Add `vram_budget_bytes = 13` to `MetabolicProfile`. |
| Every `ModuleRequest` and `ModuleResponse` gains input and output labels | Neither message exists in `proto/`. Labels go on `Channel` (field 8) and `Trigger` (field 4). |
| `VisionModule`, `PlannerModule`, `VerifierModule`, `RouterExpert` | None exists in the repository. They are new modules, and each needs a design. |
| `FlowLabel`, `LearnedAdapter`, `FeedbackEvent`, `CalibrationReport` as proto | None exists. `CalibrationCertificate` covers calibration evidence. `LearnedAdapter` is an `ArtifactKind` literal. `FeedbackEvent` is a Python work-domain type first. |
| The promote order is static, contract, sandbox, shadow, promote, rollback | Contracts, sandbox, shadow, promote, with rollback that deregisters (`docs/AUDIT_v1.8.md`). |
| A browser extension is a Source in the work agent's Ticket flow | The work agent is designed for repository work, and its executor is the Claude Code CLI. Only the Source and Policy concepts are proposed for reuse. See decision CD4. |
| Organism has no calibrated uncertainty primitive | Partly wrong. Conformal calibration exists. ECE and Brier do not. |

---

## 4. Phased plan

### Phase 0. Interface lock (this change)

- Record the open questions O-11 (proto numbering) and O-12 (bridge fit) in Custode's decision log.
- Publish `docs/custode/` (this package) and this plan.
- Exit: owners named for O-11 and O-12. No code or proto change.

### Phase 1. Contract extensions (after O-11)

- Additive proto changes in `router.proto` (`TaskForm` 14 and 15), `contract.proto` (`OutputForm` 10 and 11,
  `MetabolicProfile.vram_budget_bytes` 13, `Channel.flow_label` 8), and `trace.proto` (`Trigger.flow_label` 4), plus the
  `FlowLabel` message.
- Python changes: `ArtifactKind` gains `"adapter"`, and `CapabilityDescriptor` gains `vram_budget_bytes`.
- Gates: `proto:lint`, `contract:validate`, `registry:api`, `test_api_freeze`, and `suite:fast`.
- Exit: all green, with the regenerated Python bindings committed in the same change.

### Phase 2. Browser source (design first, then code behind a flag)

- A Source type for a browser page. Observations become triggers carrying `FlowLabel` with untrusted integrity.
- No execution path. A trigger from a page cannot start a write. This is enforced by Custode's policy, and Organism
  does not execute browser actions in this phase.
- Gate: tests on synthetic observations, plus `hygiene:tree`.

### Phase 3. Bridge channel (after O-12)

- Decide whether the browser bridge is a `Channel`, or needs its own message (O-12).
- The bridge's controls are fixed in CD6. Organism Desktop hosts it only if O-10 is decided that way.

### Phase 4. Learning and evaluation

- `adapter` artifacts with promote gates: shadow precision at least 0.90 (provisional; O-7), regression no more than 0.02
  (provisional; O-7). Rollback through `rollback_last_promote`.
- `EvalSuite` as a new artifact kind, contributed back to Organism. It does not exist yet.

### Phase 5. Governance

- Custode's taint and origin rules as guardrails in the existing chain, after the guardrail code path is verified.
- MLS compliance rules as a versioned `Policy` in `organism_sdk.work`, with the approver's signature under S1.
- No MLS write executor until Custode's gates G1 to G3 clear.

### Phase 6. Optional: tier input

- Optional. `vram_budget_bytes` could become an input to tier selection. The rule for how a declared budget changes a tier
  is not designed. It needs a change to `docs/v1.11/MOA_LAYER.md` before implementation.

---

## 5. Gates

| Phase | Gates that must pass |
|---|---|
| 0 | `hygiene:staged`, `hygiene:tree` (no change to proto or code) |
| 1 | `proto:lint`, `contract:validate`, `registry:api`, `test_api_freeze`, `suite:fast` |
| 2 | Source tests, `hygiene:tree`, `suite:fast` |
| 3 | Channel or bridge tests, `suite:fast` |
| 4 | Promote gates, rollback test, `suite:fast` |
| 5 | Policy tests (`work:domain`), guardrail tests, `suite:fast` |

---

## 6. Backlog

- Verify the guardrail code path before naming it as an Organism surface.
- Check `CalibrationCertificate`'s fields against what Custode needs (ECE, Brier). Do not add a second calibration message.
- Decide whether the `neurosymbolic` catalog entry fits the verifier role. It is a catalog entry, not a verifier.
- Decide the bridge's fit to `Channel` (O-12).
- Write the `EvalSuite` artifact kind.
- Decide the signing path for adapters: the approver's key, pinned in the extension at build time.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Custode's release cycle is coupled to Organism's | Keep Phase 1 small and additive. Do not start Phase 2 before Phase 1 is green. |
| Proto drift between the two repositories | The Organism proto is the source. Custode's copy of the numbers is a proposal and is checked against it. |
| The work agent is used for something it was not designed for | CD4: only Source and Policy concepts are reused. |
| The thread's second half is mostly governance, legal, and lifecycle discussion with few code hooks | Treat it as backlog. Do not build from it without a decision. |
| The bridge is a new attack surface | CD6 sets the minimum controls. A third-party review is required before Phase 3 ships. |
| Model and teacher licenses are unknown | Record each license before any download (Custode O-3). |

---

## 8. Decisions (proposed)

Proposed, not accepted. The prefix `CD` is new in this repository and does not clash with D1 to D5, S1, or W-D*.

- **CD1.** Custode is an application on Organism's substrate, not a standalone system. Open until O-10 is decided.
- **CD2.** Only additive proto changes, using the numbers in `docs/custode/CONTRACT_EXTENSIONS.md`. Pending O-11.
- **CD3.** Tier selection uses MoA tiers T0 to T4. The global `DegradationMachine` remains a separate input, as the v1.11
  design already records.
- **CD4.** Browser actions do not go through the work agent's Ticket and executor path. Only the Source and Policy
  concepts are reused. A browser write path would need its own decision and risk review.
- **CD5.** `LearnedAdapter` is an `ArtifactKind` (`"adapter"`) with promote gates, in the existing `ArtifactStore`.
- **CD6.** Any loopback channel from a browser to Organism uses at least these controls: a Host check, an Origin check
  against the extension ID, a per-start token, explicit user pairing, rate limiting, a size limit, default-deny
  capability grants, and an audit log that records method names and never parameters.

---

## 9. What was checked and what was not

**Checked, on 2026-11-05 in this worktree:**

- The existence, field numbers, and enum values of every name in section 2 and section 3, using search and reads of the
  `.proto` files, `sdk/python/organism_sdk/`, `ci/gates.yaml`, and the design records in `docs/`.
- The absence of `FlowLabel`, `LearnedAdapter`, `FeedbackEvent`, `CalibrationReport`, `ModuleRequest`, `ModuleResponse`,
  `VisionModule`, `PlannerModule`, `VerifierModule`, `EvalSuite`, and `OUTPUT_FORM_*` as identifiers in the repository.
- That the `CD` prefix is not already used in `docs/` or `CHANGELOG.md`.

**Not checked:**

- The runtime behavior of the guardrail chain, the MoA scorer, the tier logic, and the work agent's Policy signing.
- Whether `CalibrationCertificate` covers ECE or Brier. Only its name and position were read.
- Whether the `neurosymbolic` module fits the verifier role.
- Whether the browser bridge fits `Channel`'s semantics. The fit is an open question (O-12).
- Performance. Nothing in this plan is measured.
- The Custode side. Its tests and its measured results are in the Custode repository's `STATUS.md`.
