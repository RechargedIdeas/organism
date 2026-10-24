# Artifact I — Autonomic Controller and Apoptosis (outline)

**Status:** v0.2 first-cut outline + invariants.  
**Depends on:** `STRUCTURAL_ANSWERS.md` §2 and §4.  
**Source:** biological extension §5–6.

---

## I.1 AutonomicController

Declarative state machine, **no learned components**, fast loop (sub-second), independent of telemetry cadence.

```
mode: enum[PARASYMPATHETIC, SYMPATHETIC, CRISIS, RECOVERY]
```

| Mode | Effects (parameter modulation only) |
|---|---|
| PARASYMPATHETIC | Default budgets, normal preemption, exploration OK, low cortisol target |
| SYMPATHETIC | Preempt research-tier; cut exploration; raise cross-check; tighten floors ~20% |
| CRISIS | Preempt non-T0/T1; suspend exploration; control_actuation → deterministic only; double cross-check |
| RECOVERY | Ramp budgets over `T_ramp`; bounded exploration; lower cortisol; rising melatonin |

Mode transitions are **hysteretic** (same physiology as L0–L4).

### I.1.1 Authority invariant (Structural Answer 2)

| ID | Invariant |
|---|---|
| AU-1 | Router is the sole dispatcher. |
| AU-2 | Autonomic writes only router-exposed parameters: preemption class, cross-check frequency, exploration budget (+ declared metabolic multipliers). |
| AU-3 | Every autonomic mode change and parameter write emits `AutonomicTraceEntry`. |
| AU-4 | Fast-path triggers (ISE crisis_precursor, Immune PAMP) may enter SYMPATHETIC/CRISIS without waiting for control-loop diagnosis, but still trace. |
| AU-5 | AutonomicController does not route tasks or select modules. |

---

## I.2 Apoptosis / lifecycle extension

```
DELIBERATION → SELF_TERMINATING → SUCCEEDED
                    ↓ memory export + DeathCertificate
              successor spawned (EXPLORATION / DEVELOPMENT)
```

### I.2.1 Triggers (declared in contract, not learned)

- Entropy collapse (degenerate output distribution).  
- Staleness past `max_idle_time`.  
- Developmental obsolescence with `replaceable = true` and better successor.

### I.2.2 Protocol sketch

1. Emit `SELF_TERMINATING` to registry.  
2. `on_drain` to deadline.  
3. Export memory (weights summary, decision history, failure modes, calibration).  
4. Write `DeathCertificate` to workspace.  
5. Registry → `SUCCEEDED` (not `RETIRED`).  
6. Spawn successor if `successor_spec` present; shadow-validate against DeathCertificate decisions before promotion.

### I.2.3 Hard constraints (Structural Answer 4)

| ID | Invariant |
|---|---|
| AP-1 | `self_termination_permitted = true` required on contract. |
| AP-2 | **T0 never self-terminates.** |
| AP-3 | Control-affecting modules need immediately available cross-check-capable successor; else `DEGRADED` + wait. |
| AP-4 | `DEVELOPMENT ⊂ EXPLORATION` (inherits restrictions). |
| AP-5 | DeathCertificate + memory export digest required before `SUCCEEDED`. |

### I.2.4 Planned proto deltas (docs-only for now)

Additive lifecycle enum values for a future `proto/organism/v2/`:

```
SELF_TERMINATING = N
SUCCEEDED = N+1
DEVELOPMENT = N+2   # documented as EXPLORATION sub-state; wire format TBD
```

**Do not** break v0.1 codegen. Prefer documenting until G–I vertical slice needs enums.

---

## I.3 Trace

`emit_autonomic` stub in SDK. Category M/N in F extension.
