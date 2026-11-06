# v1.11 — Organism changes from CryptoMiner substrate review (OC-1 … OC-13)

Source: CryptoMiner `docs/ORGANISM_CHANGES_PROPOSED.md` (proposals only on the
CryptoMiner side). Implemented in Organism **v1.11.0**.

| ID | Fix |
|---|---|
| **OC-1** | `DEPRECATED` / `RETIRED` are non-routable under live `min_lifecycle_state` filters. Router `DELIBERATION` queries no longer return demoted modules. |
| **OC-2** | `LifecycleOperation.ROLLBACK` (proto + Python). `LifecycleTraceEntry.rollback_of_entry_id` / `reason`. `RegistryClient.rollback()`. LCT-12 checks the link. |
| **OC-3** | `SafetyDeclaration.l4_terminal` (validated: T0 + GOVERNANCE + DETERMINISTIC + RULE_TRACE). L4 eligibility uses the flag; `deterministic_engine` stays eligible for BC. |
| **OC-4** | `HealthSignals.neural_modules` / `leading_predictive` default to `()`. Callers must name their own modules. |
| **OC-5** | `SandboxPolicy.isolate_network` (default on when `allow_network=False`) plans `CLONE_NEWNET` without `ORGANISM_JAIL_FULL_NS`. `require_network_isolation` fail-closes. Capabilities report `network_namespace`; degraded always says `isolation_not_claimed` when net was not applied. |
| **OC-6** | `DegradationThresholds` on `DegradationMachine` (thermal, GC, queue, byzantine, α/δ). |
| **OC-7** | `RouterPolicyArtifact.ranking`: `trust_first` (default) \| `learned_first_with_t0_fallback` \| `metabolic`. Included in the policy digest. |
| **OC-8** | Public `organism_sdk.contract_factory`. Wheel ships `organism_modules` + reference substrates (`reservoir`, `hdc_module`, `kernel_module`, `energy_hopfield`, `spectral`, `snn_sentinel`, `neurosymbolic`) and `_common`. |
| **OC-9** | `Router.set_health()` and `RegistryClient.state(module_id)`. |
| **OC-10** | Policy fields `cpu_quota`, `cpu_affinity`, `nice`, `seccomp_profile` — applied when available, otherwise named in `JailResult.degraded`. |
| **OC-11** | `SandboxPolicy.devices: tuple[str, …] = ()` (interface; empty = CPU only). Binding is not yet implemented; runs report `devices_not_bound`. |
| **OC-12** | R-36 / R-39 already resolved. LCT-3 warning-tolerant + LCT-12 in `organism_sdk.lifecycle_trace`. R-40/R-41-class tensions left open. |
| **OC-13** | `V02TraceSink(maxlen=…)`. `TraceEmitter` default-attaches a bounded sink; missing sink is a no-op with diagnosis instead of `NotImplementedError`. |

## Behaviour changes (callers)

- **HealthSignals**: if you relied on the implicit `learned_module_t2` neural list, pass it explicitly.
- **Sandbox**: deny-network jails now *attempt* a net namespace by default. Read `namespaces_used` / `degraded` / `capabilities()` — never assume isolation.
- **Policy digest**: bootstrap digest bytes change (ranking field). Regenerate / refresh any stored digests.
- **Registry query**: demoted modules disappear from `min_lifecycle_state="DELIBERATION"` results.

## CryptoMiner workarounds now removable

Once CryptoMiner is on Organism ≥ 1.11.0:

- OC-1: stop deregister/re-register as `PROPOSED` on demote; use `DEPRECATED` + rely on non-routing.
- OC-5: drop `sandbox_exec._full_namespaces()` env lock around spawns.
- OC-3: set `l4_terminal=True` on `cm_det_strategy` and serve at L4.
- OC-4 / OC-6: pass native module lists and `DegradationThresholds` instead of normalising thermal.
- OC-7: use `ranking="learned_first_with_t0_fallback"` on one form instead of split forms.
- OC-9: use `set_health` / `state` instead of reaching into privates.
- OC-13: drop manual `attach_v02_sink` unless you want a custom sink.

## Tests

`sdk/python/tests/test_v111_oc_fixes.py` covers every OC item. Gate `v111:oc_fixes`.
