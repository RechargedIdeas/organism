"""Digital-twin telemetry → workspace bindings + optional hormone window feed."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from organism_sdk.hormone import HormoneBus
from organism_sdk.hypervector import Hypervector
from organism_sdk.trace import TraceEmitter, WorkspaceTraceEntry
from organism_sdk.workspace import BindingRecord, WorkspaceClient

from bio_digital.hal import BioDigitalHAL

BIO_TWIN_TAG = "bio_twin"


@dataclass
class TwinWindow:
    window_id: str
    payload: dict[str, Any]
    binding_id: str
    stress: float


class TwinBridge:
    """Writes HAL/sim twin samples into workspace; may feed HormoneBus stress."""

    def __init__(
        self,
        *,
        workspace: WorkspaceClient | None = None,
        hormone: HormoneBus | None = None,
        trace: TraceEmitter | None = None,
    ) -> None:
        self.ws = workspace or WorkspaceClient()
        self.hormone = hormone
        self.trace = trace or TraceEmitter()
        self.windows: list[TwinWindow] = []

    def publish(
        self,
        hal: BioDigitalHAL,
        *,
        module_id: str,
        extra: dict[str, Any] | None = None,
        feed_hormone: bool = False,
    ) -> TwinWindow:
        twin = hal.sample_twin()
        if extra:
            twin = {**twin, **extra}
        env_ok = bool(twin.get("is_healthy", True))
        stress = 0.0 if env_ok else 0.85
        twin["stress"] = stress
        twin["exploration_only"] = True
        twin["affects_control"] = False

        window_id = f"bio-twin-{uuid.uuid4().hex[:10]}"
        bid = uuid.uuid4()
        payload = {"window_id": window_id, "twin": twin, "module_id": module_id}
        role = Hypervector.random(seed=(hash(window_id) ^ 0x7A11) & 0xFFFFFFFF)
        filler = Hypervector.random(seed=(hash(module_id) ^ 0xB10D) & 0xFFFFFFFF)
        rec = BindingRecord(
            binding_id=bid,
            hypervector=role.bind(filler),
            role=role,
            filler=filler,
            tags=(BIO_TWIN_TAG, "physical", "exploration"),
            module_id=module_id,
            salience=1.0,
            fidelity="FULL",
            payload=payload,
            affects_control=False,
        ).with_checksum()
        wr = self.ws.write(rec)
        if wr.status != "ACCEPTED":
            raise RuntimeError(f"bio_twin write rejected: {wr.reason_code}")
        self.trace.emit_workspace(
            WorkspaceTraceEntry(
                operation="bio_twin_window",
                batch_id=str(bid),
                accepted=1,
                policy_id=module_id,
            )
        )

        if feed_hormone and self.hormone is not None:
            levels = self.hormone.compute_release(
                stress_load=stress,
                viability_score=1.0 if env_ok else 0.2,
                crisis_precursor_count=1.0 if stress > 0 else 0.0,
                source=module_id,
            )
            # Override window id for correlating twin ↔ hormone
            levels.window_id = window_id
            self.hormone.write_telemetry_window(levels)

        tw = TwinWindow(window_id=window_id, payload=payload, binding_id=str(bid), stress=stress)
        self.windows.append(tw)
        return tw
