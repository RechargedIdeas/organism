"""PerceptionInput multi-modality — A3.1 + E-2."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from organism_sdk.contract import DataType, Modality
from organism_sdk.errors import ModalityUnavailable

if TYPE_CHECKING:
    from organism_sdk.workspace import WorkspaceReader


@dataclass(frozen=True)
class ModalityPayload:
    modality: Modality
    shape: tuple[int, ...]
    dtype: DataType
    data: bytes


@dataclass(frozen=True)
class TaskDescriptor:
    """C.2 TaskDescriptor (subset needed by modules); submitted_at is R-2."""

    task_id: str
    form: str  # e.g. pattern_recognition, control_actuation
    safety_tier: str  # research|low|medium|high|critical
    deadline_ms: int
    submitted_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)
    requires_interpretability: bool = False


@dataclass(frozen=True)
class PerceptionInput:
    modalities: dict[Modality, ModalityPayload]
    task_descriptor: TaskDescriptor
    workspace_reader: Any  # WorkspaceReader; capability-scoped
    deadline_remaining_ms: float
    required_modalities: tuple[Modality, ...] = ()

    def require(self, modality: Modality) -> ModalityPayload:
        if modality not in self.modalities:
            required = modality in self.required_modalities
            raise ModalityUnavailable(modality.value, required=required)
        return self.modalities[modality]

    def get(self, modality: Modality) -> ModalityPayload | None:
        return self.modalities.get(modality)
