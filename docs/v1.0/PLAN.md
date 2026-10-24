# Organism v1.0 — Completion Plan

**Date:** 2026-10-24 (America/New_York)  
**Base:** v0.4.0 @ `1fed718` (115 tests)  
**Repo:** https://github.com/RechargedIdeas/organism  
**Goal:** Complete **software Organism** and tag **v1.0.0**. Real silicon/wetware remain external; faithful simulators behind hardware gates count as phase-complete (`RESEARCH_SIM` in STATUS).

## Gaps from STATUS E.8 / OOS (closing in v1.0)

| Gap | Close via | Notes |
|---|---|---|
| Kernel / reservoir / HDC / energy / spectral / neurosymbolic production modules | **Phase B** | Reference modules with full SubstrateContract |
| Full RL-DCA online training; learned ISE on control after promote; revoke | **Phase C** | Promote success + revoke tests |
| Live metamodel NAS (tiny search space) + shadow winners | **Phase C** | Exploration → sandbox → shadow → promote |
| Multi-**process** distributed + federated oxytocin ≥3 + BFT-ish (f=1, N=4) | **Phase D** | Software sim; clock skew injection |
| Neuromorphic simulator (`ORGANISM_NEURO_SIM=1`) | **Phase E** | Default gated off |
| Physical/molecular research module | **Phase E** | Exploration-only; never control path |
| Rust runtime parity (registry/workspace already; router/degradation stubs) | **Phase F** | cargo test green |
| Wall-clock/soak docs, CI gates, README, CHANGELOG, API freeze 1.0 | **Phase G** | |
| Tag `v1.0.0` + GitHub Release + STATUS COMPLETE | **Phase H** | |

## Optimal order (do not skip)

| Phase | Deliverable | Exit |
|---|---|---|
| **A** | This plan + STATUS open | committed + pushed |
| **B** | Six substrate modules + tests | suite green; push |
| **C** | RL-DCA loop, ISE promote/revoke, live NAS | suite green; push |
| **D** | Multi-process cluster, oxytocin, BFT-ish, clock skew | suite green; push |
| **E** | Neuro sim backend + physical research module | suite green; push |
| **F** | Rust router + degradation parity | cargo test green; push |
| **G** | Hardening docs, gates, freeze, versions → 1.0.0 | push |
| **H** | Full pytest + cargo; annotated tag; `gh release create` | **COMPLETE** |

## Substrate ecology (Phase B targets)

From corpus §2 substrates that were stubs or missing as Python modules:

1. **kernel** — kernel fallback + reservoir readout trainer hooks (T1 SOLVER / FEATURE)
2. **hdc** — HDC workspace helper / fingerprint module (beyond Hypervector primitives)
3. **reservoir** — fixed dynamics + ridge/kernel readout (T1 PREDICTION temporal)
4. **energy_hopfield** — energy-based / Hopfield constraint solver (T1 SOLVER)
5. **spectral** — spectral / wavelet front-end (T1 FRONTEND / FEATURE_EXTRACTOR)
6. **neurosymbolic** — three-level causal verifier certificates (T0/T1 VERIFIER)

Keep `deterministic_engine` + `learned_module` + `snn_sentinel`.

## Constraints (carry forward)

1. Prior 115+ tests stay green.
2. Prefer real thin implementations over theater.
3. Never put physical/molecular on control path.
4. Continuous STATUS updates; IMP-* for mechanical amendments.
5. Never force-push; `git pull --rebase` before push.
6. If blocked on real silicon/wetware → ship simulator + mark `RESEARCH_SIM`.

## True external deps after v1.0 (allowed remaining)

- Real neuromorphic silicon (Loihi-class)
- Wet-lab / molecular physical substrates
- Production BFT across WAN / hardware TPM attestation
