# v1.12 work agent: open decisions

Each item below needs a choice from the user before the code can go further. For each one this
page gives the question, the options, a recommendation, and what stays blocked until the choice is
made. Nothing listed here is built, unless the item says so. The design record is
[WORK_AGENT.md](WORK_AGENT.md).

## 1. Stop phrases (Outcome.STOP)

**Question:** may a person end a Ticket with a message on its Thread, such as "stop"?

**Today:** the only end is `organism work stop TICKET`. The domain has `Outcome.STOP`, and Eval
never produces it. The principles say an executor cannot declare that a person asked it to stop,
and only Eval decides the strength of an end.

**Options**

- A. Keep the CLI as the only stop. No change.
- B. Read a fixed set of phrases (for example `stop` and `cancel`) in Eval, from a listed sender,
  on the Ticket's own Thread, and end the Ticket with strength `explicit`.
- C. Let a Rule's pattern produce STOP. Rules already match text, but this lets a Rule end work,
  so it would need the same shadow gate that accept uses.

**Recommendation:** A now. B later if wanted. B is small and safe when it is limited to the
Ticket's own Thread and a listed sender. C adds a path the shadow gate has not tested.

**Blocked until chosen:** which phrases count, and who may send them.

## 2. External writes (GitHub replies)

**Question:** when may the reply channel post to real GitHub threads?

**Today:** `reply_handlers` returns no handler unless `enabled=True`, and no command passes it.
Replies queue, and nothing is posted (section 11 of WORK_AGENT.md).

**Options**

- A. Keep it off until the user makes a separate, explicit change to enable it.
- B. A deployment-config flag per Source, default off, that the operator sets. Queued replies stay
  visible in `attention` until they post.
- C. A dry-run period that logs each would-be post for a set number of days, then enables the
  flag. It ties to the shadow gate.

**Recommendation:** C, then B. Nothing posts until the operator sets the flag after the dry-run
shows the replies are right.

**Blocked until chosen:** the go-ahead itself. The agent does not enable external writes.

## 3. Approver signing key

**Question:** how does the approver sign a Policy, and where does the private key live?

**Today:** the agent verifies only (W-D5). Signatures are Ed25519 through `organism_sdk.signing`,
which has `sign(seed, payload)` and `verify_any`. The trust file lists the approvers' public keys,
and the code generates no key.

**Options**

- A. The user signs offline, on their own machine, with a seed kept outside the repo. They use
  `signing.sign` or a short script they run themself, write the signature to a file, and pass it
  to `organism work adopt --signature FILE`.
- B. An `organism work sign` command that reads a seed file the user names. It works, but the
  agent's machine would then hold a signing path, which W-D5 rules out.
- C. A hardware key or an SSH agent that holds the seed. It is the strongest option and needs a
  different signer.

**Recommendation:** A. Ship a short procedure and a small offline script under `docs/`. The seed
never goes in the repo, the agent's environment or the jail. Tests already reject a Policy signed
by an author key.

**Blocked until chosen:** the signer, and generating the key pair on the user's machine. The agent
will not generate, store or read a private key.

## 4. Per-scope listening

**Question:** which rows and Sources does Eval listen to?

**Today:** `evaluate` treats every Trigger as listened and observed, in the row given by `--row`
(section 15 of WORK_AGENT.md).

**Options**

- A. A list of (source, row) pairs in the deployment config. Eval skips any Trigger outside it.
- B. A scope on each Mandate, decided when the Decision is accepted.

**Recommendation:** A. It is one file the operator reads, and it cannot widen a Mandate.

**Blocked until chosen:** the list of scopes to listen to.

## 5. Instruction text as versioned artifacts, and the "default updated" flag (W9)

**Question:** when a default instruction changes, should open Tickets that used the old text be
told, or should only new Tickets get the new text?

**Options**

- A. Store the text by hash. A Ticket keeps the hash it started with. A default change queues a
  `policy_notice` for each open Ticket that used the old text, as a Policy change does, and never
  cancels a Ticket.
- B. Store the text by hash. Only new Tickets use the new default, and nothing is notified.

**Recommendation:** A. It reuses the notice path built for Policy changes, and a running Ticket
never changes its text under it.

**Blocked until chosen:** the choice. The rest of W9 waits on it.

## 6. Related Threads (Correlation)

**Status:** built as context only. `Trigger.related_threads` stores a Trigger's related Threads.
Routing reads `Trigger.thread` alone, as section 3 of WORK_AGENT.md requires, and the tests in
`test_v112_work_followups.py` hold that. The GitHub source does not fill the field yet.

**Question:** what should a Ticket do with a Trigger's related Threads?

**Options**

- A. Nothing yet. They are stored and shown to no one.
- B. Add them to the executor's task text, so the run can see the linked Threads. The Mandate does
  not change, and the links add context only.
- C. Use them to hold a Trigger for a person. This routes, which section 3 rules out, so it needs
  that principle changed first.

**Recommendation:** A until a Source produces related Threads. Then B, which leaves routing as it
is. C reverses "Correlation adds context and never routes", so it needs the user's explicit
agreement first.

**Blocked until chosen:** whether the context reaches the executor (B), and whether Correlation
may ever route (C).

## 7. Hand-back, release and pull-request following (D7, D9)

**Status:** blocked on shadow data, not on a choice. Section 13 of WORK_AGENT.md says these wait for
it. The shadow gate exists, and no real run has produced the data yet.

**Decision needed later:** the shadow threshold that should open each of these. No action now.

## 8. Network enforcement for the executor

**Status:** chosen overnight by the manager, pending the user's confirmation. Built on Linux as
option A below. Revertible: set `enforce_network=False` in `SandboxPolicy.work_executor()`
(`sdk/python/organism_sdk/sandbox/policy.py`). The proxy and namespace code stay, so the revert is
one line.

**Question:** how does the work executor's network allowlist get enforced?

**Today:** enforced on Linux. The child runs in its own network namespace and reaches the allowlist
only through the bridge (`sandbox/egress_bridge.py`) and the proxy (`sandbox/egress.py`), as section
10 of WORK_AGENT.md describes. The executor refuses to run on any host that lacks Linux containment,
so it cannot run on Windows at all. Whether the CLI honours `HTTPS_PROXY` is not yet checked on a
live run.

**Options**

- A. An in-tree CONNECT proxy that allows only the named hosts, with the child in a network
  namespace that reaches the proxy through a Unix socket bridge. Linux only.
- B. nftables rules inside the namespace. This needs root on the host, so the executor would
  need a privileged step.
- C. Leave it unenforced, and say so in the profile. This is the state today.

**Recommendation:** A, as built. The proxy (`sandbox/egress.py`, any host) and the bridge
(`sandbox/egress_bridge.py`, Linux) are both in place, and the profile sets the namespace.

**Blocked until chosen:** whether an in-tree bridge is acceptable, or whether the user prefers a
separate tool for it. Until then, the one-line revert above stands.

## 9. Subscriptions and context-only follows (W8)

**Status:** deferred overnight by the manager (option A), pending the user's confirmation. Nothing
here is built: no Subscription, and no context-only follow.

**Question:** should a Subscription exist in v1, and should a message on a subscribed Thread add
context to a Ticket without admitting anything?

**Options**

- A. Defer both until a real Source needs them.
- B. Build context-only follows: a message on a subscribed Thread is added to an existing
  Ticket's context and never admits new work. A Subscription does not check admission; the Mandate
  does (section 3 of WORK_AGENT.md).

**Recommendation:** A. No current Source needs either, so building now would be speculative.

**Blocked until chosen:** whether any Source the user runs needs subscriptions in v1.
