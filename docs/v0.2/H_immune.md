# Artifact H — Immune Layer Specification (outline)

**Status:** v0.2 first-cut outline + invariants.  
**Depends on:** `STRUCTURAL_ANSWERS.md` §3.  
**Source:** biological extension §4.

---

## H.1 Purpose

Close the gap between anomaly detection (GBG fingerprints, Byzantine cross-check, workspace integrity) and true immunity: **self**, **tolerance**, **memory**.

Three layers (each T1 with deterministic core; learned refinement optional later):

1. **Negative selection** — self-profile + non-self detectors (HDC/VSA natural fit).  
2. **Danger classification (DCA)** — PAMP / Danger / Safe.  
3. **Immune memory** — memory cells with response history; replay remembered response on match.

---

## H.2 Invariants (normative)

| ID | Invariant |
|---|---|
| IM-1 | Every immune decision is a workspace binding with `salience.fidelity = FULL` and `safety.affects_control = true`. |
| IM-2 | ImmuneLayer **must not** call registry lifecycle or router dispatch APIs directly. |
| IM-3 | Quarantine / demote / surveillance = bindings consumed by registry/router only. |
| IM-4 | ImmuneLayer never actuates hardware. |
| IM-5 | Every ingress classification emits `ImmuneTraceEntry` (including Safe / pass-through). |
| IM-6 | Tolerance margin may widen under cortisol and narrow under melatonin; changes are themselves traced hormone-modulated parameters. |
| IM-7 | Under high cortisol, default response to antigen is **quarantine, not kill**. |

---

## H.3 Ingress gate (pre-router)

```
ingress(task_or_emission):
  1. antigenicity vs self-profile
  2. below threshold → pass (self); still emit Safe/self trace if policy requires
  3. else classify PAMP / Danger / Safe
     PAMP: memory hit → replay; else write quarantine/demote bindings + cortisol request
     Danger: write surveillance binding; raise cross-check; cortisol ∝ novelty
     Safe: add to self-profile with tolerance marker; pass
  4. emit ImmuneTraceEntry always
```

---

## H.4 Schemas (sketch)

```yaml
ImmuneDecisionBinding:   # workspace key immune_decision / immune_decision/<id>
  decision: enum[PASS, QUARANTINE, DEMOTE, SURVEIL, TOLERATE]
  classification: enum[SELF, PAMP, DANGER, SAFE]
  antigen_score: float
  source_module_id: string | null
  memory_cell_id: string | null
  salience: {fidelity: FULL}
  safety: {affects_control: true}

MemoryCell:
  signature_hv: bytes
  response_history: [{action, success, recovery_s}]
  last_match_at: datetime
```

---

## H.5 Trace

`emit_immune` stub in SDK. Category L scenarios must release, measure, and replay immune decisions (see F extension).

---

## H.6 Explicit non-goals (this cut)

- Running ImmuneLayer in v0.1 path.  
- RL-DCA online training.  
- Direct module kill from immune code.
