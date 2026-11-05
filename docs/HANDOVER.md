# Handover: Organism (start here)

Updated 2026-11-05. For the next agent or human taking over Organism. Keep this file public-safe: no secrets, no machine
paths, no usernames. Machine-specific state belongs in local notes, not here.

## What Organism is

A substrate for heterogeneous modules, not a model. The Python reference SDK (`sdk/python/organism_sdk`) holds the
contracts, the lifecycle ladder, the structural router, the degradation levels, the workspace (hypervectors), the
generative pipelines and, on `main`, the mixture-of-experts layer. The Kotlin SDK (`sdk/kotlin`) is a dependency-free port
of selected areas. `conformance/` holds the language-neutral vectors that tie the ports to the reference.

The main consumer is **KotMoE**, a separate private-to-public agent repository that depends on this SDK. Its Lightspeed
model line is designed on this substrate. See the KotMoE pointers in section 7.

## Current state (2026-11-05)

- **Branch `feat/kotlin-parity`**. The last commit pushed to `origin` (the owner's private repository) is `0a84692`.
  Everything after it is local only and not pushed: the K1b work, K2, K6, the merges and the fixes. Do not push without
  the owner's go.
  - K0 done: Kotlin hypervector and degradation, conformant to the vectors.
  - K1 partly done (`34c25a2`): contract validation, lifecycle ladder, synchronized registry, and vectors
    `contract.json` and `lifecycle.json`.
  - K1b done in the working tree. Items 1 to 6 are in `38d5fdd`. Task 7 (health and drain, calibration and measured-metabolics
    evidence, GPU and NPU classes) is uncommitted. See "Owner review after K1b task 7".
  - K2 done (`c706613`, merged as `5a00291`): eligibility mask with typed exclusions, canonical `DispatchPlan` bytes,
    policy digest and routing trace entries. Python and Kotlin, with `router.json`.
  - K6 done (`0d38866`, merged as `931e72c`): shadow gate in `promote()` and `ShadowRunner`. Python and Kotlin, with
    `shadow.json`. The section "Owner review after K2 and K6" lists what it raised.
  - `cc543e4` fixes the lint and test expectations found after the merge.
- **Branch `main`**: `feat/kotlin-parity` contains all of `main` (checked 2026-11-05). The earlier note "12 commits behind"
  is out of date. Check again with `git rev-list --count main..feat/kotlin-parity` before any PR.
- **Test baseline (2026-11-05, Windows):**
  - Fast tier, `ci/run.py run --tier fast`, with task 7 uncommitted: **76 passed, 0 blocking failures**, none cached.
  - Kotlin, `cd sdk/kotlin && ./gradlew cleanTest test`: **24 passed** in six classes (canonical and signature 4,
    conformance 2, contract 8, router 5, shadow 2, tool and artifact 3).
  - Python, `pytest -m "not slow" sdk/python/tests`: **1109 passed, 3 skipped, 2 deselected, 4 xfailed**. `test_k1b_task7.py`: 12 passed.
  - The full tier was not run. Run it before a PR.
- **Private publish:** `./gradlew publish` in `sdk/kotlin` writes `sdk/kotlin/build/private-repo` by default. A shared
  private repository is set in the user's Gradle properties (`organismPrivateRepo`, `organismRepoUser`,
  `organismRepoToken`). Never put tokens in the repository.

## Owner decisions (settled, 2026-11-04)

1. **KotMoE depends on the Kotlin SDK; it does not reimplement the concepts.** The coordinate is
   `org.organism:organism-kotlin`, pinned to one exact version.
2. **The artifact goes to a private repository.** Organism stays private. Outside builds of the public KotMoE repository
   cannot resolve the artifact, and its public docs must say so.
3. **KotMoE is not pushed** until its history is rewritten and the owner says go. That rule is in the KotMoE repository's
   own handover.

Still open (see `docs/LIGHTSPEED_ON_ORGANISM.md` section 10): naming of `org.organism.sdk` imports in public code, the
first confinement platform, shadow traffic defaults, evolution autonomy, the learned MoA backend (decision D1), and the
provenance decision D4.

## Owner review after K2 and K6 (open, 2026-11-05)

These came out of the K2 and K6 work. Each is a choice for the owner to confirm or change. None blocks the branch.

1. **The approver is checked only when keys are configured.** With no trust store (Python) or no approver keys (Kotlin),
   a promotion's approver signature is not checked. The evidence gate still applies. Decide whether a gated promotion
   must always carry a verified approver.
2. **Generative runtime modules now stop at SANDBOXED.** Their synthetic shadow evidence is below the threshold, so
   `test_v17_generative.py` and `desktop/tests/test_organism_evolution.py` now expect SANDBOXED, not EXPLORATION. Decide
   whether generated modules should get real shadow evidence before any promotion.
3. **The shadow thresholds are defaults, not measurements.** `ShadowThreshold(min_invocations=100, max_error_ratio=1.0)`
   means the candidate's error may not exceed the incumbent's. Gap H3 (a measured quality record) is open, so these values
   are not backed by data yet.
4. **The promotion payload changed.** Shadow errors are integers in parts per million and latency is an integer in
   microseconds, so the payload has no float text. Approver signatures made over the earlier payload no longer verify.
   Any that exist must be re-made.
5. **The `DispatchPlan` bytes leave out `plan_id`.** Two plans for the same decision therefore have the same bytes.
   Confirm that is the identity you want.
6. **K1b rules flagged for review.** The tool contract (A2) and the model-artifact manifest (A8) were written by the K1b
   worker. The owner has not agreed their rules.

## Owner review after K1b task 7 (open, uncommitted)

1. **Thresholds are placeholders.** Calibration: `max_ece` 0.05, `max_coverage_gap` 0.05, `min_samples` 200. Measured
   metabolics: `factor` 1.25, `min_samples` 100. None of these is measured. Set them from data before a tier relies on them.
2. **Evidence is required only on request.** `require_calibration` and `require_measurement` default to off. Evidence that
   is supplied is always checked. Decide the default for gated promotions.
3. **T1 and T2 claim calibration; T3 does not.** A calibrated tier must show a record when the registry requires it. Confirm
   that T1 belongs with T2.
4. **The drain deadline changed.** `deregister` now gives `on_drain` the time now + `timeout_s`. The reference used now and
   ignored the timeout. No module in the repository reads the deadline. The Kotlin API changed: `deregister` takes
   `(moduleId, nowMs, timeoutS)`, and `register` takes optional hooks.
5. **GPU and NPU are declared, not verified.** `HardwareRequirement` gained GPU and NPU. A `gpu_flag_mismatch` warning fires
   when `requires_gpu` and the GPU class disagree. The proto enum has no GPU or NPU value, and `to_proto` does not send
   hardware, so the gRPC surface does not carry them yet. No GPU or NPU device was available. Nothing was measured on one,
   and the measured values in `evidence.json` are synthetic, with device class `CPU`.
6. **Health reports are narrowed.** The Kotlin port compares status and score. Active failures and probe results are not ported.

## Rules that still hold

- **Vectors are the contract.** `conformance/generate.py` runs the reference. Regenerate only after a reviewed reference
  change. A vector change is an API change, and every SDK's tests change in the same commit.
- **Port exactly.** Same validation order, same codes, same ladder. Deviations are listed in section 6 and in the header
  comments of the Kotlin files.
- **Organism never depends on KotMoE.** KotMoE's runtime never needs Organism's Python code or an Organism service.
- **No secrets or machine paths in tracked files.** Gradle credentials stay in the user's Gradle properties.
- **Safety invariants.** Bio and wet-lab actuation stays refused. Modules synthesised at runtime have `may_actuate=False`.
  Shield parameters stay unreachable from modulators.
- **Do not remove a feature, screen or command** without the owner's decision.
- **Commit and push only when the owner asks.**

## How to build and test

Python (Windows; on POSIX use `.venv/bin/python` and `:` as the path separator):

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev,desktop]"
.venv/Scripts/python.exe -m pip install grpcio-tools    # if not already present
make proto-python PYTHON=.venv/Scripts/python.exe        # generated into sdk/python/organism_sdk/_proto (gitignored)
export PYTHONPATH="sdk/python;modules;desktop;."         # POSIX: sdk/python:modules:desktop:.
.venv/Scripts/python.exe -m pytest -q -m "not slow" -p no:cacheprovider tests modules harness sdk/python/tests
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -m "not slow" -p no:cacheprovider desktop/tests
```

Note: `pytest` with no paths collects `desktop/tests` by default, and the default collection errors without PySide6. Pass
paths explicitly, or install the desktop extra.

Conformance vectors:

```bash
.venv/Scripts/python.exe conformance/generate.py   # reference change only
```

The generator writes LF on every host (K2). A working copy written before that can differ from git only in CRLF. Compare
with `git diff --ignore-cr-at-eol`.

Kotlin (needs JDK 17 as used here; the wrapper is Gradle 8.11.1; the Kotlin plugin is 1.9.22):

```bash
cd sdk/kotlin && ./gradlew test
cd sdk/kotlin && ./gradlew publish     # to build/private-repo, unless organismPrivateRepo is set
```

## Where things are

| Path | What it holds |
|---|---|
| `sdk/python/organism_sdk/contract.py`, `registry.py`, `router.py`, `shadow_runner.py`, `signing.py`, `evidence.py`, `health.py`, `degradation.py`, `workspace.py` | The reference: contracts, registry and ladder, router, shadow runner and promotion payload, calibration and measurement evidence, health, degradation, workspace |
| `sdk/python/organism_sdk/moa/` | MoA layer (on `main` only): keyword experts, scorer, shadow gate, tiers, VSA aggregation |
| `sdk/python/organism_sdk/sandbox/`, `generative/` | Native jail (rlimits, Linux namespaces) and the code, asset and skill pipelines |
| `sdk/kotlin/src/main/kotlin/org/organism/sdk/` | `Hypervector.kt`, `Degradation.kt`, `Json.kt` (`parse` and `parseExact`), `Canonical.kt` (C3), `Ed25519.kt` (A9), `Contract.kt` (K1), `Registry.kt` (K1, K6), `Routing.kt` (K2), `Shadow.kt` and `Signing.kt` (K6), `Health.kt` and `Evidence.kt` (K1b task 7) |
| `sdk/kotlin/src/test/kotlin/org/organism/sdk/` | `ConformanceTest.kt` (hypervector, degradation), `ContractConformanceTest.kt` (contract, lifecycle, queries, evidence gate), `RouterConformanceTest.kt`, `ShadowConformanceTest.kt`, `CanonicalSignatureConformanceTest.kt`, `ToolArtifactConformanceTest.kt` |
| `conformance/generate.py`, `conformance/vectors/*.json` | The generator and the vectors (hypervector, degradation, contract, lifecycle, canonical, signature, tool, model artifact, router, shadow, health, evidence) |
| `ci/gates.yaml` | The gate list. The only conformance gate is `conformance:kotlin` |
| `docs/INTEROP.md` | Rules for vectors and ports, the areas table, and the running commands |
| `docs/KOTLIN_PARITY_PLAN.md` | The K-phases (K0 to K8), the gaps G1 to G14, and the KotMoE integration table |
| `docs/AI_MODEL_GAPS.md` | 40 gaps for KotMoE, Lightspeed and future models, with evidence, priority and planned fix |
| `docs/LIGHTSPEED_ON_ORGANISM.md` | System design for the KotMoE Lightspeed model on this substrate, and the owner decisions |
| `docs/KOTMOE_SUBSTRATE.md`, `docs/ORGANISM_FIT_PLAN.md` | The 1 November analyses. Both have a status note at the top that supersedes part of them |

## Deviations from the Python reference (K1)

1. Closed in K6: `promote()` checks shadow evidence for the gated states in both SDKs. The approver is checked when keys
   are configured (owner review, item 1).
2. An unknown module id is a `not_found` rejection in Kotlin. The reference raises `KeyError`.
3. Promotion from or to a state outside the ladder (DEVELOPMENT, SELF_TERMINATING, SUCCEEDED, DEGRADED) is an
   `invalid_promotion` rejection in Kotlin. The reference raises `ValueError`. The vectors record the Python behaviour
   as `invalid_promotion`.
4. The Kotlin contract models a field subset (see the header of `Contract.kt`). Validation reads only the fields it covers.
5. Messages are not conformance. Codes, severities and field paths are.

Kept from the reference: a duplicate `register` replaces the entry; any state is allowed as the initial state; query
rank for DEVELOPMENT equals EXPLORATION.

## Next steps, in order

1. **Review "Owner review after K1b task 7"**, then decide when to commit task 7. Nothing is committed or pushed.
2. **K3:** hormone bus, autonomic, circadian, immune and interoception parity; plain-name modulators (E3); the level table
   as data (E1). This is the next K-phase in `docs/KOTLIN_PARITY_PLAN.md`.
3. **K4, persistence and traces:** a lifecycle stream on the op log with a digest chain (B2, C1), and a redaction hook in
   the trace sink (C2).
4. **CI:** a regenerate-and-diff check for the vectors (I5), and the planned `conformance:all` gate that `INTEROP.md`
   promises. Both change the pipeline, so they need the owner's go.
5. **KotMoE integration after K2** (the `PlanningRouter` that wraps `Rama.decide`) is KotMoE's work, in the KotMoE
   repository. Nothing in this repository changes for it.

## Gotchas

- Python on Windows reads `;` as the path separator in `PYTHONPATH`.
- The vector generator writes LF (K2). Working copies written before that can show as modified in CRLF only. Check with
  `git diff --ignore-cr-at-eol`.
- Two extra git worktrees hold the K2 and K6 branches (`k2-router`, `k6-shadow`). Remove them only with the owner's go-ahead.
- `.venv/`, `build/`, `.gradle/`, `*.egg-info/` and the generated `_proto/` folder are gitignored. Regenerate `_proto/`
  after a fresh checkout.
- `make` comes from the MSYS toolchain on this machine. Pass `PYTHON=` explicitly.
- Keep `ci/gates.yaml` in step with what the tests really run. The conformance gate is incomplete (I5).

## KotMoE pointers

- The KotMoE repository (separate) holds `docs/HANDOVER.md` and `docs/LIGHTSPEED.md` for the model line. Its owner rule
  "never push KotMoE" still applies.
- The Lightspeed design, with its scorecard, roadmap and risks, is `docs/LIGHTSPEED_ON_ORGANISM.md` in this repository.
