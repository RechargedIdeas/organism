# Organism

**Organism** is a production-grade AI/ML substrate: a runtime, contract system, and orchestration layer that hosts heterogeneous computational modules, couples them through a shared vector-symbolic workspace, routes work by task structure and physiological state, and degrades through a graded series of alternative metabolisms rather than crashing.

Organism is not a model. It is the **substrate** in which models live.

## Status

| | |
|---|---|
| **Release** | **v0.4.0** (API freeze) |
| **Repo** | https://github.com/RechargedIdeas/organism (private) |
| **Default tests** | 115 passed (`-m 'not slow'`) |
| **Spec** | closed v0.1 corpus + v0.2 biological + v0.3 E.8 lifts + v0.4 hardening |

- **API freeze:** [docs/API_FREEZE_v0.4.md](docs/API_FREEZE_v0.4.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **Implementation status:** [STATUS.md](STATUS.md)
- **Plans / perf:** [docs/v0.4/PLAN.md](docs/v0.4/PLAN.md) · [docs/v0.4/PERF.md](docs/v0.4/PERF.md) · [docs/v0.3/PLAN.md](docs/v0.3/PLAN.md)

Stable surface = Python SDK core + proto `organism.v1`. Biological organs, multi-node simulation, learned ISE/metamodel, and SNN are **experimental** (tested, fail-closed; not SemVer-frozen). See the freeze note.

## Quickstart

```bash
# Generate proto stubs
make proto

# Install Python SDK (prefer a venv)
make python-install

# Build Rust workspace
make rust-build

# Run default test suite (excludes @pytest.mark.slow)
make test
# or:
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
```

Opt-in longer runs:

```bash
ORGANISM_WALL_CLOCK_FULL=1 ...  # Category I wall-clock / perf:slo
ORGANISM_SOAK_FULL=1 ...        # extended soak
```

## Repository structure

| Directory | Contents |
|---|---|
| `proto/` | proto3 source of truth (`organism.v1`) |
| `sdk/python/` | Python authoring SDK |
| `sdk/rust/` | Rust runtime SDK |
| `runtime/` | Core runtime services (registry, workspace, router, degradation, control loop) |
| `modules/` | Reference modules (deterministic engine, learned, kernel, HDC, SNN sentinel) |
| `harness/` | Test harness (runner, injector, observer, scenarios) |
| `ci/` | CI gate definitions |
| `docs/` | Architecture, v0.2–v0.4 plans, API freeze |

## Milestone lines

| Line | Deliverable |
|---|---|
| **v0.1 M1–M7** | Proto + SDK + registry/workspace/router + learned + snapshots + degradation + CI bootstrap |
| **v0.2** | Biological organs + full J–O fault matrix |
| **v0.3** | Learned ISE, metamodel, multi-node sim, SNN sentinel (ordered E.8 lifts) |
| **v0.4** | Soak, perf budgets, security fuzz + **API freeze / tag** |

## Architecture

See the spec artifacts folded into this repository's docs and STATUS:

- **A** — Substrate Contract + Registry API
- **B** — Degradation State Machine (L0–L4)
- **C** — Router Decision Tree
- **D** — Workspace Memory Model (VSA hypervector store)
- **E** — Reference Implementation Plan
- **F** — Test Harness
- **A0–A6** — Amendments (triggers, rule-trace, calibration, SDK, health, traces, exploration)
- **G–J / J–O** — Biological organs and fault matrix (v0.2+)

## License

Apache-2.0. See `LICENSE`.
