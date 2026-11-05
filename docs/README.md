# Organism documentation

Start with [STATUS.md](../STATUS.md) for the current release and what is in progress, and
[CHANGELOG.md](../CHANGELOG.md) for what changed in each version.

## Current work

- [GAP_ANALYSIS.md](GAP_ANALYSIS.md): the latest gap review. It lists what is fixed, what is open,
  and the decisions still needed.
- [UPGRADE_AND_EXPANSION_PLAN.md](UPGRADE_AND_EXPANSION_PLAN.md): the roadmap, including the
  open decisions in section 7.
- [v1.11/MOA_LAYER.md](v1.11/MOA_LAYER.md): the mixture-of-experts layer. Its design record covers
  experts, routing, tiers, and the Phase 5 guardrails.

## Frozen contracts

- [API_FREEZE_v0.4.md](API_FREEZE_v0.4.md): the frozen Python SDK surface. A test checks every name.
- [API_FREEZE_v1.0.md](API_FREEZE_v1.0.md): the v1.0.0 API freeze.

## Platform and operations

- [CPU_EVERYWHERE.md](CPU_EVERYWHERE.md): the CPU-first product guarantee.
- [v1.10/BARE_METAL_AND_SANDBOX.md](v1.10/BARE_METAL_AND_SANDBOX.md): host portability and the native sandbox.
- [architecture/README.md](architecture/README.md): the closed artifact corpus (A to F, addenda A0
  to A6, and the R-amendments).
- [ops/SOAK_RUNBOOK.md](ops/SOAK_RUNBOOK.md): running the extended soak.
- [ops/DEGRADATION_DRILLBOOK.md](ops/DEGRADATION_DRILLBOOK.md): degradation drills for the Desktop
  Physiology view (a virtual-clock demo).
- [ops/WETLAB_SAFETY_POLICY.md](ops/WETLAB_SAFETY_POLICY.md): the wet-lab safety policy. Actuation
  is hard-refused.
- [v0.4/PERF.md](v0.4/PERF.md): the v0.4 performance budgets.

## Integrations

- [integrations/VENDOR.md](integrations/VENDOR.md): the upstream Bio-Digital Hybrid Cluster
  repository and the Organism adapters in `modules/bio_digital/`.
- [integrations/BIO_DIGITAL_HYBRID_CLUSTER.md](integrations/BIO_DIGITAL_HYBRID_CLUSTER.md): how the
  Bio-Digital Hybrid Cluster maps onto Organism.

## Audits and history

- [AUDIT_v1.8.md](AUDIT_v1.8.md): the v1.8 software audit.
- [v1.9/AUDIT_CLOSURE.md](v1.9/AUDIT_CLOSURE.md): how the audit backlog was closed in v1.9.
- [v0.4/PLAN.md](v0.4/PLAN.md): the v0.4 hardening plan.

Each version folder (`v0.2` to `v1.11`) holds the design notes for that release.

## Local CI

The local pipeline and its gates are documented in [../ci/README.md](../ci/README.md). Its gate
definitions are in [../ci/gates.yaml](../ci/gates.yaml).
