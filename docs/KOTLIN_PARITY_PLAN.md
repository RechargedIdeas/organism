# Organism v1.11+ build-out: Kotlin parity, gaps, KotMoE integration

Branch `feat/kotlin-parity`. Source for the KotMoE-driven requirements: the substrate analysis for KotMoE
(`KOTMOE_SUBSTRATE.md`, kept outside the public KotMoE repo). Design corpus: `docs/design/IDEA.txt` (spec v0.1).

Goals, in the owner's words: add what Organism is missing, give everything that exists full Kotlin parity, make tools,
systems and pipelines interoperable across languages (and future ones), build whatever KotMoE needs into Organism, then
integrate with KotMoE as it goes, keeping docs and repos current.

## Status (2026-11-04)

- K0 is done. K1 is partly done (commit `34c25a2`): contracts, validation, lifecycle ladder, registry (synchronized),
  and the conformance vectors `contract.json` and `lifecycle.json`. K1b (below) is open. K2 is next.
- Decisions: KotMoE consumes this SDK as a dependency, not a reimplementation. The artifact is published to a
  private repository (`./gradlew publish`). Both were decided on 2026-11-04.
- The next agent starts with `docs/HANDOVER.md`. The full gap list, with priorities, is `docs/AI_MODEL_GAPS.md`.
  The design for the KotMoE side is `docs/LIGHTSPEED_ON_ORGANISM.md`.
- This branch is 12 commits behind `main`, which has the v1.11 MoA layer. Merge or rebase before any PR.

## Gaps found in Organism (to fill)

| # | Gap | Plan |
|---|---|---|
| G1 | Reference only in Python; Rust thin | Kotlin SDK (this plan), conformance vectors, Rust vectors |
| G2 | No language-neutral behaviour contract | `conformance/` + `docs/INTEROP.md` (done for 2 areas) |
| G3 | Architecture corpus not in repo | `docs/design/IDEA.txt` added; split into `docs/architecture/` (A..F) |
| G4 | Task taxonomy is sensor-only | add agent/assistant forms (chat, retrieve, tool, route, verify) to router |
| G5 | No eligibility mask with typed exclusions as a reusable API | Kotlin + Python `Eligibility` (K2) |
| G6 | No shadow validation on live traffic, only synthetic | `ShadowRunner` (K6) |
| G7 | No expert spawn/specialise/retire/merge as proposals | evolution layer (K7), propose-only |
| G8 | Degradation thresholds hard-coded | level table as data (JSON), vectors for custom tables (K3) |
| G9 | No durable, language-neutral op log | JSON-lines op log with digest chain (K4) |
| G10 | Sandbox weak off Linux | policy shape shared; platform confinement providers per SDK (K5) |
| G11 | Stubs presented as modules (hypernetwork, multinode) | label honestly, add real implementations later (R-track) |
| G12 | Plain-name API | alias layer: `stress/reward/trust/rest` over hormone names |
| G13 | No MCP/ACP/OpenAI-compatible surface | `organism-gateway` (K8) |
| G14 | Python deps heavy (grpc, numpy) for tiny hosts | keep core importable without them |

## Phases

| Phase | Content | Effort | State |
|---|---|---|---|
| K0 | Fork on X:, venv, baseline, conformance harness, Kotlin build, hypervector + degradation parity | S | **done** |
| K1 | Contract, validation, registry + lifecycle ladder (Kotlin), vectors `contract.json`, `lifecycle.json` | M | **partly done** (`34c25a2`): contract field subset, validation, ladder, registry, vectors |
| K1b | Output forms (text, token stream, tool call), tool contract, human-confirmation justification, Ed25519 signature verification, health and drain interfaces, calibration evidence, measured-metabolics record, GPU and NPU hardware classes, canonical JSON writer | M | open. The P0 rows of `docs/AI_MODEL_GAPS.md` come first |
| K2 | Router, `DispatchPlan` canonical bytes, trace entries, eligibility mask + exclusions (Python+Kotlin), vectors | M | |
| K3 | Hormone bus, autonomic, circadian, immune, interoception parity; plain-name modulators; level table as data | M | |
| K4 | Workspace, ops log, snapshots, replay (JSONL + digest chain), vectors | M | |
| K5 | Sandbox policy parity, confinement provider interface, Windows/Linux/Android providers | L | |
| K6 | Shadow runner and promotion on live traffic | M | |
| K7 | Evolution proposals: spawn, specialise, retire, merge, apoptosis certificates | L | |
| K8 | Gateway: HTTP/OpenAI-compatible, MCP, ACP; Rust vectors; TS SDK stub | L | |
| KM-n | KotMoE integration after each K phase (below) | per phase | |

## KotMoE integration (per phase)

KotMoE consumes the Kotlin SDK as a pinned dependency, `org.organism:organism-kotlin`, from the private repository
(JVM target 11, stdlib only). Integration is always additive,
off by default, and lands as a KotMoE branch reviewed by the owner; Organism never gains a runtime need for KotMoE.

| After | KotMoE change |
|---|---|
| K1 | `ExpertDescriptor` projects to `ModuleContract`; lifecycle states in `ExpertRegistry` |
| K2 | `PlanningRouter` wraps `Rama.decide`; masked catalogue feeds the RAMA prompt; trace extended |
| K3 | Android/desktop signal sources feed `DegradationMachine`; modulators throttle `LearningLoop` |
| K4 | `RouteTrace`, WorkItem and EffectQueue streams on the op log |
| K5 | Confinement providers behind the ToolHost |
| K6 | Shadow tap in `PromotionGate` |
| K7 | Spawner/Retirer proposals in the Agents page, owner approval queue |
| K8 | MCP/ACP tools, `/v1/substrate/*` routes |

## Hard rules carried over

100% self-independent at runtime; Kotlin-first for KotMoE; Android fully on device; workers OS-confined before real
tasks; safety tooling propose-only; no feature removal without owner decision; bio actuation refused; public/private
split (this repo is private, KotMoE is public: concepts cross, source does not unless the owner decides).
