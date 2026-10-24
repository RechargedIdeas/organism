"""M4: learned module registers with conformal calibration; KERNEL_BOUND cross-check."""
from __future__ import annotations

import struct
from datetime import datetime, timezone

from deterministic_engine.engine import DeterministicEngine
from learned_module.module import KernelBoundVerifier, LearnedModule
from organism_sdk.contract import DataType, Modality, ReliabilityTier, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.workspace import WorkspaceClient


def test_learned_registers_t2_calibrated():
    mod = LearnedModule(precalibrate=True)
    c = mod.declare_contract()
    assert c.safety.reliability_tier == ReliabilityTier.T2_LEARNED_CALIBRATED
    errors = [i for i in c.validate() if i.severity == Severity.ERROR]
    assert errors == []
    reg = RegistryClient()
    resp = reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=mod,
        test_bypass_promote="DELIBERATION",
    )
    assert resp.module_id == "learned_module_t2"


def test_kernel_bound_cross_check_for_high_control():
    """Cross-check path: learned emission justified with KERNEL_BOUND; T0 verifies."""
    learned = LearnedModule(precalibrate=True)
    engine = DeterministicEngine()
    ws = WorkspaceClient()
    data = struct.pack("<" + "f" * 8, *([0.5] * 8))
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(8,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="cx-1",
            form="control_actuation",
            safety_tier="high",
            deadline_ms=1000,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=800.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    # Learned modules normally don't actuate; for cross-check demo we still
    # produce a KERNEL_BOUND token on a prediction-class emission used as evidence.
    # Force action_class via handle+justify for control path verification.
    emission = learned.handle(inp)
    # Manually require justify for control_actuation class
    from organism_sdk.justification import Emission

    forced = Emission(
        action_class="control_actuation",
        payload=emission.payload,
        metadata=dict(emission.metadata),
    )
    token = learned.justify(forced)
    assert token is not None
    assert token.kind.value == "KERNEL_BOUND"
    verifier = KernelBoundVerifier(verifier_id=engine.declare_contract().identity.module_id)
    result = token.verify(verifier)
    assert result.outcome == "VERIFIED"


def test_router_pattern_recognition_selects_learned():
    reg = RegistryClient()
    learned = LearnedModule(precalibrate=True)
    engine = DeterministicEngine()
    for mod in (learned, engine):
        c = mod.declare_contract()
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"s",
            module=mod,
            test_bypass_promote="DELIBERATION",
        )
    router = Router(reg, level="L0", plan_id_factory=lambda: "p")
    plan = router.decide(
        RouterTask(task_id="pr1", form="pattern_recognition", safety_tier="medium")
    )
    assert plan.disposition == "DISPATCH"
    assert plan.primary.module_id == "learned_module_t2"


def test_uncalibrated_falls_to_t3():
    mod = LearnedModule(precalibrate=False)
    assert mod.declare_contract().safety.reliability_tier == ReliabilityTier.T3_LEARNED_UNCALIBRATED
