# Organism

**Organism** is a production-grade AI/ML substrate: a runtime, contract system, and orchestration layer that hosts heterogeneous computational modules, couples them through a shared vector-symbolic workspace, routes work by task structure and physiological state, and degrades through a graded series of alternative metabolisms rather than crashing.

Organism is not a model. It is the **substrate** in which models live.

## Status

| | |
|---|---|
| **Release** | **v1.10.0** — Bare metal first · native sandbox · Docker optional |
| **Repo** | https://github.com/RechargedIdeas/organism (private) |
| **API freeze** | [docs/API_FREEZE_v1.0.md](docs/API_FREEZE_v1.0.md) |
| **Plan** | [docs/v1.0/PLAN.md](docs/v1.0/PLAN.md) |
| **Hardening** | [docs/v1.0/HARDENING.md](docs/v1.0/HARDENING.md) |
| **CPU Everywhere** | [docs/CPU_EVERYWHERE.md](docs/CPU_EVERYWHERE.md) |
| **Deploy** | [deploy/README.md](deploy/README.md) — **Docker optional; bare metal first** |
| **Bare metal + sandbox** | [docs/v1.10/BARE_METAL_AND_SANDBOX.md](docs/v1.10/BARE_METAL_AND_SANDBOX.md) |
| **Soak runbook** | [docs/ops/SOAK_RUNBOOK.md](docs/ops/SOAK_RUNBOOK.md) |
| **Degradation drillbook** | [docs/ops/DEGRADATION_DRILLBOOK.md](docs/ops/DEGRADATION_DRILLBOOK.md) |
| **Wet-lab safety** | [docs/ops/WETLAB_SAFETY_POLICY.md](docs/ops/WETLAB_SAFETY_POLICY.md) |
| **Desktop** | [docs/v1.5/DESKTOP.md](docs/v1.5/DESKTOP.md) · [docs/v1.6/DESKTOP.md](docs/v1.6/DESKTOP.md) · [docs/v1.6.1/DESKTOP.md](docs/v1.6.1/DESKTOP.md) · [docs/v1.7/DESKTOP.md](docs/v1.7/DESKTOP.md) · [docs/v1.8/DESKTOP.md](docs/v1.8/DESKTOP.md) |
| **Generative** | [docs/v1.7/ORGANISM_GENERATIVE_EVOLUTION.md](docs/v1.7/ORGANISM_GENERATIVE_EVOLUTION.md) · [docs/v1.8/ORGANISM_SURFACES.md](docs/v1.8/ORGANISM_SURFACES.md) |
| **Audit** | [docs/AUDIT_v1.8.md](docs/AUDIT_v1.8.md) · [docs/v1.9/AUDIT_CLOSURE.md](docs/v1.9/AUDIT_CLOSURE.md) |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |
| **Implementation** | [STATUS.md](STATUS.md) |
| **CI** | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) · [`ci/gates.yaml`](ci/gates.yaml) |

Stable surface = Python SDK core + proto `organism.v1` + substrate ecology modules + Rust registry/workspace/router/degradation/control-loop + Desktop + generative pipelines. Neuromorphic/physical without hardware remain **RESEARCH_SIM** / exploration-only.

## Quickstart

```bash
make proto
make python-install   # prefer .venv
make rust-build

PYTHONPATH=sdk/python:modules:desktop:. .venv/bin/python -m pytest -q -m 'not slow'
cargo test --workspace
```

Opt-in longer / sim runs:

```bash
ORGANISM_WALL_CLOCK_FULL=1 ...   # Category I ~480s (opt-in; see SOAK_RUNBOOK)
ORGANISM_SOAK_FULL=1 ...         # extended soak — target-box cadence, not default CI
ORGANISM_NEURO_SIM=1 ...         # neuromorphic RESEARCH_SIM
ORGANISM_BIO_GPU_TWIN=1 ...      # prefer GPU twin; CPU fallback automatic
ORGANISM_LLM_ENABLED=1 ...       # optional HostedLLMBackend (never default-on)
```

## Generative CLI (Organism self-evolution)

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk list-templates
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  evolve-skill --name navigator --intent "Navigate feature space"
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  evolve-looks --brief "ocean theme" --pack
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  evolve-code --intent "score features" --auto-promote
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk rollback-code
```

Promote gates remain mandatory. Hot-register caps at **EXPLORATION** /
`may_actuate=False`. Bio actuation stays refused.

## Run on any hardware (CPU-only, N steps)

No GPU, no Hybrid checkout, and **no Docker** required. See [deploy/README.md](deploy/README.md) and [docs/v1.10/BARE_METAL_AND_SANDBOX.md](docs/v1.10/BARE_METAL_AND_SANDBOX.md).

```bash
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk sandbox self-check
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk status
```

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev,desktop]"
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  validate-config -c deploy/config/cpu_only.yaml
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  serve -c deploy/config/cpu_only.yaml --dry-run
organism-desktop   # PySide6 control plane
```

Docker is **optional**. Prefer bare metal / VM (`deploy/bare/install.sh`).
Container example (Podman or Docker):
`podman build -f deploy/container/Containerfile -t organism:cpu .`

## Repository structure

| Directory | Contents |
|---|---|
| `proto/` | proto3 source of truth (`organism.v1`) |
| `sdk/python/` | Python authoring SDK (+ distributed, generative, neuro_sim) |
| `sdk/rust/` | Rust runtime SDK |
| `runtime/` | Registry, workspace, router, degradation, control loop |
| `modules/` | deterministic, learned, `kernel_module`, `hdc_module`, reservoir, energy, spectral, neurosymbolic, snn, physical, `generative`, `bio_digital` |
| `modules/hdc` · `modules/kernel` | Tiny **Rust helper crates** (not Python modules) — see [modules/README_RUST_HELPERS.md](modules/README_RUST_HELPERS.md) |
| `desktop/` | Organism Desktop (PySide6) + packaging `.spec` |
| `harness/` | Fault injection + scenarios |
| `ci/` | Gate definitions (`gates.yaml`) |
| `.github/workflows/` | GitHub Actions CI |
| `docs/` | Architecture, plans, audit, ops |

## Milestone lines

| Line | Deliverable |
|---|---|
| **v0.1–v0.4** | Proto through hardening + API freeze 0.4.0 |
| **v1.0** | Substrate ecology, learned control, multi-process federation, HW sims, Rust parity |
| **v1.5–v1.8** | Desktop control plane + Organism generative evolution |
| **v1.9** | Audit closure — CI, hosted LLM adapter, sandbox jail, generative CLI, physiology depth |

## License

Apache-2.0. See `LICENSE`.

## Bio-Digital Hybrid Cluster

See [docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md](docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md) for the mapping of Physarum/Mycelium RESEARCH_TIER adapters (`modules/bio_digital/`). Hybrid Studio UI is **not** imported.
