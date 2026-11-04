# Handover: Organism (start here)

Updated 2026-11-04. For the next agent or human taking over Organism. Keep this file public-safe: no secrets, no machine
paths, no usernames. Machine-specific state belongs in local notes, not here.

## What Organism is

A substrate for heterogeneous modules, not a model. The Python reference SDK (`sdk/python/organism_sdk`) holds the
contracts, the lifecycle ladder, the structural router, the degradation levels, the workspace (hypervectors), the
generative pipelines and, on `main`, the mixture-of-experts layer. The Kotlin SDK (`sdk/kotlin`) is a dependency-free port
of selected areas. `conformance/` holds the language-neutral vectors that tie the ports to the reference.

The main consumer is **KotMoE**, a separate private-to-public agent repository that depends on this SDK. Its Lightspeed
model line is designed on this substrate. See the KotMoE pointers in section 7.

## Current state (2026-11-04)

- **Branch `feat/kotlin-parity`** (pushed to `origin`, the owner's private repository):
  - K0 done: Kotlin hypervector and degradation, conformant to the vectors.
  - K1 partly done (commit `34c25a2`): contract validation, lifecycle ladder, synchronized registry, and vectors
    `contract.json` and `lifecycle.json`. K1b is open (section 5).
- **Branch `main`** has the v1.11 MoA layer (Phases 0 to 3, see `docs/v1.11/MOA_LAYER.md`) and the Windows fixes listed below.
  **`feat/kotlin-parity` is 12 commits behind `main`. Nothing has been merged.** Merge or rebase before any PR. Expect
  conflicts in `STATUS.md` and `CHANGELOG.md`.
- **Test baseline on `feat/kotlin-parity` (Windows, Python 3.14 venv, after `pip install -e ".[dev,desktop]"` and
  `make proto-python`):**
  - Python, excluding `slow`, over `tests modules harness sdk/python/tests`: **273 passed, 3 skipped, 3 failed**.
  - Desktop, `desktop/tests`, with `QT_QPA_PLATFORM=offscreen`: **96 passed, 2 failed**.
  - Kotlin, `cd sdk/kotlin && ./gradlew test`: **6 passed**.
  - The failures are all Windows-specific and all are fixed on `main`: four are the evolve wall-clock budget (250 ms
    here, measured about 360 ms; `main` uses 2000 ms on Windows, 1000 ms elsewhere), and one is the POSIX executable-bit
    test (`main` skips it on Windows).
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

On Windows the generator writes CRLF. Git stores LF. Compare normalised content, not raw bytes.

Kotlin (needs JDK 17 as used here; the wrapper is Gradle 8.11.1; the Kotlin plugin is 1.9.22):

```bash
cd sdk/kotlin && ./gradlew test
cd sdk/kotlin && ./gradlew publish     # to build/private-repo, unless organismPrivateRepo is set
```

## Where things are

| Path | What it holds |
|---|---|
| `sdk/python/organism_sdk/contract.py`, `registry.py`, `router.py`, `degradation.py`, `workspace.py` | The reference: contracts, registry and ladder, router, degradation, workspace |
| `sdk/python/organism_sdk/moa/` | MoA layer (on `main` only): keyword experts, scorer, shadow gate, tiers, VSA aggregation |
| `sdk/python/organism_sdk/sandbox/`, `generative/` | Native jail (rlimits, Linux namespaces) and the code, asset and skill pipelines |
| `sdk/kotlin/src/main/kotlin/org/organism/sdk/` | `Hypervector.kt`, `Degradation.kt`, `Json.kt` (parse only), `Contract.kt` (K1), `Registry.kt` (K1) |
| `sdk/kotlin/src/test/kotlin/org/organism/sdk/` | `ConformanceTest.kt` (hypervector, degradation), `ContractConformanceTest.kt` (contract, lifecycle, queries) |
| `conformance/generate.py`, `conformance/vectors/*.json` | The generator and the vectors (hypervector, degradation, contract, lifecycle) |
| `ci/gates.yaml` | The gate list. The only conformance gate is `conformance:kotlin` |
| `docs/INTEROP.md` | Rules for vectors and ports, the areas table, and the running commands |
| `docs/KOTLIN_PARITY_PLAN.md` | The K-phases (K0 to K8), the gaps G1 to G14, and the KotMoE integration table |
| `docs/AI_MODEL_GAPS.md` | 40 gaps for KotMoE, Lightspeed and future models, with evidence, priority and planned fix |
| `docs/LIGHTSPEED_ON_ORGANISM.md` | System design for the KotMoE Lightspeed model on this substrate, and the owner decisions |
| `docs/KOTMOE_SUBSTRATE.md`, `docs/ORGANISM_FIT_PLAN.md` | The 1 November analyses. Both have a status note at the top that supersedes part of them |

## Deviations from the Python reference (K1)

1. `promote()` does not check shadow evidence or an approver. The reference does not check them either. K6 has to add
   the gate. Until then the registry does not enforce "never serve before shadow validation".
2. An unknown module id is a `not_found` rejection in Kotlin. The reference raises `KeyError`.
3. Promotion from or to a state outside the ladder (DEVELOPMENT, SELF_TERMINATING, SUCCEEDED, DEGRADED) is an
   `invalid_promotion` rejection in Kotlin. The reference raises `ValueError`. The vectors record the Python behaviour
   as `invalid_promotion`.
4. The Kotlin contract models a field subset (see the header of `Contract.kt`). Validation reads only the fields it covers.
5. Messages are not conformance. Codes, severities and field paths are.

Kept from the reference: a duplicate `register` replaces the entry; any state is allowed as the initial state; query
rank for DEVELOPMENT equals EXPLORATION.

## Next steps, in order

1. **Merge `main` into `feat/kotlin-parity`** (or rebase). That brings in the MoA layer and the Windows fixes. Resolve
   `STATUS.md` and `CHANGELOG.md`. Run the tests again. This is the owner's call on merge versus rebase.
2. **K1b, P0 items from `docs/AI_MODEL_GAPS.md`:** output forms including text, token stream and tool call (A1); a tool
   contract (A2); a human-confirmation justification (A3); a canonical JSON writer (C3); Ed25519 signature verification
   (A9).
3. **K2:** eligibility mask with typed exclusions, canonical `DispatchPlan` bytes, and a router policy artifact with a
   digest. Python and Kotlin, with a `router.json` vector. This is the first stage on the Lightspeed path.
4. **Persistence and traces:** a lifecycle stream on the op log with a digest chain (B2, C1), and a redaction hook in the
   trace sink (C2).
5. **K6:** shadow gate inside the registry's `promote` (B1). Learned experts must not be promoted before this exists.
6. **CI:** a regenerate-and-diff check for the vectors (I5), and the planned `conformance:all` gate that `INTEROP.md`
   promises. Both change the pipeline, so they need the owner's go.
7. **Health and drain** in Kotlin (B6), calibration evidence (A5), a measured-metabolics record (A6), and GPU and NPU
   hardware classes (A7).
8. **KotMoE integration** after K2. The KotMoE side is in the KotMoE repository's `docs/LIGHTSPEED.md`, stage B.

## Gotchas

- Python on Windows reads `;` as the path separator in `PYTHONPATH`.
- The vector generator writes CRLF on Windows, and git stores LF.
- `.venv/`, `build/`, `.gradle/`, `*.egg-info/` and the generated `_proto/` folder are gitignored. Regenerate `_proto/`
  after a fresh checkout.
- `make` comes from the MSYS toolchain on this machine. Pass `PYTHON=` explicitly.
- Keep `ci/gates.yaml` in step with what the tests really run. The conformance gate is incomplete (I5).

## KotMoE pointers

- The KotMoE repository (separate) holds `docs/HANDOVER.md` and `docs/LIGHTSPEED.md` for the model line. Its owner rule
  "never push KotMoE" still applies.
- The Lightspeed design, with its scorecard, roadmap and risks, is `docs/LIGHTSPEED_ON_ORGANISM.md` in this repository.
