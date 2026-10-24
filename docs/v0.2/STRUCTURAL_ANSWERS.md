# v0.2 Structural Answers — Biological Extension Gate

**Corpus:** `/workspace/organism-handoff.txt` §5.1 (≈L4780)  
**Date:** 2026-10-24 (America/New_York)  
**Status:** Adopted as the gate to Artifacts G–J. Preferred resolutions from the corpus; no conflicting design invented.

These five answers must hold before any biological mechanism enters a runnable v0.2 artifact. E.8 out-of-scope items for v0.1 remain out of the v0.1 runtime unless a v0.2 artifact explicitly brings them in.

---

## 1. HormoneBus vs. Axiom 2 (and Axiom 6 reconstructibility)

**Resolution (corpus preferred):**

- The **HormoneBus is a declared channel** (passes the letter of revised Axiom 2: no undeclared channels).
- Hormone readings are **written to the workspace every telemetry window** as a single binding tagged `hormone_state`.
- The workspace binding is the **source of truth**.
- The bus is a **low-latency mirror**, not an alternative source of truth.

**Axiom 6 corollary (handoff addition on HormoneBus vs. reconstructibility):**

- If the router (or any consumer) reads from the bus at time `t`, the bus may lag the workspace binding by up to one telemetry window.
- The Decision Trace **must record the bus reading as the consumer saw it**, including `staleness_ms`.
- Replay reconstructs decision-correctness against that **recorded** reading/staleness, not against the workspace state at `t`.

Without the mirror pattern + staleness attestation, either Axiom 6 is violated (unattested bus reads) or Axiom 2 is violated (bus becomes a second workspace).

See `G_endocrine_interoceptive.md`.

---

## 2. AutonomicController vs. router authority

**Resolution (corpus preferred — simpler path):**

- The **router remains the sole dispatcher**.
- The AutonomicController **only modulates parameters the router already exposes**:
  - preemption class / mask
  - cross-check frequency
  - exploration budget
  - (and related metabolic multipliers already on the router/governor surface)
- Autonomic writes are **traced** (`AutonomicTraceEntry` / `emit_autonomic`).
- The autonomic system is a **modulator**, not a decision-maker; it shapes the environment in which dispatch happens.

(The more auditable alternative — autonomic decisions as workspace bindings the router reads — remains available later; v0.2 first-cut adopts parameter modulation + mandatory tracing.)

See `I_autonomic_apoptosis.md`.

---

## 3. ImmuneLayer placement and audit trail

**Resolution (corpus preferred):**

- Every immune-layer decision is a workspace binding with:
  - `salience.fidelity = FULL`
  - `safety.affects_control = true`
- The ImmuneLayer **may not** take lifecycle or routing actions except by writing bindings that the **registry and router consume**.
- The immune system never actuates hardware; it signals. Autonomic + router execute.
- Always emit `ImmuneTraceEntry` (`emit_immune`), regardless of PAMP / Danger / Safe classification.

This is the immune system's version of Axiom 2: no unaudited super-authority.

See `H_immune.md`.

---

## 4. Lifecycle states for apoptosis and morphogenesis

**Resolution (corpus preferred):**

New lifecycle states (planned proto deltas; docs-first for v0.2 open):

| State | Constraints |
|---|---|
| `SELF_TERMINATING` | Requires `contract.lifecycle.self_termination_permitted = true` |
| `SUCCEEDED` | Self-chosen end (distinct from `RETIRED`) after memory export + DeathCertificate |
| `DEVELOPMENT` | **Subset of `EXPLORATION`**; inherits all EXPLORATION restrictions; cannot enter deliberation until stages validated |

Hard constraints:

- **T0 modules never self-terminate** (deterministic engine is the L4 refuge).
- Control-affecting modules may self-terminate **only** with an immediately available cross-check-capable successor; otherwise enter `DEGRADED` and wait for external replacement.
- Transition conditions, registry invariants, trace entries, and promotion gates must be specified with A.1 discipline before codegen.

Planned additive enum sketch: document in `I_autonomic_apoptosis.md` / optional `proto/organism/v2/` later — **not** folded into v0.1 protos.

---

## 5. Extend F.7 with categories J–O

**Resolution (corpus preferred):**

| Category | Scope |
|---|---|
| **J** | Interoception / allostasis |
| **K** | Endocrine (HormoneBus + `hormone_state` replay) |
| **L** | Immune (negative selection, DCA, memory cells) |
| **M** | Autonomic (mode transitions, parameter modulation) |
| **N** | Apoptosis (self-termination, DeathCertificate, successor) |
| **O** | Morphogenesis (developmental stages, genome validation) |

A hormone that cannot be released, measured, and replayed is not a hormone; the test matrix is what makes each mechanism real.

See `F_extension_biological_matrix.md` for scenario outlines (not yet implemented).

---

## Sequencing reminder

| Phase | Artifact | Gate |
|---|---|---|
| v0.2 open | G — Endocrine + Interoceptive | These five answers |
| v0.2 open | H — Immune Layer | Same |
| v0.2 open | I — Autonomic + Apoptosis | Same |
| v0.2 open | J — Morphogenesis / Metabolism / Circadian | Same |
| v0.2 | F extension — biological fault-injection | G–J specified |
| v0.2 | Reference implementation | F extension green |

**v0.1 design constraints preserved now (not mechanisms):**

1. L0→L1 is reactive-only; preemptive ISE trigger deferred to v0.2.
2. Any global disposition that affects routing must be recorded in the trace (`degradation_level` stands in for “stress” in v0.1).
3. T0 must never be permitted to self-terminate.
