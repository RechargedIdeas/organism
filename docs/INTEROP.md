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
   thresholds are written as `1.0 - ALPHA - delta`, not folded). Canonical byte output (plans, traces, promotion
   payloads, shadow digests) uses the canonical JSON writer, which has no float text at all (gap C3; see "Canonical JSON"
   below). Sums over floats use explicit loops in the same order in each SDK, because Python's `sum()` is compensated and
   Kotlin's is not.
5. **Randomness is not portable.** Vectors never depend on an RNG stream. Generators write explicit inputs.
   **Comparison rules (contract area):** the vectors compare severity, code and field path, in order. Messages are for
   people and are not conformance. The generator writes LF on every host (K2). A working copy written before that can
   differ only in CRLF; compare with `git diff --ignore-cr-at-eol`.
6. **Time is injected.** Anything with hysteresis takes a virtual clock so vectors are deterministic.
7. **Safety invariants are tested in every language**: bio actuation refused, `may_actuate=False` for synthesised modules,
   shield parameters unreachable, promote ladder order, fail-closed defaults.
8. **No SDK may need a cloud or another app at runtime.** Optional bridges stay off by default.

## Areas and status

| Area | Vectors | Python | Kotlin | Rust |
|---|---|---|---|---|
| Hypervector (bind, permute, similarity, bundle) | `hypervector.json` | reference | **conformant** | partial (no bundle/permute vectors yet) |
| Degradation machine L0..L4 | `degradation.json` | reference | **conformant** (26 scenarios, all levels) | port exists, vectors pending |
| Contract + validation | `contract.json` (33 cases; K1b added the output forms TEXT, TOKEN_STREAM, TOOL_CALL and the justification kind HUMAN_CONFIRMATION; task 7 added the GPU and NPU classes and `gpu_flag_mismatch`) | reference | **conformant** (K1; field subset, see `Contract.kt`) | planned |
| Registry + lifecycle ladder | `lifecycle.json` (121 transitions, 11 mismatches, 8 queries) | reference | **conformant** (K1; registry is synchronized) | partial |
| Canonical JSON writer (C3) | `canonical.json` (35 cases) | reference (`canonical.py`) | **conformant** (`Canonical.kt`) | none |
| Ed25519 verification (A9) | `signature.json` (17 cases, RFC 8032 section 7.1 plus rejects) | reference (`signing.verify`, over OpenSSL) | **conformant** (`Ed25519.kt`, pure BigInteger, verify only) | none |
| Tool contract (A2) | `tool.json` (24 cases) | reference (`ToolContract`) | **conformant** | none |
| Model artifact manifest (A8) | `model_artifact.json` (22 cases) | reference (`model_artifact.py`) | **conformant** | none |
| Shadow evidence, promotion gate, approver payload (K6) | `shadow.json` (5 cases); `lifecycle.json` evidence cases (12), threshold and gated states | reference (`shadow_runner.py`, `registry.py`, `signing.py`) | **conformant** (`Shadow.kt`, `Signing.kt`, `Registry.kt`) | none |
| Router: eligibility mask, `DispatchPlan` bytes, policy digest | `router.json` (8 eligibility, 8 exclusion codes, 2 plans, 4 policy, 2 traces) | reference (`router.py`) | **conformant** (K2, `Routing.kt`) | partial |
| Workspace + ops log + snapshots | planned `workspace.json` | reference | planned (K4) | partial |
| Hormone bus / autonomic / immune / circadian | planned | reference | planned (K3) | none |
| Routing trace entries | in `router.json` (2 cases) | reference | **conformant** (K2, `Routing.kt`) | none |
| Health and drain (B6, K1b task 7) | `health.json` (8 cases) | reference (`health.py`, `registry.py`) | **conformant** (`Health.kt`, `Registry.kt`) | none |
| Calibration and measured-metabolics gates (A5, A6, K1b task 7) | `evidence.json` (8 calibration, 7 metabolic, 9 promote cases) | reference (`evidence.py`, `registry.py`) | **conformant** (`Evidence.kt`, `Registry.kt`); GPU and NPU device runs not done | none |
| Sandbox policy | planned `sandbox.json` | reference | planned (K5) | none |

**Not verified on hardware.** The GPU and NPU classes (A7) are declared and checked as data. No GPU or NPU device was
available, so no vector came from one. The measured values in `evidence.json` are synthetic, with device class `CPU`.

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
- The routing plan and trace bytes (K2), the shadow evidence digest and the promotion payload (K6) are all written by this
  writer.

## Ed25519 verification

`Ed25519.verify(publicKey, signature, message)` follows RFC 8032 section 5.1.7: 32-byte key, 64-byte signature, the key and
R must decode to curve points (y below 2^255 - 19), S must be below the group order (S + L is rejected), and the check is
cofactorless. A wrong length or a bad point is `false`, never an exception. The Kotlin version is pure `BigInteger` because
`java.security` has Ed25519 only from JDK 15 and the SDK targets JVM 11. It verifies only; signing stays in Python.

## Promotion payload and shadow digest (K6)

An approver signs the domain line `organism.registry.promote.v1` and a newline, followed by the canonical JSON of
`{module_id, from_state, to_state, shadow}`. Each shadow record becomes `{invocations, incumbent_error_ppm,
candidate_error_ppm, p95_latency_us, gates_passed, evidence_digest}`. Errors are scaled to integer parts per million and
latency to integer microseconds, rounded half to even: Python's `round` and Kotlin's `Math.rint` agree on that rule. Any
change to the evidence changes the bytes, so an approval cannot be reused with other evidence. Approver signatures made
over the earlier payload no longer verify.

The shadow evidence digest is the SHA-256 of the canonical JSON `{"version": 1, "rows": [...]}`. Each row is `[incumbent
loss, candidate loss, candidate failed (0 or 1), candidate latency in microseconds]`. Losses are integers from 0 to 1000.

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
