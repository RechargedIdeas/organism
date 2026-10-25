"""Phase 2 — Hybrid telemetry → HealthReport probes + hormone stress."""
from __future__ import annotations

from organism_sdk.hormone import HormoneBus, HORMONE_STATE_TAG
from organism_sdk.workspace import WorkspaceClient

from bio_digital.telemetry_bridge import (
    EnvironmentStateView,
    MetricsSnapshot,
    NodeStatusView,
    TelemetryBridge,
)


def test_metric_to_probe():
    bridge = TelemetryBridge()
    report = bridge.ingest_metrics(
        MetricsSnapshot(counters={"requests": 3}, gauges={"gpu": 12.5})
    )
    assert report.status == "HEALTHY"
    assert report.probes["affects_control"] is False
    assert report.probes["metrics"]["counters"]["requests"] == 3
    assert report.probes["metrics"]["gauges"]["gpu"] == 12.5
    assert report.probes["exploration_only"] is True


def test_node_status_to_probe_degraded():
    bridge = TelemetryBridge()
    report = bridge.ingest_node_status(
        NodeStatusView(
            node_id="slime-0",
            substrate="Physarum",
            temperature_c=40.0,
            humidity_pct=10.0,
            co2_ppm=400.0,
            is_healthy=False,
        )
    )
    assert report.status == "DEGRADED"
    assert report.probes["stress"] > 0
    assert report.probes["node"]["affects_control"] is False
    assert report.probes["affects_control"] is False


def test_environment_to_probe():
    bridge = TelemetryBridge()
    report = bridge.ingest_environment(
        EnvironmentStateView(temp_c=22.0, humidity_pct=80.0, co2_ppm=400.0, is_healthy=True)
    )
    assert report.status == "HEALTHY"
    assert report.probes["environment"]["affects_control"] is False


def test_stress_to_hormone_state():
    ws = WorkspaceClient()
    hormone = HormoneBus(ws)
    bridge = TelemetryBridge(workspace=ws, hormone=hormone)
    fed = bridge.apply_status_to_hormone(
        {
            "node_id": "myc-0",
            "substrate": "Mycelium",
            "temperature_c": 40.0,
            "humidity_pct": 10.0,
            "co2_ppm": 900.0,
            "is_healthy": False,
        }
    )
    assert fed is not None
    assert fed["affects_control"] is False
    assert fed["stress"] > 0
    hormones = ws.read_by_tag([HORMONE_STATE_TAG])
    assert hormones
    assert hormones[0].payload["cortisol"] > 0
    # Twin/telemetry feeds must not mark control
    assert hormones[0].affects_control is False or hormones[0].payload.get("affects_control") in (None, False)


def test_dict_shapes_accepted():
    bridge = TelemetryBridge()
    r1 = bridge.ingest_node_status(
        {
            "node_id": "n1",
            "substrate": "x",
            "temperature_c": 21.0,
            "humidity_pct": 80.0,
            "co2_ppm": 400.0,
            "is_healthy": True,
        }
    )
    r2 = bridge.ingest_metrics({"counters": {"a": 1}, "gauges": {}, "histograms": {}})
    assert r1.probes["affects_control"] is False
    assert r2.probes["affects_control"] is False


def test_telemetry_workspace_mirror_not_control():
    ws = WorkspaceClient()
    bridge = TelemetryBridge(workspace=ws)
    bridge.ingest_node_status(
        NodeStatusView(
            node_id="n2",
            substrate="Physarum",
            temperature_c=22.0,
            humidity_pct=80.0,
            co2_ppm=400.0,
            is_healthy=True,
        )
    )
    from bio_digital.telemetry_bridge import TELEMETRY_TAG

    bindings = ws.read_by_tag([TELEMETRY_TAG])
    assert bindings
    assert bindings[0].affects_control is False
    assert bindings[0].payload["affects_control"] is False
