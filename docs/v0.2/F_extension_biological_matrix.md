# F Extension — Biological Fault-Injection Matrix (Categories J–O)

**Status:** Outline only. Scenarios are not implemented until G–I are solid enough for a thin vertical slice.  
**Depends on:** `STRUCTURAL_ANSWERS.md` §5; Artifacts G–J.  
**Extends:** F.7 (Categories A–I remain v0.1).

A mechanism without fault-injection is theatrical. Each row below must become a CI scenario with measured timing, trace assertions, and replay.

---

## Category J — Interoception / allostasis

| ID | Scenario | Assertions (outline) |
|---|---|---|
| J1 | Drive health vector toward thermal cliff; ISE predicts breach within horizon | `crisis_precursor` before L0→L1; setpoint adaptation requested |
| J2 | ISE offline / timeout | Diagnosis falls back to reactive B path; diagnosis event; no silent skip |
| J3 | Replay interoceptive bindings | Zero mismatches; viability trajectory reconstructible |
| J4 | False-high viability under failing probe | Autonomic must not stay PARASYMPATHETIC; cross-check with `h_m` |

---

## Category K — Endocrine

| ID | Scenario | Assertions (outline) |
|---|---|---|
| K1 | Release cortisol via declared function | `hormone_state` workspace binding updated within 1 telemetry window |
| K2 | Router reads bus with induced staleness | Trace has `staleness_ms`; replay uses traced levels |
| K3 | Cortisol above receptor threshold | Learned module modulation applied by SDK; safety shield unchanged |
| K4 | Attempt hormone override of shield | Rejected; shield permits nothing extra |
| K5 | Kill HormoneBus mirror | Consumers fall back to workspace `hormone_state`; diagnosis event |
| K6 | Replay dispatch under high cortisol vs baseline | Plans distinguishable via hormone fields in trace |

---

## Category L — Immune

| ID | Scenario | Assertions (outline) |
|---|---|---|
| L1 | Novel binding matching detector (Danger) | SURVEIL binding FULL/affects_control; no direct demote API call |
| L2 | PAMP with memory hit | Remembered response replayed; faster than first exposure |
| L3 | Safe novelty under low cortisol | Tolerated; added to self-profile |
| L4 | Same novelty under high cortisol | Quarantine binding (not kill); IM-7 |
| L5 | Immune tries registry.deregister | Forbidden — test harness asserts no direct lifecycle call |
| L6 | Replay immune decisions | Trace + workspace bindings match |

---

## Category M — Autonomic

| ID | Scenario | Assertions (outline) |
|---|---|---|
| M1 | ISE crisis_precursor → CRISIS | Mode change <1s; router params updated; traced |
| M2 | Sustained recovery → RECOVERY → PARASYMPATHETIC | Hysteresis holds; no flap on single good sample |
| M3 | Autonomic cannot select module for task | Inject attempt; router still sole dispatcher |
| M4 | Oscillate viability around SYMPATHETIC threshold | Transition count bounded (hysteresis) |

---

## Category N — Apoptosis

| ID | Scenario | Assertions (outline) |
|---|---|---|
| N1 | T2 with `self_termination_permitted` entropy-collapses | SELF_TERMINATING → DeathCertificate → SUCCEEDED; successor EXPLORATION |
| N2 | T0 attempts self-terminate | Rejected (AP-2) |
| N3 | Control-affecting without successor | DEGRADED; no SUCCEEDED |
| N4 | Drain killed mid-export | Runtime synthetic lifecycle record; no silent SUCCEEDED |
| N5 | Successor shadow-validate vs DeathCertificate | Fail blocks promotion |

---

## Category O — Morphogenesis

| ID | Scenario | Assertions (outline) |
|---|---|---|
| O1 | Developmental genome stage-3 fail | Stages 1–2 retained; mutation at stage-3 locus |
| O2 | DEVELOPMENT module offered control_actuation | Held / rejected — EXPLORATION restrictions |
| O3 | All stages valid → leave DEVELOPMENT | Promotion gates same as EXPLORATION→… |
| O4 | Circadian rest during crisis | Melatonin suppressed; consolidation checkpointed not lost |
| O5 | Metabolic share vs Kleiber prediction | Inefficiency flag when energy ≫ predicted share |

---

## Harness notes

- Prefer hysteresis overrides for CI time compression (same as F), except soak tests.  
- Biological scenarios are **non-blocking** until G–I vertical slice lands; then promote per artifact readiness.  
- Do not cite v0.1 harness green as evidence for J–O.
