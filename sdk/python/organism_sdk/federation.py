"""v0.2 federation stubs — fail closed. Distributed Organism remains E.8 OOS.

Provides single-node stubs that:
- refuse federated oxytocin consensus
- refuse multi-node HormoneBus mirror lag simulation as a real cluster
and record unsupported diagnosis events for CI gate proof.
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
    """Single-node gate: federation features fail closed and are audited."""

    TAG = "federation_unsupported"

    def __init__(self, workspace: WorkspaceClient | None = None) -> None:
        self._ws = workspace
        self.events: list[UnsupportedEvent] = []

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

    def federated_oxytocin_release(
        self, *, adapter_acceptance_rate: float, peer_nodes: list[str]
    ) -> HormoneLevels:
        """Refuse multi-node oxytocin consensus; single-node local release only via HormoneBus."""
        if peer_nodes:
            self._record(
                "FEDERATED_OXYTOCIN",
                f"federated oxytocin refused for peers={peer_nodes}; E.8 distributed OOS",
            )
            raise FederationUnsupported(
                "FEDERATED_OXYTOCIN",
                "Federated oxytocin requires Distributed Organism (E.8 out of scope)",
            )
        # Zero peers: still not a federation — fail closed on the federation API
        self._record(
            "FEDERATED_OXYTOCIN",
            "federation API invoked on single node; use HormoneBus.oxytocin_release locally",
        )
        raise FederationUnsupported(
            "FEDERATED_OXYTOCIN",
            "Federated oxytocin API is unsupported in v0.2; use local HormoneBus",
        )

    def simulate_multi_node_mirror_lag(
        self, bus: HormoneBus, *, peer_count: int, lag_ms: float
    ) -> dict[str, Any]:
        """Do not build a cluster. Record unsupported and raise."""
        self._record(
            "MULTI_NODE_MIRROR_LAG",
            f"multi-node mirror lag refused peer_count={peer_count} lag_ms={lag_ms}",
        )
        raise FederationUnsupported(
            "MULTI_NODE_MIRROR_LAG",
            "Multi-node HormoneBus mirror lag simulation requires Distributed Organism (E.8)",
        )

    def is_distributed_supported(self) -> bool:
        return False
