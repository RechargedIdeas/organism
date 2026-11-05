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
| Mypy hand-written findings (ratchet) | 527 | 0 on Windows and Linux |
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
| F14 | Typing | 33 test and harness functions had no annotations, so their calls were untyped as well. | Annotated them and narrowed the `Optional` reads that the annotations exposed, with asserts. Ratchet 130 to 59. | `4083925` |

## Open gaps

Items marked **blocked** need a decision from you before work can go on. Items marked **open** can be
done without one, but were not done in this review, with the reason given.

| ID | Area | Gap | Status |
|---|---|---|---|
| O1 | Roadmap | MoA Phase 4 (synthesizer and router-policy evolution) needs a routing-policy artifact type and a learned backend. | **blocked** on D1 |
| O2 | Roadmap | The MoA judge (Phase 5 remainder). Calibration needs a learned backend. | **blocked** on D1 |
| O3 | Roadmap | MoA Phase 6 (lifecycle and provenance). | **blocked** on D4 |
| O4 | Routing | Extraction queries built around "email address" route to unsure. A plain keyword lost precision (7 of 11), so the phrase now counts only beside a verb of retrieval (`CuedKeyword`). **fixed** on the fresh set written before the rule (`moa_routing_email_context.json`): 11 of 12 extraction requests reached the extractor, with no wrong route. A second pass (O13) and a held-out set (`moa_routing_recall_fresh.json`) now give 7 of 8, with no wrong route. The one miss has no verb and no question. See `docs/v1.11/MOA_LAYER.md`, section 4. |
| O13 | Routing | A cue verb counted wherever it appeared. "Which email address should the new hire get?" and "Which email addresses are allowed to post to the all-staff list?" routed to the extractor. The noun "list" and the verb "get" were both cues. Found by the held-out set `moa_routing_recall_fresh.json`. | **fixed**. A cue counts in command position (first word, or after "please" or "can you"). A question opener ("which", "what", "are there", "is there") counts with a reference to supplied text ("this", "these", "the attached", "below", "above", "following"). See `docs/v1.11/MOA_LAYER.md`, section 4. |
| O14 | Routing | No intent covers sending email. "Please email the signed contract to the client" is unsure. The context set labels it `intent_classifier`, and the held-out set labels it `unsure`. | open. Adding a send intent is a product choice (see D6). |
| O5 | Guardrails | Three known misses, recorded as strict xfails in `test_v111_moa_redteam.py`: a Cyrillic homoglyph, a prompt-disclosure paraphrase, and a persona request without "you are now". | **fixed**. Each has a rule or a letter fold, and each is now a plain test. The labeled FP and FN counts are unchanged (2 of 25, 2 of 26), and 13 benign near-misses pass. See `docs/v1.11/MOA_LAYER.md` §10. |
| O6 | Signing | The trust store is not configured in any production entry point. The deploy stack, the generative runtime, and the MoA experts still pass placeholder bytes such as `b"deploy"` and `b"reference-unsigned"`. | **partly fixed** (D5, option b). The deploy stack reads `stack.trust_store` and registers its two built-in modules through `RegistryClient(builtin_ids=...)`. Before this, a configured trust store made `build_minimal_stack` raise `RegistrationRejected`. A built-in id skips the author check and is audited as `built_in`. The desktop's catalog and its two bio modules are built-in too (`DESKTOP_BUILTIN_IDS`). The MoA reference experts are listed by `reference_expert_ids()`, but no production path registers them yet. The generative runtime refuses its own output under a trust store: `hot_register_promoted` returns `None` and records a `refused` evolution event. What remains is an approver-signed path that lets generative output register. The default stays unchecked, so existing behaviour is unchanged. |
| O7 | Guardrails | Aggregation picks the highest-confidence answer. A grounded but wrong answer passes the guards, and a compromised expert reporting confidence 1.0 wins. The guards bound fabricated values, not correctness. | open, documented in `MOA_LAYER.md` §10. Calibration belongs to the judge, so it is covered by O2. |
| O8 | Dependencies | No Python lock or constraints file. Installs resolve fresh every time. | **partly fixed** (`653fea9`). Dev tools are pinned in `constraints-dev.txt`, and runtime dependencies stay unpinned by choice. A full lock file is still open, because it adds a tool and an upkeep cost. |
| O9 | Typing | The last 20 hand-written mypy findings, down from 59 at F14. | **fixed**. The ratchet is at 0 on Windows, where the baseline is measured. See the backlog section below. |
| O10 | Docs | `STATUS.md` was dated 2026-10-25 and listed MoA Phases 4 and 5 as not started. | fixed in this review. The CHANGELOG's chrono note was also wrong: `runtime/registry` no longer depends on chrono, but `runtime/workspace` and `organism-client` still do. |
| O11 | Tests | The desktop evolve budget gate (`v17:desktop_organism`) asserts that one evolve call finishes within 2000 ms on Windows. `DesktopService` keeps its state in `organism_data/`, and `DraftReplayLog` appends to `organism_data/artifacts/draft_replay.json` on every evolve. That file reached about 0.9 MB. The gate failed on the main checkout's state. A copy of that state passed in 47.7 s, and fresh state passed in 6.3 s. | **fixed**. The gate was fixed in `edd2924`: the evolve tests use `DesktopService.create(data_root=...)` on a temp directory. The replay journal is now bounded. It keeps the newest 500 drafts (`DEFAULT_REPLAY_MAX_ENTRIES`), about 0.4 MB at the measured 825 bytes an entry. An older draft can no longer be replayed, and a longer file is trimmed when it next loads or records. Tests are in `test_v17_generative.py`. |
| O12 | Typing | `envstore_windows.py` (added in `4eecd3f`) is Windows-only, so mypy's Linux view has no `ctypes.WinDLL` or `ctypes.get_last_error`. `python -m mypy --platform linux sdk/python` reported 5 `attr-defined` errors in that file. The ratchet is measured on Windows, so it did not see them. | **fixed**, with per-call branches (option c). Each Windows call goes through a helper with a `sys.platform` branch: `_advapi32()` loads advapi32 on first use, and `_last_error()` reads the error code. Off Windows the helpers raise `OSError`, and mypy skips their Windows branches there. The module now imports off Windows, and the failure moves to the first call. Nothing imports it off Windows, and Windows behaviour is unchanged. |

## Decisions needed

These are the user's to make. Nothing above was decided on your behalf.

- **D1 (plan §7).** Which domains and base models for the first two learned experts? This blocks O1 and O2. Both candidate models need a download, which also needs permission.
- **D2 (plan §7).** Is CPU-only the first target? The current default under CPU Everywhere says yes. Confirming it closes D2.
- **D3 (plan §7).** May a hosted LLM serve as `llm_fallback`? It is off by default and stays off until you decide.
- **D4 (plan §7).** Include Phase 6 (lifecycle and provenance) in scope? This decides O3.
- **S1 (decided 2026-11-04).** Production signing keys live with the approver, never in the repo or the agent's environment. The agent verifies only, against a trust-store file of public keys in a user-owned location that deployment config names, and seeds are generated on the approver's machine. The deploy stack and the desktop read the trust store now, and the generative runtime refuses its output under one (O6, partly). The default stays unchecked.
- **S2 (decided 2026-11-05).** A fresh labeled set for the email recall gap (O4), written and committed before the context rule: `sdk/python/tests/data/moa_routing_email_context.json`. The rule is not tuned on it.
- **D5 (new, 2026-11-05).** How do the stack's own registrations get author signatures once a trust store is configured? They are the deploy stack's two modules (the deterministic engine and the learned module), the MoA reference experts, and generative promotions. The agent holds no keys, so the options are: (a) an approver-signed manifest of those registrations, made on the approver's machine and loaded with the trust store; (b) register the built-in modules outside the agent's startup path, so only signed generative promotions are checked; (c) keep the stack unchecked and enforce only the promotions that carry an approver signature. This blocks O6. **Decided: (b).** The stack's two built-in modules register through `RegistryClient(builtin_ids=...)`, and only those skip the author check. Generative registrations and promotions still need signatures when a trust store is set. Wired since: the desktop's static catalog and its two bio modules (`DESKTOP_BUILTIN_IDS`), the MoA reference experts (`reference_expert_ids()`), and a generative refusal that does not raise. Not built: the approver's signing step for generative output, so that output stays out under a trust store until it is.
- **T1 (decided 2026-11-05).** The generative sandbox timeout stays at 2 s, and the evolve budget stays at 2000 ms on Windows and 1000 ms elsewhere (`generative/budgets.py`). `test_v17_generative.py` pins both values, so a change needs new measurements first.
- **N1 (new).** The GitHub nightly workflow uses Actions minutes. The nightly tier took 589 s locally when it was last measured, and the job is capped at 120 minutes. Keep it, or leave only the Windows task (`OrganismNightlyCI`, which is registered and runs at 02:00)?

- **D6 (new, 2026-11-05).** Should the intent classifier cover sending email, as a `send` intent? Without one, "Please email the signed contract to the client" stays unsure (O14). A send intent needs its own cue rule, because a bare "email" would also match "Pull the email addresses out of this". This is a product choice, so nothing was added.

## Accepted decisions (recorded 2026-11-05)

The user accepted these recommendations. Recording them here changes no code by itself.

- **D1.** The intent classifier comes first. The domains and base models for the learned experts stay open until a named encoder is chosen, and any download needs permission. O1 and O2 stay blocked.
- **D2.** CPU-only is the first target. Confirmed.
- **D3.** A hosted LLM stays off as `llm_fallback`.
- **D4.** Phase 6 is deferred, so O3 stays blocked.
- **N1.** The nightly workflow is `workflow_dispatch` only (`653fea9`). The Windows task is the scheduled run.
- **O8.** Partly fixed, as the table says. The user should confirm the split: dev tools pinned, runtime unpinned.
- **O7.** Stays open until O2, as recommended.
- **Recall misses.** O4 and O13 are fixed on the held-out set. O14 is open under D6.

## Mypy backlog (0 findings on Windows and Linux)

The ratchet was at 59 after F14. Four slices cleared it (to 35, 24, 20, then 0). The breakdown at 59
was:

| Code | Count | Where it sits |
|---|---|---|
| `arg-type` | 17 | values passed where a narrower type is expected |
| `attr-defined` | 11 | attribute access on objects typed too broadly |
| `union-attr` | 6 | `Optional` values used without a narrowing check |
| `comparison-overlap` | 6 | equality checks mypy says can never be true |
| `no-any-return` | 5 | returns that are `Any` from functions declared to return a concrete type |
| `index` | 4 | indexing a value whose type is a union |
| `assignment`, `misc`, `var-annotated`, `operator`, `call-arg` | 10 | one-off findings |

The `comparison-overlap` findings in `sdk/python/organism_sdk/generative/code_pipeline.py` (lines 474 and
478 at 59) were not dead code. `run_static` sets the `REJECTED` stage at line 343, and the check in
`evolve()` is reached when it does. mypy had narrowed `b.stage` after `start()`, so the check now goes
through `_rejected()`, which makes the same comparison. Runtime behaviour is unchanged.

## Verification

- Fast tier, the pre-push gate: passed on every push in this review. It ran 58 gates before the Phase 5 gates were added, and 60 after.
- `pytest -m 'not slow'` collects 591 tests.
- Full tier on Windows at `77e110c`: 61 of 61 gates pass in 258.7 s.
- Full tier on WSL Ubuntu at `77e110c`: 61 of 61 gates pass in 80.9 s. The first run failed `lint:mypy` on a stale `.mypy_cache`, and clearing the cache fixed it (see the troubleshooting section of [ci/README.md](../ci/README.md)). In a non-login shell the run needs `/root/.cargo/bin` on `PATH`.
- Full tier on Windows at `4083925`: 60 of 61 gates pass. `v17:desktop_organism` fails its evolve budget on the local state, which is open as O11.
- Full tier on WSL Ubuntu at `4083925`: 61 of 61 gates pass in 111.5 s.
- Full tier on Windows at `edd2924`: 61 of 61 gates pass in 244.5 s. The evolve tests run on a clean data root (O11).
- Full tier on WSL Ubuntu at `edd2924`: 61 of 61 gates pass in 110.3 s.
- Mypy slice 3 (the last 20 findings): the ratchet is at 0 on Windows. `python -m mypy --platform linux sdk/python` reported 5 findings in O12 before the O12 fix and reports 0 after it. mypy is not installed in the WSL venv (`kc-venv`), and nothing was installed, so the WSL lint gate was not run.
- O12 fix: the envstore tests pass on Windows (26 passed, 1 skipped for POSIX permission bits) and WSL (26 passed, 1 skipped for the Windows-only credential test).
- Tests for the modules this slice touches: 233 passed, 31 skipped on Windows; 261 passed, 3 skipped on WSL.
