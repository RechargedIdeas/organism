# Changelog

All notable changes to Organism are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer for the **frozen** surface in `docs/API_FREEZE_v0.4.md`.

## [0.4.0] — 2026-10-24

### Added
- **API freeze** — `docs/API_FREEZE_v0.4.md` (stable Python SDK + `organism.v1` proto; experimental biology / multi-node / SNN called out).
- **v0.4 hardening (M0–M3)**
  - Soak harness (`harness/scenarios/v04_soak.py`) with GC pressure and reconstructible traces; full soak via `ORGANISM_SOAK_FULL=1`.
  - Perf budgets (`docs/v0.4/PERF.md`) + blocking `perf:router` / `perf:workspace` / `perf:hormone` / `perf:degradation` gates.
  - Security fuzz: malformed contracts, unjustified control actuation, Byzantine → L4, capability-scope violations, immune quarantine forgery.
- **v0.3 E.8 lifts (M0–M4)** — learned ISE + RL-DCA (shadow), metamodel synthesizer (exploration), in-process multi-node + oxytocin, SNN sentinel (HW-gated).
- **v0.2 biological organs** — HormoneBus, ISE, Immune, Autonomic/apoptosis, circadian, morphogenesis; full J–O fault matrix.
- **v0.1 M1–M7** — proto, Python SDK, deterministic_engine, registry, workspace, router, learned_module, snapshots, degradation, two-module bootstrap + CI.

### Changed
- Package / crate / SDK versions aligned to **0.4.0**.
- README status refreshed to v0.4.0-ready.

### Security
- Immune forgery rejection without FULL / affects_control / immune_layer.
- Justification required for untrusted `control_actuation`.
- Capability-scoped workspace write/read enforcement under fuzz.

### Out of scope (unchanged)
Real neuromorphic silicon, full BFT cluster, live NAS, molecular/physical substrates on the control path.

### Test baseline
Default suite: **115 passed** (2 slow deselected).

## [0.3.0] — 2026-10-24

Internal milestone line (learned ISE, metamodel, multi-node sim, SNN sentinel). Superseded by 0.4.0 packaging.

## [0.2.0] — 2026-10-24

Biological extension (HormoneBus through morphogenesis + J–O matrix). Superseded by 0.4.0 packaging.

## [0.1.0] — 2026-10-24

Initial closed-corpus implementation (Batch 1 + M1–M7).

[0.4.0]: https://github.com/RechargedIdeas/organism/releases/tag/v0.4.0
