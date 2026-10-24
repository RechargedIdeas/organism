"""v0.4-M3 security fuzz against trust model / fault matrix."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from deterministic_engine.engine import DeterministicEngine
from harness.scenarios.v04_security_fuzz import (
    _UnjustifiedActuator,
    fuzz_immune_forgeries,
    fuzz_malformed_contracts,
    malformed_contract_empty_identity,
    malformed_contract_required_modality_undeclared,
)
from learned_module.module import LearnedModule
from organism_sdk.contract import Modality, Severity
from organism_sdk.degradation import BYZ_COUNT_L4, DegradationMachine, FaultInjector, HealthSignals, T_DOWN_FAST
from organism_sdk.errors import CapabilityScopeMissing, JustificationMissing, RegistrationRejected
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer, validate_control_binding
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.workspace import BindingRecord, WorkspaceClient


def test_malformed_contracts_rejected():
    for c in (malformed_contract_empty_identity(), malformed_contract_required_modality_undeclared()):
        errors = [i for i in c.validate() if i.severity == Severity.ERROR]
        assert errors
        with pytest.raises(RegistrationRejected):
            c.require_valid()


def test_fuzz_malformed_contracts_fixed_seed():
    stats = fuzz_malformed_contracts(seed=0x564F3433, trials=32)
    assert stats.rejected_contracts == 32


def test_untrusted_learned_control_without_justification_rejected():
    from organism_sdk.contract import DataType

    mod = _UnjustifiedActuator()
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    data = b"\x00" * 32
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(8,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="bad-ca",
            form="control_actuation",
            safety_tier="high",
            deadline_ms=1000,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=800.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    with pytest.raises(JustificationMissing):
        run_handle(mod, inp)


def test_byzantine_drives_l3_l4_and_degraded_plan():
    reg = RegistryClient()
    eng = DeterministicEngine()
    learned = LearnedModule(precalibrate=True)
    for mod in (eng, learned):
        c = mod.declare_contract()
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"s",
            module=mod,
            test_bypass_promote="DELIBERATION",
        )
    deg = DegradationMachine(
        level="L3",
        signals=HealthSignals(
            h_m={"learned_module_t2": "FAILED", "deterministic_engine": "HEALTHY"},
            c_m={"learned_module_t2": 0.2},
            neural_modules=("learned_module_t2",),
            leading_predictive=("learned_module_t2",),
            trace_ok=True,
            det_ok=True,
        ),
        t_down=dict(T_DOWN_FAST),
    )
    inj = FaultInjector(deg)
    for _ in range(BYZ_COUNT_L4):
        inj.byzantine_strike()
    deg.tick()
    deg.advance(T_DOWN_FAST["L4"])
    assert deg.level == "L4"
    router = Router(reg, level="L4", plan_id_factory=lambda: "byz")
    plan = router.decide(RouterTask(task_id="b1", form="control_actuation", safety_tier="high"))
    assert plan.plan_type == "DegradedDispatchPlan"
    assert plan.primary is not None
    assert plan.primary.module_id == "deterministic_engine"


def test_capability_scope_violation_on_workspace_read():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("allowed_tag",))
    role = Hypervector.random(seed=9)
    filler = Hypervector.random(seed=10)
    ws.bind_exact(role, filler, tags=("allowed_tag",), module_id="ok")
    ws.bind_exact(role, Hypervector.random(seed=11), tags=("secret",), module_id="ok")
    reader = ws.reader()
    # in-scope ok
    assert reader.read_by_tag(["allowed_tag"])
    # entirely out-of-scope request raises
    with pytest.raises(CapabilityScopeMissing):
        reader.read_by_tag(["secret"])


def test_capability_scope_write_rejected():
    ws = WorkspaceClient(write_tags=("allowed",), read_tags=("*",))
    role = Hypervector.random(seed=1)
    filler = Hypervector.random(seed=2)
    hv = role.bind(filler)
    rec = BindingRecord(
        binding_id=uuid4(),
        hypervector=hv,
        role=role,
        filler=filler,
        tags=("forbidden",),
        module_id="x",
    )
    result = ws.write(rec)
    assert result.status == "REJECTED"
    assert result.reason_code == "capability_scope_missing"


def test_immune_quarantine_forgery_rejected():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    role = Hypervector.random(seed=3)
    filler = Hypervector.random(seed=4)
    hv = role.bind(filler)
    forged = BindingRecord(
        binding_id=uuid4(),
        hypervector=hv,
        role=role,
        filler=filler,
        tags=("immune_decision", "immune_decision/quarantine"),
        module_id="attacker",
        salience=0.2,
        fidelity="PARTIAL",
        payload={"decision": "QUARANTINE", "safety": {"affects_control": False}},
        affects_control=False,
    )
    result = ws.write(forged)
    assert result.status == "REJECTED"
    assert result.reason_code == "immune_forgery_rejected"
    assert not validate_control_binding(forged)
    # Legitimate ImmuneLayer path still works
    immune = ImmuneLayer(ws)
    antigen = Hypervector.random(seed=55)
    immune._detectors.insert(0, antigen)
    d = immune.ingress(antigen, cortisol=0.8)
    assert d.decision == "QUARANTINE"
    b = ws.read_by_tag(["immune_decision"])[-1]
    assert validate_control_binding(b)


def test_fuzz_immune_forgeries_fixed_seed():
    stats = fuzz_immune_forgeries(seed=0x494D4D46, trials=40)
    assert stats.rejected_forgeries >= 20  # most random combos are forgeries
    assert stats.trials == 40
