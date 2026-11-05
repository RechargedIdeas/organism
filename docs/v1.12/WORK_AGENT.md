# Work Agent Layer: Design Record (v1.12)

**Status:** W0 accepted with the working defaults in section 1. W1 (pure domain), W2 (store and effects queue), W3 (GitHub source, read only) and W4 (Eval, rule assessment and shadow promotion) implemented. W5 onward not started.

**Covers:** [docs/SUPERAGENT_COMPARISON.md](../SUPERAGENT_COMPARISON.md), the comparison with dsh-superagent and the build-out plan this record follows.

**Code:** `sdk/python/organism_sdk/work/`. **Tests:** `sdk/python/tests/test_v112_work_*.py`. **Gate:** `work:domain` in [ci/gates.yaml](../../ci/gates.yaml).

## 1. Decisions

| ID | Decision | Status |
|---|---|---|
| W-D1 | The executor is an external coding-agent CLI, run in non-interactive mode inside the `ProcessJail`. | Decided 2026-11-04 |
| W-D1a | Which CLI: Claude Code, run in non-interactive print mode, as the only CLI in the argv template. Before W5 starts, install it in the jail environment, check its print-mode and permission flags against the installed version, and allow only its API host and its one key variable in the `work_executor` profile. | Decided 2026-11-04. W5 still needs the CLI installed and its flags checked |
| W-D2 | Whether a hosted LLM may classify proactive candidates. Rules first. An LLM, when revisited, is off by default, sees only inferred candidates, redacts before sending, and only proposes. | Decided 2026-11-04: no hosted LLM yet. The LLM part of W4 stays unbuilt |
| W-D3 | First Source: GitHub. | Working default |
| W-D4 | No auto-merge in v1. | Working default |
| W-D5 | Policy signing keys (decision S1): the approver's private key stays with the approver, never in the repo, the agent's environment or the jail. The agent verifies only, against a `TrustStore` of public keys in a user-owned file that deployment config names. | Decided 2026-11-04. Unblocks W9 |
| W-D6 | Placement: `organism_sdk/work/`, outside the frozen v1.0 surface. | Working default, applied in W1 |
| W-D7 | Vocabulary: the superagent's domain terms. | Working default, applied in W1 |

A working default is what the code uses now. It can change before W2. Changing W-D6 or W-D7 after W1 means renaming modules.

## 2. Principles

- **Code enforces permissions.** Prompt text and message content cannot change the gate or a Mandate.
- **Denied by default.** A Trigger is admitted only by a listed sender, an admission cell, a listed bot, or a follow-up on a Thread that already has a Ticket.
- **A Mandate is immutable.** A wider scope needs a new Ticket.
- **The domain is pure.** `domain.py`, `stage.py`, `gate.py` and `policy.py` do no I/O and read no clock. Time comes in as data (`Trigger.at`). A test enforces this.
- **Versioned decisions.** A Policy version is a digest of everything that decides admission, and every Mandate records the version it was accepted under.
- **Outward writes are off by default.** The W6 channel starts with `may_write_external=False`.

## 3. Rejected concepts carried over

These come from the superagent's domain document and are kept as rules:

- No principal or membership entity. Identities belong to a Source, and nothing maps them across Sources.
- Eval never schedules its own delayed Triggers. Waiting belongs to Sources.
- No "at most one live Ticket per Thread".
- No "append to Ticket" decision. Appending is fan-out.
- A Subscription does not check admission. The Mandate does.
- Correlation adds context and never routes.
- A Ticket's state is its own, not the executor session's.
- An executor cannot declare that a person asked it to stop. Only Eval decides the strength of an end.
- A Policy change never cancels a running Ticket. It is recorded and delivered.
- Attaching a message to a Ticket needs an explicit reference. Topic similarity is not enough, so the hypervector workspace does not route attachment.

## 4. Reused from Organism

| Need | Organism piece | Used in |
|---|---|---|
| Durable state | `snapshot.py`: SQLite WAL ops log with replay | W2, with the same WAL setup and its own schema. It does not import `snapshot.py`. |
| Observe, then promote | `generative/stages.py` `PromoteGate` and `rollback_last_promote` | W4 |
| Signed Policy versions | `signing.py` `TrustStore` | W9 |
| Execution isolation | `sandbox/jail.py` `ProcessJail` and `sandbox/policy.py` `SandboxPolicy` | W5 |
| Health | `health.py` `HealthReport` | W3 |
| Trace | `trace.py` `TraceEmitter` | Later. W2 did not need it. |

## 5. Module layout

| Module | Holds |
|---|---|
| `domain.py` | `Trigger`, `Thread`, `Mandate`, `Assignment`, `Ticket`, `Decision` and their enums, including `Verdict`. `thread_key` and `decision_key` build the keys. Plain values. |
| `stage.py` | The Ticket stage table from the superagent's execution document (003): `Stage`, `stage_of`, `waits_for_person`. |
| `gate.py` | `admit`, the deterministic first layer of Eval. Returns an `Admission`. |
| `policy.py` | `AcceptMode`, `Cell`, `AdmissionRow`, `Rule` (with `pattern` and `auto`), `SourcePolicy`, `Policy`, `policy_version`, `may_accept_inferred`. |
| `assess.py` | `RuleAssessor`, `Assessment`: which enabled rule patterns a Trigger matches. Pure. |
| `decide.py` | `decide`, `EvalReason`, `rule_reason`: one Decision per Trigger and Policy version. Pure. |
| `promote.py` | `shadow_gate`, `graduate`, `ShadowGate`: when a rule may graduate from observe to auto. Pure. |
| `runner.py` | `evaluate`, `EvalReport`, `DEADLINE_S`: runs Eval over a store. It does no I/O itself; the store does. |
| `codec.py` | `encode`, `decode`, `to_text`, `from_text`: the JSON form of the domain, read from each dataclass's annotations. Pure. |
| `store.py` | `WorkStore`: SQLite state, rounds, Receipts, the effects queue, the pause flag, the writer lock, source errors, Decisions, labels and the Triggers still undecided. The only top-level module that does I/O. |
| `sources/github.py` | `GitHubSource`, `GhCli`, `RoundReport`: reads one repository through `gh api`, read only. An I/O adapter, so it lives in `sources/`. |

## 6. W1 behaviour

### Admission

`admit` checks in this order:

1. The scope is not listened to: refused.
2. The Source has no Policy part: refused.
3. The Trigger has no actor, as a CI result does: only the last cell applies.
4. The sender is a bot: admitted only if it is on the Source's bot list and either addresses the agent or the scope is observed. Always inferred, never explicit.
5. A listed person addresses the agent: explicit.
6. The Thread has a Ticket, so the message is a follow-up. A listed person is explicit. An unlisted person whose addressed message hits an explicit cell is explicit. Otherwise the follow-up is inferred, whatever the cell says.
7. Otherwise the message's admission cell applies. An unaddressed message needs an observed scope.
8. Any inferred result is refused in `off` mode. Explicit results work in every mode.

Two invariants follow, and the gate tests check them over every combination of inputs:

- Explicit requires a listed sender, or an explicit cell on an addressed message.
- A bot is never explicit.

### Stage

The table in the superagent's execution document, read top to bottom, first match wins. An ended Ticket has no stage, and `stage_of` raises for it.

### Policy version

The version is `sha256:` followed by the digest of the Policy's canonical JSON: keys sorted, sets sorted, Sources ordered by name, rules in the order given (the order is part of the prompt), and ids case-folded. Equal Policies give equal versions, whichever way they were built.

## 7. W2 behaviour

### Store

`store.py` is the only top-level module of the package that does I/O. The adapters in `sources/` do I/O too. It keeps its state in SQLite in WAL mode with `synchronous=FULL`, as the ops log in `snapshot.py` does. Opening a store takes a writer lock: an OS lock on the store's `.lock` file, held until the store closes or its process dies. A second writer, in this process or another, is refused at once with `StoreInUse`. A crash leaves nothing to clear, because the OS releases the lock. Threads in one process are serialized by an in-process lock. WAL lets readers run beside the writer, which the operator views of W7 will use.

A round of intake is one transaction. Its Triggers, the Source's cursor and the effects it queues commit together or not at all, so a restart neither drops a Trigger nor stores one twice.

A Trigger is stored once, by id. A Decision and a Receipt are stored once too: a repeat changes nothing. A Ticket and an Assignment are replaced by their id, so the store keeps their current facts.

`codec.py` writes the domain as JSON, with enums by value, sets sorted and keys sorted. It reads each value back from the dataclass annotations, so a new field needs no change in the codec.

### Effects

An effect is a kind, a key and a payload. Queuing an effect whose kind and key are already waiting replaces its payload, makes it due at once and keeps its place in the queue.

`run_due` runs the due effects of the kinds it has handlers for, oldest first, up to a limit. A failing effect waits 5, 10, 20 ... seconds before its next try, capped at 300. Nothing runs while the store is paused; intake keeps recording.

Effects run at least once. A handler that runs and is killed before its completion is stored runs again after the restart, so every handler must be idempotent. `run_due` deletes an effect only when its payload is unchanged, so a payload queued during its own run runs on the next call to `run_due`.

### Receipts

An outbound message is queued once, by id, as pending. It is then settled as sent or dropped, and a drop carries its reason.

### Restart

`test_v112_work_restart.py` kills a child process with `os._exit` at four points:

- inside a round, before its commit: nothing is stored, and the replay stores the round once;
- after a round's commit: the round is kept, and the replay adds nothing;
- inside an effect handler: the effect runs again;
- with the pause flag set: the flag survives, and nothing runs.

A child that opens a store another process holds is refused with `StoreInUse`, and a crashed writer releases the lock for the next process.

## 8. W3 behaviour

### The GitHub source

`work/sources/github.py` reads one repository, named `owner/name`, and never writes to GitHub. It asks `gh api` for that repository's notifications, with `all=true`, and after the first round with `since` set to the cursor. For each notification on an Issue or pull request, it reads that item's comments, and for a pull request also its review comments. Each new comment becomes a Trigger. Its thread is `github:owner/name#number`. A comment that @-mentions the agent's login is addressed (`MENTION`). A comment from a Bot account is not human. The agent's own comments are never Triggers.

Reads go through `gh api --paginate` with an argument list and no shell, so a repository name cannot become a command. The source takes its `gh` as a `GhCli`, and the tests replace it with a fake script. The live smoke test runs only when `ORGANISM_GH_SMOKE_REPO` is set.

### Cursor and failures

The cursor is the newest notification time read, and it is stored under `github:owner/name`, so one store can follow several repositories. A round sorts its notifications by time. If one item fails, its error is stored against that item in `source_errors`, and the cursor stops before its notification. The items after it are still stored, and they are read again next round, where intake de-duplicates them by id. When the item recovers, its error is cleared and the cursor advances. The round's Triggers, cursor and error records commit in one transaction. A failed notifications listing fails the whole round and stores nothing.

### Gate

`work:github_fake` runs `test_v112_work_github.py` against a fake `gh`. It makes no network calls.

## 9. W4 behaviour

### Rules

A Rule has an id, an instruction, `enabled`, an optional `pattern` and `auto`. The pattern is a regular expression of at most 200 characters, compiled when the Rule is made, and searched case-insensitively in a Trigger's text. A Rule with no pattern is never matched, because judging it needs a model, which is not adopted (W-D2). `auto` is graduation: a Rule starts work on its own only once it has passed the shadow gate below.

### Decision

`decide` returns one Decision per Trigger and Policy version. Its id is the Trigger id, then "@", then the version, so each Trigger is decided once per version. The first reason is always the gate's own. The outcome is decided in this order:

1. Not admitted by the gate: ignored.
2. Late, meaning received more than an hour earlier: ignored, with `deadline_passed`. This applies to explicit requests too.
3. Explicit: accepted.
4. Inferred, and the assessor failed: unavailable. Nothing is stored, so the next run tries again, until the Trigger is late.
5. Inferred, in auto mode, and a matched rule has graduated: accepted.
6. Inferred, and a matched rule has not graduated: ignored as a `would_accept`. This is the shadow evidence.
7. Inferred, and no rule matched: ignored, with `no_rule_matched`.

`evaluate` runs this over the store. It skips a Trigger that already has a Decision under the Policy version, so a repeated run decides nothing twice.

### Deadline

A new Policy version evaluates every stored Trigger again, so a graduation would otherwise start work on the old backlog. The deadline stops that. It is an hour from the time the store received the Trigger, read from the store's clock. It applies to explicit requests as well, so a request that waited too long is recorded as ignored.

### Graduation

`graduate` marks a Rule `auto` only when its shadow gate passes:

- the Rule has a pattern and an instruction, and is enabled;
- at least 20 of its would-accept Decisions under the current Policy version carry a verdict;
- at least 90% of those verdicts agree.

A verdict is a person's `Verdict` on one Decision, stored with `WorkStore.label`, and the latest verdict stands. Decisions made under an earlier Policy version are not evidence, so any change to the Policy starts the evidence again. `graduate` returns a new Policy. Nothing adopts it until the operator does (W7 and W9).

### Changes from W3

- `Rule` gained `pattern` and `auto`, so every Policy with a rule has a new digest. The digest of the empty Policy is unchanged. No Mandate is stored yet, so no recorded version is affected. Section 12 applies from the first Mandate on.
- `may_accept_inferred` requires a graduated rule. Before W4, auto mode accepted any enabled matched rule.
- The store is at schema 2. `triggers` records when each Trigger was received, `tickets` records its Thread, and `labels` is new. A schema 1 store is refused, as before.

## 10. Not yet built

- Several Threads per Trigger (Correlation). A Trigger has one Thread for now. Adding it needs its own tested rule.
- A model-judged rule and the LLM assessor: W-D2, not adopted. Eval judges one Trigger at a time, so it needs no batching. Batching comes with a model.
- Mandates from accepted Decisions, and the Executor: W5.
- Stop requests. `Outcome.STOP` is in the domain, but Eval does not produce it. A stop needs a Ticket to stop: W5.
- Operator labelling, and adopting a graduated Policy: W7 and W9.
- Mandate revalidation and Policy-change notices: W9.
- Subscriptions, follow-up ownership, hand-back and release: W8.
- Context-only follows, which do not admit anything: W8.

## 11. Gates

`work:domain` (fast tier) runs three files:

- `test_v112_work_stage.py`: the stage table, row by row, and the `waits_for_person` predicate.
- `test_v112_work_gate.py`: the admission cells, plus the invariants over every input combination.
- `test_v112_work_policy.py`: the version digest, the shape of admission rows, `may_accept_inferred`, a pinned digest of the empty Policy, and the purity check, which allows I/O only in `store.py`.
- `test_v112_work_store.py` (`work:store`, fast tier): intake, rounds and their transactions, Tickets, Assignments, Receipts, effects, the pause flag and the codec.
- `test_v112_work_restart.py` (`work:restart`, fast tier): a process killed mid-round and mid-effect, what the replay leaves behind, and a second writer refused while the store is held.
- `test_v112_work_admission.py` (`work:admission`, fast tier): the rule assessment, and the decision for one Trigger with no store, through each outcome and each reason.
- `test_v112_work_shadow_promote.py` (`work:shadow_promote`, fast tier): the shadow gate's thresholds, the current-version rule, and graduation.
- `test_v112_work_eval.py` (`work:eval`, fast tier): Eval over a real store. It covers once per version, the unavailable retry, the deadline, followups on open and ended Tickets, labels, and a graduated rule accepting new work but not the old backlog.

## 12. Changing this record

Changing the canonical form of the Policy digest changes the version of every Policy, and so the recorded version of every Mandate. Treat that as a breaking change to stored records. Make it only with a migration.
