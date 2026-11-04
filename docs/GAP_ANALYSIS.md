# Organism gap analysis

**Date:** 2026-11-04 · **Release at the time:** 1.10.0 with the v1.11 MoA layer in progress

This records what the repository was missing when it was checked, what was fixed, and what is still
open. Each open item says whether it is blocked on a decision. The decisions are listed in
[Decisions needed](#decisions-needed).

## Method

The review covered six areas:

- **Code.** Lint and type ratchets, silent exception handlers, public API surface.
- **Tests.** Coverage of the frozen API, host detection, version alignment, and the MoA layer.
- **CI.** Gate definitions, the nightly tier, and whether anything runs on a schedule in GitHub.
- **Dependencies.** Declared versus used packages, version drift, and vulnerability auditing.
- **Security.** Whether signatures are checked, and how the guardrails hold up under attack.
- **Roadmap.** Phases 4 to 6 of the [upgrade plan](UPGRADE_AND_EXPANSION_PLAN.md) and their decisions.

Counts were taken with the project venv (`.venv`), the same interpreter the gates use.

## Baseline at the start of the review

| Measure | Start | Now |
|---|---|---|
| Ruff findings (ratchet) | 170 | 1 (intentional `exec` in the generative sandbox) |
| Mypy hand-written findings (ratchet) | 527 | 130 |
| Package versions | 1.4.0 (SDK), 1.3.0 (Rust), 1.10.0 (root) | 1.10.0 everywhere, guarded by a test |
| Declared dependencies unused in code | pydantic, blake3, structlog, SDK numpy | removed |
| Registry signatures checked | never | when a trust store is configured |
| Scheduled CI on GitHub | none | nightly tier and advisory audit |
| MoA guardrails | none | input and output guardrails, red-team suite |

## Fixed in this review

| ID | Area | Gap | Fix | Commit |
|---|---|---|---|---|
| F1 | Versions | Three different versions across packages and the Rust workspace. | Aligned to 1.10.0. `test_version_alignment.py` fails on drift. | `07c6cb1` |
| F2 | Dependencies | Four declared dependencies with no import in the code. | Removed. The preflight module list now matches what is used. | `07c6cb1` |
| F3 | Public API | The v0.4 frozen Python surface was documented but not enforced. | `test_api_freeze.py` reads the list from `docs/API_FREEZE_v0.4.md` and checks each name is exported. | `07c6cb1` |
| F4 | Tests | The soak executable-bit check was skipped on Windows. | It checks the git index mode (`100755`) on every platform. | `07c6cb1` |
| F5 | Tests | Host and container detection had no tests for the evidence branches. | `test_host_detect_evidence.py` (17 tests) fakes the host files. | `07c6cb1` |
| F6 | Typing | Generated protobuf code counted as mypy findings. | Excluded from mypy. The ratchet drops from 527 to 168. | `27cec08` |
| F7 | Typing | Public SDK helpers had no return types. Mypy reported `import-untyped` for the in-repo `modules/` packages, which have no `py.typed` marker. | Annotated the helpers. The four in-repo packages are typed `Any` at the import boundary. Ratchet 168 to 130. | `77e110c` |
| F8 | Lint | Silent `except` handlers in 24 modules, with no logging. | Stdlib `logging` at each handler, with `exc_info`. Ruff ratchet 170 to 1. | `9b9839a` and earlier |
| F9 | Security | The registry accepted any `author_signature` and `approver_signature`. | `organism_sdk.signing` (Ed25519) and a `TrustStore` with separate author and approver keys. Enforced when a trust store is passed. | `9940be9` |
| F10 | CI | Nothing ran nightly in GitHub, and no dependency vulnerability scan existed. | `.github/workflows/nightly.yml`: the nightly tier at 02:00 UTC, plus advisory `pip-audit` and `cargo audit`. | `0d0d9fa` |
| F11 | Roadmap | MoA Phase 5 (guardrails and red team) was not started. | Rule-based input and output guardrails, a labeled set with measured error rates, and a non-blocking red-team suite. | `aedc234` |
| F12 | Determinism | An equal-score workspace replay could pick either binding. | Ties are broken by binding id. | `5516388` |
| F13 | Docs | Budget text in `MOA_LAYER.md` §8 and the CHANGELOG said Linux keeps 250 ms. | Updated to the measured values in `budgets.py`. | this review |

## Open gaps

Items marked **blocked** need a decision from you before work can go on. Items marked **open** can be
done without one, but were not done in this review, with the reason given.

| ID | Area | Gap | Status |
|---|---|---|---|
| O1 | Roadmap | MoA Phase 4 (synthesizer and router-policy evolution) needs a routing-policy artifact type and a learned backend. | **blocked** on D1 |
| O2 | Roadmap | The MoA judge (Phase 5 remainder). Calibration needs a learned backend. | **blocked** on D1 |
| O3 | Roadmap | MoA Phase 6 (lifecycle and provenance). | **blocked** on D4 |
| O4 | Routing | Extraction queries built around "email address" route to unsure. The xfail is `test_v111_moa_routing.py::test_known_recall_gap_singular_email_is_routed_to_extractor`. Adding the phrases lost precision (7 of 11), so a context rule is needed. | **blocked** on S2 (a fresh labeled set, written before the rule) |
| O5 | Guardrails | Three known misses, recorded as strict xfails in `test_v111_moa_redteam.py`: a Cyrillic homoglyph, a prompt-disclosure paraphrase, and a persona request without "you are now". | open. Each rule adds false-positive risk, so each needs a measured change against the labeled set. |
| O6 | Signing | The trust store is not configured in any production entry point. The deploy stack, the generative runtime, and the MoA experts still pass placeholder bytes such as `b"deploy"` and `b"reference-unsigned"`. | **blocked** on S1 (where keys live and who holds them). The default stays unchecked, so existing behaviour is unchanged. |
| O7 | Guardrails | Aggregation picks the highest-confidence answer. A grounded but wrong answer passes the guards, and a compromised expert reporting confidence 1.0 wins. The guards bound fabricated values, not correctness. | open, documented in `MOA_LAYER.md` §10. Calibration belongs to the judge, so it is covered by O2. |
| O8 | Dependencies | No Python lock or constraints file. Installs resolve fresh every time. | open. A lock file adds a tool and an upkeep cost, so it is a choice, not a gap to close silently. |
| O9 | Typing | 130 hand-written mypy findings remain. See the breakdown below. | open. About 64 are annotation work (`no-untyped-def` and `no-untyped-call`). The rest need the code read first, starting with `comparison-overlap` and `arg-type`. |
| O10 | Docs | `STATUS.md` was dated 2026-10-25 and listed MoA Phases 4 and 5 as not started. | fixed in this review. The CHANGELOG's chrono note was also wrong: `runtime/registry` no longer depends on chrono, but `runtime/workspace` and `organism-client` still do. |

## Decisions needed

These are the user's to make. Nothing above was decided on your behalf.

- **D1 (plan §7).** Which domains and base models for the first two learned experts? This blocks O1 and O2. Both candidate models need a download, which also needs permission.
- **D2 (plan §7).** Is CPU-only the first target? The current default under CPU Everywhere says yes. Confirming it closes D2.
- **D3 (plan §7).** May a hosted LLM serve as `llm_fallback`? It is off by default and stays off until you decide.
- **D4 (plan §7).** Include Phase 6 (lifecycle and provenance) in scope? This decides O3.
- **S1 (new).** Where do signing keys live, and who holds the trust store? Decide this before wiring the trust store into the deploy stack, the desktop app, or the generative runtime (O6). The default stays unchecked until then.
- **S2 (new).** Approve a fresh labeled set for the email recall gap (O4). It has to be written before the context rule, so the rule is not tuned on the test that checks it.
- **N1 (new).** The GitHub nightly workflow uses Actions minutes. The nightly tier took 589 s locally when it was last measured, and the job is capped at 120 minutes. Keep it, or leave only the Windows task (`OrganismNightlyCI`, which is registered and runs at 02:00)?

## Mypy backlog (130 findings)

Measured by the ratchet at 130. This is the breakdown by error code, from the same run:

| Code | Count | Where it sits |
|---|---|---|
| `no-untyped-call` | 37 | calls to helper functions in tests and the harness that have no annotations |
| `no-untyped-def` | 27 | the helper functions themselves, mostly in tests and the harness |
| `arg-type` | 22 | values passed where a narrower type is expected |
| `attr-defined` | 11 | attribute access on objects typed too broadly |
| `union-attr` | 6 | `Optional` values used without a narrowing check |
| `index` | 6 | indexing a value whose type is a union |
| `comparison-overlap` | 6 | equality checks mypy says can never be true |
| `no-any-return` | 5 | returns that are `Any` from functions declared to return a concrete type |
| `assignment`, `misc`, `var-annotated`, `operator`, `call-arg` | 10 | one-off findings |

Start with the six `comparison-overlap` findings. One is in `sdk/python/organism_sdk/generative/code_pipeline.py`
(lines 474 and 478), where a check against `CodeStage.REJECTED` is one mypy says can never match. It
may be dead code or a branch that was meant to run, so read it before changing it. The other five are
in harness and test files.

## Verification

- Fast tier, the pre-push gate: passed on every push in this review. It ran 58 gates before the Phase 5 gates were added, and 60 after.
- `pytest -m 'not slow'` collects 591 tests.
- Full tier on Windows at `77e110c`: 61 of 61 gates pass in 258.7 s.
- Full tier on WSL Ubuntu at `77e110c`: 61 of 61 gates pass in 80.9 s. The first run failed `lint:mypy` on a stale `.mypy_cache`, and clearing the cache fixed it (see the troubleshooting section of [ci/README.md](../ci/README.md)). In a non-login shell the run needs `/root/.cargo/bin` on `PATH`.
