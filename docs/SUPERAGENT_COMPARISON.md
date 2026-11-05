# Organism compared with dsh-superagent

**Date:** 2026-11-04 · **Status:** proposal. It is not on the roadmap until the decisions in section 6 are made.

**Compared:** [deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype) at `8c32a9d`, a shallow clone at `H:\Projects\dsh-superagent-prototype`, outside this repository. The README calls it a research prototype and says it is MIT licensed.

## 1. Summary

dsh-superagent is an application. It turns GitHub events, and optionally Feishu messages, into authorized coding work. Each piece of work runs in its own sandboxed session and directory, and the result goes back to the original conversation. A web panel shows first what needs a person. Its design rule is "take as little human attention as possible." The source is about 14,300 lines of TypeScript, plus about 15,000 lines of tests. DeepSeek Harness supplies the LLM sessions.

Organism is a substrate. It has module contracts, a shared workspace, structural and capability routing (MoA), degradation tiers, promote-gated evolution, a process sandbox, and a desktop control plane. Its Python SDK is about 14,000 lines. It has no concept of an external event, a requester, a work item, an agent session, or an outbound message.

**Verdict.** Organism does not have the superagent's feature set, and the gap is not a few missing parts. The superagent's domain, which runs Source → Trigger → Eval → Mandate → Ticket → Assignment → Channel, does not exist in Organism. Organism does have several pieces that the design needs, and it is ahead on most of them: a promote gate with shadow scoring and rollback, an Ed25519 trust store, a process sandbox with a network allowlist and shell-escape denial, a SQLite WAL ops log with replay, health reports, and gate ratchets.

**Recommendation.** Build the work layer as a new package, `organism_sdk/work/`, on top of those pieces. Do not make sources, channels, or executors into `SubstrateContract` modules. They are I/O adapters, not compute modules. Leave the frozen v1.0 surface unchanged. The build-out is in section 5, and the decisions it needs are in section 6.

## 2. Method

- Read the superagent README, docs 000 to 008, and the cookbook, plus the architecture module tables. Did not run its code or install its dependencies. Its docs are tested against its code (`tests/docs.spec.ts`, `tests/model-surface.spec.ts`), so the docs were taken as the specification.
- Searched Organism with grep over `sdk/`, `modules/`, `runtime/`, `desktop/`, `harness/`, `deploy/`, `scripts/` and `docs/`, for: github, feishu, webhook, ticket, mandate, subscription, allowlist, worktree, pull request, lark, outbox, backoff, approval, attention, pause, cron, schedule. Also listed the desktop panels, the CLI subcommands, and the HTTP routes in `deploy/serve.py`.
- Read `generative/backends.py`. `HostedLLMBackend` is a single-shot OpenAI-compatible chat call that drafts code. It is off by default (`ORGANISM_LLM_ENABLED`). Nothing in the repository runs a multi-turn, tool-using agent.
- A grep finds terms that exist, not terms that are missing. Treat the "Missing" entries as "not found by these searches."

Status values: **Missing**, **Partial** (a related piece exists, but not the capability), **Present** (in place, or Organism is ahead).

## 3. Feature matrix

### A. Intake

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| A1 | Source kinds as plugins, each with a config schema, form fields, health entries and a cursor (007, 008) | No external event intake. `inputs.py` covers perception modalities only | Missing | New `work/sources/` with a `Source` protocol |
| A2 | GitHub source: notifications, subscribed Issues and pull requests, CI changes, merge and close events, optional repository-wide intake (001, 003) | None. `.github/workflows` runs only Organism's own CI | Missing | `gh` through an argv-only runner, like `infra/commands.ts` |
| A3 | Feishu source and channel (001) | None | Missing | Defer. A Channel port makes it an addition later |
| A4 | Idempotent intake by stable id. The cursor moves only after the store commits. A restart does not replay (008 §1, §9) | `snapshot.py`: SQLite WAL ops log with replay | Partial | Reuse its WAL layout for the work store |
| A5 | Filtered events carry a reason code the operator can see (005) | `trace.py` has per-subsystem trace entries | Partial | Add `WorkTraceEntry` |

### B. Authorization

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| B1 | Allowed list of requesters for each Source, in that Source's identities (002) | None | Missing | Deterministic gate, plain code |
| B2 | Admission table: receiving scope × sender on the list × addressed the agent → explicit, inferred or ignore (002) | None | Missing | Same gate. Use the cells in 002 as the spec |
| B3 | Bot list. Bots are never explicit and never stop a Ticket (002) | None | Missing | Same gate |
| B4 | Accept modes `off`, `observe` and `auto`. `observe` records "would accept" (002) | `PromoteGate` with shadow scoring (default minimum 0.9) and `rollback_last_promote` (`generative/stages.py`, `code_pipeline.py`) | Partial. Same idea, different object | Graduate each rule from observe to auto only after `PromoteGate` passes on the recorded would-accept decisions. This is the closest fit in the repository |
| B5 | Policy version on every Mandate. A version change discards running Evals and notifies live Tickets (001, 002) | Registry versions and promote history | Partial | Policy as a versioned artifact. Record its digest on each Mandate |
| B6 | Mandate: an immutable grant with scope, strength, matched rules and basis. Revalidated before a resume (001, 002) | None | Missing | `Mandate` dataclass plus a revalidation function |
| B7 | Signed Policy changes. Superagent relies on settings and does not sign them | Ed25519 `TrustStore` with separate author and approver keys (`signing.py`, `registry.py`) | Present. Organism is ahead | Approver signature on each Policy version. Depends on decision S1 |
| B8 | Prompt text never changes permissions. Enforcement is in code (004) | Organism's gates and refusals are in code | Present | Keep the rule and state it in the design record |

### C. Eval

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| C1 | One Eval per Thread at a time. Triggers that arrive meanwhile merge into the next batch. A deadline. Two retries, then `unavailable` (001, 002) | MoA routes one query at a time, synchronously | Missing | Per-Thread queue with batching and a deadline. The degradation-style hysteresis in `moa/tiers.py` is a reference for the retry rule only |
| C2 | Two layers: a deterministic gate, then a model assessment that must judge every enabled rule (002, 007) | MoA's guardrails and capability scorer are rule-based | Partial | Build the gate without an LLM. Put the assessment behind an `Assessor` port |
| C3 | Decision history, each with reason codes (007) | None | Missing | Stored in the work store |

### D. Tickets and execution

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| D1 | Ticket stage computed from its latest report and what it waits for (003). Seven rows, the first match wins | None | Missing | A pure function with a row-by-row table test, as superagent does in `stage.spec.ts` |
| D2 | An Assignment is bound to one executor. A retry starts a new Assignment in the same directory. A restart sends a recovery note (003) | `snapshot.py` replay and `health.py` | Partial | The recovery-note logic is new |
| D3 | Per-Ticket executor: its own directory, a prepare command with a ten-minute limit, and execution variables (003) | `sandbox/jail.py` `ProcessJail` with a wall-clock timeout, rlimits, namespaces where available, environment scrub, workdir, and shell-escape denial (`sandbox/policy.py`) | Partial. The jail exists; the per-Ticket directory and prepare step do not | Add a `work_executor` `SandboxPolicy` profile. Longer timeout, larger RSS and CPU caps, a network allowlist for the forge hosts |
| D4 | Worker slots. One extra slot for a person's message. Launches run concurrently (003) | `max_concurrent_invocations` in `MetabolicProfile` (`contract.py`). `distributed/multiprocess.py` | Partial | A small slot semaphore |
| D5 | Background shell jobs and subagents, with a 30-minute limit and a wake on completion (003) | Sandbox timeouts only. No job model | Missing | Left to the executor's own process model |
| D6 | An executor that works unattended, through a tool-using agent session (003, 004) | `HostedLLMBackend` is single-shot and off by default. No tool-using loop exists anywhere | Missing | Decided (W-D1): an external coding-agent CLI, run in the jail. Organism gets no tool-using loop |
| D7 | Follow-up ownership, hand-back, and release when a Ticket ends (002, 003) | None | Missing | Defer. Start with "a Ticket owns its own Thread" |
| D8 | Subscriptions. Thread messages fan out to subscribed Tickets as context (001) | `workspace.py` binds and broadcasts hypervectors, not Threads | Missing | Not a fit as it stands. Use explicit tables. Attachment needs an explicit reference, not similarity, so do not route attachment through the hypervector workspace |
| D9 | Pull-request following and the done rule (003) | None | Missing | GitHub adapter, in a later phase |
| D10 | Auto-merge is default-off. The agent never enables it on its own account (003) | None | Missing | Do not build auto-merge in v1. Keep the human merge |

### E. Outbound writes

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| E1 | Channel writes of four kinds: acknowledgement, answer, result, attention. Each is allowed by a named rule (001, 007) | None | Missing | Channel port with a `gh` implementation |
| E2 | Outbound messages and effects are stored, then retried with backoff from 5 s to 300 s. Health per kind (007) | No durable outbound queue. `snapshot.py` covers only the workspace | Missing | An `effect` table in the work store |
| E3 | Messages for one Ticket to one conversation keep their order. A conversation that is gone is dropped and never queued again (003, 008) | None | Missing | Follows from E2 |
| E4 | Idempotent sends through a hidden marker in the body (008 §5) | None | Missing | Marker in the comment body |
| E5 | Honest-delivery rules. A draft is marked unfinished (004) | Promote gates refuse unverified artifacts. `may_actuate=False` is the default | Present in spirit | Same default for writes: `may_write_external=False`. Add a dry-run mode that logs would-write, like `observe` |

### F. Operator surface

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| F1 | A panel that lists first what needs a person (000, 005) | Desktop panels: home, ops, traces, pipelines, physiology, registry and others. No attention queue | Missing | New `needs_you` panel built on `panels/_widgets.py`. Also `organism work attention` in the CLI |
| F2 | Panel tabs by workflow: Overview, Source, Trigger, Eval, Execution, Settings (005) | Panels are organized by subsystem | Missing | A separate panel group. Do not force it into the existing panels |
| F3 | Search across Triggers, Threads and Tickets (005) | `traces.py` panel covers part of it | Partial | Low priority |
| F4 | Pause processing (003, 005) | None | Missing | One flag in the work store, checked by every pass |
| F5 | Settings with revision history and conflict-safe saves (004, 005) | `deploy/config/*.yaml` with `validate-config` | Partial | Store saves as versioned artifacts |

### G. Prompts and skills

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| G1 | Team-editable instruction sections, versioned, with a "default updated" flag (004) | None for instructions. `SkillRegistry` versions code skills | Missing | Store instruction text as versioned artifacts in `ArtifactStore` |
| G2 | Built-in source skills, for GitHub and Feishu (004) | None | Missing | After the executor is decided |
| G3 | Routing. The main session routes with an LLM (004) | `router.py` is structural and deterministic | Partial. Different job | Keep the structural router. The assessment role goes to `Assessor` |

### H. Deployment and operations

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| H1 | Deployment as a plugin bundle for the host (006, 007) | `deploy/`, `bundle-export`, `bundle-import`, `serve` with health and status HTTP | Partial. Organism's own deploy stack | New source and executor settings go in `deploy/config/*.yaml`, checked by `validate-config` |
| H2 | Health with one entry per part. A problem is raised after three failures in a row (003, 007) | `health.py` with `HealthReport` and `HealthServer` | Present | Reuse. Set the failure threshold in the work layer |
| H3 | Status command and an hourly check (006) | `organism status`. A nightly CI tier, Windows Task Scheduler at 02:00, and `nightly.yml` on GitHub | Partial | Add `organism work status` |
| H4 | Retention. Superagent deletes nothing yet (007 Persistence) | Organism has the same problem. O11 in [GAP_ANALYSIS.md](GAP_ANALYSIS.md): `draft_replay.json` grows without bound | Missing in both | One compaction design for both |

### I. Testing and gates

| ID | Superagent capability | Organism today | Status | Build-out |
|---|---|---|---|---|
| I1 | A spec per module, row-by-row table tests, and a check that the docs index is complete (007 Tests) | 42 test files under `sdk/python/tests`. 60 fast-tier gates. Ratchets for ruff, mypy and rustfmt | Present. Organism's gate breadth is larger | Add `work:*` gates to `ci/gates.yaml` |
| I2 | A simulated host for tests (`tests/fixtures/host.ts`) | `harness/` fault injection and scenarios | Present | A fake `gh` and a fake executor as harness scenarios |

## 4. Where Organism is ahead

Keep these. They are reasons to build on Organism rather than port the superagent's design wholesale.

- **Promote gate with shadow scoring, and rollback.** The superagent has nothing equivalent for changes to its own behavior.
- **Signed registry with a trust store (B7).** The superagent does not sign anything.
- **Process sandbox (D3).** The superagent says its wrappers "establish defaults, not a security boundary," and its workers run "without approval as the operator's OS user" (003). Organism's jail has rlimits, namespaces where available, environment scrub, shell-escape denial, and a network allowlist.
- **Health, degradation drills, deterministic replay, and fault injection** in `harness/`.
- **Gate breadth.** Lint, types, Rust formatting and clippy, proto, determinism, perf budgets, and tiers.
- **Refusal posture.** Actuation is refused, and hosted LLM calls are off by default.

## 5. Build-out plan

Each phase names its gates and its exit criteria. Gates go in `ci/gates.yaml`. Docs go in `docs/v1.12/WORK_AGENT.md`. Effort is relative (S, M, L), not calendar time.

**W0. Decisions and design record.** No code. Decide W-D1a and W-D2 to W-D7 in section 6. W-D1 is already decided. Write `docs/v1.12/WORK_AGENT.md`, which adopts the superagent's terms where they name a concept (Source, Trigger, Thread, Eval, Mandate, Ticket, Assignment, Channel). Carry its rejected concepts over as rules: no principal entity, no mapping of identities across Sources, no Eval that schedules its own triggers, no cancelling running Tickets on a Policy change, no topic-similarity attachment. *Exit:* design record accepted. Effort S.

**W1. Pure domain.** `work/domain.py` (Trigger, Thread, Mandate, Ticket, Assignment, Decision), `work/gate.py` (admission cells, bot list, strength), `work/stage.py` (the seven stage rows, with a table test copied from the superagent's stage table as the spec), and `work/policy.py` (versioned, with a digest). No I/O imports, enforced by a hygiene check. Gate `work:domain` in the fast tier. *Exit:* table tests pass. Effort M.

**W2. Store and effects.** `work/store.py` on SQLite WAL, reusing the `snapshot.py` layout. Tables: trigger, decision, ticket, assignment, effect, receipt, cursor, and a single pause flag. Idempotent intake. The effects queue retries with backoff from 5 s to 300 s. Gates `work:store` and `work:restart`, where the restart gate kills the process mid-round and checks that replay neither duplicates nor drops anything. *Exit:* both gates pass. Effort M.

**W3. GitHub source, read only.** `work/sources/github.py` reads through `gh api` with argv only, never a shell, and scoped to one repository. It polls notifications and subscribed Issues and pull requests. A failed item keeps its own error and does not fail the round. The cursor moves only after the store commits. Tests use a fake `gh` script, so CI never touches the network. A live smoke test against a test repository is opt-in only. Gate `work:github_fake`. Effort M.

**W4. Gate and assessment.** The gate runs on W3's intake. Accept modes are `off`, `observe` and `auto`. The `Assessor` port has two implementations: `RuleAssessor`, deterministic, used in tests and shadow runs, and `LLMAssessor`, optional and off by default, which needs decision W-D2. Graduating a rule from `observe` to `auto` requires a passing `PromoteGate` run on its would-accept records. Gates `work:admission` (the 002 cells as a table) and `work:shadow_promote`. Effort M to L, depending on W-D2.

**W5. Executor and sandboxed execution.** An `Executor` protocol. The first implementation, `ProcessExecutor`, runs a configured argv inside `ProcessJail`, in a per-Ticket directory after a prepare argv with a ten-minute limit. It uses a `work_executor` `SandboxPolicy` profile: a thirty-minute wall-clock limit, larger memory and CPU caps, and a network allowlist limited to the forge's hosts. It has a blocked-command list, a worker-slot semaphore (D4), and a recovery note after a restart (D2). Gates `work:jail_profile` and `work:executor_fake`. The jail behaves differently on Windows and on Linux, so run `capabilities()` on each platform and record what differs. Use WSL for the namespace paths. Effort L. W-D1 is decided: the executor is an external CLI. The CLI is an argv template in the deployment config, so no CLI is hard-coded. Which CLI to use is W-D1a, adopted 2026-11-04 as Claude Code. The CLI must be installed and its flags checked before this phase starts.

**W6. GitHub channel.** Comments and review-thread replies through `gh`. Each reply carries a hidden idempotency marker. Replies for one Ticket stay in order. Only a 410-class answer counts as "gone." Gate `work:channel_idempotent`. Effort S to M.

**W7. Operator surface.** CLI: `organism work {status, tickets, attention, pause, resume, stop, retry, evaluate}`. A `needs_you` desktop panel that lists attention first and shows healthy states in one line. A status route in `serve`. Gates: CLI tests, and a panel smoke test under `QT_QPA_PLATFORM=offscreen`, which the desktop `--smoke` path already uses. Effort M.

**W8. Follow-ups and pull requests.** Start with one rule: a Ticket owns its own Thread, and a human message there goes to its executor. Hand-back and release (D7) come only after shadow data shows the need. Then pull-request following and the done rule (D9). Gate `work:followups`, with property tests. Effort L, and it can be deferred.

**W9. Policy governance.** Policy versions signed by an approver through the existing `TrustStore`, which depends on S1. A Policy change notifies only the live Tickets it affects, and never cancels a running Ticket. Instruction text is stored as versioned artifacts with a "default updated" flag. Gate `work:policy_version`. Effort M.

**Cross-cutting.** Retention and compaction (H4) for the work store and for the replay log in O11. One design for both.

**Not planned.**

- Auto-merge (D10). The superagent defaults to a human merge, and the agent never merges on its own account.
- Feishu, until a Channel port exists and someone needs it.
- Repository-wide intake of every Issue and comment. The superagent offers this as a switch, but it multiplies the attention cost, which the superagent's own philosophy warns against.

## 6. Decisions needed

These are the user's to make. Nothing here was decided on your behalf.

- **W-D1. Executor. Decided: an external coding-agent CLI, run in non-interactive mode inside the Organism jail.** The CLI brings its own model access, and Organism stores no model code. The options not taken were an Organism-native tool-using LLM loop, which is a large new surface and would need D3 approved, and DeepSeek Harness, which ties Organism to another runtime.
- **W-D1a. Which CLI (blocks W5).** Adopted 2026-11-04: Claude Code, run in non-interactive print mode, as the only CLI in the argv template. Checked 2026-11-04 against Claude Code 2.1.318, installed on Windows and in WSL. Print mode is `-p`, and the output format is `--output-format`. The choices for `--permission-mode` include `dontAsk`, and `--permission-prompts none` denies anything that would prompt; which combination an unattended run uses is still to be decided. `--allowedTools` names the tools, `--bare` skips hooks, and `--no-session-persistence` keeps no session. There is no turn-limit flag. The key variable is `ANTHROPIC_API_KEY`, and the `work_executor` profile passes only that variable. The API host is recorded in its network allowlist, which the jail does not enforce yet.
- **W-D2. Assessment model (blocks the LLM part of W4).** May a hosted LLM classify proactive candidates? This extends D3. **Adopted 2026-11-04: rules first. Revisit once labelled would-accept records exist.**
- **W-D3. First source.** GitHub only (**recommended**), or GitHub and Feishu.
- **W-D4. Auto-merge.** Confirm that v1 has none (**recommended**).
- **W-D5. Policy signing keys.** Adopted 2026-11-04 (S1): the approver's private key stays with the approver, never in the repo, the agent's environment or the jail. The agent verifies only, through a `TrustStore` file of public keys that deployment config names. This unblocks W9.
- **W-D6. Placement.** `organism_sdk/work/` with its docs under `docs/v1.12/` (**recommended**), outside the frozen v1.0 surface. The alternative is a separate package outside the SDK.
- **W-D7. Vocabulary.** Adopt the superagent's domain terms (**recommended**).

**Licensing.** The superagent is MIT. Organism is Apache-2.0. **Recommended:** write the code from the superagent's documents, and do not copy its source. If any code is copied, keep its copyright notice.

## 7. Risks

- **Scope.** The superagent's source is about 14,300 lines, and its follow-up model (002, 003) holds most of the complexity. Build the simple path first, and add the rest only when the data shows it is needed.
- **Platform containment.** The jail behaves differently on Windows and on Linux. Check it on each before promising containment.
- **CLI credentials and network (W-D1).** An external CLI needs its model API reachable and its key present in the jail. Two defaults in `SandboxPolicy` work against that. `scrub_env_prefixes` removes `OPENAI_` and `AWS_` variables, and `network_allowlist` is empty. The `work_executor` profile must allow the CLI's API host and pass its key variable by name, and it must not pass anything else through.
- **Prompt behavior is hard to test.** The superagent tests its built-in text against rules, through `cards.spec.ts` and `model-surface.spec.ts`. Use the same approach.
- **Outward writes.** Comments and pull requests cannot be recalled in practice. Keep `may_write_external=False` as the default, and run in `observe` first.
- **Attention cost.** A noisy agent does more harm than no agent (superagent 000). The first live run should stay in `observe` mode until its would-accept records look right.

## 8. Not verified

- I did not run the superagent's code or its tests. What is said about it comes from its documents and from its source layout. Its documents are tested against its code, but I did not check every rule against the source.
- Organism's absences come from grep, as described in section 2.
- Sizes are relative (S, M, L), not time estimates.
