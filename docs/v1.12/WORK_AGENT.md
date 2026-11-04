# Work Agent Layer: Design Record (v1.12)

**Status:** W0 accepted with the working defaults in section 1. W1 (pure domain) implemented. W2 onward not started.

**Covers:** [docs/SUPERAGENT_COMPARISON.md](../SUPERAGENT_COMPARISON.md), the comparison with dsh-superagent and the build-out plan this record follows.

**Code:** `sdk/python/organism_sdk/work/`. **Tests:** `sdk/python/tests/test_v112_work_*.py`. **Gate:** `work:domain` in [ci/gates.yaml](../../ci/gates.yaml).

## 1. Decisions

| ID | Decision | Status |
|---|---|---|
| W-D1 | The executor is an external coding-agent CLI, run in non-interactive mode inside the `ProcessJail`. | Decided 2026-11-04 |
| W-D1a | Which CLI. The executor reads an argv template from the deployment config, so no CLI is hard-coded. | Open. Blocks W5 |
| W-D2 | Whether a hosted LLM may classify proactive candidates. This extends D3. | Open. Blocks the LLM part of W4. W1 uses no model |
| W-D3 | First Source: GitHub. | Working default |
| W-D4 | No auto-merge in v1. | Working default |
| W-D5 | Policy signing keys (decision S1). | Open. Blocks W9 |
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
| Durable state | `snapshot.py`: SQLite WAL ops log with replay | W2 |
| Observe, then promote | `generative/stages.py` `PromoteGate` and `rollback_last_promote` | W4 |
| Signed Policy versions | `signing.py` `TrustStore` | W9 |
| Execution isolation | `sandbox/jail.py` `ProcessJail` and `sandbox/policy.py` `SandboxPolicy` | W5 |
| Health | `health.py` `HealthReport` | W2, W3 |
| Trace | `trace.py` `TraceEmitter` | W2 |

## 5. Module layout

| Module | Holds |
|---|---|
| `domain.py` | `Trigger`, `Thread`, `Mandate`, `Assignment`, `Ticket`, `Decision` and their enums. Plain values. |
| `stage.py` | The Ticket stage table from the superagent's execution document (003): `Stage`, `stage_of`, `waits_for_person`. |
| `gate.py` | `admit`, the deterministic first layer of Eval. Returns an `Admission`. |
| `policy.py` | `AcceptMode`, `Cell`, `AdmissionRow`, `Rule`, `SourcePolicy`, `Policy`, `policy_version`, `may_accept_inferred`. |

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

## 7. Not in W1

- The store, the effects queue and restart: W2.
- Several Threads per Trigger (Correlation). A Trigger has one Thread for now. Adding it needs its own tested rule.
- Eval batching, deadlines and `unavailable`: W4.
- Mandate revalidation and Policy-change notices: W4 and W9.
- Subscriptions, follow-up ownership, hand-back and release: W8.
- Context-only follows, which do not admit anything: W8.

## 8. Gates

`work:domain` (fast tier) runs three files:

- `test_v112_work_stage.py`: the stage table, row by row, and the `waits_for_person` predicate.
- `test_v112_work_gate.py`: the admission cells, plus the invariants over every input combination.
- `test_v112_work_policy.py`: the version digest, the shape of admission rows, `may_accept_inferred`, a pinned digest of the empty Policy, and the purity check.

## 9. Changing this record

Changing the canonical form of the Policy digest changes the version of every Policy, and so the recorded version of every Mandate. Treat that as a breaking change to stored records. Make it only with a migration.
