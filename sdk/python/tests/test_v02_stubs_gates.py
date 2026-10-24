"""Learned ISE, federated oxytocin, mirror-lag OOS, metamodel disabled gates."""
from __future__ import annotations

import pytest

from organism_sdk.federation import FederationGate, FederationUnsupported
from organism_sdk.hormone import HormoneBus
from organism_sdk.interoceptive import HealthVector
from organism_sdk.learned_ise import LearnedISE
from organism_sdk.metamodel import MetamodelDisabled, MetamodelTracker
from organism_sdk.workspace import WorkspaceClient


def test_learned_ise_blocked_until_promotion():
    ise = LearnedISE()
    h = HealthVector(thermal=0.7)
    ise.update(h, 0.75)
    with pytest.raises(PermissionError):
        ise.estimate(h, for_control=True)
    ise.record_shadow_validate(pass_rate=0.99, ece_ok=True)
    assert ise.promote()
    assert ise.estimate(h, for_control=True).model_version.startswith("0.2.0-learned")


def test_federated_oxytocin_fail_closed_records_event():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    gate = FederationGate(ws)
    with pytest.raises(FederationUnsupported) as ei:
        gate.federated_oxytocin_release(adapter_acceptance_rate=1.0, peer_nodes=["b"])
    assert ei.value.kind == "FEDERATED_OXYTOCIN"
    assert ws.read_by_tag(["federation_unsupported"])


def test_multi_node_mirror_lag_oos():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    gate = FederationGate(ws)
    with pytest.raises(FederationUnsupported) as ei:
        gate.simulate_multi_node_mirror_lag(HormoneBus(ws), peer_count=3, lag_ms=10)
    assert ei.value.kind == "MULTI_NODE_MIRROR_LAG"
    assert not gate.is_distributed_supported()


def test_metamodel_reproductive_disabled():
    t = MetamodelTracker()
    assert not t.reproductive_path_enabled()
    with pytest.raises(MetamodelDisabled):
        t.synthesize({"x": 1})
    assert t.attempts[-1]["reason"] == "E.8_metamodel_reproductive_disabled"
