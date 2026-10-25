# Organism

**Organism** is a production-grade AI/ML substrate: a runtime, contract system, and orchestration layer that hosts heterogeneous computational modules, couples them through a shared vector-symbolic workspace, routes work by task structure and physiological state, and degrades through a graded series of alternative metabolisms rather than crashing.

Organism is not a model. It is the **substrate** in which models live.

## Status

| | |
|---|---|
| **Release** | **v1.3.0** — CPU Everywhere (GPU workloads fall back to CPU) |
| **Repo** | https://github.com/RechargedIdeas/organism (private) |
| **API freeze** | [docs/API_FREEZE_v1.0.md](docs/API_FREEZE_v1.0.md) |
| **Plan** | [docs/v1.0/PLAN.md](docs/v1.0/PLAN.md) |
| **Hardening** | [docs/v1.0/HARDENING.md](docs/v1.0/HARDENING.md) |
| **CPU Everywhere** | [docs/CPU_EVERYWHERE.md](docs/CPU_EVERYWHERE.md) |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |
| **Implementation** | [STATUS.md](STATUS.md) |

Stable surface = Python SDK core + proto `organism.v1` + substrate ecology modules + Rust registry/workspace/router/degradation. Neuromorphic/physical without hardware remain **RESEARCH_SIM** / exploration-only.

## Quickstart

```bash
make proto
make python-install   # prefer .venv
make rust-build

PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q -m 'not slow'
cargo test --workspace
```

Opt-in longer / sim runs:

```bash
ORGANISM_WALL_CLOCK_FULL=1 ...   # Category I ~480s
ORGANISM_SOAK_FULL=1 ...         # extended soak
ORGANISM_NEURO_SIM=1 ...         # neuromorphic RESEARCH_SIM
ORGANISM_BIO_GPU_TWIN=1 ...      # prefer GPU twin; CPU fallback automatic
```

## Repository structure

| Directory | Contents |
|---|---|
| `proto/` | proto3 source of truth (`organism.v1`) |
| `sdk/python/` | Python authoring SDK (+ distributed, neuro_sim) |
| `sdk/rust/` | Rust runtime SDK |
| `runtime/` | Registry, workspace, router, degradation, control loop |
| `modules/` | deterministic, learned, kernel, hdc, reservoir, energy, spectral, neurosymbolic, snn, physical |
| `harness/` | Fault injection + scenarios |
| `ci/` | Gate definitions |
| `docs/` | Architecture, v0.2–v1.0 plans, API freeze |

## Milestone lines

| Line | Deliverable |
|---|---|
| **v0.1–v0.4** | Proto through hardening + API freeze 0.4.0 |
| **v1.0** | Substrate ecology, learned control, multi-process federation, HW sims, Rust parity, tag **v1.0.0** |

## License

Apache-2.0. See `LICENSE`.


## Bio-Digital Hybrid Cluster

See [docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md](docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md) for the mapping of Physarum/Mycelium RESEARCH_TIER adapters (`modules/bio_digital/`).
