# Organism software audit — v1.8.1

**Date:** 2026-10-24 (America/New_York)  
**Tip audited:** `1b9d7e8` · tag **v1.8.1**  
**Suite:** 334 passed · 0 skipped · 2 slow deselected (`-m 'not slow'`)  
**Scope:** Software improvements, enhancements, and gaps. Hardware/external deps listed separately and **not** proposed as “software fixes.”

## Executive summary

STATUS.md correctly frames neuromorphic silicon, wet-lab GPIO, and production WAN BFT+TPM as **out-of-software**. This audit still finds meaningful **software** work: docs/README drift, missing CI workflows, no v1.8 gates, generative backends that are offline stubs/procedural SVG, Desktop/SDK surface gaps, and sandbox that is AST-whitelist rather than process-isolated.

**Counts (software only):** P0 **1** · P1 **8** · P2 **14** · P3 **7**  
**Hardware/external (won't fix in software alone):** **5**

### Top 10 prioritized actions

1. **P0** Add GitHub Actions (or documented CI runner) that executes `ci/gates.yaml` — gates exist but `.github/workflows` is absent.
2. **P1** Refresh README + Desktop docs links to **v1.8.1** (README still advertises v1.7.2).
3. **P1** Extend `ci/gates.yaml` with `v18:organism_surfaces` + Desktop polish suites.
4. **P1** Optional `HostedLLMBackend` implementing `GeneratorBackend` (env-gated; default remains template/LLM stub; CPU Everywhere).
5. **P1** Process/timeout isolation around `SafeSandbox.exec` (wall-clock kill + memory cap) — AST forbid is strong but not OS isolation.
6. **P1** Deepen Physiology / Ops for Immune + Autonomic operator actions (service constructs them; UI is thin).
7. **P1** Generative **CLI** parity (`evolve` / `promote` / `rollback` / `bundle`) matching Desktop Evolution.
8. **P2** Asset pipeline quality: richer procedural packs + pluggable image backend protocol (offline default).
9. **P2** Implement or clearly demote Rust `runtime/control_loop` (1-line placeholder) vs “Rust parity” claims.
10. **P2** Packaging: committed PyInstaller `.spec` + CI smoke artifact, or explicit NiceGUI/status ops surface.

## Gap table

| Gap | Area | Severity | Effort | Notes / evidence |
|---|---|---|---|---|
| No `.github/workflows` despite `ci/gates.yaml` | Ops / CI | P0 | M | `ls .github` empty; gates define blocking commands through v17 only |
| README release line stuck at **v1.7.2** | Docs | P1 | S | `README.md` L11 vs `STATUS.md` / tag v1.8.1 |
| No `v18:*` entries in `ci/gates.yaml` | Ops / CI | P1 | S | v17 generative/desktop gates present; v18 surfaces tests exist but ungated |
| Hosted LLM not wired (stub only) | Generative | P1 | M | `LLMStubBackend` / `resolve_backend`; STATUS lists hosted LLM as optional external |
| Sandbox = AST whitelist + restricted builtins, in-process `exec` | Security | P1 | M | `generative/sandbox.py`; fuzz covers many payloads; no seccomp/subprocess jail |
| Immune/Autonomic constructed in service, weak Desktop controls | Desktop vs SDK | P1 | M | `DesktopService` sets `immune`/`autonomic`; Physiology focuses hormones/drill/federation |
| No generative CLI (CLI = validate/status/serve only) | CLI vs Desktop | P1 | M | `organism_sdk/cli.py` |
| Apoptosis / Circadian / Morphogenesis / Snapshot lack first-class Desktop panels | Desktop vs SDK | P1 | L | SDK modules present; Metamodel covers partial morphogenesis path |
| Trace `emit_immune` / `emit_hormone` / `emit_autonomic` require `attach_v02_sink` | SDK | P1 | S | `trace.py` raises `NotImplementedError` without sink |
| Asset engine `procedural_v1.7.1` SVG/JSON only | Generative assets | P2 | M | `assets.py` — not production image-model quality; protocol could extend |
| Promote hot-register caps at EXPLORATION / `may_actuate=False` forever | Generative / safety | P2 | L | Intentional safety; document as product limit or design gated deliberation path |
| Federation Desktop stub `not_production_bft` | Distributed | P2 | L | Software multi-node only; real WAN BFT+TPM is hardware/external |
| Rust `organism-control-loop` is 1-line placeholder | Rust | P2 | M | `runtime/control_loop/src/lib.rs` |
| Packaging sketch only (no committed `.spec` / binary) | Ops | P2 | M | `desktop/docs/PACKAGING.md` |
| Dockerfile / serve path omits Desktop + generative extras | Deploy | P2 | M | `deploy/Dockerfile` installs `.[dev]`, serves health only |
| `ORGANISM_GENERATIVE_EVOLUTION.md` header still “Release: v1.7.2” | Docs | P2 | S | Follow-on points to v1.8 docs — OK but header stale |
| Modules list in README omits `generative` / Desktop | Docs | P2 | S | README structure table outdated |
| Generative module tests thin (1 file) vs SDK suite | Tests | P2 | S | `modules/generative/tests/test_generative_module.py` |
| Physiology does not expose apoptosis / circadian controls | Desktop | P2 | M | Hormone timeline + drillbook + federation stub present |
| Learned-ISE promotion UX not a dedicated panel | Desktop vs SDK | P2 | M | Overlaps Metamodel + Evolution |
| Multiprocess distributed APIs not in Desktop Ops | Desktop vs SDK | P2 | M | `organism_sdk/distributed/` |
| Soak/wall-clock full paths opt-in only | Perf | P2 | S | By design; document target-box cadence in STATUS |
| NiceGUI status page explicitly out of STATUS scope | Ops UI | P3 | M | CHANGELOG 1.8.1 |
| Empty/legacy `modules/hdc` + `modules/kernel` Rust dirs beside `*_module` | Repo hygiene | P3 | S | Cargo.toml present; easy to confuse with Python modules |
| Template library limited to 6 named skills | Generative | P3 | S | Extensible via `GeneratorBackend` |
| No Desktop “replay draft from DraftReplayLog” UI | Generative UX | P3 | S | SDK has `DraftReplayLog` / `replay_draft` |
| Docs panel may not link v1.7/v1.8 generative docs | Desktop docs | P3 | S | Verify `docs_links()` |
| Hypervector viz is preview-only | Desktop | P3 | S | Workspace panel |
| Category I 480s wall-clock still opt-in | Perf | P3 | — | Evidence path exists; not a defect |

## Quick wins (≤1 day each)

- Sync README release badge, Desktop doc links (v1.7 + v1.8), modules table (`generative`, Desktop).
- Add `v18:organism_surfaces` + `v18:desktop_polish` to `ci/gates.yaml`.
- Point Docs panel / `docs_links()` at `docs/v1.7/ORGANISM_GENERATIVE_EVOLUTION.md` and `docs/v1.8/*`.
- Annotate STATUS “software gaps closed” → “generative/Desktop wave closed; see AUDIT_v1.8 for residual software.”
- Remove or README-clarify orphan `modules/hdc` / `modules/kernel` Rust crates vs `hdc_module` / `kernel_module`.

## Medium (days–week)

- GitHub Actions matrix: proto + pytest `-m 'not slow'` + selected gates + optional `cargo test`.
- `HostedLLMBackend` (HTTP provider) behind env (`ORGANISM_LLM_*`); refuse if keys missing; never default-on; sandbox/promote unchanged.
- Sandbox runner: child process + timeout + RSS cap; keep AST gate as first line.
- Physiology panel: immune quarantine view, autonomic mode readout, circadian phase, jump to Traces for hormone/immune kinds.
- CLI: `organism_sdk evolve-*` / `promote-*` / `bundle export|import` mirroring DesktopService.
- Richer asset packs (multi-SVG themes, icon sets) + `ImageBackend` protocol with procedural default.
- Rust control_loop: minimal tick loop parity with Python deploy serve, or mark RESEARCH/placeholder in STATUS.

## Strategic (multi-sprint)

- Deliberation-tier generative promote (still `may_actuate=False` unless separate, audited actuation policy — **do not** weaken bio refuse).
- Cross-Organism skill marketplace with signed provenance + immune admission.
- Ops status surface (NiceGUI or Desktop-only remote) with SLO dashboards from soak artifacts.
- True multi-node software BFT *simulation* hardening (still not TPM/WAN hardware).
- End-to-end “Organism birth → evolve looks/skills → bundle ship → import twin” product narrative tests.

## Hardware / external (won't fix in software alone)

| Dep | Evidence | Notes |
|---|---|---|
| Real neuromorphic silicon | STATUS; `ORGANISM_NEURO_SIM` / RESEARCH_SIM | CPU sim only |
| Real bioreactor GPIO / wet-lab HW | STATUS; `docs/ops/WETLAB_SAFETY_POLICY.md`; HAL stub | `may_actuate=False`; deny_all policy |
| Production WAN BFT + TPM | STATUS; federation stub labels | Multi-process / multi-node software stubs only |
| Hybrid PySide6 Studio / OpenGL twin UI | STATUS; VENDOR.md | **Not imported** by design |
| Hosted LLM provider account/network | STATUS optional | Software can add a client; provider itself is external |

## Desktop panels vs SDK — mismatch list

| SDK capability | Desktop today | Gap |
|---|---|---|
| Registry / contracts / router / workspace | Panels | OK |
| Hormone timeline / degradation drill | Physiology | OK |
| ImmuneLayer | Service snapshot only | Thin UI |
| AutonomicController | Service flag only | Thin UI |
| ApoptosisService | — | Missing panel |
| CircadianClock | Hormone path uses phase | No dedicated controls |
| MorphogenesisTracker | Partial via Metamodel | Incomplete |
| LearnedISE | Overlap Metamodel/Evolution | No dedicated ISE console |
| Generative pipelines | Organism Evolution panel | OK (strong) |
| Generative CLI | — | Missing |
| Federation / multinode | Physiology stub button | Labeled non-production |
| Distributed multiprocess | — | Missing |
| Snapshot / deep replay | Traces explorer | Partial |
| Deploy profiles / soak / fuzz / rust probe | Ops | OK |
| Bio HAL / wetlab refuse | Bio panel | OK (hard refuse) |
| Neuro sim | Env-gated module | No Desktop toggle UX |

## Generative evolution — production-grade residual

| Claim | Reality @ v1.8.1 | Residual |
|---|---|---|
| Promote gates | Sandbox → contracts → shadow → promote; rollback deregisters | Strong |
| Bio safety | `may_actuate=False`; Desktop `ActuationRefused` | Strong — keep |
| Code backends | Template library + LLM **stub** | Need optional real LLM adapter |
| Assets | Procedural SVG/theme JSON | Need quality backends / packs |
| Skills | DAG, improve-from-trace, hot-register EXPLORATION | No deliberation/control actuation |
| Isolation | In-process restricted exec | Need OS-level isolation for “production” bar |
| Ops | Replay log, artifact hash, soak | CLI + CI gates for v18 |

## Security / safety notes

- **Keep:** bio `may_actuate=False`, wet-lab deny_all, RESEARCH_TIER catalog refuse if `may_actuate=True`, generative never flips actuation.
- **Improve:** sandbox process isolation; secret handling plan before any hosted LLM (env/vault — no keys in repo; none found today).
- **Federation / wet HAL “write placeholder”:** remain stub; do not treat as production actuation.

## Perf / ops

- Fast soak + perf budgets gated; full soak / 480s wall-clock opt-in (`docs/ops/SOAK_RUNBOOK.md`).
- Desktop short soak/fuzz harness writes under `desktop/artifacts/`.
- Docker CPU image serves health/status only — fine for headless; Desktop packaging still sketch.

## Docs vs reality drift

| Doc | Drift |
|---|---|
| README | Release **v1.7.2**; thin Desktop/generative links |
| STATUS | Accurate for v1.8.1; over-claims “software gaps closed” relative to this audit |
| `ORGANISM_GENERATIVE_EVOLUTION.md` | Header v1.7.2; body still useful; v1.8 follow-on OK |
| `ci/gates.yaml` | Stops at v17 |
| PACKAGING.md | Still “v1.6” sketch |

## Suggested release themes

### v1.8.2 — Audit closure (docs + CI)
README/STATUS sync, `AUDIT_v1.8.md` (this file), v18 gates, Docs panel links, orphan crate hygiene, optional GH Actions skeleton.

### v1.9 — Generative production bar
Hosted LLM adapter (optional), sandbox process jail, generative CLI, richer assets/`ImageBackend`, Physiology immune/autonomic/circadian UX, draft-replay Desktop.

### v2.0 — Substrate productization
Rust control_loop parity or honest demotion, Ops status surface, signed Organism bundles, deliberation-tier evolution policy (still no silent bio actuation), multi-node software BFT sim hardening — **hardware remains external**.

## Method

Read-only + light probes on tip `1b9d7e8`: STATUS, CHANGELOG, docs v1.5–v1.8, CPU_EVERYWHERE, ops, generative docs, `ci/gates.yaml`, Desktop `nav`/`service`, SDK generative/sandbox/trace/federation, Rust crate sizes, pytest collect, ripgrep for TODO/FIXME/RESEARCH_TIER/not_production/may_actuate stubs. No hardware invented beyond STATUS/docs evidence.
