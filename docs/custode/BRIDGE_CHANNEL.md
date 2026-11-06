# The browser bridge as an Organism Channel

This document describes the loopback bridge between the browser extension and Organism's desktop side, and how it maps
onto Organism's `Channel` message. The open question is whether that mapping holds (O-12).

**Status:** Proposed. The bridge is built in the Custode repository (`bridge/`, 45 tests). No Organism code exists for it.

---

## 1. The bridge as built in Custode

- Loopback only: `127.0.0.1`. A bind to any other address is refused.
- JSON-RPC 2.0 over WebSocket, with a 256 KiB message limit and compression turned off.
- Handshake: the upgrade request must have a `Host` of `127.0.0.1:<port>` or `localhost:<port>`, and an `Origin` of
  exactly `chrome-extension://<extension id>`. Anything else gets HTTP 403 before any frame is read.
- First message: `hello`, with a pairing code, a per-start token, and the extension ID. The token and the code are
  compared in constant time. Five failures lock the gate for 60 seconds.
- First valid pairing waits for the user to approve it. The approval is in the desktop UI (not yet built; the terminal
  prompt stands in for it).
- Default deny. Only `ping` and `capabilities.list` run without a grant. Each other method needs a grant the user made.
- Rate limit of 20 messages per second, burst 40, on every message.
- Audit log: a hash chain that records method names and refusal reasons, never parameters or tokens.

The full specification is `docs/09-desktop-bridge.md` in the Custode repository. That file is not part of this
repository.

---

## 2. Mapping to `Channel`

`Channel` (`proto/organism/v1/contract.proto`, line 299) has these fields:

| Field | Type | Fit for the bridge |
|---|---|---|
| `channel_id` (1) | `string` | Good: one ID per paired browser profile |
| `producer_module` (2) | `string` | The browser Source |
| `consumer_modules` (3) | `repeated string` | The desktop consumers the user granted |
| `payload_modality` (4) | `Modality` | `MODALITY_TEXT` (9). Structured controls have no modality of their own. |
| `payload_shape` (5) | `Shape` | Partial fit. Observations are records, not tensors. |
| `delivery` (6) | `Delivery` | `DELIVERY_AT_MOST_ONCE` (1). A browser message is not replayed. |
| `logged_for_trace` (7) | `bool` | Yes, with method names only |
| `flow_label` (8, proposed) | `FlowLabel` | Needed for provenance. See the overlap check in [CONTRACT_EXTENSIONS.md](CONTRACT_EXTENSIONS.md), section 1.4. |

The bridge has no concept of a handshake or of pairing. `Channel` describes a route between modules, and it says nothing
about how the endpoints authenticate. That gap is the question below.

---

## 3. Options for O-12

**Option A: use `Channel` as it is.** The handshake and pairing stay in the bridge, outside Organism's proto. The
`Channel` describes the route once the connection is authenticated. This needs no new message, and it keeps the proto
small. The risk is that the auth step lives outside the contract, so a reader of the contract cannot see it.

**Option B: add a `ChannelEndpoint` message** with an authentication method, an endpoint kind (loopback socket), and a
pairing record. This makes the contract complete, and it costs a new message in the frozen proto surface. The message
is new; no name for it exists yet.

**Option C: keep the bridge out of the proto entirely**, as a Python transport under Organism Desktop, with its own
interface. This is the smallest change, and it gives up the contract's type checks for the link.

The proposal is Option A now, and a move to Option B only if a second transport needs the same contract. This is a
judgment, and it is recorded as O-12 for the maintainers to decide.

---

## 4. Controls that do not depend on the option

Whichever option is chosen, any loopback channel from a browser to Organism must have these controls (decision CD6 in
the upgrade plan):

1. Host check, to block DNS rebinding.
2. Origin check against the extension's ID.
3. A per-start token, compared in constant time, and never written to a plaintext file.
4. Explicit user approval of the first pairing.
5. Rate limiting and a size limit on every message.
6. Default-deny capability grants.
7. An audit log that records method names and never parameters.

Items 1 and 2 answer a known browser risk: a web page can reach a service on localhost, because the same-origin policy
does not block WebSocket connections to localhost. Custode's security notes cover this in
`docs/08-security-and-privacy.md`.

---

## 5. Out of scope

- TLS. The loopback channel is plaintext. A pinned certificate is possible, and it is not decided.
- Organism Desktop's UI for pairing. The pairing window is part of the desktop work and is not designed here.
