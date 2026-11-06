# NLP-CLI on the Organism substrate

Status: **design record and first implementation** (branch `feat/nlp-cli-substrate`, not merged).
Date 2026-11-06. Covers the mapping of the offline command router `nlp-cli` (repository `LoopyLuci/NLP-CLI`,
private) onto Organism's contract, registry, tool, calibration and confinement pieces, and the Organism
gaps that the mapping needed closed.

Code: `sdk/python/organism_sdk/{calibration,learned,pathscope,tool_host}.py` (new),
`modules/nlp_cli/` (adapter). Tests: `sdk/python/tests/test_v113_*.py`.

## 1. What NLP-CLI is, in substrate terms

NLP-CLI turns one natural-language request into one of five decisions: `execute` (a read tool with valid
arguments), `confirm` (a write, execute or destructive tool that needs a person's yes), `no_tool` (chat),
`declined` (negated or escalated), or `abstain` (a missing argument or low confidence). Its pipeline is
fixed and ordered:

1. **Gate**: negation and privilege-escalation checks (`crates/core/src/gate.rs`).
2. **T0 grammar**: exact templates with typed slots (`t0.rs`), with a path rule for broad templates.
3. **T1 classifier**: a small MLP over word and character n-grams, temperature-calibrated, abstaining
   below a validation-chosen threshold (`t1.rs`).
4. **Policy**: negated requests are declined, missing arguments abstain, read tools execute, and every
   other risk returns `confirm`.

A held-out evaluation (frozen sets, safety must-pass suite) gates any model change. Teaching and review
feed a training file, and every answer to a confirmation is written to an audit log.

## 2. Mapping

| NLP-CLI part | Organism piece | Status here |
|---|---|---|
| The router as a unit | `SubstrateContract` (`contract.py`), with `OutputForm.TOOL_CALL`, `may_actuate=False` | Built: `modules/nlp_cli/router.py` `router_contract()`. It validates with no error, and is not yet registered in a registry (the artifact digest is an argument, to be filled from the model file) |
| Declared reliability | `ReliabilityTier.T2_LEARNED_CALIBRATED`. The grammar is T0, the classifier is learned and calibrated, so the router as a whole is declared at the learned tier | Declared, not measured. The calibration evidence (A5) is produced by `calibration.py` but is not yet attached to the contract |
| Tool catalogue `spec/tools.json` | One `ToolContract` per tool (A2, existing) | Built: `tool_contracts()` converts the spec |
| Risk levels read, write, execute, destructive | `MaxSafetyTier` LOW, MEDIUM, HIGH, HIGH | Built: see section 3 |
| "Always requires confirmation" | `ToolConfirmation.ALWAYS` plus `HUMAN_CONFIRMATION` (A3, existing) | Built: `tool_host.py` refuses a call without a confirmation callback and records the approver |
| Argument validation | JSON Schema text on `ToolContract.schema_json` | Built: `tool_host.validate_args` (a subset that fails closed on any keyword it does not support) |
| Path confinement to the workspace | Organism had no Windows confinement (G2) | Built: `pathscope.py` (string rules, reserved names, alternate data streams, symlink escape). It is a host-side check, not an OS sandbox |
| Gate, T0 grammar | Deterministic experts (`moa/reference.py` pattern, T0) | Not moved. They stay in NLP-CLI's Rust code, which is the source of truth for the rules |
| T1 classifier | Learned backend interface (D2, open before) | Built: `learned.py` `LearnedBackend` and `decide_label`. The MLP itself stays in Rust, behind the adapter |
| Abstention threshold chosen on validation | Calibration service (D3, open before) | Built: `calibration.choose_threshold` (lowest threshold that meets the target precision with enough support), `fit_temperature`, `expected_calibration_error` |
| Held-out and safety evaluation | Shadow runner and promote gate (H1, B1, both existing), and the model-quality record (H3) | Built: `quality.py`. A record names the model digest and the evaluation-set digest, holds metrics as parts per million, and carries a `clean` claim. `quality_gate` refuses a promotion on a metric below its minimum, a record for another model, too few samples, or an unclean set. NLP-CLI's eval report is not yet written as a record |
| Model file and provenance | `ModelArtifact` (A8) and signed registration (A9), both existing | Existing. NLP-CLI's `.sha256` sidecar is the digest. Not wired |
| Executors | `ToolHost` (G1, open before), plus `ProcessExecutor` and `ProcessJail` from the work agent (existing, Linux-only) | `ToolHost` built. NLP-CLI's executors were added in its own repository (`crates/core/src/exec.rs`, `scope.rs`, branch `feat/nlp-cli-expansion`). See section 5 |
| Audit log of answers | Trace and op log (C1, open) | Partly built: `ToolHost` keeps a hash-chained record of every call in memory and passes each record to a sink. Durable storage is still open |
| Degradation when the model is missing | MoA tier T4 deterministic fallback (`moa/tiers.py`, existing) | Mapped. A missing model means grammar and gate only |
| Teach and review loop | Data gate (Training Gate, `docs/MODEL-PHILOSOPHY.md`) | Open. No data-quality type exists yet; NLP-CLI's review step is manual |
| Redaction of logs | Redaction hook in the trace sink (C2, open) | Open. The audit log holds user text, so it must not leave the machine until C2 exists |

## 3. Risk mapping

NLP-CLI's four risk levels map to Organism's scale as follows. The mapping keeps every rule that
`ToolContract.validate()` enforces (HIGH needs confirmation, CRITICAL needs it on every call, and
internet access or HIGH risk needs confinement).

| NLP-CLI risk | Organism tier | Confirmation | Network | Confinement |
|---|---|---|---|---|
| read | LOW | NONE | NONE | SCOPED when the tool takes a path, else NONE |
| write | MEDIUM | ALWAYS | NONE | SCOPED |
| execute | HIGH | ALWAYS | LOCAL | SCOPED |
| destructive | HIGH | ALWAYS | NONE, or INTERNET for `git_push` | STRICT |

**Owner decision needed.** `destructive` maps to HIGH, not CRITICAL. CRITICAL would also make the
tool need confirmation on every call, which it already gets, and a stricter tier would change the
Organism promotion rules for this router. The mapping is recorded here until the owner decides.

## 4. Organism gaps closed by this branch

| Gap | Before | Now | Remaining |
|---|---|---|---|
| D2 learned backend | No interface; the policy artifact had no weights type | `LearnedBackend` protocol and `decide_label` (abstain below threshold, keep the best label) | No weights type; the backend is any object that returns logits |
| D3 calibration service | ECE in `evidence.py` only as an input; no fitting | Temperature fit, ECE, and threshold choice for a target precision | Isotonic calibration is not built; only temperature |
| G1 tool host | No interface; loops in each product | `ToolHost`: validation, confirmation, scope, audit | No durable audit sink; no network enforcement |
| G2 confinement (partial) | Linux rlimits and `unshare` only | `PathScope`: a host-side path check that works on Windows | Not an OS sandbox. Process confinement on Windows is still open |
| H3 model-quality record | Harness checked faults, soak and speed, never accuracy | `quality.py`: a record bound to a model digest and an evaluation-set digest, metrics in parts per million, and a pure gate | The record does not verify its `clean` claim; NLP-CLI's report is not yet written as a record; per-model gate files (H2) are open |

Gaps not touched here: A4 (warning versus error for unchecked actuation), B6 (Kotlin health), C1 and C2
(traces), E2 (signal sources), F1 (embedding index), H2 (per-model gate files),
I5 (vector drift check). None of these blocks NLP-CLI.

## 5. What stays in NLP-CLI

- The grammar, the gate and the training data. These are NLP-CLI's own rules and evaluation sets. Moving
  them into Organism would make the frozen sets Organism's, and that changes who may edit them.
- The MLP and the frozen sets. The adapter treats the router as a black box that returns JSON, so the
  model can change without an Organism release.
- The executors for the tools (`read_file`, `git_status`, and so on). They run inside NLP-CLI, because the
  tools are NLP-CLI's own. Organism's `ToolHost` enforces the contract around them. It does not run them.

The adapter (`modules/nlp_cli/`) calls the router with `nlp-cli route --json` and maps the result onto
`ToolHost` calls. The `ToolHost` refuses any call whose confirmation or path check fails, whatever the
router decided.

## 6. Open decisions for the owner

1. Declared tier of the router: T2 (learned and calibrated, as built) or T3 until the calibration evidence
   is attached to the contract.
2. `destructive` at HIGH or CRITICAL (section 3).
3. Whether `git_push` should be INTERNET network with STRICT confinement, which is the current mapping.
4. Whether the Organism `ToolHost` audit chain should be the one NLP-CLI's audit log uses, or stay separate.

## 7. Verification

- `sdk/python/tests/test_v113_*.py`: 45 tests for the four gap modules, 9 for the quality record and 23
  for the adapter. The adapter test that runs the real binary needs `NLPCLI_BIN` and `NLPCLI_SPEC`. With
  both set, all 77 pass against the NLP-CLI build on `feat/nlp-cli-expansion`.
- `ruff check` is clean on the new files. `mypy` reports one error, in `contract.py` (a generated proto
  module that is missing in a fresh checkout). It is not in the new code, and CI generates the module first.
- Symbolic-link tests in `test_v113_substrate_gaps.py` skip when the host cannot create links. On this
  Windows host they skip, because creating links needs an administrator here. The refusal of a link out of
  the scope is tested on NLP-CLI's side only where links can be created.
- Not run: the full `pytest -m 'not slow'` suite, and the Rust workspace of Organism. Both need the CI
  environment.
- Changes are uncommitted in the worktree `X:/Projects/Organism-nlp-cli` on branch `feat/nlp-cli-substrate`,
  which starts from `main` at `094eca2`. The primary Organism checkout has someone else's staged changes,
  and this work does not touch them.

## 8. Known limits

- The router's artifact digest is passed in by the caller. It is not read from the model file yet.
- `ToolHost`'s audit chain is in memory. A durable sink is open (C1).
- `PathScope` checks paths; it does not stop a command from opening other files. `run_command` and the
  test runner run without an OS sandbox on Windows. The confirmation is the only guard for them.
- The calibration service does temperature scaling only. Isotonic calibration is not built.
