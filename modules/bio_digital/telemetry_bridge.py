"""Hybrid telemetry → Organism HealthReport probes + optional hormone stress.

Consumes Hybrid-shaped payloads (NodeStatus / EnvironmentState / metrics dicts)
in-process without requiring a FastAPI server. Optional HTTP client can pull
JSON from a Hybrid /health or /metrics sidecar when available.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from organism_sdk.health import HealthReport
from organism_sdk.hormone import HormoneBus
from organism_sdk.workspace import WorkspaceClient

from bio_digital.vendor_loader import load_hybrid

TELEMETRY_TAG = "bio_telemetry"


@dataclass
class NodeStatusView:
    """Hybrid-compatible NodeStatus without requiring Hybrid import."""

    node_id: str
    substrate: str
    temperature_c: float
    humidity_pct: float
    co2_ppm: float
    impedance_ohms: float = 0.0
    gpu_utilization_pct: float = 0.0
    is_healthy: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "NodeStatusView":
        return cls(
            node_id=str(data.get("node_id", "unknown")),
            substrate=str(data.get("substrate", "")),
            temperature_c=float(data.get("temperature_c", data.get("temp_c", 0.0))),
            humidity_pct=float(data.get("humidity_pct", 0.0)),
            co2_ppm=float(data.get("co2_ppm", 0.0)),
            impedance_ohms=float(data.get("impedance_ohms", 0.0)),
            gpu_utilization_pct=float(data.get("gpu_utilization_pct", 0.0)),
            is_healthy=bool(data.get("is_healthy", True)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "substrate": self.substrate,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "co2_ppm": self.co2_ppm,
            "impedance_ohms": self.impedance_ohms,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "is_healthy": self.is_healthy,
            "affects_control": False,
        }


@dataclass
class EnvironmentStateView:
    temp_c: float
    humidity_pct: float
    co2_ppm: float
    is_healthy: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "EnvironmentStateView":
        return cls(
            temp_c=float(data.get("temp_c", data.get("temperature_c", 0.0))),
            humidity_pct=float(data.get("humidity_pct", 0.0)),
            co2_ppm=float(data.get("co2_ppm", 0.0)),
            is_healthy=bool(data.get("is_healthy", True)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "temp_c": self.temp_c,
            "humidity_pct": self.humidity_pct,
            "co2_ppm": self.co2_ppm,
            "is_healthy": self.is_healthy,
            "affects_control": False,
        }


@dataclass
class MetricsSnapshot:
    counters: dict[str, int] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, dict[str, float]] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "MetricsSnapshot":
        return cls(
            counters={k: int(v) for k, v in (data.get("counters") or {}).items()},
            gauges={k: float(v) for k, v in (data.get("gauges") or {}).items()},
            histograms=dict(data.get("histograms") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": dict(self.histograms),
            "affects_control": False,
        }


def stress_from_env(env: EnvironmentStateView | NodeStatusView) -> float:
    if isinstance(env, NodeStatusView):
        healthy = env.is_healthy
    else:
        healthy = env.is_healthy
    return 0.0 if healthy else 0.85


class TelemetryBridge:
    """Maps Hybrid metrics into HealthReport probes and optional hormone feed."""

    def __init__(
        self,
        *,
        workspace: WorkspaceClient | None = None,
        hormone: HormoneBus | None = None,
        module_id: str = "bio_digital.telemetry",
    ) -> None:
        self.ws = workspace
        self.hormone = hormone
        self.module_id = module_id
        self.last_report: HealthReport | None = None

    def ingest_node_status(self, status: NodeStatusView | dict[str, Any]) -> HealthReport:
        view = status if isinstance(status, NodeStatusView) else NodeStatusView.from_mapping(status)
        stress = stress_from_env(view)
        status_str = "HEALTHY" if view.is_healthy else "DEGRADED"
        score = 1.0 if view.is_healthy else 0.3
        probes = {
            "source": "node_status",
            "node": view.as_dict(),
            "stress": stress,
            "affects_control": False,
            "exploration_only": True,
        }
        report = HealthReport(
            module_id=self.module_id,
            status=status_str,
            score=score,
            probes=probes,
            active_failures=(
                []
                if view.is_healthy
                else [{"code": "bio_env_unhealthy", "node_id": view.node_id}]
            ),
        )
        self.last_report = report
        self._mirror_probe_binding(report)
        return report

    def ingest_environment(self, env: EnvironmentStateView | dict[str, Any]) -> HealthReport:
        view = env if isinstance(env, EnvironmentStateView) else EnvironmentStateView.from_mapping(env)
        stress = stress_from_env(view)
        report = HealthReport(
            module_id=self.module_id,
            status="HEALTHY" if view.is_healthy else "DEGRADED",
            score=1.0 if view.is_healthy else 0.3,
            probes={
                "source": "environment_state",
                "environment": view.as_dict(),
                "stress": stress,
                "affects_control": False,
                "exploration_only": True,
            },
            active_failures=(
                [] if view.is_healthy else [{"code": "bio_env_unhealthy"}]
            ),
        )
        self.last_report = report
        self._mirror_probe_binding(report)
        return report

    def ingest_metrics(self, metrics: MetricsSnapshot | dict[str, Any]) -> HealthReport:
        snap = metrics if isinstance(metrics, MetricsSnapshot) else MetricsSnapshot.from_mapping(metrics)
        # Prefer Hybrid in-process metrics module shape when live and empty input.
        if not snap.counters and not snap.gauges:
            bundle = load_hybrid()
            if bundle.is_live and bundle.metrics_mod is not None:
                try:
                    snap = MetricsSnapshot.from_mapping(bundle.metrics_mod.get_all_metrics())
                except Exception:
                    pass
        probes = {
            "source": "api_metrics",
            "metrics": snap.as_dict(),
            "affects_control": False,
            "exploration_only": True,
        }
        report = HealthReport(
            module_id=self.module_id,
            status="HEALTHY",
            score=1.0,
            probes=probes,
        )
        self.last_report = report
        self._mirror_probe_binding(report)
        return report

    def feed_hormone_stress(
        self,
        *,
        stress: float,
        viability_score: float | None = None,
        source: str | None = None,
    ) -> dict[str, Any] | None:
        """Optional HormoneBus window from twin/telemetry stress. Never control."""
        if self.hormone is None:
            return None
        if self.ws is None:
            # HormoneBus needs a workspace; construct if omitted
            self.hormone = self.hormone  # already set
        levels = self.hormone.compute_release(
            stress_load=float(stress),
            viability_score=1.0 if viability_score is None else float(viability_score),
            crisis_precursor_count=1.0 if stress > 0 else 0.0,
            source=source or self.module_id,
        )
        self.hormone.write_telemetry_window(levels)
        return {
            "window_id": levels.window_id,
            "cortisol": levels.cortisol,
            "stress": stress,
            "affects_control": False,
            "exploration_only": True,
        }

    def apply_status_to_hormone(self, status: NodeStatusView | dict[str, Any]) -> dict[str, Any] | None:
        view = status if isinstance(status, NodeStatusView) else NodeStatusView.from_mapping(status)
        self.ingest_node_status(view)
        return self.feed_hormone_stress(
            stress=stress_from_env(view),
            viability_score=1.0 if view.is_healthy else 0.2,
            source=view.node_id,
        )


    def _mirror_probe_binding(self, report: HealthReport) -> None:
        """Optional workspace mirror of probes; always affects_control=False."""
        if self.ws is None:
            return
        import uuid
        from organism_sdk.hypervector import Hypervector
        from organism_sdk.workspace import BindingRecord

        bid = uuid.uuid4()
        role = Hypervector.random(seed=(hash(report.module_id) ^ 0x7E1E) & 0xFFFFFFFF)
        filler = Hypervector.random(seed=(hash(report.status) ^ 0x7E1F) & 0xFFFFFFFF)
        rec = BindingRecord(
            binding_id=bid,
            hypervector=role.bind(filler),
            role=role,
            filler=filler,
            tags=(TELEMETRY_TAG, "physical", "exploration"),
            module_id=report.module_id,
            salience=1.0,
            fidelity="FULL",
            payload={
                "probes": report.probes,
                "status": report.status,
                "score": report.score,
                "affects_control": False,
                "exploration_only": True,
            },
            affects_control=False,
        ).with_checksum()
        self.ws.write(rec)

    def fetch_remote_json(self, url: str, *, timeout_s: float = 1.0) -> dict[str, Any] | None:
        """Optional live client for Hybrid FastAPI /health or metrics JSON."""
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                body = resp.read()
            data = json.loads(body.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
            return None
