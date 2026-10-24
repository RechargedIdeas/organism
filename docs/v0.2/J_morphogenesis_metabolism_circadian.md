# Artifact J — Morphogenesis, Metabolism, Circadian (outline)

**Status:** v0.2 first-cut outline. Extensions to existing layers — not new organs.  
**Depends on:** `STRUCTURAL_ANSWERS.md` §4–5.  
**Source:** biological extension §7.

---

## J.1 Morphogenesis

Metamodel synthesizes a **DevelopmentalGenome** + programme instead of a finished artifact when `developmental = true`.

- Registry tracks developmental stage.  
- Module in `DEVELOPMENT` is in exploration mode by definition.  
- Cannot enter deliberation until all stages validated.  
- Stage failure localizes mutation locus (no wasted recompute of prior stages).

Category O scenarios outline stage fail / resume / shadow validation.

---

## J.2 Metabolism (Kleiber-style scaling)

Replace flat `BudgetClass {LEAN, STANDARD, HEAVY, RESEARCH}` with declared scaling:

\[
\mathrm{declared\_share}(m) = k \cdot (\mathrm{functional\_complexity}(m))^{\beta}
\]

- `β ∈ [0.7, 0.8]`, default `0.75`.  
- Budget class becomes **derived**.  
- Evaluation Gate 3 gains scaling check: energy/inference vs predicted share.

Does **not** enter v0.1 runtime (E.8). Spec only until Category O/J metabolic scenarios exist.

---

## J.3 CircadianClock

Phase variable advanced by control loop (not a naive wall-clock cron):

| Parameter | Behaviour |
|---|---|
| Consolidation cadence | Prefer rest window (melatonin high); defer if crisis |
| Exploration window | Larger in active phase; near zero in rest |
| Sensitivity thresholds | Slightly tighter in rest |
| Hormone baselines | Melatonin↑ / cortisol baseline↓ in rest |

Homeostatic sleep pressure + configurable time-of-day; either can dominate.

Integrates with HormoneBus melatonin release and Autonomic RECOVERY.

---

## J.4 Interactions (pointer)

See biological extension §8 cascade (ISE → cortisol → autonomic → immune tolerance → router). J specifies the morphogenesis/metabolism/circadian limbs of that cascade only.
