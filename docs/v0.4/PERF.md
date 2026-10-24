# Organism v0.4 — Performance Budgets

**Date:** 2026-10-24 (America/New_York)  
**Box:** single-process CI / developer box (no neuromorphic HW)  
**Measured baseline (n≈200, warm):** see table.

## Budgets (CI gates)

| Metric | p50 budget | p95 budget | Gate | Blocking |
|---|---|---|---|---|
| Router `decide` latency | ≤ 2.0 ms | ≤ 5.0 ms | `perf:router` | true |
| Workspace `bind_exact` | ≤ 2.0 ms | ≤ 5.0 ms | `perf:workspace` | true |
| Workspace `read_by_binding_id` | ≤ 0.5 ms | ≤ 1.0 ms | `perf:workspace` | true |
| Workspace `unbind` | ≤ 1.0 ms | ≤ 2.0 ms | `perf:workspace` | true |
| Hormone `write_telemetry_window` | ≤ 2.0 ms | ≤ 5.0 ms | `perf:hormone` | true |
| Degradation L0→L1 confirm (virtual + `T_DOWN_FAST`) | ≤ 1.0 ms | ≤ 2.0 ms | `perf:degradation` | true |

Headroom is intentional: budgets are ~50–100× above measured baseline on this box so CI stays stable under load/noise while still catching regressions.

## Measured baseline (this box, 2026-10-24)

| Metric | p50 | p95 |
|---|---|---|
| Router decide | ~0.008 ms | ~0.013 ms |
| Workspace bind | ~0.057 ms | ~0.079 ms |
| Workspace query | ~0.0004 ms | ~0.0006 ms |
| Workspace unbind | ~0.005 ms | ~0.006 ms |
| Hormone publish | ~0.079 ms | ~0.101 ms |
| Degradation confirm | ~0.005 ms | ~0.010 ms |

## Notes

- Degradation budget covers **evaluation + virtual advance**, not real wall hysteresis.
- Full B.4 wall-clock physiology remains under `perf:slo` / Category I (opt-in 480s).
- Multi-node / neuromorphic latency is **out of scope** for these budgets.
