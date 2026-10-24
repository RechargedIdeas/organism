# Organism API Freeze — v1.0.0

**Date:** 2026-10-24 (America/New_York)  
**Release:** `v1.0.0`  
**Repo:** https://github.com/RechargedIdeas/organism (private)  
**Plan:** [docs/v1.0/PLAN.md](v1.0/PLAN.md)

SemVer **1.0.0** freezes the software Organism. Breaking changes to frozen symbols require a major bump.

## Version alignment

| Artifact | Version |
|---|---|
| Python `organism` / `organism-sdk` | `1.0.0` |
| `organism_sdk.__version__` | `1.0.0` |
| Rust workspace | `1.0.0` |
| Git tag | `v1.0.0` |

## Stable (frozen)

1. Proto `organism.v1` (nine files) — additive-only field/enum rules unchanged from v0.4.
2. Python SDK core: contract, module ABC, registry, workspace, router, degradation, hypervector, justification, health, inputs, snapshot/trace clients as in v0.4 freeze.
3. Reference modules on default control path: `deterministic_engine`, `learned_module` (cross-check), plus **substrate ecology** contracts for `kernel_module`, `hdc_module`, `reservoir`, `energy_hopfield`, `spectral`, `neurosymbolic` (register/handle/health APIs).
4. Rust runtime crates used in M2–M6 paths: `organism-registry`, `organism-workspace`, `organism-router`, `organism-degradation` public APIs tested in-crate.
5. Blocking CI gates in `ci/gates.yaml` for v0.1–v1.0 remain blocking.

## Graduated to stable-with-gates (were experimental in 0.4)

| Area | Gate |
|---|---|
| Learned ISE control path | Only after shadow+promote; revoke supported |
| Metamodel / NAS winners | Exploration → sandbox → shadow → promote |
| Multi-process federation | Opt-in ProcessCluster; default single-box |
| SNN sentinel | Hardware gate; `ORGANISM_NEURO_SIM=1` = RESEARCH_SIM |

## Still experimental / RESEARCH_SIM (not control-path by default)

| Area | Status |
|---|---|
| Physical/molecular module | Exploration-only; refuses `control_actuation` |
| Neuromorphic without sim/HW | Register OK; no production dispatch |
| Full WAN BFT / TPM attestation | Software BFT-ish sim only (f=1, N=4) |
| Real Loihi-class silicon / wet lab | **External** — not in this release |

## Opt-in long runs

Documented in [docs/v1.0/HARDENING.md](v1.0/HARDENING.md):

- `ORGANISM_WALL_CLOCK_FULL=1` — Category I ~480s wall-clock
- `ORGANISM_SOAK_FULL=1` — extended soak
- `ORGANISM_NEURO_SIM=1` — neuromorphic RESEARCH_SIM

## Compatibility with v0.4

v1.0 is a **compatible major** for frozen 0.4 symbols (additive). Experimental 0.4 biology APIs remain available; multi-process and substrate modules are additive.
