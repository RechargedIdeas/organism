# Degradation Drillbook (Desktop)

**Audience:** operators exercising Physiology on Organism Desktop  
**Safety class:** virtual-clock software demo only  
**Release:** v1.6.1+

## What it does

The **Drillbook L0→L4** button on the Physiology panel drives
`DegradationMachine` through scripted `HealthSignals` with **FAST hysteresis**
(`T_DOWN_FAST` / `T_UP_FAST`) so L0→L1→L2→L3→L4 completes in milliseconds of
wall time while still exercising the same transition logic as production
physiology.

Each downward hop emits a `DegradationTraceEntry` on the shared `TraceEmitter`
(visible in the Traces panel).

## Safety rules

1. **Confirm required** — Desktop shows a Yes/No dialog; the service refuses
   without `confirm=True`.
2. **No bio / wet-lab actuation** — drillbook never sets `may_actuate`, never
   touches HAL control paths, never enables GPIO.
3. **Virtual clock only** — `advance(dt)` on the machine; no wall-clock waits.
4. **Reset** — use **Reset physiology** to return to L0 after a drill.
5. **Not a fault injector for live serve** — do not point this at a production
   `organism serve` process; it mutates the Desktop in-process stack only.

## Scripted signal progression

| Hop | Primary signals |
|---|---|
| L0→L1 | `h_m[learned]=DEGRADED`, low thermal |
| L1→L2 | `h_m[learned]=FAILED`, `causal_ok=False` |
| L2→L3 | elevated `gc` / `q_p95` |
| L3→L4 | `trace_ok=False`, `det_ok=False`, high mem/gc, `byz_count≥3` |

## Related

- Physiology **Hormone timeline** — virtual-clock `hormone_state` rows + Traces
- Physiology **Federation / oxytocin stub** — multi-node software only (not WAN BFT+TPM)
- `docs/ops/SOAK_RUNBOOK.md` — longer soak harness
- `docs/ops/WETLAB_SAFETY_POLICY.md` — deny-by-default wet-lab policy
