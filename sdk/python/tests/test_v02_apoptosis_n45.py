"""N4 drain-killed + N5 shadow-validate promotion path."""
from __future__ import annotations

from dataclasses import replace

from deterministic_engine.engine import DeterministicEngine

from organism_sdk.apoptosis import ApoptosisService, MemoryExport
from organism_sdk.contract import ReliabilityTier as RT
from organism_sdk.trace import TraceEmitter, V02TraceSink
from organism_sdk.workspace import WorkspaceClient


def _svc():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    tr = TraceEmitter()
    tr.attach_v02_sink(V02TraceSink())
    return ApoptosisService(ws, trace=tr), ws


def _t2(mid: str):
    c = DeterministicEngine().declare_contract()
    return replace(
        c,
        safety=replace(c.safety, reliability_tier=RT.T2_LEARNED_CALIBRATED, may_actuate=False),
        lifecycle=replace(c.lifecycle, self_termination_permitted=True),
        identity=replace(c.identity, module_id=mid),
    )


def test_n4_drain_killed_synthetic_no_succeeded():
    svc, ws = _svc()
    r = svc.begin_self_terminate(
        _t2("drain_mod"),
        cause="x",
        memory=MemoryExport({}, [{"id": 1}], [], {}),
        successor_available=True,
        control_affecting=False,
        drain_killed_mid_export=True,
    )
    assert r.state == "SELF_TERMINATING" and r.drain_outcome == "killed"
    assert r.synthetic_lifecycle_recorded
    assert ws.read_by_tag(["lifecycle_synthetic"])[-1].payload["on_drain_outcome"] == "killed"


def test_n5_fail_blocks_then_pass_promotes():
    svc, ws = _svc()
    assert svc.begin_self_terminate(
        _t2("parent"),
        cause="entropy",
        memory=MemoryExport({}, [{"id": 1}], ["e"], {}),
        successor_available=True,
        control_affecting=True,
        successor_spec={"successor_id": "child", "mode": "EXPLORATION"},
    ).accepted
    fail = svc.shadow_validate_successor("child", "parent", pass_rate=0.1)
    assert fail.promotion_blocked and not svc.promote_successor("child").promoted
    ok = svc.shadow_validate_successor("child", "parent", pass_rate=0.99, decisions=[{"id": 1}])
    assert ok.passed and svc.promote_successor("child").promoted
