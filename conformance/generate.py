"""Generate language-neutral conformance vectors from the Python reference SDK.

Every SDK (Kotlin, Rust, ...) must reproduce these byte for byte. Run:
    PYTHONPATH=sdk/python:modules:. python conformance/generate.py
Vectors are checked in; regenerate only with a reviewed reference change (see docs/INTEROP.md).
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import get_args

from organism_sdk.canonical import CanonicalError, canonical_bytes, canonical_text
from organism_sdk.contract import (
    CapabilityScopes,
    DataType,
    Determinism,
    EmissionSignature,
    FailureSignature,
    HealthEscalationPolicy,
    HealthHttp,
    HealthProbe,
    HealthRpc,
    HealthStream,
    Identity,
    JustificationKind,
    JustificationSpec,
    Lifecycle,
    MaxSafetyTier,
    MetabolicProfile,
    Modality,
    ModuleRole,
    OutputForm,
    PerceptionSignature,
    RecoveryKind,
    RecoveryProcedure,
    ReliabilityTier,
    SafetyDeclaration,
    Severity,
    Shape,
    SubstrateContract,
    ToolConfinement,
    ToolConfirmation,
    ToolContract,
    ToolNetwork,
    UncertaintyKind,
)
from organism_sdk.degradation import DegradationMachine, HealthSignals
from organism_sdk.hypervector import DIM, WORD_COUNT, Hypervector
from organism_sdk.model_artifact import ModelArtifact
from organism_sdk.registry import CapabilityFilter, LifecycleState, RegistryClient
from organism_sdk.signing import verify as ed25519_verify

OUT = Path(__file__).parent / "vectors"
SCHEMA = 1


def hx(hv: Hypervector) -> list[str]:
    return [f"{w:016x}" for w in hv.words]


def hv_from(h: list[str]) -> Hypervector:
    return Hypervector(tuple(int(x, 16) for x in h))


def hypervector_vectors() -> dict:
    rng = random.Random(1010)
    hvs = [Hypervector.random(rng=rng) for _ in range(6)]
    cases = []
    cases.append({"op": "bind", "a": hx(hvs[0]), "b": hx(hvs[1]), "out": hx(hvs[0].bind(hvs[1]))})
    for k in (0, 1, 63, 64, 65, 9999, 10000, 12345, 1_000_003):
        cases.append({"op": "permute", "a": hx(hvs[2]), "k": k, "out": hx(hvs[2].permute(k))})
    for i, j in ((0, 1), (2, 2), (3, 4)):
        cases.append({"op": "similarity", "a": hx(hvs[i]), "b": hx(hvs[j]), "out": hvs[i].similarity(hvs[j])})
    for n in (1, 2, 3, 4, 5, 6):
        sel = hvs[:n]
        cases.append({"op": "bundle", "in": [hx(h) for h in sel], "out": hx(Hypervector.bundle(sel))})
    cases.append({"op": "bundle", "in": [], "out": hx(Hypervector.bundle([]))})
    return {"schema": SCHEMA, "dim": DIM, "word_count": WORD_COUNT, "cases": cases}


NEURAL = ["learned_module_t2"]


def sig_dict(**kw) -> dict:
    d = {"h_m": {}, "c_m": {}, "thermal": 1.0, "power": 1.0, "mem": 0.0, "q_p95": 1.0, "gc": 0.0,
         "byz": False, "byz_count": 0, "trace_ok": True, "det_ok": True, "causal_ok": True,
         "neural_modules": NEURAL, "leading_predictive": NEURAL}
    d.update(kw)
    return d


def to_signals(d: dict) -> HealthSignals:
    return HealthSignals(h_m=dict(d["h_m"]), c_m=dict(d["c_m"]), thermal=d["thermal"], power=d["power"],
                         mem=d["mem"], q_p95=d["q_p95"], gc=d["gc"], byz=d["byz"], byz_count=d["byz_count"],
                         trace_ok=d["trace_ok"], det_ok=d["det_ok"], causal_ok=d["causal_ok"],
                         neural_modules=tuple(d["neural_modules"]), leading_predictive=tuple(d["leading_predictive"]))


def run_scenario(steps: list[dict]) -> dict:
    m = DegradationMachine()
    levels = []
    for st in steps:
        m.signals = to_signals(st["signals"])
        m.human_ack = bool(st.get("human_ack", False))
        m.advance(float(st["dt"]))
        levels.append(m.level)
    return {"steps": steps, "levels": levels, "transitions": [list(t) for t in m.transitions],
            "final_human_ack": m.human_ack}


def degradation_vectors() -> dict:
    sc = []
    # thermal drop -> L1 -> recover
    st = [{"dt": 1.0, "signals": sig_dict(thermal=0.1)} for _ in range(8)]
    st += [{"dt": 10.0, "signals": sig_dict(thermal=0.9)} for _ in range(15)]
    sc.append({"name": "thermal_down_up", **run_scenario(st)})
    # full descent and human-ack recovery
    st = []
    st += [{"dt": 2.0, "signals": sig_dict(h_m={NEURAL[0]: "DEGRADED"})} for _ in range(4)]
    st += [{"dt": 10.0, "signals": sig_dict(h_m={NEURAL[0]: "FAILED"})} for _ in range(5)]
    st += [{"dt": 20.0, "signals": sig_dict(h_m={NEURAL[0]: "FAILED"}, gc=0.6)} for _ in range(5)]
    st += [{"dt": 5.0, "signals": sig_dict(trace_ok=False)} for _ in range(5)]
    st += [{"dt": 100.0, "signals": sig_dict(), "human_ack": True} for _ in range(30)]
    sc.append({"name": "descent_and_ack_recovery", **run_scenario(st)})
    # randomized stress, seeded
    rng = random.Random(77)
    for n in range(24):
        steps = []
        for _ in range(60):
            kw = {}
            if rng.random() < 0.3: kw["thermal"] = rng.choice([0.05, 0.15, 0.3, 0.6, 1.0])
            if rng.random() < 0.3: kw["h_m"] = {NEURAL[0]: rng.choice(["HEALTHY", "DEGRADED", "FAILED"])}
            if rng.random() < 0.3: kw["c_m"] = {NEURAL[0]: rng.choice([0.5, 0.75, 0.84, 0.92, 1.0])}
            if rng.random() < 0.2: kw["gc"] = rng.choice([0.0, 0.4, 0.6, 0.9])
            if rng.random() < 0.15: kw["q_p95"] = rng.choice([1.0, 60.0, 300.0])
            if rng.random() < 0.15: kw["mem"] = rng.choice([0.1, 0.95])
            if rng.random() < 0.1: kw["trace_ok"] = rng.random() < 0.5
            if rng.random() < 0.1: kw["det_ok"] = rng.random() < 0.5
            if rng.random() < 0.1: kw["causal_ok"] = rng.random() < 0.5
            if rng.random() < 0.1:
                kw["byz"] = True
                kw["byz_count"] = rng.choice([1, 3, 4])
            steps.append({"dt": rng.choice([0.5, 1.0, 5.0, 20.0, 70.0, 200.0]), "signals": sig_dict(**kw),
                          "human_ack": rng.random() < 0.2})
        sc.append({"name": f"random_{n}", **run_scenario(steps)})
    return {"schema": SCHEMA, "scenarios": sc}


def make_contract(
    module_id: str = "m.base",
    version: str = "1.0.0",
    role: ModuleRole = ModuleRole.SOLVER,
    tier: ReliabilityTier = ReliabilityTier.T0_DETERMINISTIC,
    may_actuate: bool = False,
    requires_cross_check: bool = False,
    modalities: tuple = (Modality.DENSE_VECTOR,),
    required: tuple = (),
    justification: JustificationKind = JustificationKind.NONE,
    requires_justification_for: tuple = (),
    probe: HealthProbe | None = None,
    escalation: HealthEscalationPolicy | None = None,
    override_trace: bool = False,
    override_exploration: bool = False,
    exploration_sink: str = "",
    output_form: OutputForm = OutputForm.SCALAR,
) -> SubstrateContract:
    """A valid base contract (no errors) with the knobs the vectors vary."""
    return SubstrateContract(
        identity=Identity(module_id=module_id, version=version, author="conformance", license="Apache-2.0",
                          role=role, artifact_digest=b"\x00" * 32),
        perception=PerceptionSignature(modalities=tuple(modalities), required_modalities=tuple(required)),
        emission=EmissionSignature(output_form=output_form, shape=Shape(dims=(1,), dtype=DataType.FP32),
                                   uncertainty=UncertaintyKind.NONE, determinism=Determinism.DETERMINISTIC,
                                   requires_justification_for=tuple(requires_justification_for)),
        metabolic=MetabolicProfile(latency_p50_ms=5.0, latency_p95_ms=10.0, latency_p99_ms=20.0,
                                   energy_per_inference_j=0.01, memory_footprint_mb=64.0, memory_peak_mb=96.0),
        failure=FailureSignature(
            modes=(),
            probe=probe or HealthProbe(kind=HealthHttp(url="http://127.0.0.1:9/health")),
            recovery=RecoveryProcedure(kind=RecoveryKind.RESTART, max_attempts=3),
            escalation=escalation or HealthEscalationPolicy(),
        ),
        safety=SafetyDeclaration(reliability_tier=tier, may_actuate=may_actuate,
                                 requires_cross_check=requires_cross_check, max_safety_tier=MaxSafetyTier.MEDIUM),
        lifecycle=Lifecycle(hot_swap_supported=False, shadow_validation_required=True,
                            self_termination_permitted=False),
        capabilities=CapabilityScopes(can_override_trace_sink=override_trace,
                                      can_override_trace_sink_exploration=override_exploration,
                                      exploration_trace_sink_id=exploration_sink),
        justification=JustificationSpec(kind=justification),
    )


def _probe_dict(kind) -> dict:
    if isinstance(kind, HealthHttp):
        return {"type": "HTTP", "url": kind.url, "expected_status": kind.expected_status, "timeout_ms": kind.timeout_ms}
    if isinstance(kind, HealthRpc):
        return {"type": "RPC", "method_fqn": kind.method_fqn, "timeout_ms": kind.timeout_ms}
    return {"type": "STREAM", "topic": kind.topic, "expected_period_ms": kind.expected_period_ms,
            "stall_timeout_ms": kind.stall_timeout_ms}


def contract_dict(c: SubstrateContract) -> dict:
    """The fields the Kotlin SDK models. Enum values are their Python names."""
    e, m, s, cap, lc = c.failure.escalation, c.metabolic, c.safety, c.capabilities, c.lifecycle
    return {
        "identity": {"module_id": c.identity.module_id, "version": c.identity.version,
                     "role": c.identity.role.value},
        "perception": {"modalities": [x.value for x in c.perception.modalities],
                       "required_modalities": [x.value for x in c.perception.required_modalities]},
        "emission": {"output_form": c.emission.output_form.value, "uncertainty": c.emission.uncertainty.value,
                     "determinism": c.emission.determinism.value,
                     "requires_justification_for": list(c.emission.requires_justification_for)},
        "metabolic": {"latency_p50_ms": m.latency_p50_ms, "latency_p95_ms": m.latency_p95_ms,
                      "latency_p99_ms": m.latency_p99_ms, "energy_per_inference_j": m.energy_per_inference_j,
                      "memory_footprint_mb": m.memory_footprint_mb, "memory_peak_mb": m.memory_peak_mb,
                      "requires_gpu": m.requires_gpu, "requires_gradient_training": m.requires_gradient_training,
                      "max_concurrent_invocations": m.max_concurrent_invocations},
        "failure": {"probe": _probe_dict(c.failure.probe.kind),
                    "escalation": {"kind": e.kind.value,
                                   "consecutive_probe_failures": e.consecutive_probe_failures,
                                   "degraded_duration_ms": e.degraded_duration_ms,
                                   "escalate_on_probe_timeout": e.escalate_on_probe_timeout,
                                   "escalate_on_probe_unreachable": e.escalate_on_probe_unreachable,
                                   "probe_interval_ms": e.probe_interval_ms},
                    "recovery": {"kind": c.failure.recovery.kind.value,
                                 "max_attempts": c.failure.recovery.max_attempts}},
        "safety": {"reliability_tier": s.reliability_tier.value, "may_actuate": s.may_actuate,
                   "requires_cross_check": s.requires_cross_check,
                   "requires_causal_certificate": s.requires_causal_certificate,
                   "max_safety_tier": s.max_safety_tier.value},
        "capabilities": {"can_override_trace_sink": cap.can_override_trace_sink,
                         "can_override_trace_sink_exploration": cap.can_override_trace_sink_exploration,
                         "exploration_trace_sink_id": cap.exploration_trace_sink_id},
        "lifecycle": {"hot_swap_supported": lc.hot_swap_supported,
                      "shadow_validation_required": lc.shadow_validation_required,
                      "self_termination_permitted": lc.self_termination_permitted},
        "justification": {"kind": c.justification.kind.value},
    }


def _issues(c: SubstrateContract) -> list[dict]:
    return [{"severity": i.severity.value, "code": i.code, "field_path": i.field_path} for i in c.validate()]


def contract_vectors() -> dict:
    """Validation outcomes from the Python reference. Order of issues is part of the contract."""
    cases = []

    def add(name: str, c: SubstrateContract) -> None:
        issues = _issues(c)
        cases.append({"name": name, "contract": contract_dict(c),
                      "registered": not any(i["severity"] == Severity.ERROR.value for i in issues),
                      "issues": issues})

    add("valid_t0", make_contract())
    add("valid_t2_actuate_with_cross_check", make_contract(tier=ReliabilityTier.T2_LEARNED_CALIBRATED,
                                                          may_actuate=True, requires_cross_check=True))
    add("warn_t2_actuate_no_cross_check", make_contract(tier=ReliabilityTier.T2_LEARNED_CALIBRATED,
                                                       may_actuate=True))
    add("warn_t3_actuate_no_cross_check", make_contract(tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
                                                       may_actuate=True))
    add("t1_actuate_no_warning", make_contract(tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED, may_actuate=True))
    add("missing_module_id", make_contract(module_id=""))
    add("missing_version", make_contract(version=""))
    add("missing_id_and_version", make_contract(module_id="", version=""))
    slow_http = HealthProbe(kind=HealthHttp(url="http://127.0.0.1:9/health", timeout_ms=20000))
    add("probe_timeout_over_degraded_and_cadence", make_contract(probe=slow_http))
    add("probe_timeout_over_cadence_no_escalation",
        make_contract(probe=slow_http, escalation=HealthEscalationPolicy(escalate_on_probe_timeout=False)))
    add("degraded_window_too_short", make_contract(escalation=HealthEscalationPolicy(degraded_duration_ms=8000)))
    add("stream_probe_ok", make_contract(probe=HealthProbe(kind=HealthStream(
        topic="telemetry.x", expected_period_ms=1000, stall_timeout_ms=500))))
    add("stream_probe_stall_over_period", make_contract(probe=HealthProbe(kind=HealthStream(
        topic="telemetry.x", expected_period_ms=1000, stall_timeout_ms=2000))))
    add("rpc_probe_ok", make_contract(probe=HealthProbe(kind=HealthRpc(method_fqn="organism.v1.Health/Ping",
                                                                       timeout_ms=2000))))
    add("required_modality_undeclared", make_contract(modalities=(Modality.DENSE_VECTOR,),
                                                     required=(Modality.TEXT,)))
    add("required_modality_declared", make_contract(modalities=(Modality.DENSE_VECTOR, Modality.TEXT),
                                                   required=(Modality.TEXT,)))
    add("exploration_override_t2_ok", make_contract(tier=ReliabilityTier.T2_LEARNED_CALIBRATED,
                                                  override_exploration=True, exploration_sink="sink-1"))
    add("exploration_override_t3_rejected", make_contract(tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
                                                         override_exploration=True, exploration_sink="sink-1"))
    add("exploration_sink_missing", make_contract(tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED,
                                                 override_exploration=True, exploration_sink=""))
    add("trace_override_t0_ok", make_contract(override_trace=True))
    add("trace_override_t2_rejected", make_contract(tier=ReliabilityTier.T2_LEARNED_CALIBRATED,
                                                   override_trace=True))
    add("justification_unused_warning", make_contract(justification=JustificationKind.CAUSAL_CERT))
    add("justification_used_ok", make_contract(justification=JustificationKind.CAUSAL_CERT,
                                              requires_justification_for=("actuate",)))
    add("combined_issue_order", make_contract(module_id="", tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
                                              may_actuate=True, modalities=(Modality.DENSE_VECTOR,),
                                              required=(Modality.TEXT,),
                                              justification=JustificationKind.CAUSAL_CERT))
    # A1 output forms and A3 human confirmation (added in K1b; appended so earlier cases keep their place).
    add("output_text_ok", make_contract(output_form=OutputForm.TEXT))
    add("output_token_stream_ok", make_contract(output_form=OutputForm.TOKEN_STREAM))
    add("output_tool_call_unjustified_warning", make_contract(output_form=OutputForm.TOOL_CALL))
    add("output_tool_call_justified_ok", make_contract(output_form=OutputForm.TOOL_CALL,
                                                      justification=JustificationKind.HUMAN_CONFIRMATION,
                                                      requires_justification_for=("irreversible",)))
    add("human_confirmation_unused_warning", make_contract(justification=JustificationKind.HUMAN_CONFIRMATION))
    return {"schema": SCHEMA, "cases": cases}


def _transition(initial: str, frm: str, to: str) -> dict:
    """One promote() call on a fresh registry. The Python reference raises ValueError for states that are
    not on the promotion ladder; the vector records that as a rejection with code invalid_promotion."""
    rc = RegistryClient()
    rc.register(make_contract(module_id="m.lc"), b"\x00" * 32, b"", initial_state=initial)
    try:
        resp = rc.promote("m.lc", frm, to, [], b"")
        accepted = resp.accepted
        code = resp.validation_issues[0].code if resp.validation_issues else None
    except ValueError:
        accepted, code = False, "invalid_promotion"
    state_after = rc.query(CapabilityFilter())[0].state
    return {"initial": initial, "from": frm, "to": to, "accepted": accepted, "code": code, "state_after": state_after}


QUERY_MODULES = [
    ("a", ModuleRole.SOLVER, ReliabilityTier.T0_DETERMINISTIC, "EXPLORATION"),
    ("b", ModuleRole.PERCEPTION, ReliabilityTier.T2_LEARNED_CALIBRATED, "DELIBERATION"),
    ("c", ModuleRole.ACTUATOR, ReliabilityTier.T3_LEARNED_UNCALIBRATED, "PROPOSED"),
    ("d", ModuleRole.SOLVER, ReliabilityTier.T1_CALIBRATED_NONLEARNED, "DEVELOPMENT"),
    ("e", ModuleRole.GOVERNANCE, ReliabilityTier.T0_DETERMINISTIC, "SHADOW_VALIDATED"),
    ("f", ModuleRole.SOLVER, ReliabilityTier.T2_LEARNED_CALIBRATED, "RETIRED"),
]

QUERY_FILTERS = [
    {},
    {"roles": ["SOLVER"]},
    {"min_reliability": "T2_LEARNED_CALIBRATED"},
    {"min_reliability": "T0_DETERMINISTIC"},
    {"min_lifecycle_state": "EXPLORATION"},
    {"min_lifecycle_state": "DEVELOPMENT"},
    {"roles": ["SOLVER"], "min_reliability": "T1_CALIBRATED_NONLEARNED", "min_lifecycle_state": "DELIBERATION"},
    {"min_lifecycle_state": "RETIRED"},
]


def lifecycle_vectors() -> dict:
    states = list(get_args(LifecycleState))
    transitions = [_transition(s, f, t) for s in states for f in states for t in states if s == f]
    # The state is not the one promote() expects: lifecycle_mismatch is checked first and leaves the state alone.
    mismatch = []
    for s in states:
        frm = "PROPOSED" if s == "EXPLORATION" else "EXPLORATION"
        mismatch.append(_transition(s, frm, "DELIBERATION"))

    rc = RegistryClient()
    for mid, role, tier, state in QUERY_MODULES:
        rc.register(make_contract(module_id=mid, role=role, tier=tier), b"\x00" * 32, b"", initial_state=state)
    handles = {h.module_id: h for h in rc.query(CapabilityFilter())}
    modules = [{"id": mid, "state": handles[mid].state, "contract": contract_dict(make_contract(
        module_id=mid, role=role, tier=tier))} for mid, role, tier, _ in QUERY_MODULES]
    queries = []
    for f in QUERY_FILTERS:
        flt = CapabilityFilter(
            roles=tuple(ModuleRole(r) for r in f.get("roles", [])),
            min_reliability=ReliabilityTier(f["min_reliability"]) if "min_reliability" in f else None,
            min_lifecycle_state=f.get("min_lifecycle_state"),
        )
        ids = sorted(h.module_id for h in rc.query(flt))
        queries.append({"filter": f, "expected_ids": ids})
    return {"schema": SCHEMA, "contract": contract_dict(make_contract(module_id="m.lc")), "states": states,
            "transitions": transitions, "lifecycle_mismatch": mismatch,
            "queries": {"modules": modules, "cases": queries}}


CANONICAL_CASES = [
    # (name, input JSON text). The input is parsed with the reference parser, then written canonically.
    ("empty_object", "{}"),
    ("empty_array", "[]"),
    ("empty_string", '""'),
    ("null", "null"),
    ("true", "true"),
    ("false", "false"),
    ("nested_sorted_keys", ' { "b" : { "z" : 1 , "a" : [ 3 , 2 , 1 ] } , "a" : null , "c" : [ ] , "d" : { } } '),
    ("key_order_is_code_point_order", r'{"\uff5e":1,"\ud83d\ude00":2,"b":3,"B":4,"":5,"a\u0000":6,"a":7}'),
    ("array_order_kept", '[3,"a",[2,1],{"y":1,"x":2},null,true]'),
    ("escapes", r'"quote\" back\\ slash/ \b\f\n\r\t \u0000 \u0001 \u001f \u007f"'),
    ("escaped_key", r'{"a\"b":1,"a\nb":2,"a\\b":3}'),
    ("unicode_bmp", r'"caf\u00e9 \u4e16\u754c \u2028\u2029 \uffff"'),
    ("unicode_raw_input", '"caf\u00e9 \u4e16\u754c"'),
    ("unicode_astral_pair", r'"\ud83d\ude00 \ud834\udd1e"'),
    ("numbers_integers", "[0,-0,1,-1,10,123456789012,9007199254740991,-9007199254740991]"),
    ("number_exponent_free", "[100,-100,1000000]"),
    ("deep_nesting", '{"a":{"b":{"c":{"d":[[[[1]]]]}}}}'),
    ("realistic_tool_schema", '{"type":"object","required":["path"],"properties":{"path":{"type":"string","minLength":1},"mode":{"enum":["r","w"]}},"additionalProperties":false}'),
    ("reject_float", "1.5"),
    ("reject_whole_float", "1.0"),
    ("reject_negative_zero_float", "-0.0"),
    ("reject_exponent", "1e3"),
    ("reject_float_in_array", '[1,{"b":2.5}]'),
    ("reject_nan", "NaN"),
    ("reject_infinity", "Infinity"),
    ("reject_negative_infinity", "-Infinity"),
    ("reject_overflow_to_infinity", "1e400"),
    ("reject_nan_beats_float_by_key_order", '{"b":1.5,"a":NaN}'),
    ("reject_integer_above_range", "9007199254740992"),
    ("reject_integer_below_range", "-9007199254740992"),
    ("reject_huge_integer", "99999999999999999999999"),
    ("reject_lone_high_surrogate", r'"\ud800"'),
    ("reject_lone_low_surrogate", r'"a\udc00"'),
    ("reject_reversed_surrogates", r'"\ude00\ud83d"'),
    ("reject_lone_surrogate_key", r'{"\udc00":1}'),
]


def canonical_vectors() -> dict:
    """Canonical JSON writer outcomes. ``input`` is JSON text. A case has either ``canonical`` and ``hex``
    (the UTF-8 bytes) or an ``error`` code."""
    cases = []
    for name, text in CANONICAL_CASES:
        value = json.loads(text)
        try:
            out = canonical_text(value)
            cases.append({"name": name, "input": text, "canonical": out, "hex": canonical_bytes(value).hex()})
        except CanonicalError as exc:
            cases.append({"name": name, "input": text, "error": exc.code})
    return {"schema": SCHEMA, "max_safe_integer": 2**53 - 1, "cases": cases}


# RFC 8032 section 7.1: (name, public key, message, signature). Checked against the reference in signature_vectors().
RFC8032 = [
    ("rfc8032_test1_empty_message",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("rfc8032_test2_one_byte",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("rfc8032_test3_two_bytes",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ("rfc8032_test_sha_abc",
     "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b58909351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]

ED25519_L = 2**252 + 27742317777372353535851937790883648493


def _flip(h: str, byte_index: int) -> str:
    b = bytearray(bytes.fromhex(h))
    b[byte_index] ^= 0x01
    return b.hex()


def signature_vectors() -> dict:
    """Ed25519 verification outcomes (RFC 8032, cofactorless, S must be below the group order)."""
    cases = []

    def add(name: str, pk: str, msg: str, sig: str) -> None:
        ok = ed25519_verify(bytes.fromhex(pk), bytes.fromhex(sig), bytes.fromhex(msg))
        cases.append({"name": name, "public_key": pk, "message": msg, "signature": sig, "valid": ok})

    for name, pk, msg, sig in RFC8032:
        add(name, pk, msg, sig)
        assert cases[-1]["valid"], name
    _, pk1, msg1, sig1 = RFC8032[0]
    _, pk2, _msg2, sig2 = RFC8032[1]
    add("tampered_message", pk2, "73", sig2)
    add("tampered_message_extra_byte", pk2, "7200", sig2)
    add("tampered_signature_r", pk1, msg1, _flip(sig1, 0))
    add("tampered_signature_s", pk1, msg1, _flip(sig1, 40))
    add("wrong_key", pk2, msg1, sig1)
    s = int.from_bytes(bytes.fromhex(sig1)[32:], "little")
    add("s_not_reduced_malleable", pk1, msg1, (bytes.fromhex(sig1)[:32] + (s + ED25519_L).to_bytes(32, "little")).hex())
    add("zero_signature", pk1, msg1, "00" * 64)
    add("public_key_not_on_curve", "02" + "00" * 31, msg1, sig1)
    add("signature_too_short", pk1, msg1, sig1[:-2])
    add("signature_too_long", pk1, msg1, sig1 + "00")
    add("signature_empty", pk1, msg1, "")
    add("public_key_too_short", pk1[:-2], msg1, sig1)
    add("public_key_empty", "", msg1, sig1)
    assert [c["valid"] for c in cases] == [True] * 4 + [False] * (len(cases) - 4)
    return {"schema": SCHEMA, "cases": cases}


def tool_dict(t: ToolContract) -> dict:
    return {"name": t.name, "schema": t.schema_json, "risk_tier": t.risk_tier.value,
            "confirmation": t.confirmation.value, "network": t.network.value, "confinement": t.confinement.value}


def tool_vectors() -> dict:
    """Tool contract validation outcomes (A2). Order of issues is part of the contract."""
    schema = canonical_text({"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}})
    base = {"name": "fs.read", "schema_json": schema, "risk_tier": MaxSafetyTier.LOW}
    cases = []

    def add(case: str, /, **kw) -> None:
        t = ToolContract(**{**base, **kw})
        issues = [{"severity": i.severity.value, "code": i.code, "field_path": i.field_path} for i in t.validate()]
        cases.append({"name": case, "tool": tool_dict(t), "registered": t.is_registrable(), "issues": issues})

    add("valid_low_risk")
    add("valid_name_with_dots_dashes", name="a.b-c_d9")
    add("name_empty", name="")
    add("name_uppercase", name="FsRead")
    add("name_starts_with_digit", name="1tool")
    add("name_too_long", name="a" * 65)
    add("name_longest_ok", name="a" * 64)
    add("schema_not_json", schema_json="{not json")
    add("schema_empty", schema_json="")
    add("schema_not_object", schema_json="[1,2]")
    add("schema_has_whitespace", schema_json='{"type": "object"}')
    add("schema_keys_unsorted", schema_json='{"type":"object","properties":{}}')
    add("schema_has_float", schema_json='{"maximum":1.5,"type":"number"}')
    add("schema_empty_object_ok", schema_json="{}")
    add("high_risk_no_confirmation", risk_tier=MaxSafetyTier.HIGH, confinement=ToolConfinement.SCOPED)
    add("high_risk_confirmed", risk_tier=MaxSafetyTier.HIGH, confirmation=ToolConfirmation.ON_FIRST_USE,
        confinement=ToolConfinement.SCOPED)
    add("high_risk_unconfined", risk_tier=MaxSafetyTier.HIGH, confirmation=ToolConfirmation.ALWAYS)
    add("critical_first_use_only", risk_tier=MaxSafetyTier.CRITICAL, confirmation=ToolConfirmation.ON_FIRST_USE,
        confinement=ToolConfinement.STRICT)
    add("critical_always_confined", risk_tier=MaxSafetyTier.CRITICAL, confirmation=ToolConfirmation.ALWAYS,
        confinement=ToolConfinement.STRICT)
    add("internet_unconfined", network=ToolNetwork.INTERNET)
    add("internet_confined", network=ToolNetwork.INTERNET, confinement=ToolConfinement.SCOPED)
    add("local_network_unconfined_ok", network=ToolNetwork.LOCAL)
    add("research_risk_ok", risk_tier=MaxSafetyTier.RESEARCH)
    add("everything_wrong", name="", schema_json="[]", risk_tier=MaxSafetyTier.CRITICAL,
        network=ToolNetwork.INTERNET)
    return {"schema": SCHEMA, "cases": cases}


def artifact_dict(a: ModelArtifact) -> dict:
    return {"model_id": a.model_id, "version": a.version, "weights_digest": a.weights_digest,
            "tokenizer_digest": a.tokenizer_digest, "quantisation": a.quantisation, "license": a.license,
            "gate_report_digest": a.gate_report_digest, "adapter_lineage": list(a.adapter_lineage),
            "data_provenance": list(a.data_provenance)}


def _digest(tag: str) -> str:
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def model_artifact_vectors() -> dict:
    """ModelArtifact manifest validation outcomes (A8). Order of issues is part of the contract."""
    base = {"model_id": "lightspeed.core", "version": "1.0.0", "weights_digest": _digest("weights"),
                "tokenizer_digest": _digest("tokenizer"), "quantisation": "q4_k_m", "license": "Apache-2.0",
                "gate_report_digest": _digest("gates"), "adapter_lineage": (_digest("adapter-1"), _digest("adapter-2")),
                "data_provenance": ("corpus.public-2026-10",)}
    cases = []

    def add(case: str, /, **kw) -> None:
        a = ModelArtifact(**{**base, **kw})
        issues = [{"severity": i.severity.value, "code": i.code, "field_path": i.field_path} for i in a.validate()]
        cases.append({"name": case, "artifact": artifact_dict(a), "releasable": a.is_releasable(),
                      "issues": issues})

    good = _digest("x")
    add("valid_with_adapters")
    add("valid_no_adapters", adapter_lineage=())
    add("model_id_missing", model_id="")
    add("version_missing", version="")
    add("weights_digest_missing", weights_digest="")
    add("weights_digest_no_prefix", weights_digest=good[len("sha256:"):])
    add("weights_digest_wrong_algorithm", weights_digest="sha512:" + "a" * 64)
    add("weights_digest_short", weights_digest="sha256:" + "a" * 63)
    add("weights_digest_long", weights_digest="sha256:" + "a" * 65)
    add("weights_digest_upper_case", weights_digest="sha256:" + "A" * 64)
    add("weights_digest_not_hex", weights_digest="sha256:" + "g" * 64)
    add("tokenizer_digest_missing", tokenizer_digest="")
    add("tokenizer_digest_invalid", tokenizer_digest="sha256:abc")
    add("quantisation_missing", quantisation="")
    add("license_missing", license="")
    add("gate_report_missing", gate_report_digest="")
    add("gate_report_invalid", gate_report_digest="report.json")
    add("adapter_digest_invalid", adapter_lineage=(_digest("a"), "adapter-2"))
    add("adapter_duplicate", adapter_lineage=(_digest("a"), _digest("b"), _digest("a")))
    add("provenance_empty", data_provenance=())
    add("provenance_entry_empty", data_provenance=("corpus.a", ""))
    add("everything_missing", model_id="", version="", weights_digest="", tokenizer_digest="", quantisation="",
        license="", gate_report_digest="", adapter_lineage=("x",), data_provenance=())
    return {"schema": SCHEMA, "cases": cases}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("hypervector", hypervector_vectors()), ("degradation", degradation_vectors()),
                       ("contract", contract_vectors()), ("lifecycle", lifecycle_vectors()),
                       ("canonical", canonical_vectors()), ("signature", signature_vectors()),
                       ("tool", tool_vectors()), ("model_artifact", model_artifact_vectors())):
        (OUT / f"{name}.json").write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        print("wrote", name)
    d = json.loads((OUT / "degradation.json").read_text())
    seen = {t[1] for s in d["scenarios"] for t in s["transitions"]}
    print("levels reached:", sorted(seen))


if __name__ == "__main__":
    main()
