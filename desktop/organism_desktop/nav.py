"""Stable panel registry for navigation and tests."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PanelSpec:
    id: str
    title: str
    description: str


PANELS: tuple[PanelSpec, ...] = (
    PanelSpec("home", "Home / Status", "Version, CPU backend, degradation, serve status"),
    PanelSpec("registry", "Substrate Registry", "Modules, contracts, health, may_actuate"),
    PanelSpec("workspace", "Workspace", "Bindings, capability-scoped R/W, hypervector viz"),
    PanelSpec("pipelines", "Router / Pipelines", "TaskDescriptor → DispatchPlan + traces"),
    PanelSpec("physiology", "Physiology", "Degradation, hormones, immune, autonomic"),
    PanelSpec("metamodel", "Metamodel", "Synthesize → sandbox → shadow → promote"),
    PanelSpec("bio", "Bio-Digital", "Slime / mycelium / HAL — exploration only"),
    PanelSpec("traces", "Traces / Replay", "Decision traces and snapshot replay"),
    PanelSpec("ops", "Ops", "Config validate, soak, CPU Everywhere, wet-lab policy"),
    PanelSpec("docs", "Docs / Help", "CPU Everywhere, soak runbook, API freeze"),
)


def panel_ids() -> list[str]:
    return [p.id for p in PANELS]
