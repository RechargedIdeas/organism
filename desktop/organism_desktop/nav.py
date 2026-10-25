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
    PanelSpec("catalog", "Module Catalog", "Available substrates · RESEARCH_TIER · one-click register"),
    PanelSpec("workspace", "Workspace", "Bindings, capability-scoped R/W, hypervector viz"),
    PanelSpec("pipelines", "Router / Pipelines", "TaskDescriptor → DispatchPlan + plan inspector"),
    PanelSpec("physiology", "Physiology", "Degradation, hormones, immune, autonomic"),
    PanelSpec("metamodel", "Metamodel", "Synthesize → sandbox → shadow → promote"),
    PanelSpec(
        "organism",
        "Organism Evolution",
        "Evolve skills / looks / code promotions / evolution log",
    ),
    PanelSpec("bio", "Bio-Digital", "Slime / mycelium / HAL — exploration only"),
    PanelSpec("traces", "Traces / Replay", "Filterable explorer · export JSON · jump from pipeline"),
    PanelSpec("contracts", "Contracts / Assert", "Last SubstrateContract.validate() results"),
    PanelSpec("ops", "Ops", "Multi-profile deploy, soak, CPU Everywhere, wet-lab policy"),
    PanelSpec("docs", "Docs / Help", "CPU Everywhere, soak runbook, API freeze, packaging"),
)


def panel_ids() -> list[str]:
    return [p.id for p in PANELS]
