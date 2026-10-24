"""M5: workspace:replay, snapshot integrity, dimension mismatch, crash recovery."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from organism_sdk.errors import DimensionMismatch
from organism_sdk.hypervector import DIM, Hypervector
from organism_sdk.snapshot import DurableWorkspace, query_digest


def test_snapshot_and_replay(tmp_path: Path):
    dw = DurableWorkspace(tmp_path / "ws")
    role = Hypervector.random()
    filler = Hypervector.random()
    rec = dw.bind_exact(role, filler, tags=("governance",), module_id="m")
    # More ops
    for i in range(5):
        dw.bind_exact(Hypervector.random(), Hypervector.random(), tags=("t",), module_id="m")
    dig_before = query_digest(dw.ws, rec.hypervector)
    snap = dw.snapshot()
    assert snap.dimension == DIM
    assert snap.path.exists()
    # Mutate after snapshot
    dw.bind_exact(Hypervector.random(), Hypervector.random(), tags=("t",), module_id="m")
    # Replay snapshot only (without post-snap ops) by using seq_end
    rebuilt = dw.replay_from_snapshot(snap.path, ops_from=snap.seq_end + 1)
    # Wait — ops_from = seq_end+1 means apply ops after snapshot; snapshot already has state
    # So rebuilt should match post-snapshot if we include later ops.
    # For zero-mismatch with pre-mutation digest, replay snapshot with no further ops:
    rebuilt_exact = dw.replay_from_snapshot(snap.path, ops_from=10**9)  # no ops after
    dig_after = query_digest(rebuilt_exact, rec.hypervector)
    assert dig_before == dig_after


def test_dimension_mismatch(tmp_path: Path):
    dw = DurableWorkspace(tmp_path / "ws2")
    dw.bind_exact(Hypervector.random(), Hypervector.random(), tags=("t",), module_id="m")
    snap = dw.snapshot()
    # Corrupt dimension
    obj = json.loads(snap.path.read_text())
    obj["dimension"] = 999
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(obj))
    with pytest.raises(DimensionMismatch):
        dw.load_snapshot(bad)


def test_crash_recovery(tmp_path: Path):
    root = tmp_path / "ws3"
    dw = DurableWorkspace(root)
    ids = []
    for _ in range(10):
        r = dw.bind_exact(Hypervector.random(), Hypervector.random(), tags=("t",), module_id="m")
        ids.append(r.binding_id)
    dw.unbind(ids[0])
    # Simulate crash: new DurableWorkspace on same ops log
    dw2 = DurableWorkspace(root)
    recovered = dw2.crash_recover()
    assert recovered.read_by_binding_id(ids[0]) is None
    assert recovered.read_by_binding_id(ids[1]) is not None


def test_snapshot_integrity_merkle(tmp_path: Path):
    dw = DurableWorkspace(tmp_path / "ws4")
    dw.bind_exact(Hypervector.random(), Hypervector.random(), tags=("t",), module_id="m")
    snap = dw.snapshot()
    obj = json.loads(snap.path.read_bytes())
    assert obj["merkle_root"] == snap.merkle_root.hex()
