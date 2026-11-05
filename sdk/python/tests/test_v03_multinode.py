"""v0.3-M3 — Multi-node mirror lag + federated oxytocin quorum."""
from __future__ import annotations

import pytest
from organism_sdk import multinode
from organism_sdk.federation import FederationGate, FederationUnsupported
from organism_sdk.hormone import HormoneBus
from organism_sdk.multinode import MultiNodeCluster
from organism_sdk.workspace import WorkspaceClient


def test_default_gate_still_fail_closed() -> None:
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    gate = FederationGate(ws, enable_multi_node=False)
    with pytest.raises(FederationUnsupported):
        gate.federated_oxytocin_release(adapter_acceptance_rate=1.0, peer_nodes=["b"])
    with pytest.raises(FederationUnsupported):
        gate.simulate_multi_node_mirror_lag(HormoneBus(ws), peer_count=2, lag_ms=5)
    assert not gate.is_distributed_supported()


class _Clock:
    """Stands in for the time module in multinode: time moves only when the test moves it."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_mirror_lag_slo(monkeypatch: pytest.MonkeyPatch) -> None:
    # A real 25 ms sleep can overshoot the 40 ms SLO on a loaded machine (a 47 ms run failed this
    # check). On a fake clock the wait is exactly 25 ms, so the check tests the SLO and nothing else.
    monkeypatch.setattr(multinode, "time", _Clock())
    cluster = MultiNodeCluster(["a", "b"], default_lag_ms=5.0, lag_slo_ms=40.0)
    cluster.release_and_mirror("a", lag_ms=5.0, stress_load=0.7, viability_score=0.5)
    applied = cluster.advance(wait_ms=25.0)
    assert applied >= 1
    cluster.assert_lag_slo()
    assert cluster.max_observed_lag_ms() >= 4.0  # roughly configured lag
    assert any(r["from"] == "a" for r in cluster.nodes["b"].mirror_receipts)


def test_oxytocin_quorum_agreement() -> None:
    cluster = MultiNodeCluster(["a", "b", "c"], default_lag_ms=1.0)
    result = cluster.federated_oxytocin(
        votes={"a": 0.9, "b": 0.85, "c": 0.8}, accept_threshold=0.5
    )
    assert result.agreed
    assert result.oxytocin > 0.0
    assert len(result.votes) == 3


def test_oxytocin_quorum_reject() -> None:
    cluster = MultiNodeCluster(["a", "b", "c"])
    result = cluster.federated_oxytocin(
        votes={"a": 0.9, "b": 0.1, "c": 0.1}, accept_threshold=0.5
    )
    assert not result.agreed
    assert result.reason == "quorum_failed"


def test_partition_safe_degrade() -> None:
    cluster = MultiNodeCluster(["a", "b"])
    cluster.partition("b")
    result = cluster.federated_oxytocin(votes={"a": 1.0, "b": 1.0})
    assert not result.agreed
    assert result.degrade == "QUORUM_LOST"
    # Partitioned node local release uses safe degrade
    levels = cluster.nodes["b"].local_release(adapter_acceptance_rate=1.0)
    assert levels.oxytocin == 0.0
    assert cluster.nodes["b"].degrade in ("PARTITION_SAFE", "QUORUM_LOST")


def test_enabled_gate_mirror_and_oxytocin(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same fake clock as test_mirror_lag_slo: a real sleep overshot the 30 ms SLO on a loaded
    # machine (62 ms in one run), so the check ran on the clock and not on the code under test.
    monkeypatch.setattr(multinode, "time", _Clock())
    gate = FederationGate(enable_multi_node=True, default_lag_ms=3.0, lag_slo_ms=30.0)
    assert gate.is_distributed_supported()
    info = gate.simulate_multi_node_mirror_lag(
        HormoneBus(WorkspaceClient(write_tags=("*",), read_tags=("*",))),
        peer_count=2,
        lag_ms=3.0,
    )
    assert info["supported"] is True
    cluster = gate.cluster
    assert cluster is not None  # enable_multi_node=True builds the cluster
    levels = gate.federated_oxytocin_release(
        adapter_acceptance_rate=0.95, peer_nodes=list(cluster.nodes.keys())
    )
    assert levels.oxytocin >= 0.0
