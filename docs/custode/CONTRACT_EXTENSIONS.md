# Contract extensions for Custode

This document is the exact proposal for additive changes to `organism.v1` and to the Python SDK. It matches the
corrected numbering in the Custode repository (`docs/organism/PROTO-CHANGES.md`). Nothing here is applied yet. Applying
it requires decision O-11.

**Rules applied** (from `docs/API_FREEZE_v1.0.md` and `docs/API_FREEZE_v0.4.md`): field numbers and existing enum values
are immutable. New fields and values are additive, numbered after the current maximum. No name is renamed or removed.

Every existing number below was read from the proto files in this repository. Every proposed number is marked as
proposed.

---

## 1. Proto changes

### 1.1 `router.proto`: `TaskForm`

`TaskForm` (line 30) has values 0 to 13. Add one value:

```protobuf
enum TaskForm {
  // existing values 0 to 13, unchanged
  TASK_FORM_PERCEPTION = 14;   // a screen observation to a structured observation (browser source)
}
```

The first draft also proposed `TASK_FORM_AUDIO = 15`. It is dropped: no part of the browser design uses audio.

### 1.2 `contract.proto`: `OutputForm`

`OutputForm` (line 92) has values 0 to 9, where 9 is `OUTPUT_JUSTIFICATION_TOKEN`. Add two values:

```protobuf
enum OutputForm {
  // existing values 0 to 9, unchanged
  OUTPUT_OBSERVATION = 10;     // structured observation record
  OUTPUT_TOOL_CALL   = 11;     // a named tool call with its arguments
}
```

### 1.3 `contract.proto`: `MetabolicProfile` (conditional)

`MetabolicProfile` (line 123) has fields 1 to 12. Field 13 is unused. The proposed field is:

```protobuf
message MetabolicProfile {
  // existing fields 1 to 12, unchanged
  uint64 vram_budget_bytes = 13;   // peak device memory the module may use, in bytes; 0 means not declared
}
```

**This field overlaps an existing one.** `memory_footprint_mb` (field 5) and `memory_peak_mb` (field 6) already state
memory in megabytes. The proposed field states device memory in bytes, for an exact budget. O-11 must decide whether
megabyte precision is enough. If it is, drop this field and leave 13 unused.

### 1.4 `common.proto`: `FlowLabel` (new message)

A new message. Put it in `common.proto`, the shared types file, unless the O-11 review finds a reason for a separate
`flow.proto`:

```protobuf
message FlowLabel {
  enum Integrity {
    INTEGRITY_UNSPECIFIED = 0;
    INTEGRITY_TRUSTED     = 1;
    INTEGRITY_UNTRUSTED   = 2;
  }
  enum Confidentiality {
    CONFIDENTIALITY_UNSPECIFIED = 0;
    CONFIDENTIALITY_PUBLIC      = 1;
    CONFIDENTIALITY_PRIVATE     = 2;
    CONFIDENTIALITY_SECRET      = 3;
  }
  Integrity       integrity       = 1;
  Confidentiality confidentiality = 2;
}
```

Integrity is the least trusted of the inputs, so a value derived from untrusted content stays untrusted. This is the
proposed rule. Custode's `extension/src/policy/flow.ts` implements label combination and taint for the browser side.

**Check for overlap first.** `CapabilityScopes` (`contract.proto`, line 285) already names access by tag, with
`read_tags` (field 3) and `write_tags` (field 4). `FlowLabel` names provenance. If one mechanism can serve both, use
one. Two mechanisms for the same purpose would be a design error.

### 1.5 `contract.proto`: `Channel`

`Channel` (line 299) has fields 1 to 7. Add one field, which carries the label on the payload:

```protobuf
message Channel {
  // existing fields 1 to 7, unchanged
  FlowLabel flow_label = 8;
}
```

### 1.6 `trace.proto`: `Trigger`

`Trigger` (line 100) has fields 1 to 3. Add one field, so a browser observation that starts work carries its label:

```protobuf
message Trigger {
  // existing fields 1 to 3, unchanged
  FlowLabel flow_label = 4;
}
```

---

## 2. Python SDK changes

These are not proto changes. They are the right place for them while the proto surface stays small.

| File | Change |
|---|---|
| `sdk/python/organism_sdk/generative/artifacts.py`, line 20 | `ArtifactKind` gains the literal `"adapter"`. It is `Literal["code", "asset", "skill", "manifest", "pack"]` today. |
| `sdk/python/organism_sdk/moa/experts.py`, line 77 | `CapabilityDescriptor` gains `vram_budget_bytes: int = 0`. Only if 1.3 is kept. |
| `sdk/python/organism_sdk/generative/` (new module, name to be chosen) | An `AdapterMeta` dataclass for a learned adapter: base model ID, adapter kind, rank, training events hash, parent hash, and a reference to a `CalibrationCertificate` (`proto/organism/v1/calibration.proto`, line 34). The name is new. |
| `sdk/python/organism_sdk/work/` | A `FeedbackEvent` domain type. The name is new. A proto message is a later decision, made only if another language needs it. |

Regenerating the bindings: `proto:lint` regenerates `sdk/python/organism_sdk/_proto` from `proto/` when it is stale. The
regenerated files are part of the same change as the proto edit.

---

## 3. Names that are not used

These names appeared in the first draft. They do not exist in the repository, and this document does not use them:

- `TASK_FORM_TEXT`, `TASK_FORM_SYMBOLIC`, `TASK_FORM_TEMPORAL`, `TASK_FORM_SPECTRAL`, `TASK_FORM_AUDIO`
- `OUTPUT_FORM_OBSERVATION`, `OUTPUT_FORM_TOOL_CALL`
- `ModuleRequest`, `ModuleResponse` (labels go on `Channel` and `Trigger` instead)
- `CalibrationReport` (use `CalibrationCertificate`)
- `CapabilityDescriptor` as a proto message (it is a Python dataclass)
- `VisionModule`, `PlannerModule`, `VerifierModule`, `RouterExpert`

---

## 4. Compatibility

- An existing module that sets none of the new fields behaves as before. A `Channel` or `Trigger` without a label is read
  as unlabeled. The proposed rule is that a consumer which enforces labels treats an unlabeled input as untrusted.
- Tier selection (`sdk/python/organism_sdk/moa/tiers.py`) chooses tiers from expert health, the latency budget, and GPU
  availability, as its module docstring says. It does not read a memory budget today.
- Phase 6 of the upgrade plan proposes an optional input to tier selection from `vram_budget_bytes`. How a declared
  budget changes a tier is not designed. It needs a change to `docs/v1.11/MOA_LAYER.md` first.

---

## 5. Test plan

| Test | How it runs | What it checks |
|---|---|---|
| Proto compiles and lints | gate `proto:lint` | New fields and values are valid, and bindings regenerate |
| Contract validation | gate `contract:validate` (`tests/contract`) | Existing contract tests still pass |
| Registry API | gate `registry:api` | Registry accepts modules with the new fields |
| API freeze | run directly: `pytest sdk/python/tests/test_api_freeze.py` | No frozen symbol is removed or renamed |
| Round trip | new test, in `tests/contract/` | A `Channel` with a `FlowLabel` survives encode and decode unchanged |
| Default enum behavior | new test | An unset `OUTPUT_*` or `TASK_FORM_*` value behaves as before |

The round-trip and default-value tests are new work for Phase 1. They do not exist yet.
