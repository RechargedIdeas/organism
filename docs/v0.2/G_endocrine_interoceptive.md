# Artifact G — Endocrine and Interoceptive Specification (first cut)

**Status:** v0.2 first-cut spec (docs-first). No full HormoneBus runtime in tree yet.  
**Depends on:** `STRUCTURAL_ANSWERS.md` §1.  
**Source:** biological extension §2–3 + §5.1 preferred resolutions.

---

## G.1 Interoceptive State Estimator (ISE)

Organ-level **T0/T1** module on a fixed cadence. Produces one `InteroceptiveState` written to the workspace; consumed by control loop, router, and AutonomicController.

```yaml
InteroceptiveState:
  timestamp: datetime
  viability_score: float[0,1]
  allostatic_setpoints:
    thermal_target: float
    latency_target_ms: float
    calibration_target: float
    energy_target_j: float
  predicted_trajectory:
    horizon_s: float
    viability_at_horizon: float
    confidence_interval: [float, float]
  signals:
    heart_rate_analog: float
    stress_load: float
    recovery_capacity: float
  provenance:
    module_id: "interoceptive_state_estimator"
    model_version: semver
```

**Components (T0 baseline first):**

1. **Viability model** — auditable monotone bounded `f(H)`; weighted geometric mean acceptable initially.
2. **Allostatic setpoint adapter** — anticipatory adjustment before thresholds cross.
3. **Trajectory predictor** — small recurrent/reservoir projecting viability; distribution + CI.

**Diagnosis pre-step (integration):**

1. `viability_score < viability_floor` → `crisis_precursor` → AutonomicController  
2. `viability_at_horizon < floor` → request setpoint adaptation  
3. `recovery_capacity < recovery_floor` → chronic_stress → cortisol release  
4. Else existing B diagnosis logic  

v0.1 note: L0→L1 remains reactive; ISE preemption is v0.2.

---

## G.2 HormoneBus

**Declared channel.** Four hormones: `CORTISOL`, `DOPAMINE`, `OXYTOCIN`, `MELATONIN`.

```yaml
Hormone:
  name: enum[CORTISOL, DOPAMINE, OXYTOCIN, MELATONIN]
  level: float[0,1]
  release_rate: float
  decay_rate: float          # half-life seconds
  source: string
  released_at: datetime
  receptor_scope: enum[GLOBAL, ROLE_SCOPED, LEVEL_SCOPED]
```

| Hormone | Organism effect (modulation only) |
|---|---|
| Cortisol | Raise router risk aversion; widen conformal intervals; increase cross-check; preempt exploration |
| Dopamine | Scale exploration / positive-outcome weight in consolidation |
| Oxytocin | Federated/cooperation tolerance (v0.2+ federation surfaces) |
| Melatonin | Consolidation phase; reduce exploration; long-term salience weight |

**Release functions are deterministic and declared** (coefficients in HormoneBus contract) — not learned. See corpus §3.2 for the algebraic forms.

### G.2.1 Source of truth (Structural Answer 1)

1. Every telemetry window: write workspace binding `hormone_state` (FULL audit).  
2. HormoneBus mirrors that binding for low-latency reads.  
3. Consumers that read the bus **must** emit `HormoneTraceEntry` with `staleness_ms` and the levels as seen.  
4. Replay uses the traced reading, not live workspace at `t`.

### G.2.2 Receptors

Optional contract section `hormone_receptors`:

```yaml
HormoneReceptor:
  hormone: enum[...]
  response: enum[THRESHOLD_GATE, CONTINUOUS_MODULATION, BINARY_SWITCH]
  mapping:
    threshold: float | null
    gain: float | null
    target_parameter: string
```

SDK applies modulation before `handle()`.  

**Hard constraint:** hormones **modulate**; they **never override** the safety shield. Shield may *read* hormone state but is not a receptor.

---

## G.3 Trace

- `emit_hormone(HormoneTraceEntry)` — stub in SDK; requires `attach_v02_sink()`.  
- Required fields for Axiom 6: levels, `hormone_state_digest`, `staleness_ms`, consumer identity (via policy/level stamp).

---

## G.4 Planned lifecycle / proto deltas

None required for endocrine beyond optional contract sections on Artifact A (`hormone_receptors`). Proto v2 sketch deferred until G is fault-injection ready (Category K).

---

## G.5 Out of scope for this cut

- Full bus implementation, consensus broadcast, federated oxytocin paths.  
- Learned ISE replacing T0 `f(H)`.  
- Folding into v0.1 CI gates.
