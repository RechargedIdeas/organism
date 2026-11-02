# Organism interoperability: one behaviour, many languages

Python (`sdk/python/organism_sdk`) is the **reference implementation**. Every other SDK (Kotlin first, Rust, later
TypeScript and others) is a port that must behave identically. Identity is enforced by data, not by promise:

```
reference (Python) ──generate──▶ conformance/vectors/*.json ◀──replay── Kotlin / Rust / future SDKs
```

## Rules

1. **Vectors are the contract.** `conformance/generate.py` runs the reference and writes `conformance/vectors/<area>.json`
   (compact, sorted keys, `schema` field). Vectors are checked in. A port is conformant for an area when it replays every
   case and gets the same output.
2. **A vector change is an API change.** Regenerate only with a reviewed reference change; every SDK's tests must be
   updated in the same PR (CI gate `conformance:all`).
3. **Wire formats are language neutral.** Messages use `proto/organism/v1` (gRPC) or the JSON forms in the vectors. Byte
   strings (hypervectors) are lower-case hex words, never language-native ints (64-bit safety).
4. **Floats.** Vectors carry IEEE-754 doubles; ports must use the same operation order as the reference (the degradation
   thresholds are written as `1.0 - ALPHA - delta`, not folded). Canonical byte output (plans, traces) will use the
   reference's shortest round-trip float text; each SDK ships a formatter proven against the vectors.
5. **Randomness is not portable.** Vectors never depend on an RNG stream. Generators write explicit inputs.
6. **Time is injected.** Anything with hysteresis takes a virtual clock so vectors are deterministic.
7. **Safety invariants are tested in every language**: bio actuation refused, `may_actuate=False` for synthesised modules,
   shield parameters unreachable, promote ladder order, fail-closed defaults.
8. **No SDK may need a cloud or another app at runtime.** Optional bridges stay off by default.

## Areas and status

| Area | Vectors | Python | Kotlin | Rust |
|---|---|---|---|---|
| Hypervector (bind, permute, similarity, bundle) | `hypervector.json` | reference | **conformant** | partial (no bundle/permute vectors yet) |
| Degradation machine L0..L4 | `degradation.json` | reference | **conformant** (26 scenarios, all levels) | port exists, vectors pending |
| Contract + validation | planned `contract.json` | reference | planned (K1) | planned |
| Registry + lifecycle ladder | planned `lifecycle.json` | reference | planned (K1) | partial |
| Router + canonical `DispatchPlan` bytes | planned `router.json` | reference | planned (K2) | partial |
| Workspace + ops log + snapshots | planned `workspace.json` | reference | planned (K4) | partial |
| Hormone bus / autonomic / immune / circadian | planned | reference | planned (K3) | none |
| Trace entries | planned `trace.json` | reference | planned (K2) | none |
| Sandbox policy | planned `sandbox.json` | reference | planned (K5) | none |

## Adding a language

1. Create `sdk/<lang>/` with its own build, tests reading `conformance/vectors`.
2. Make the areas above pass in the order listed. Keep the SDK dependency free where the target allows it.
3. Add a row/column here, a CI gate, and a `docs/<lang>.md` note on platform limits (for example Android API level).
4. Cross-language runtime interop (processes in different languages in one organism) uses gRPC `organism.v1`; the
   language-neutral JSON op log (`store`, planned) is the storage interop format.

## Running

```bash
# regenerate (reference change only)
PYTHONPATH=sdk/python:modules python conformance/generate.py
# Kotlin
cd sdk/kotlin && ./gradlew test
```
