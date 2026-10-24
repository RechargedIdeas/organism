"""Federation gate — v0.2 fail-closed by default; v0.3-M3 optional multi-node.

When ``enable_multi_node=False`` (default), federated oxytocin and mirror-lag
APIs raise ``FederationUnsupported`` (preserves v0.2 stub tests).
When enabled, delegates to ``MultiNodeCluster``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.hormone import HormoneBus, HormoneLevels
from organism_sdk.workspace import WorkspaceClient

UnsupportedKind = Literal[
    "FEDERATED_OXYTOCIN",
    "MULTI_NODE_MIRROR_LAG",
    "DISTRIBUTED_ORGANISM",
]


class FederationUnsupported(Exception):
    def __init__(self, kind: UnsupportedKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class UnsupportedEvent:
    kind: UnsupportedKind
    detail: str
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "recorded_at": self.recorded_at.isoformat(),
            "supported": False,
            "e8_oos": True,
        }


class FederationGate:
    """Gate: federation features fail closed unless enable_multi_node=True."""

    TAG = "federation_unsupported"

    def __init__(
        self,
        workspace: WorkspaceClient | None = None,
        *,
        enable_multi_node: bool = False,
        node_ids: list[str] | None = None,
        default_lag_ms: float = 5.0,
        lag_slo_ms: float = 50.0,
    ) -> None:
        self._ws = workspace
        self.events: list[UnsupportedEvent] = []
        self.enable_multi_node = enable_multi_node
        self._cluster = None
        if enable_multi_node:
            from organism_sdk.multinode import MultiNodeCluster

            self._cluster = MultiNodeCluster(
                node_ids or ["node_a", "node_b", "node_c"],
                default_lag_ms=default_lag_ms,
                lag_slo_ms=lag_slo_ms,
            )

    def _record(self, kind: UnsupportedKind, detail: str) -> UnsupportedEvent:
        ev = UnsupportedEvent(kind, detail)
        self.events.append(ev)
        if self._ws is not None:
            from organism_sdk.hypervector import Hypervector
            import uuid
            from organism_sdk.workspace import BindingRecord

            role = Hypervector.random(seed=0x46454400)
            filler = Hypervector.random()
            rec = BindingRecord(
                binding_id=uuid.uuid4(),
                hypervector=role.bind(filler),
                role=role,
                filler=filler,
                tags=(self.TAG, f"federation/{kind.lower()}"),
                module_id="federation_gate",
                salience=0.5,
                fidelity="FULL",
                payload=ev.as_dict(),
                affects_control=False,
            )
            self._ws.write(rec)
        return ev

    @property
    def cluster(self):
        return self._cluster

    def federated_oxytocin_release(
        self, *, adapter_acceptance_rate: float, peer_nodes: list[str]
    ) -> HormoneLevels:
        if not self.enable_multi_node or self._cluster is None:
            if peer_nodes:
                self._record(
                    "FEDERATED_OXYTOCIN",
                    f"federated oxytocin refused for peers={peer_nodes}; enable_multi_node=False",
                )
                raise FederationUnsupported(
                    "FEDERATED_OXYTOCIN",
                    "Federated oxytocin requires enable_multi_node=True (v0.3-M3)",
                )
            self._record(
                "FEDERATED_OXYTOCIN",
                "federation API invoked on single node; use HormoneBus.oxytocin_release locally",
            )
            raise FederationUnsupported(
                "FEDERATED_OXYTOCIN",
                "Federated oxytocin API unsupported without multi-node; use local HormoneBus",
            )
        # Multi-node path: peer_nodes map to votes at given rate
        votes = {nid: adapter_acceptance_rate for nid in self._cluster.nodes}
        for p in peer_nodes:
            if p in votes:
                votes[p] = adapter_acceptance_rate
        result = self._cluster.federated_oxytocin(votes=votes)
        if not result.agreed:
            raise FederationUnsupported(
                "FEDERATED_OXYTOCIN",
                f"oxytocin quorum failed: {result.reason}",
            )
        # Return levels from first live node
        for n in self._cluster.nodes.values():
            if not n.partitioned:
                return n.bus._mirror
        return HormoneLevels(oxytocin=result.oxytocin)

    def simulate_multi_node_mirror_lag(
        self, bus: HormoneBus, *, peer_count: int, lag_ms: float
    ) -> dict[str, Any]:
        if not self.enable_multi_node or self._cluster is None:
            self._record(
                "MULTI_NODE_MIRROR_LAG",
                f"multi-node mirror lag refused peer_count={peer_count} lag_ms={lag_ms}",
            )
            raise FederationUnsupported(
                "MULTI_NODE_MIRROR_LAG",
                "Multi-node HormoneBus mirror lag requires enable_multi_node=True (v0.3-M3)",
            )
        # Use cluster: release on node_a, advance past lag
        ids = list(self._cluster.nodes.keys())
        src = ids[0]
        self._cluster.release_and_mirror(
            src, lag_ms=lag_ms, stress_load=0.5, viability_score=0.8
        )
        self._cluster.advance(wait_ms=lag_ms + 2.0)
        self._cluster.assert_lag_slo()
        return {
            "peer_count": len(ids) - 1,
            "lag_ms_configured": lag_ms,
            "lag_ms_observed_max": self._cluster.max_observed_lag_ms(),
            "supported": True,
        }

    def is_distributed_supported(self) -> bool:
        return bool(self.enable_multi_node and self._cluster is not None)
