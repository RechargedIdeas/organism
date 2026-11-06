# Browser runtime as an Organism Source

This document describes how a browser agent would fit into Organism: the Source, the trigger it emits, the tiers its
experts use, and the resource model. It does not describe the browser's internal design, which is in the Custode
repository.

**Status:** Proposed.

---

## 1. Where the browser sits

Organism would see the browser as one **Source**: a producer of observations that can start work. The browser does not
run inside Organism's Python process. It is a separate process, and it talks to Organism only through the bridge (see
[BRIDGE_CHANNEL.md](BRIDGE_CHANNEL.md)).

```
Browser extension (TypeScript; GPU experts in an offscreen document)
  observation -> trigger with FlowLabel  ->  Organism Source -> Trigger -> ...
  page action <- coordinator decision (inside the extension, never from Organism)
```

Each side keeps its own policy. The extension's coordinator decides every action on the page. Organism's MoA layer
decides tiers for work done on Organism's side. This package does not give Organism control of browser actions.

---

## 2. What the Source emits

Each observation the user shares becomes a `Trigger` (`proto/organism/v1/trace.proto`, line 100, fields 1 to 3, with
`flow_label` at 4 under the proposal). The trigger carries:

- the observation kind, as `TASK_FORM_PERCEPTION` (value 14, under the proposal)
- the page's **hostname only**. The path and the query string are not sent, because they can carry personal data.
- a `FlowLabel` with `INTEGRITY_UNTRUSTED`, because the observation came from page content
- the structured observation (see Custode `docs/03-perception.md`)

A trigger cannot start a write on the page. Writes are decided and confirmed inside the extension, under the origin
and taint rules in [GOVERNANCE.md](GOVERNANCE.md).

---

## 3. Tiers

The browser adds no tier. Its experts use the tiers defined in `docs/v1.11/MOA_LAYER.md`, section 6: T0 full, T1
reduced, T2 single, T3 CPU, and T4 deterministic. Tiers are chosen per request, from expert health, the latency budget,
and GPU availability (`sdk/python/organism_sdk/moa/tiers.py`).

Three rules from the tier design matter for a browser Source:

- An expert that needs a GPU (`requires_gpu`, field 8) is skipped under T3 when no GPU is available, and the rest run on
  CPU.
- The global `DegradationMachine` level does not map onto the tiers one for one. The level enters as an input, and L4
  forces T4. The rule is written in `docs/v1.11/MOA_LAYER.md` as "Tiers are not the `DegradationMachine`".
- T4 is the deterministic fallback. No model runs, and the result is not a model's output.

---

## 4. Resource model

- **GPU.** `MetabolicProfile.requires_gpu` (field 8) states whether a module needs a GPU. The browser's experts that need
  a GPU declare it.
- **Memory.** Organism's proto states memory in megabytes (`memory_footprint_mb`, field 5; `memory_peak_mb`, field 6).
  The browser enforces its own device-memory budget inside the extension (Custode `ARCHITECTURE.md`, section 5.3). Whether
  Organism needs the same figure in bytes is the open question in [CONTRACT_EXTENSIONS.md](CONTRACT_EXTENSIONS.md),
  section 1.3.
- **Model residency and eviction** are described in Custode `docs/05-model-cache.md`.
- **Weights** are kept in the browser's origin-private file system, as Custode's design sets out. Persistence is
  Specified, not yet built (Custode `ARCHITECTURE.md`, section 5.4). Model weights are not Organism artifacts. Only
  adapters would be (see [LEARNING_AND_EVAL.md](LEARNING_AND_EVAL.md)).

---

## 5. Failure behavior

All rows are proposed. The browser side is the authority for what it does on its own.

| Failure | Behavior |
|---|---|
| The bridge is not connected | The browser works alone. Triggers are not queued for later delivery, so none arrive late. |
| No GPU is available | The Source reports no GPU, and tier selection moves to T3 or T4 under [section 3](#3-tiers). |
| A trigger is malformed | Organism rejects it at the Channel boundary and logs the rejection without the payload. |
| A model file fails its hash check | The browser refuses the file, and the expert is not activated (Custode `ARCHITECTURE.md`, model cache section). |

---

## 6. Open items

- The Source's name and identity fields. Proposed: one Source per browser profile, with a random ID, not the user's name.
- Whether the Source's triggers belong on the work agent's flow at all. The work agent is designed for repository work
  (`docs/v1.12/WORK_AGENT.md`), and its executor is the Claude Code CLI. Custode's CD4 decision says browser actions do
  not use that path, and only the Source and Policy concepts are reused. Until that is settled, the browser Source emits
  triggers to a named consumer and does not enter the Ticket path.
