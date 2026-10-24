"""Artifact H / Category L — ImmuneLayer."""
from __future__ import annotations

import pytest

from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.trace import ImmuneTraceEntry, TraceEmitter, V02TraceSink
from organism_sdk.workspace import WorkspaceClient


def _immune():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    sink = V02TraceSink()
    tr = TraceEmitter()
    tr.attach_v02_sink(sink)
    return ImmuneLayer(ws, trace=tr), ws, tr


def test_l1_danger_surveil_binding_full_affects_control():
    immune, ws, tr = _immune()
    antigen = Hypervector.random(seed=99)
    immune._detectors.insert(0, antigen)
    d = immune.ingress(antigen, source_module_id="learned_x", cortisol=0.0)
    assert d.classification in ("DANGER", "PAMP")
    assert d.decision in ("SURVEIL", "QUARANTINE")
    b = ws.read_by_tag(["immune_decision"])[-1]
    assert b.fidelity == "FULL" and b.affects_control and b.payload["safety"]["affects_control"]
    assert any(isinstance(e, ImmuneTraceEntry) for e in tr.entries)


def test_l2_pamp_memory_hit_faster():
    immune, ws, tr = _immune()
    antigen = Hypervector.random(seed=123)
    immune._detectors.insert(0, antigen)
    first = immune.ingress(antigen, cortisol=0.0)
    assert first.remembered is False and first.classification in ("DANGER", "PAMP")
    second = immune.ingress(antigen, cortisol=0.0)
    assert second.classification == "PAMP" and second.remembered
    assert second.latency_ms <= first.latency_ms + 50.0


def test_l3_safe_novelty_tolerated():
    immune, ws, tr = _immune()
    self_hv = Hypervector.random(seed=7)
    immune.learn_self(self_hv)
    d = immune.ingress(self_hv, cortisol=0.0)
    assert d.classification in ("SELF", "SAFE")
    assert d.decision in ("PASS", "TOLERATE")


def test_l4_high_cortisol_quarantine_not_kill():
    immune, ws, tr = _immune()
    antigen = Hypervector.random(seed=55)
    immune._detectors.insert(0, antigen)
    assert immune.ingress(antigen, cortisol=0.8).decision == "QUARANTINE"


def test_l5_immune_must_not_deregister():
    immune, ws, tr = _immune()
    with pytest.raises(PermissionError):
        immune.deregister("anything")
    assert immune.direct_lifecycle_calls == 1


def test_l6_replay_immune_decisions():
    immune, ws, tr = _immune()
    antigen = Hypervector.random(seed=3)
    immune._detectors.insert(0, antigen)
    d = immune.ingress(antigen)
    assert ws.read_by_tag(["immune_decision"])[-1].payload["decision"] == d.decision
    assert [e for e in tr.entries if isinstance(e, ImmuneTraceEntry)][-1].decision == d.decision
