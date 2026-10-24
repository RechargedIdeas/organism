# Organism v0.3 — Plan

**Date:** 2026-10-24 (America/New_York)  
**Corpus base:** closed v0.1 + v0.2 biological (Artifacts G–J / F J–O)  
**Repo:** https://github.com/RechargedIdeas/organism  
**Prior HEAD at open:** `5105a54` (81 tests green)

## Goal

Lift intentional E.8 deferrals that are implementable as **single-box / in-process** vertical slices, without placing physical/molecular substrates or real neuromorphic hardware on the control path.

## Optimal dependency order (do not reorder)

| ID | Milestone | Depends on | Exit criteria |
|---|---|---|---|
| **M0** | Plan + STATUS | — | This document + STATUS.md updated |
| **v0.3-M1** | Learned ISE + RL-DCA | M0, v0.2 G/I | Online predictive ISE; prediction error → allostatic/hormone signal; shadow vs T0; failed promotion never actuates; suite green |
| **v0.3-M2** | Metamodel reproductive synthesizer | M1 (ecology + exploration) | synthesize → sandbox → shadow → promote/reject; new organ cannot actuate until promoted; `MetamodelDisabled` scoped (disabled mode / non-exploration) |
| **v0.3-M3** | Multi-node foundation | M2 optional; HormoneBus | ≥2 in-process nodes; hormone/workspace mirror + measurable lag; federated oxytocin quorum for 2–3 nodes; single-device default; partition → safe degrade; suite green |
| **v0.3-M4** | SNN sentinel | M3 optional; registry/router | Module registers with SPIKE_TRAIN contract; **hardware gate**: no production control dispatch without NEUROMORPHIC capability; simulated spike-rate wake escalates router; suite green |

## What stays hardware-gated / research-tier

| Topic | Status in v0.3 |
|---|---|
| Real neuromorphic silicon / Loihi-class SNN | **Hardware-gated** — register + simulate only; no control dispatch |
| Physical / molecular substrates | **Research-tier docs only** — never on control path |
| Full BFT cluster / clock sync / state replication | **Deferred** — M3 is in-process multi-node simulation, not production cluster |
| Live NAS / large hypernetwork training | **Stub OK** — instant hypernetwork-style synthesizer if NAS too heavy; must still pass four-part contract + shadow |
| Full RL-DCA offline corpus training loops | Thin online residual + Danger/PAMP/Safe weights; heavy training deferred |

## Design constraints (carry forward)

1. Workspace remains SoT for hormone / immune / interoceptive bindings; bus is mirror.
2. T0 never self-terminates; control-affecting successors need shadow-validate + promotion.
3. Router is sole dispatcher; autonomic only modulates declared params.
4. Prefer thin vertical slices over unfinished grandiose code.
5. Prior 81+ tests stay green; add new tests; full default suite must pass before each push to `main`.
6. Never force-push; `git pull --rebase` before push.

## Gates (additive)

| Gate id | Blocking | Milestone |
|---|---|---|
| `v03:plan` | docs | M0 |
| `v03:learned_ise` | true | M1 |
| `v03:metamodel` | true | M2 |
| `v03:multinode` | true | M3 |
| `v03:snn_sentinel` | true | M4 |

## Physical / molecular note

Any molecular, wetware, or exotic physical substrate remains **research-tier documentation** under `docs/v0.3/`. It must not appear on the control or actuation path in this cut.
