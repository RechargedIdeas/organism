"""v1.0-D — Multi-process distributed Organism."""
from __future__ import annotations

from organism_sdk.distributed import BFTCrossCheck, ProcessCluster, run_multiprocess_oxytocin


def test_multiprocess_oxytocin_quorum_three_nodes():
    r = run_multiprocess_oxytocin(n=3, lag_ms=5.0, lag_slo_ms=50.0)
    assert r.n_processes == 3
    assert r.votes_total >= 3
    assert r.oxytocin_accepted
    assert r.lag_slo_ok
    assert r.details["pids_unique"]


def test_partition_safe_degrade():
    r = run_multiprocess_oxytocin(n=3, partition=True, lag_ms=5.0)
    assert r.partition_degraded
    # Partitioned node does not vote; remaining may still form quorum of 2
    assert r.votes_total == 2


def test_bft_ish_four_nodes_f1():
    cluster = ProcessCluster(n=4, lag_ms=5.0, accept_map={"proc_3": False})
    r = cluster.run(bft=True)
    assert r.bft_ok is True  # 3 honest share digest >= quorum 3
    chk = BFTCrossCheck(f=1, n=4)
    ok, digest, count = chk.agree(
        ["critical-binding-v1"] * 3 + ["byzantine-x"]
    )
    assert ok and digest == "critical-binding-v1" and count == 3
    ok2, _, _ = chk.agree(["a", "b", "c", "d"])
    assert not ok2


def test_clock_skew_injection():
    r = ProcessCluster(n=3, lag_ms=8.0, clock_skew_ms=25.0).run()
    assert r.clock_skew_ms == 25.0
    assert r.lag_slo_ok
    assert r.votes_total >= 2
