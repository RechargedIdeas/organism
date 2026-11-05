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
   updated in the same PR. The CI gate `conformance:all` is planned. Today only `conformance:kotlin` runs, and nothing
   checks that the checked-in vectors match a fresh run (`docs/AI_MODEL_GAPS.md`, I5).
3. **Wire formats are language neutral.** Messages use `proto/organism/v1` (gRPC) or the JSON forms in the vectors. Byte
   strings (hypervectors) are lower-case hex words, never language-native ints (64-bit safety).
4. **Floats.** Vectors carry IEEE-754 doubles; ports must use the same operation order as the reference (the degradation
   thresholds are written as `1.0 - ALPHA - delta`, not folded). Canonical byte output (plans, traces) will use the
   reference's shortest round-trip float text; each SDK ships a formatter proven against the vectors.
   The canonical JSON writer (gap C3) is done and uses no floats at all; see "Canonical JSON" below.
5. **Randomness is not portable.** Vectors never depend on an RNG stream. Generators write explicit inputs.
   **Comparison rules (contract area):** the vectors compare severity, code and field path, in order. Messages are for
   people and are not conformance. The generator writes text with the host's newline, so on Windows the files are CRLF
   and git stores them as LF. Compare normalised content.
6. **Time is injected.** Anything with hysteresis takes a virtual clock so vectors are deterministic.
7. **Safety invariants are tested in every language**: bio actuation refused, `may_actuate=False` for synthesised modules,
   shield parameters unreachable, promote ladder order, fail-closed defaults.
8. **No SDK may need a cloud or another app at runtime.** Optional bridges stay off by default.

## Areas and status

| Area | Vectors | Python | Kotlin | Rust |
|---|---|---|---|---|
| Hypervector (bind, permute, similarity, bundle) | `hypervector.json` | reference | **conformant** | partial (no bundle/permute vectors yet) |
| Degradation machine L0..L4 | `degradation.json` | reference | **conformant** (26 scenarios, all levels) | port exists, vectors pending |
| Contract + validation | `contract.json` (29 cases; K1b added the output forms TEXT, TOKEN_STREAM, TOOL_CALL and the justification kind HUMAN_CONFIRMATION) | reference | **conformant** (K1; field subset, see `Contract.kt`) | planned |
| Registry + lifecycle ladder | `lifecycle.json` (121 transitions, 11 mismatches, 8 queries) | reference | **conformant** (K1; registry is synchronized) | partial |
| Canonical JSON writer (C3) | `canonical.json` (35 cases) | reference (`canonical.py`) | **conformant** (`Canonical.kt`) | none |
| Ed25519 verification (A9) | `signature.json` (17 cases, RFC 8032 section 7.1 plus rejects) | reference (`signing.verify`, over OpenSSL) | **conformant** (`Ed25519.kt`, pure BigInteger, verify only) | none |
| Tool contract (A2) | `tool.json` (24 cases) | reference (`ToolContract`) | **conformant** | none |
| Model artifact manifest (A8) | `model_artifact.json` (22 cases) | reference (`model_artifact.py`) | **conformant** | none |
| Router + canonical `DispatchPlan` bytes | planned `router.json` | reference | planned (K2) | partial |
| Workspace + ops log + snapshots | planned `workspace.json` | reference | planned (K4) | partial |
| Hormone bus / autonomic / immune / circadian | planned | reference | planned (K3) | none |
| Trace entries | planned `trace.json` | reference | planned (K2) | none |
| Sandbox policy | planned `sandbox.json` | reference | planned (K5) | none |

## Canonical JSON

One writer rule, so signed or hashed JSON has the same bytes in every language (`organism_sdk/canonical.py`,
`org.organism.sdk.Canonical`, vectors `canonical.json`). Each vector case has the input as JSON text and either the
expected text with its UTF-8 bytes in hex, or an error code.

- Object keys are sorted by Unicode code point, which is the order of their UTF-8 bytes. UTF-16 order is not the same
  above U+FFFF, so a port must not use its native string compare.
- No whitespace outside strings. Output is UTF-8. Non-ASCII characters are written as themselves.
- Strings escape `"` and `\`, use `\b \f \n \r \t` for those five, and `\u00xx` (lower-case hex) for every other character
  below U+0020. `/`, U+007F and all higher characters are written as they are. A lone surrogate is rejected.
- Numbers are integers only, in base 10, in the range -(2^53 - 1) to 2^53 - 1 (`-0` is `0`). Every float is rejected,
  including `1.0`, so no float text has to be agreed. A tool schema that needs a fractional bound writes it as a string.
- Error codes, in the order a writer meets them: `non_string_key`, `unsupported_type`, `float_not_allowed`,
  `non_finite_number` (NaN and the infinities), `integer_out_of_range`, `invalid_string`.
- The Kotlin `Json.parseExact` reads integer literals as `Long` (or `BigInteger`) and accepts `NaN`/`Infinity`, as
  Python's `json.loads` does, so the writer can reject them by code. The plain `Json.parse` is unchanged.

## Ed25519 verification

`Ed25519.verify(publicKey, signature, message)` follows RFC 8032 section 5.1.7: 32-byte key, 64-byte signature, the key and
R must decode to curve points (y below 2^255 - 19), S must be below the group order (S + L is rejected), and the check is
cofactorless. A wrong length or a bad point is `false`, never an exception. The Kotlin version is pure `BigInteger` because
`java.security` has Ed25519 only from JDK 15 and the SDK targets JVM 11. It verifies only; signing stays in Python.

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
# publish the Kotlin SDK to the private repository (default: sdk/kotlin/build/private-repo)
cd sdk/kotlin && ./gradlew publish
```
