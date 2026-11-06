# Learning, evaluation, and promotion

This document covers how a browser agent's learned parts would be stored, promoted, and rolled back in Organism. The
learning logic is built in the Custode repository, with no training worker. The Organism side is a proposed mapping.

**Status:** Proposed.

---

## 1. What exists in Custode (built logic, no training worker)

Custode's learning loop (`docs/06-learning-loop.md`) has these parts:

- **Feedback capture and validation.** Feedback is checked before use. A rating with no signal, or one that is too old
  or low in reliability, is set aside. A note that contradicts its rating is sent to review.
- **Importance scoring.** `importance = 0.35 * novelty + 0.25 * consistency + 0.20 * recency + 0.20 * reliability`
  (`docs/06-learning-loop.md`; `extension/src/learning/feedback.ts`, line 124). Recency halves every seven days
  (`feedback.ts`, line 139).
- **Promotion gate.** A candidate adapter must score at least **0.90** on the frozen held-out suite, and must not regress
  more than **0.02** against the current version (`docs/06-learning-loop.md`; `extension/src/learning/promotion.ts`,
  line 4). Both numbers are provisional until O-7 confirms them against measured data.
- **Rollback history.** The gate and the rollback history are in `extension/src/learning/promotion.ts`.
- **Drift check.** Every 10 sessions by default, the check replays the held-out suite on the current adapter. A drop past
  the threshold triggers a rollback and a warning (`docs/06-learning-loop.md`).
- **Training** is Specified, not built (`ARCHITECTURE.md`, section 6.5).

---

## 2. Organism side (proposed mapping)

### 2.1 Adapters as artifacts

- `ArtifactKind` (`sdk/python/organism_sdk/generative/artifacts.py`, line 20) is `code`, `asset`, `skill`, `manifest`, or
  `pack` today. The proposal adds `"adapter"` ([CONTRACT_EXTENSIONS.md](CONTRACT_EXTENSIONS.md), section 2).
- `ArtifactStore` (same file, line 71) already stores artifacts. An adapter would be stored through it.
- An `AdapterMeta` record would name the base model, the adapter kind, its rank, the hash of its training events, its
  parent's hash, and a `CalibrationCertificate` (`proto/organism/v1/calibration.proto`, line 34). The name is new.

### 2.2 Feedback

`FeedbackEvent` would be a Python work-domain type first (new name). A proto message is a later decision.

Organism already has a precedent for promotion on feedback. The work agent marks a rule as automatic only after 20
verdicts on its would-accept decisions, and only if at least 90% of them agree (`sdk/python/organism_sdk/work/promote.py`,
lines 20 and 21: `MIN_LABELED = 20` and `MIN_SCORE = 0.9`). The numbers match Custode's floor, but the measures differ:
one counts agreeing verdicts, the other scores a held-out suite.

### 2.3 Promotion path

- The existing order is sandbox, then contracts, then shadow, then promote. A rollback deregisters the module
  (`docs/AUDIT_v1.8.md`, the promote-gates row).
- The rollback is `CodePipeline.rollback_last_promote` (`sdk/python/organism_sdk/generative/code_pipeline.py`, line 445),
  called by `DesktopService` (`desktop/organism_desktop/service.py`, line 2192).
- The default minimum shadow score is 0.9 (`sdk/python/organism_sdk/generative/stages.py`, line 30).
- The proto side is `Lifecycle` (`contract.proto`, line 338), which carries `shadow_validation_required` and a
  `PromotionCriteria` (line 346): `shadow_invocations_min`, `max_incumbent_error_delta`, `required_gates`,
  `approver_role`, and `causal_review_required`.

**Mapping gap.** Custode's regression limit is a drop in score, 0.02. `PromotionCriteria.max_incumbent_error_delta` is a
change in error. The two are close but not the same measure. The mapping must be decided before an adapter uses this
path.

---

## 3. Evaluation status

Custode's router has a 26-case Tier 1 set, and all 26 pass. Those cases were written by the same author as the rule
router, so the result is a smoke check, not an accuracy claim. The Phase 2 gate is 90% on a held-out set, which has not
been written yet (Custode `docs/11-evaluation.md`, and Custode `STATUS.md`). The gate is not met.

---

## 4. Open items

- Confirm the promotion floor (0.90) and regression limit (0.02) against measured data (O-7).
- Write the held-out set before tuning the router against it.
- Decide how Custode's regression limit maps onto `PromotionCriteria`.
- Decide whether adapters are an `ArtifactKind` (O-11).
