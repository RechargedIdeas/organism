"""v1.0-E — Physical research module never actuates; neuro sim gate."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from organism_sdk.contract import DataType, MaxSafetyTier, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.neuro_sim import hardware_caps_with_sim, neuro_sim_enabled
from organism_sdk.registry import CapabilityFilter, RegistryClient
from organism_sdk.router import Router, RouterTask, default_bootstrap_policy
from organism_sdk.workspace import WorkspaceClient
from physical_research.module import PhysicalResearchModule, MODULE_ID
from snn_sentinel.module import SNNSentinel, MODULE_ID as SNN_ID
from deterministic_engine.engine import DeterministicEngine


def test_physical_contract_research_only():
    mod = PhysicalResearchModule()
    c = mod.declare_contract()
    assert c.safety.may_actuate is False
    assert c.safety.max_safety_tier == MaxSafetyTier.RESEARCH
    assert c.metabolic.requires_special_hardware.value == "PHYSICAL_SUBSTRATE"
    assert not [i for i in c.validate() if i.severity == Severity.ERROR]


def test_physical_refuses_control_actuation():
    mod = PhysicalResearchModule()
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.PHYSICAL_SENSOR: ModalityPayload(
                modality=Modality.PHYSICAL_SENSOR, shape=(1,), dtype=DataType.FP32, data=b"\x00\x00\x00\x00"
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="p1", form="control_actuation", safety_tier="research",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.PHYSICAL_SENSOR,),
    )
    em = run_handle(mod, inp)
    assert em.action_class == "hold"
    body = json.loads(em.payload.decode())
    assert body["refused"] is True


def test_physical_exploration_emits_hypothesis():
    mod = PhysicalResearchModule()
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.PHYSICAL_SENSOR: ModalityPayload(
                modality=Modality.PHYSICAL_SENSOR, shape=(1,), dtype=DataType.FP32, data=b"\x00\x00\x00\x00"
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="p2", form="exploration", safety_tier="research",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.PHYSICAL_SENSOR,),
    )
    em = run_handle(mod, inp)
    body = json.loads(em.payload.decode())
    assert body["exploration_only"] is True
    assert "twin" in body


def test_neuro_sim_env_enables_dispatch(monkeypatch):
    monkeypatch.setenv("ORGANISM_NEURO_SIM", "1")
    assert neuro_sim_enabled()
    assert "NEUROMORPHIC" in hardware_caps_with_sim({"NONE"})
    reg = RegistryClient()
    snn = SNNSentinel()  # picks up env
    assert snn.hardware_present is True
    c = snn.declare_contract()
    reg.register(c, artifact_digest=c.identity.artifact_digest, author_signature=b"s",
                 module=snn, test_bypass_promote="DELIBERATION")
    eng = DeterministicEngine()
    ce = eng.declare_contract()
    reg.register(ce, artifact_digest=ce.identity.artifact_digest, author_signature=b"s",
                 module=eng, test_bypass_promote="DELIBERATION")
    router = Router(reg, default_bootstrap_policy(), level="L0", plan_id_factory=lambda: "p",
                    available_hardware={"NONE"})  # sim merges NEUROMORPHIC
    plan = router.decide(RouterTask(task_id="t", form="anomaly_detection", safety_tier="medium"))
    snn_excl = [e for e in plan.excluded if e.module_id == SNN_ID]
    assert not snn_excl or snn_excl[0].reason_code != "hardware_capability_missing"


def test_neuro_sim_default_off(monkeypatch):
    monkeypatch.delenv("ORGANISM_NEURO_SIM", raising=False)
    assert not neuro_sim_enabled()
    assert "NEUROMORPHIC" not in hardware_caps_with_sim({"NONE"})
