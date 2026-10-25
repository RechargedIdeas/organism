# Organism Desktop — v1.6 surfaces

**Release:** v1.6.0  
**Stack:** PySide6 · CPU Everywhere · bio `may_actuate=False` hard-refuse  
**Not:** Hybrid PySide6 Studio

## New / deepened surfaces

| Surface | Behavior |
|---|---|
| **Trace explorer** | Filterable table (`kind`, `task_id`, `emitted_at`); **Export JSON**; **Jump from last pipeline** |
| **Router / plan inspector** | Structured summary + ranking_trace steps + excluded table; raw JSON retained; **Open result in Traces** |
| **Multi-profile deploy** | Ops combo: `cpu_only` (8787) ↔ `default` (8788); `switch_deploy_profile` rebuilds stack; status_facts delta shown |
| **Module catalog** | 10 substrates; **RESEARCH_TIER** badge on `snn_sentinel` / `physical_research`; one-click register |
| **Contracts / Assert** | `SubstrateContract.validate()` over registered (+ bio) modules; last results panel |
| **Packaging** | `organism-desktop` entry; `desktop/docs/PACKAGING.md` PyInstaller sketch |

## Navigation (12 panels)

```
Home → Registry → Catalog → Workspace → Pipelines → Physiology →
Metamodel → Bio-Digital → Traces → Contracts → Ops → Docs
```

Shortcuts: **Ctrl+1–9**, **Ctrl+0** (10th), **Ctrl+Alt+1…** (11+); **Ctrl+R** /
**Ctrl+Shift+R** refresh.

## Safety

1. Bio actuation still hard-refused (`ActuationRefused`).
2. RESEARCH_TIER catalog register refuses if contract declares `may_actuate=True`.
3. Profile switch never enables GPU requirement; CPU fallback everywhere.
4. Wet-lab policy viewer remains deny-by-default.

## Service API additions

- `list_traces(..., task_id=, since_iso=)` · `export_traces_json` · `traces_for_last_pipeline`
- `inspect_plan`
- `list_deploy_profiles` · `switch_deploy_profile`
- `module_catalog` · `register_catalog_module`
- `run_contract_checks` · `last_contract_results`
