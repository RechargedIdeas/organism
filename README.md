# Organism

**Organism** is a production-grade AI/ML substrate: a runtime, contract system, and orchestration layer that hosts heterogeneous computational modules, couples them through a shared vector-symbolic workspace, routes work by task structure and physiological state, and degrades through a graded series of alternative metabolisms rather than crashing.

Organism is not a model. It is the **substrate** in which models live.

## Status

- **Spec phase:** closed. Five artifacts (A–F), six addenda (A0–A6), 87 active invariants.
- **Implementation phase:** M1 in progress.
- **v0.2 (biological extension):** gated on six structural questions, opens when M7 is green.

## Quickstart

```bash
# Generate proto stubs
make proto

# Install Python SDK
make python-install

# Build Rust workspace
make rust-build

# Run all tests
make test
```

## Repository structure

| Directory | Contents |
|---|---|
| `proto/` | proto3 source of truth (A, A0–A6, R-34/R-35 folded) |
| `sdk/python/` | Python authoring SDK |
| `sdk/rust/` | Rust runtime SDK |
| `runtime/` | Core runtime services (registry, workspace, router, degradation, control loop) |
| `modules/` | Reference modules (deterministic engine, learned, kernel, HDC) |
| `harness/` | Test harness (runner, injector, observer, scenarios) |
| `ci/` | CI gate definitions |

## Milestones

| M | Deliverable | Depends on |
|---|---|---|
| M1 | proto + Python SDK + deterministic_engine | — |
| M2 | Registry + workspace (in-memory) | M1 |
| M3 | Router + DispatchPlan | M2 |
| M4 | learned_module + cross-check | M3 |
| M5 | Ops log + snapshot + replay | M4 |
| M6 | Degradation state machine + fault injection | M5 |
| M7 | Full CI + two-module bootstrap + Category I green | M6 |

## Architecture

See the spec artifacts (folded in this repository's `docs/` once M1 lands):

- **A** — Substrate Contract + Registry API
- **B** — Degradation State Machine (L0–L4)
- **C** — Router Decision Tree
- **D** — Workspace Memory Model (VSA hypervector store)
- **E** — Reference Implementation Plan
- **F** — Test Harness
- **A0** — B.3 amendment (trigger mapping, sequencing, sign correction)
- **A1** — Rule-Trace Format
- **A2** — Conformal Calibration Protocol
- **A3** — SDK API Reference
- **A4** — Health Escalation Policy
- **A5** — Trace Entry Schemas (workspace + lifecycle)
- **A6** — Exploration Sink Registry

## License

Apache-2.0. See `LICENSE`.
