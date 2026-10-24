"""v0.3-M3 — In-process multi-node foundation (HormoneBus mirror lag + federated oxytocin).

Not a BFT cluster. Two+ OrganismNode instances share an optional MirrorFabric
with injectable lag. Federated oxytocin uses simple majority quorum.
Single-device remains the default; enable via MultiNodeCluster / FederationGate
``enable_multi_node=True``.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.hormone import HormoneBus, HormoneLevels, HORMONE_STATE_TAG
from organism_sdk.hypervector import Hypervector
from organism_sdk.workspace import BindingRecord, WorkspaceClient


DegradeMode = Literal["NONE", "PARTITION_SAFE", "QUORUM_LOST"]


@dataclass
class MirrorEnvelope:
    source_node: str
    levels: HormoneLevels
    emitted_at_mono: float
    deliver_at_mono: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class OxytocinVote:
    node_id: str
    accept: bool
    adapter_acceptance_rate: float
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class OrganismNode:
    """Single logical node with local workspace + HormoneBus."""

    def __init__(self, node_id: str, *, lag_ms: float = 0.0) -> None:
        self.node_id = node_id
        self.lag_ms = lag_ms
        self.workspace = WorkspaceClient(write_tags=("*",), read_tags=("*",))
        self.bus = HormoneBus(self.workspace)
        self.degrade: DegradeMode = "NONE"
        self.partitioned = False
        self._inbox: list[MirrorEnvelope] = []
        self._lock = threading.RLock()
        self.mirror_receipts: list[dict[str, Any]] = []

    def local_release(self, **kwargs: Any) -> HormoneLevels:
        if self.degrade in ("PARTITION_SAFE", "QUORUM_LOST") and kwargs.get("force") is not True:
            # Safe degrade: local cortisol up, block federated oxytocin contribution
            kwargs.setdefault("stress_load", 0.6)
            kwargs["adapter_acceptance_rate"] = 0.0
        return self.bus.compute_release(**{k: v for k, v in kwargs.items() if k != "force"})

    def enqueue_mirror(self, env: MirrorEnvelope) -> None:
        with self._lock:
            if self.partitioned:
                return
            self._inbox.append(env)

    def drain_mirrors(self, *, now_mono: float | None = None) -> int:
        """Apply due mirror envelopes to local bus/workspace. Returns count applied."""
        now = now_mono if now_mono is not None else time.monotonic()
        applied = 0
        with self._lock:
            due: list[MirrorEnvelope] = []
            keep: list[MirrorEnvelope] = []
            for env in self._inbox:
                if env.deliver_at_mono <= now:
                    due.append(env)
                else:
                    keep.append(env)
            self._inbox = keep
            for env in due:
                # Write peer hormone snapshot as non-control binding; update mirror reading path
                role = Hypervector.random(seed=hash(env.source_node) & 0xFFFFFFFF)
                filler = Hypervector.random()
                rec = BindingRecord(
                    binding_id=uuid.uuid4(),
                    hypervector=role.bind(filler),
                    role=role,
                    filler=filler,
                    tags=(HORMONE_STATE_TAG, "mirror", f"from:{env.source_node}"),
                    module_id=f"mirror:{env.source_node}",
                    salience=0.4,
                    fidelity="FULL",
                    payload={
                        **env.levels.as_dict(),
                        "mirror_from": env.source_node,
                        "lag_ms_observed": max(0.0, (now - env.emitted_at_mono) * 1000.0),
                    },
                    affects_control=False,
                )
                self.workspace.write(rec)
                # Soft-merge oxytocin/cortisol into local mirror for lag tests (not SoT overwrite of own window)
                merged = HormoneLevels(
                    cortisol=max(self.bus._mirror.cortisol, env.levels.cortisol * 0.5),
                    dopamine=self.bus._mirror.dopamine,
                    oxytocin=max(self.bus._mirror.oxytocin, env.levels.oxytocin * 0.5),
                    melatonin=self.bus._mirror.melatonin,
                    source=f"mirror:{env.source_node}",
                    window_id=env.levels.window_id,
                )
                self.bus._mirror = merged.clamp()
                self.bus._mirror_written_at = datetime.now(timezone.utc)
                lag_obs = max(0.0, (now - env.emitted_at_mono) * 1000.0)
                self.mirror_receipts.append(
                    {
                        "from": env.source_node,
                        "lag_ms": lag_obs,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                applied += 1
        return applied


class MirrorFabric:
    """Delivers hormone mirrors between nodes with configurable lag."""

    def __init__(self, nodes: dict[str, OrganismNode], *, default_lag_ms: float = 5.0) -> None:
        self.nodes = nodes
        self.default_lag_ms = default_lag_ms
        self._lock = threading.RLock()

    def broadcast(self, source: OrganismNode, levels: HormoneLevels, *, lag_ms: float | None = None) -> None:
        lag = self.default_lag_ms if lag_ms is None else lag_ms
        # Use source node lag override if set
        emitted = time.monotonic()
        for nid, node in self.nodes.items():
            if nid == source.node_id:
                continue
            if node.partitioned or source.partitioned:
                continue
            node_lag = lag if node.lag_ms <= 0 else node.lag_ms
            env = MirrorEnvelope(
                source_node=source.node_id,
                levels=levels,
                emitted_at_mono=emitted,
                deliver_at_mono=emitted + node_lag / 1000.0,
            )
            node.enqueue_mirror(env)

    def tick(self) -> int:
        total = 0
        now = time.monotonic()
        for node in self.nodes.values():
            total += node.drain_mirrors(now_mono=now)
        return total


@dataclass
class OxytocinQuorumResult:
    agreed: bool
    oxytocin: float
    votes: list[OxytocinVote]
    reason: str
    degrade: DegradeMode = "NONE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "agreed": self.agreed,
            "oxytocin": self.oxytocin,
            "votes": [
                {
                    "node_id": v.node_id,
                    "accept": v.accept,
                    "adapter_acceptance_rate": v.adapter_acceptance_rate,
                }
                for v in self.votes
            ],
            "reason": self.reason,
            "degrade": self.degrade,
        }


class MultiNodeCluster:
    """Minimal 2–N node simulation with mirror lag + oxytocin quorum."""

    def __init__(
        self,
        node_ids: list[str] | None = None,
        *,
        default_lag_ms: float = 5.0,
        lag_slo_ms: float = 50.0,
        quorum_fraction: float = 0.5,
    ) -> None:
        ids = node_ids or ["node_a", "node_b"]
        self.nodes = {nid: OrganismNode(nid, lag_ms=default_lag_ms) for nid in ids}
        self.fabric = MirrorFabric(self.nodes, default_lag_ms=default_lag_ms)
        self.lag_slo_ms = lag_slo_ms
        self.quorum_fraction = quorum_fraction
        self.enabled = True

    def release_and_mirror(
        self, node_id: str, *, lag_ms: float | None = None, **release_kw: Any
    ) -> HormoneLevels:
        node = self.nodes[node_id]
        levels = node.local_release(**release_kw)
        self.fabric.broadcast(node, levels, lag_ms=lag_ms)
        return levels

    def advance(self, *, wait_ms: float = 0.0) -> int:
        if wait_ms > 0:
            time.sleep(wait_ms / 1000.0)
        return self.fabric.tick()

    def max_observed_lag_ms(self) -> float:
        lags = [r["lag_ms"] for n in self.nodes.values() for r in n.mirror_receipts]
        return max(lags) if lags else 0.0

    def assert_lag_slo(self) -> None:
        observed = self.max_observed_lag_ms()
        # Allow small scheduling slack above configured fabric lag
        if observed > self.lag_slo_ms:
            raise AssertionError(f"mirror lag SLO violated: {observed:.2f}ms > {self.lag_slo_ms}ms")

    def partition(self, node_id: str) -> None:
        node = self.nodes[node_id]
        node.partitioned = True
        node.degrade = "PARTITION_SAFE"

    def heal(self, node_id: str) -> None:
        node = self.nodes[node_id]
        node.partitioned = False
        node.degrade = "NONE"

    def federated_oxytocin(
        self,
        *,
        votes: dict[str, float] | None = None,
        accept_threshold: float = 0.5,
        byzantine_reject_below: float = 0.0,
    ) -> OxytocinQuorumResult:
        """Quorum over adapter_acceptance_rate votes from non-partitioned nodes."""
        live = [n for n in self.nodes.values() if not n.partitioned]
        if len(live) < 2:
            for n in self.nodes.values():
                if n.partitioned or True:
                    # All nodes enter quorum-lost safe degrade; partitioned stay isolated
                    n.degrade = "QUORUM_LOST" if not n.partitioned else "PARTITION_SAFE"
            return OxytocinQuorumResult(
                agreed=False,
                oxytocin=0.0,
                votes=[],
                reason="insufficient_live_nodes",
                degrade="QUORUM_LOST",
            )

        vote_rates = votes or {n.node_id: 1.0 for n in live}
        ballot: list[OxytocinVote] = []
        for n in live:
            rate = float(vote_rates.get(n.node_id, 0.0))
            # Optional Byzantine-ish: very low rates count as reject
            accept = rate >= accept_threshold and rate >= byzantine_reject_below
            ballot.append(OxytocinVote(n.node_id, accept, rate))

        accepts = sum(1 for v in ballot if v.accept)
        need = max(1, int(len(ballot) * self.quorum_fraction + 0.999))  # ceil
        # majority: > 50% by default
        need = max(need, (len(ballot) // 2) + 1)
        if accepts >= need:
            oxy = sum(v.adapter_acceptance_rate for v in ballot if v.accept) / accepts
            # Apply to all live nodes
            for n in live:
                n.local_release(adapter_acceptance_rate=oxy, stress_load=0.0)
            return OxytocinQuorumResult(
                agreed=True, oxytocin=oxy, votes=ballot, reason="quorum_met"
            )
        return OxytocinQuorumResult(
            agreed=False,
            oxytocin=0.0,
            votes=ballot,
            reason="quorum_failed",
            degrade="QUORUM_LOST",
        )
