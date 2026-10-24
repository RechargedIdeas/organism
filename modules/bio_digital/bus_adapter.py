"""Map Hybrid ClusterMessage IPC onto declared Channels + VSA workspace.

Axiom 2: heartbeat / lifecycle stay on typed channels; SPIKE_TRAIN /
SPATIAL_GRAPH *results* must be written as workspace bindings.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.hypervector import Hypervector
from organism_sdk.trace import TraceEmitter, WorkspaceTraceEntry
from organism_sdk.workspace import BindingRecord, WorkspaceClient

from bio_digital.mycelium import MyceliumModule, MODULE_ID as MYCELIUM_ID
from bio_digital.slime_mold import SlimeMoldModule, MODULE_ID as SLIME_ID

CHANNEL_ONLY = frozenset(
    {"HEARTBEAT", "STATE_UPDATE", "PROMOTE", "DEMOTE", "SHUTDOWN"}
)


@dataclass
class ClusterMessageView:
    """Hybrid-compatible message view (no Hybrid import required)."""

    message_id: str
    source_node: str
    target_node: str
    payload_type: str
    data: list[float] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class BusRouteResult:
    channel_id: str
    workspace_binding_id: str | None
    result: Any
    logged: dict[str, Any]


class BioDigitalBusAdapter:
    """Routes Hybrid-style messages through Organism channels + workspace."""

    def __init__(
        self,
        *,
        workspace: WorkspaceClient | None = None,
        slime: SlimeMoldModule | None = None,
        mycelium: MyceliumModule | None = None,
        trace: TraceEmitter | None = None,
    ) -> None:
        self.ws = workspace or WorkspaceClient()
        self.slime = slime or SlimeMoldModule()
        self.mycelium = mycelium or MyceliumModule()
        self.trace = trace or TraceEmitter()
        self.channel_log: list[dict[str, Any]] = []

    def _channel_for(self, payload_type: str) -> str:
        mapping = {
            "HEARTBEAT": "bio_digital.ipc.heartbeat",
            "STATE_UPDATE": "bio_digital.ipc.lifecycle",
            "PROMOTE": "bio_digital.ipc.lifecycle",
            "DEMOTE": "bio_digital.ipc.lifecycle",
            "SHUTDOWN": "bio_digital.ipc.lifecycle",
            "EXECUTE_WORKLOAD": "bio_digital.ipc.workload",
            "SPIKE_TRAIN": "bio_digital.ipc.spike_train",
            "SPATIAL_GRAPH": "bio_digital.ipc.spatial_graph",
        }
        return mapping.get(payload_type, "bio_digital.ipc.unknown")

    def _write_result(
        self,
        *,
        module_id: str,
        tags: tuple[str, ...],
        payload: dict[str, Any],
    ) -> str:
        bid = uuid.uuid4()
        role = Hypervector.random(seed=(hash(module_id) ^ 0xB10) & 0xFFFFFFFF)
        filler = Hypervector.random(seed=(hash(tags[0]) ^ 0xD16) & 0xFFFFFFFF)
        rec = BindingRecord(
            binding_id=bid,
            hypervector=role.bind(filler),
            role=role,
            filler=filler,
            tags=tags,
            module_id=module_id,
            salience=1.0,
            fidelity="FULL",
            payload=payload,
            affects_control=False,
        ).with_checksum()
        wr = self.ws.write(rec)
        if wr.status != "ACCEPTED":
            raise RuntimeError(f"bio result write rejected: {wr.reason_code}")
        self.trace.emit_workspace(
            WorkspaceTraceEntry(
                operation="bio_digital_result",
                batch_id=str(bid),
                accepted=1,
                policy_id=module_id,
            )
        )
        return str(bid)

    def route(self, message: ClusterMessageView) -> BusRouteResult:
        channel_id = self._channel_for(message.payload_type)
        entry = {
            "channel_id": channel_id,
            "message_id": message.message_id,
            "payload_type": message.payload_type,
            "source": message.source_node,
            "target": message.target_node,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.channel_log.append(entry)

        result: Any = None
        binding_id: str | None = None

        if message.payload_type == "SPIKE_TRAIN":
            a = message.data[0] if message.data else 0.0
            b = message.data[1] if len(message.data) > 1 else 0.0
            result = self.slime.execute_logic_gate(a, b)
            binding_id = self._write_result(
                module_id=SLIME_ID,
                tags=("bio_slime_result", "exploration", "physical"),
                payload={
                    "payload_type": "SPIKE_TRAIN",
                    "inputs": [a, b],
                    "result": result,
                    "message_id": message.message_id,
                    "exploration_only": True,
                },
            )
        elif message.payload_type == "SPATIAL_GRAPH":
            result = self.mycelium.process_spike_train(list(message.data))
            binding_id = self._write_result(
                module_id=MYCELIUM_ID,
                tags=("bio_mycelium_result", "exploration", "physical"),
                payload={
                    "payload_type": "SPATIAL_GRAPH",
                    "spikes_out": result,
                    "message_id": message.message_id,
                    "exploration_only": True,
                },
            )
        elif message.payload_type == "EXECUTE_WORKLOAD":
            result = {"status": "accepted_exploration"}
            binding_id = self._write_result(
                module_id="bio_digital.bus",
                tags=("bio_workload", "exploration"),
                payload={
                    "payload_type": "EXECUTE_WORKLOAD",
                    "message_id": message.message_id,
                    "data": list(message.data),
                    "exploration_only": True,
                },
            )
        elif message.payload_type in CHANNEL_ONLY:
            result = {"channel_ack": True}
        else:
            result = {"ignored": True, "reason": "unknown_payload_type"}

        return BusRouteResult(
            channel_id=channel_id,
            workspace_binding_id=binding_id,
            result=result,
            logged=entry,
        )
