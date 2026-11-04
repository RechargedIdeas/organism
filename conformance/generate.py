"""Generate language-neutral conformance vectors from the Python reference SDK.

Every SDK (Kotlin, Rust, ...) must reproduce these byte for byte. Run:
    PYTHONPATH=sdk/python:modules:. python conformance/generate.py
Vectors are checked in; regenerate only with a reviewed reference change (see docs/INTEROP.md).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from typing import get_args

from organism_sdk.contract import (
    CapabilityScopes,
    DataType,
    Determinism,
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
    UncertaintyKind,
    EmissionSignature,
)
from organism_sdk.degradation import DegradationMachine, HealthSignals
from organism_sdk.hypervector import DIM, WORD_COUNT, Hypervector
from organism_sdk.registry import CapabilityFilter, LifecycleState, RegistryClient

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
) -> SubstrateContract:
    """A valid base contract (no errors) with the knobs the vectors vary."""
    return SubstrateContract(
        identity=Identity(module_id=module_id, version=version, author="conformance", license="Apache-2.0",
                          role=role, artifact_digest=b"\x00" * 32),
        perception=PerceptionSignature(modalities=tuple(modalities), required_modalities=tuple(required)),
        emission=EmissionSignature(output_form=OutputForm.SCALAR, shape=Shape(dims=(1,), dtype=DataType.FP32),
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("hypervector", hypervector_vectors()), ("degradation", degradation_vectors()),
                       ("contract", contract_vectors()), ("lifecycle", lifecycle_vectors())):
        (OUT / f"{name}.json").write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        print("wrote", name)
    d = json.loads((OUT / "degradation.json").read_text())
    seen = {t[1] for s in d["scenarios"] for t in s["transitions"]}
    print("levels reached:", sorted(seen))


if __name__ == "__main__":
    main()
