# Governance for a browser Source

This document sets out which rules govern a browser agent, where each rule is enforced, and how Organism's governance
mechanisms would relate to them. The browser's own rules are built in the Custode repository. The Organism side is a
proposal.

**Status:** Proposed.

---

## 1. Two layers

- **The browser layer (Custode, built).** Origin classes, the tool prefilter, taint detection, endorsement, and a
  hash-chained audit log. This layer alone can act on a page.
- **The Organism layer (proposed mapping).** Labels on `Channel` and `Trigger`, signed Policy, the MoA guardrails, and
  the sandbox for any code.

Organism can refuse to forward a label, or to use an input it cannot trust. It cannot approve a page action. A page
write needs the user's confirmation inside the extension, whatever Organism decides.

---

## 2. Browser rules (Custode, built)

| Rule | Where it is set |
|---|---|
| The origin class of a site decides what the agent may do there. Unknown and financial origins are read-only. | `docs/08-security-and-privacy.md`, origin section |
| The router's tool list is filtered by origin and member permission. Forbidden tools are absent from the list the router sees. | `docs/08-security-and-privacy.md`, threat table; `ARCHITECTURE.md`, section 1 |
| Writes always need confirmation. | Custode `docs/14-decisions.md`, D-10 |
| A tool argument is tainted when its value appears in untrusted page text. A tainted write needs endorsement of each named field. | `ARCHITECTURE.md`, section 4.3; `docs/08-security-and-privacy.md`, endorsement rule |
| An identifier shown on the page is tainted when a write copies it. | `docs/08-security-and-privacy.md`, endorsement rule |
| Every API call, tool decision, confirmation, endorsement, and verdict is recorded in a hash-chained audit log. The log holds method names and primitive fields only. | `docs/08-security-and-privacy.md`; the bridge's `audit.py` |

---

## 3. Organism mechanisms this maps onto

- **FlowLabel** (proposed; [CONTRACT_EXTENSIONS.md](CONTRACT_EXTENSIONS.md), section 1.4). Browser observations carry
  `INTEGRITY_UNTRUSTED`. Labels combine by taking the least trusted input. This is the proposed rule.
- **Signed Policy.** Organism's work agent accepts a Policy only when an approver signs it. That is covered by the gates
  `work:policy_version` and `work:approver_signing` (`ci/gates.yaml`, and `docs/v1.12/WORK_AGENT.md`). Signatures are
  Ed25519, through `TrustStore` in `sdk/python/organism_sdk/signing.py`. If browser rules are shared with Organism, they
  would be a Policy under that approval. This is proposed, not decided.
- **CapabilityScopes.** `CapabilityScopes` (`contract.proto`, line 285) limits reads and writes by role and tag, and
  it has `can_emit_control_affecting` (field 5). A browser module should not declare control-affecting output. This is
  proposed.
- **MoA guardrails.** The gate `v111:moa_guardrails` runs in the fast tier. The red-team suite `v111:moa_redteam` is
  non-blocking today: it reports guardrail misses without failing the run (`ci/gates.yaml`).
- **Sandbox.** Code that Organism runs is confined by `ProcessJail` (`sdk/python/organism_sdk/sandbox/jail.py`). The
  browser design sends no code to Organism, so the jail is not used by the browser path.

---

## 4. What Organism does not take on

- Organism does not click, type, or submit on a page.
- Organism receives hostnames and structured observations, not paths or query strings
  ([BROWSER_RUNTIME.md](BROWSER_RUNTIME.md), section 2).
- The MLS compliance rules are the Custode domain pack's content, not Organism's. If they are adopted, they would be a
  Policy like any other. See `docs/organism/ADR-001-custode-integration.md` in the Custode repository.

---

## 5. Open items

- Whether browser rules are a Policy in `organism_sdk.work` or a separate type. Not decided.
- Whether `FlowLabel` and `CapabilityScopes.read_tags` and `write_tags` can be one mechanism. Check before adding the
  label (CONTRACT_EXTENSIONS.md, section 1.4).
- Who approves a browser Policy version. Not decided.
