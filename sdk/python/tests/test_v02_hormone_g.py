"""Artifact G / Categories J–K — HormoneBus + ISE."""
from __future__ import annotations

import math
import time

import pytest
from deterministic_engine.engine import DeterministicEngine

from organism_sdk.hormone import (
    HormoneBus,
    HormoneLevels,
    HormoneReceptor,
    apply_hormone_to_module_params,
)
from organism_sdk.interoceptive import HealthVector, InteroceptiveStateEstimator
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.trace import HormoneTraceEntry, TraceEmitter, V02TraceSink
from organism_sdk.workspace import WorkspaceClient


def _bus_ws():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    sink = V02TraceSink()
    tr = TraceEmitter()
    tr.attach_v02_sink(sink)
    return ws, HormoneBus(ws, trace=tr), tr, sink


def test_k1_hormone_state_written_each_window():
    ws, bus, tr, sink = _bus_ws()
    levels = bus.compute_release(stress_load=0.9, viability_score=0.4, crisis_precursor_count=1)
    rec = bus.write_telemetry_window(levels)
    assert "hormone_state" in rec.tags and rec.fidelity == "FULL" and rec.affects_control
    assert rec.payload["cortisol"] > 0
    assert abs(bus.read_workspace_hormone_state().cortisol - levels.cortisol) < 1e-9


def test_write_mirror_read_consistency():
    ws, bus, tr, sink = _bus_ws()
    levels = HormoneLevels(cortisol=0.7, dopamine=0.1, melatonin=0.2, window_id="wtest")
    bus.write_telemetry_window(levels)
    reading = bus.read_mirror(consumer="test")
    assert reading.source == "hormone_bus_mirror"
    assert abs(reading.levels.cortisol - 0.7) < 1e-9
    assert any(isinstance(e, HormoneTraceEntry) for e in tr.entries)


def test_k2_staleness_in_trace_and_replay_uses_traced():
    ws, bus, tr, sink = _bus_ws()
    bus.write_telemetry_window(HormoneLevels(cortisol=0.55, window_id="w1"))
    time.sleep(0.02)
    reading = bus.read_mirror(consumer="router")
    assert reading.staleness_ms >= 15.0
    he = [e for e in tr.entries if isinstance(e, HormoneTraceEntry)]
    assert he and he[-1].staleness_ms == reading.staleness_ms
    bus.write_telemetry_window(HormoneLevels(cortisol=0.99, window_id="w2"))
    assert abs(he[-1].cortisol - 0.55) < 1e-9
    assert abs(bus.read_workspace_hormone_state().cortisol - 0.99) < 1e-9


def test_k5_kill_mirror_falls_back_to_workspace():
    ws, bus, tr, sink = _bus_ws()
    bus.write_telemetry_window(HormoneLevels(cortisol=0.4, window_id="w"))
    bus.kill_mirror()
    reading = bus.read_mirror(consumer="router")
    assert reading.source == "workspace_fallback"
    assert abs(reading.levels.cortisol - 0.4) < 1e-9


def test_k3_receptor_modulation_shield_unchanged():
    levels = HormoneLevels(cortisol=0.9)
    receptors = [
        HormoneReceptor("CORTISOL", "THRESHOLD_GATE", threshold=0.8, target_parameter="inference_enabled"),
        HormoneReceptor("CORTISOL", "CONTINUOUS_MODULATION", gain=0.5, target_parameter="leak_rate"),
    ]
    out = apply_hormone_to_module_params(receptors, levels, {"inference_enabled": True, "leak_rate": 1.0, "bypass_safety": False})
    assert out["inference_enabled"] is True and out["leak_rate"] > 1.0 and out["bypass_safety"] is False


def test_k4_hormone_cannot_override_shield():
    with pytest.raises(PermissionError):
        apply_hormone_to_module_params(
            [HormoneReceptor("CORTISOL", "BINARY_SWITCH", threshold=0.1, target_parameter="bypass_safety")],
            HormoneLevels(cortisol=1.0),
            {"bypass_safety": False},
        )


def test_router_disposition_in_decision_trace():
    ws, bus, tr, sink = _bus_ws()
    bus.write_telemetry_window(HormoneLevels(cortisol=0.75, window_id="disp"))
    eng = DeterministicEngine()
    reg = RegistryClient(trace=tr)
    c = eng.declare_contract()
    reg.register(c, c.identity.artifact_digest, b"s", module=eng, test_bypass_promote="DELIBERATION")
    router = Router(reg, level="L0", trace=tr, hormone_bus=bus)
    plan = router.decide(RouterTask(task_id="t1", form="control_actuation", safety_tier="critical"))
    assert plan.disposition == "DISPATCH"
    routing = [e for e in tr.entries if getattr(e, "form", None) == "control_actuation"]
    assert routing and "hormone" in routing[-1].rationale
    assert routing[-1].rationale["hormone"]["cortisol"] >= 0.7
    assert "staleness_ms" in routing[-1].rationale["hormone"]


def test_j1_ise_crisis_precursor():
    ise = InteroceptiveStateEstimator(viability_floor=0.3, horizon_s=30)
    for v in [0.9, 0.7, 0.55, 0.45, 0.38]:
        st = ise.estimate(HealthVector(thermal=v, latency_ok=v, calibration=v, energy=v, module_health_min=v))
    assert st.crisis_precursor or st.request_setpoint_adaptation or st.predicted_trajectory.viability_at_horizon < 0.3


def test_j3_replay_interoceptive_binding():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    ise = InteroceptiveStateEstimator(ws)
    st = ise.estimate(HealthVector(thermal=0.8, energy=0.9))
    rec = ise.write_state(st)
    assert rec.payload["viability_score"] == st.viability_score
    assert ws.read_by_tag(["interoceptive_state"])[0].payload["viability_score"] == st.viability_score


def test_j2_ise_offline_fallback_signal():
    ise = InteroceptiveStateEstimator()
    ise.set_offline(True)
    st = ise.estimate(HealthVector())
    assert st.model_version.endswith("offline")
    assert math.isnan(st.viability_score)
