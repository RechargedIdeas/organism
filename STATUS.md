# Organism — Implementation Status

**Date:** 2026-10-24 (America/New_York)  
**Release:** **v0.4.0 → v1.0.0 in progress**  
**Corpus:** closed v0.1–v0.4 + **v1.0 completion plan**  
**Repo:** https://github.com/RechargedIdeas/organism (private)

## v1.0 — Completion (software Organism)

See [docs/v1.0/PLAN.md](docs/v1.0/PLAN.md). Order: A → H; do not skip.

| Phase | Status | Notes |
|---|---|---|
| **A** Plan | **green** | `docs/v1.0/PLAN.md` — closes E.8/OOS via software + RESEARCH_SIM |
| **B** Substrate ecology | **green** | kernel, hdc, reservoir, energy_hopfield, spectral, neurosymbolic — 8 new tests |
| **C** Learned control maturity | **green** | RL-DCA train_online_loop; promote+revoke; live NAS search |
| **D** Distributed (multi-process) | **green** | ProcessCluster; oxytocin ≥3; BFT f=1 N=4; clock skew |
| **E** Hardware simulators | **green** | NEURO_SIM gate; physical_research exploration-only RESEARCH_SIM |
| **F** Rust runtime parity | pending | router + degradation beyond stubs |
| **G** Hardening completion | pending | freeze docs, CHANGELOG, versions 1.0.0 |
| **H** Release v1.0.0 | pending | tag + gh release; STATUS COMPLETE |

### Amendments (IMP-*)
| ID | Topic | Resolution |
|---|---|---|
| IMP-22 | contract_factory | Shared `modules/_common/contract_factory.py` for reference substrates |

---

## Milestone summary

| Milestone | Status | Notes |
|---|---|---|
| Batch 1 / Proto | **green** | Additive v0.2 lifecycle enums in `common.proto` |
| **M1–M7** (v0.1) | **green** | Unchanged; suite still green |
| Wall-clock fast / `perf:slo` | **green** | Opt-in full 480s unchanged |
| **v0.2 G–J + F J–O** | **green** | Full biological matrix |
| **v0.3-M0 Plan** | **green** | `docs/v0.3/PLAN.md` |
| **v0.3-M1** Learned ISE + RL-DCA | **green** | Online predictor + allostatic/hormone signal; promotion gate |
| **v0.3-M2** Metamodel synthesizer | **green** | synthesize→sandbox→shadow→promote; MetamodelDisabled scoped |
| **v0.3-M3** Multi-node + federated oxytocin | **green** | In-process nodes; lag SLO; oxytocin quorum; single-device default |
| **v0.3-M4** SNN sentinel | **green** | Registers; hardware-gated; simulated spike wake escalates router |
| **v0.4-M0 Plan** | **green** | `docs/v0.4/PLAN.md` — soak, perf budgets, security fuzz |
| **v0.4-M1 Soak** | **green** | Multi-window harness; GC proxy; traces reconstructible |
| **v0.4-M2 Perf budgets** | **green** | Budgets in PERF.md; blocking perf:* gates |
| **v0.4-M3 Security fuzz** | **green** | Malformed/forge/byzantine/capability/justification |
| **v0.4 API freeze / tag** | **green** | `docs/API_FREEZE_v0.4.md` + `CHANGELOG.md` + versions `0.4.0` + tag `v0.4.0` |

**Full suite (default):** 115 passed (2 slow deselected) at v0.4.0 freeze.

**Plans:** [docs/v0.3/PLAN.md](docs/v0.3/PLAN.md) · [docs/v0.4/PLAN.md](docs/v0.4/PLAN.md) · [docs/v0.4/PERF.md](docs/v0.4/PERF.md) · [docs/API_FREEZE_v0.4.md](docs/API_FREEZE_v0.4.md)

---

## v0.2 — Biological extension (runtime)

Structural answers from `docs/v0.2/STRUCTURAL_ANSWERS.md` adopted exactly.

| Organ | Module | Trace |
|---|---|---|
| HormoneBus | `organism_sdk/hormone.py` | `emit_hormone` + Decision Trace `rationale.hormone` |
| ISE | `organism_sdk/interoceptive.py` | workspace `interoceptive_state` |
| Learned ISE | `organism_sdk/learned_ise.py` | promotion gate; not control-path until promote |
| ImmuneLayer | `organism_sdk/immune.py` | `emit_immune` + `immune_decision` bindings |
| AutonomicController | `organism_sdk/autonomic.py` | `emit_autonomic`; router `set_autonomic_params` |
| Apoptosis | `organism_sdk/apoptosis.py` | DeathCertificate; N4 synthetic drain; N5 shadow-validate |
| CircadianClock | `organism_sdk/circadian.py` | exploration_budget gate |
| Morphogenesis | `organism_sdk/morphogenesis.py` | DEVELOPMENT ⊂ EXPLORATION; O2/O3 helpers |
| FederationGate | `organism_sdk/federation.py` | Fail-closed FED_OXYTOCIN / MIRROR_LAG |
| MetamodelTracker | `organism_sdk/metamodel.py` | Reproductive path disabled (E.8) |
| Kleiber share | `kleiber_declared_share` | O5 inefficiency flag |

### Invariants enforced in tests
- G/K: SoT write → mirror consistency; staleness_ms; workspace fallback + diagnosis; shield non-override
- H/L: FULL + affects_control; no `deregister`; memory hit; cortisol → quarantine; replay
- I/M/N: router sole dispatcher; T0 never self-terminates; control-affecting needs successor; drain-killed → synthetic lifecycle (no silent SUCCEEDED); shadow-validate fail blocks promotion
- J/O: stage fail retains prior; DEVELOPMENT holds control_actuation; rest suppressed in crisis; Kleiber inefficiency flag
- Stubs: learned ISE blocked pre-promotion; federated oxytocin / multi-node lag raise `FederationUnsupported`; metamodel `synthesize` raises `MetamodelDisabled`

### Proto (additive)
`ModuleLifecycleState` += `SELF_TERMINATING`, `SUCCEEDED`, `DEVELOPMENT`, `DEGRADED` (values 8–11). Proto regen green.

### Amendments (IMP-*)
| ID | Topic | Resolution |
|---|---|---|
| IMP-5..7 | Wall-clock | Prior (v0.1) |
| IMP-8 | BindingRecord payload / affects_control | Additive fields for hormone/immune/death cert payloads; snapshot serialize |
| IMP-9 | `Lifecycle.self_termination_permitted` | Python contract field; proto Lifecycle message unchanged this cut |
| IMP-10 | `Hypervector.random(seed=)` | Deterministic HV for organs/tests |
| IMP-11 | `LifecycleTraceEntry.on_drain_*` | Additive drain outcome + synthetic flag for N4 |
| IMP-12 | Apoptosis N4/N5 | Drain-killed mid-export; `shadow_validate_successor` + `promote_successor` |

### Gates
`ci/gates.yaml`: `v02:hormone`, `v02:immune`, `v02:autonomic_apoptosis`, `v02:morphogenesis_circadian`, `v02:harness_jo`, `v02:stubs_gates` — **blocking: true**, status green.

`category_bio`: **J1–J4, K1–K6, L1–L6, M1–M4, N1–N5, O1–O5**, LEARNED_ISE, FED_OXYTOCIN, MIRROR_LAG_OOS, METAMODEL_OOS — all **green**.

### Remaining deferred (clean E.8 / docs boundaries)
- **Distributed Organism** (cluster, BFT, state replication, clock sync) — E.8; federation stubs fail closed
- **Full federated oxytocin consensus** — requires Distributed; stub only
- **Real multi-node HormoneBus mirror lag cluster** — OOS gate only
- **Learned ISE replacing T0 `f(H)` in production** — stub + promotion hooks only; not deployed on control path by default
- **RL-DCA online training loop** — thin weight nudge stub; full DCA training deferred (H.out-of-scope)
- **Metamodel reproductive synthesizer** — disabled; E.8 until corpus opens it
- **SNN hardware paths / physical substrates** — E.8

### Tooling
```bash
PYTHON=.venv/bin/python
make proto PYTHON=.venv/bin/python
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m pytest -q \
  tests/contract sdk/python/tests modules/deterministic_engine/tests \
  modules/learned_module/tests tests/integration -m 'not slow'
```

---

## v0.3 — Opening (E.8 lifts, ordered)

See `docs/v0.3/PLAN.md`. Order is fixed: M0 → M1 Learned ISE → M2 Metamodel → M3 Multi-node → M4 SNN.

### Amendments (IMP-*)
| ID | Topic | Resolution |
|---|---|---|
| IMP-13 | v0.3 plan | Documented optimal order + hardware gates; physical/molecular stay research-tier |

### v0.3-M1 (landed)
- `learned_ise.py`: online RL-DCA predictive head; `AllostaticSignal`; `shadow_compare`; hormone nudge without actuation
- Tests: `test_v03_learned_ise.py`; stub gate model version → `0.3.0-learned-ise`
- IMP-14: prediction error may drive HormoneBus inputs pre-promotion; `for_control` still PermissionError until promote

### v0.3-M2 (landed)
- `metamodel.py`: exploration synthesizer (hypernetwork stub); four-part contract; sandbox/shadow/promote; deliberation only after promote
- `MetamodelDisabled` when `enabled=False` or not exploration (v0.2 stub test preserved)
- IMP-15: new organ `may_actuate=False` until PROMOTED

### v0.3-M3 (landed)
- `multinode.py`: OrganismNode, MirrorFabric, MultiNodeCluster; lag SLO; oxytocin quorum; partition → safe degrade
- `federation.py`: `enable_multi_node` opt-in; default still FederationUnsupported (v0.2 tests)
- IMP-16: multi-node is in-process simulation, not BFT cluster

### v0.3-M4 (landed)
- `modules/snn_sentinel`: SENTINEL + SPIKE_TRAIN + NEUROMORPHIC metabolic requirement
- Router: `available_hardware` gate (`hardware_capability_missing`); `escalate_from_sentinel`
- ModuleHandle: additive `hardware_requirement`
- Docs: `docs/v0.3/HARDWARE.md` — physical/molecular research-tier only
- IMP-17: no neuromorphic on box → register + simulate OK; no production control dispatch

### v0.3 complete (M0–M4)
All ordered milestones green on main. Remaining intentional gaps: real neuromorphic silicon, BFT cluster, live NAS training, molecular substrates (research-tier).

---

## v0.4 — Hardening (soak / perf / security)

See `docs/v0.4/PLAN.md`. Order is fixed: M0 → M1 Soak → M2 Perf → M3 Security fuzz.

### Amendments (IMP-*)
| ID | Topic | Resolution |
|---|---|---|
| IMP-18 | v0.4 plan | Documented optimal order; neuromorphic/BFT/NAS/molecular stay OOS unless thin-gated |
| IMP-19 | Workspace GC | `binding_count` + `gc_ephemeral`; protects hormone_state/immune_decision + affects_control |
| IMP-20 | Perf budgets | Headroom budgets (~50–100× baseline); blocking on this box |
| IMP-21 | Security harden | Immune forgery reject; out-of-scope read raise; validate_control_binding |

### Still OOS (carry from E.8)
Real neuromorphic silicon, full BFT cluster, live NAS, molecular/physical substrates — research-tier / hardware-gated only.

### v0.4-M1 (landed)
- `harness/scenarios/v04_soak.py`: register → route → hormone windows → degrade pulse → GC
- Fast CI soak (24–40 simulated windows); `ORGANISM_SOAK_FULL=1` extended soak
- Asserts: no flapping; hormone_state queryable; binding_count bounded; routing traces ≥ plans

### v0.4-M2 (landed)
- `docs/v0.4/PERF.md` + `harness/scenarios/v04_perf.py`
- Gates: `perf:router`, `perf:workspace`, `perf:hormone`, `perf:degradation` (blocking)
- Router p95 ≤5ms; workspace bind/query/unbind; hormone publish; virtual degrade confirm

### v0.4-M3 (landed)
- Malformed contracts → ERROR / RegistrationRejected
- Untrusted control_actuation without justification → JustificationMissing
- Byzantine strikes → L4 + DegradedDispatchPlan (T0 only)
- Capability-scope write reject + read raise on foreign tags
- Immune quarantine forgery rejected without FULL/affects_control/immune_layer
- Fixed-seed fuzz: `fuzz_malformed_contracts`, `fuzz_immune_forgeries`

### v0.4 complete (M0–M3)
Hardening path green. Still OOS: real neuromorphic silicon, full BFT cluster, live NAS, molecular substrates.

### v0.4.0 release freeze
- Versions bumped to `0.4.0` (root + sdk pyproject, Cargo workspace, `organism_sdk.__version__`).
- Public API freeze documented; experimental biology / multi-node / SNN explicitly non-frozen.
- Annotated git tag `v0.4.0` on the freeze commit; GitHub Release notes from CHANGELOG.
