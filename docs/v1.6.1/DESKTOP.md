# Organism Desktop — v1.6.1 surfaces

**Release:** v1.6.1  
**Stack:** PySide6 · CPU Everywhere · bio `may_actuate=False` hard-refuse  
**Not:** Hybrid PySide6 Studio · production WAN BFT+TPM · real neuromorphic silicon

## Added / deepened

| Surface | Behavior |
|---|---|
| **Hormone timeline** | Physiology table of `hormone_state` over virtual-clock windows; emits `HormoneTraceEntry`; **Open Traces** jump |
| **Degradation drillbook** | L0→L4 scripted steps with confirm dialog + reset; `docs/ops/DEGRADATION_DRILLBOOK.md` |
| **Federation / oxytocin stub** | Multi-node mirror lag + quorum exploration (explicitly not production BFT) |
| **Rust runtime status** | Ops read-only crate inventory + optional `cargo metadata` probe |
| **Soak / fuzz from Desktop** | Ops buttons write `desktop/artifacts/soak_*.json` / `fuzz_*.json` with progress + path |
| **UX polish** | Tooltips, empty hormone/bio hints, bio actuation messaging |

## Navigation (still 12 panels)

```
Home → Registry → Catalog → Workspace → Pipelines → Physiology →
Metamodel → Bio-Digital → Traces → Contracts → Ops → Docs
```

## Service API additions

- `run_hormone_timeline` · `last_hormone_timeline`
- `run_degradation_drillbook(confirm=...)` · `last_drillbook`
- `run_federation_stub` · `last_federation_stub`
- `rust_runtime_status` · `last_rust_status`
- `run_short_soak_harness` · `run_short_fuzz_harness` · `last_harness_result`

## Safety

1. Bio actuation still hard-refused (`ActuationRefused`).
2. Drillbook requires explicit confirm; virtual clock only.
3. Federation stub labeled `not_production_bft`.
4. Rust probe is read-only (no forced `cargo build` on panel refresh).
5. CPU Everywhere / no Hybrid Studio import unchanged.
