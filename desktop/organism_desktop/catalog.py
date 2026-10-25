"""Available substrate module catalog for Desktop one-click register (v1.6).

RESEARCH_TIER modules are exploration / sim-only (never may_actuate=True via Desktop).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CatalogEntry:
    catalog_id: str
    module_id: str
    title: str
    package: str
    factory: str
    tier: str
    research_tier: bool
    may_actuate_declared: bool
    description: str
    promote: str = "DELIBERATION"


def _load(package: str, factory: str) -> Any:
    mod = __import__(package, fromlist=[factory])
    cls = getattr(mod, factory)
    return cls()


# Static catalog — CPU-safe factories only (no Hybrid / GPU required).
CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        catalog_id="deterministic_engine",
        module_id="deterministic_engine",
        title="Deterministic Engine",
        package="deterministic_engine.engine",
        factory="DeterministicEngine",
        tier="T0_DETERMINISTIC",
        research_tier=False,
        may_actuate_declared=True,
        description="Rulebook / governance primary for control_actuation",
        promote="DELIBERATION",
    ),
    CatalogEntry(
        catalog_id="learned_module",
        module_id="learned_module_t2",
        title="Learned Module (T2/T3)",
        package="learned_module.module",
        factory="LearnedModule",
        tier="T2_LEARNED_CALIBRATED",
        research_tier=False,
        may_actuate_declared=False,
        description="Conformal learned substrate; may_actuate=False",
        promote="DELIBERATION",
    ),
    CatalogEntry(
        catalog_id="hdc_module",
        module_id="hdc_module",
        title="HDC Module",
        package="hdc_module.module",
        factory="HDCModule",
        tier="T1_CALIBRATED_NONLEARNED",
        research_tier=False,
        may_actuate_declared=False,
        description="Hyperdimensional computing substrate",
    ),
    CatalogEntry(
        catalog_id="kernel_module",
        module_id="kernel_module",
        title="Kernel Module",
        package="kernel_module.module",
        factory="KernelModule",
        tier="T1_CALIBRATED_NONLEARNED",
        research_tier=False,
        may_actuate_declared=False,
        description="Ridge / kernel readout substrate",
    ),
    CatalogEntry(
        catalog_id="reservoir",
        module_id="reservoir",
        title="Reservoir",
        package="reservoir.module",
        factory="ReservoirModule",
        tier="T1_CALIBRATED_NONLEARNED",
        research_tier=False,
        may_actuate_declared=False,
        description="Echo-state / reservoir computing",
    ),
    CatalogEntry(
        catalog_id="spectral",
        module_id="spectral",
        title="Spectral",
        package="spectral.module",
        factory="SpectralModule",
        tier="T1_CALIBRATED_NONLEARNED",
        research_tier=False,
        may_actuate_declared=False,
        description="Spectral feature substrate",
    ),
    CatalogEntry(
        catalog_id="energy_hopfield",
        module_id="energy_hopfield",
        title="Energy Hopfield",
        package="energy_hopfield.module",
        factory="EnergyHopfieldModule",
        tier="T1_CALIBRATED_NONLEARNED",
        research_tier=False,
        may_actuate_declared=False,
        description="Energy-based Hopfield attractor",
    ),
    CatalogEntry(
        catalog_id="neurosymbolic",
        module_id="neurosymbolic",
        title="Neurosymbolic Verifier",
        package="neurosymbolic.module",
        factory="NeurosymbolicVerifier",
        tier="T0_DETERMINISTIC",
        research_tier=False,
        may_actuate_declared=False,
        description="Causal / three-level neurosymbolic verifier",
    ),
    CatalogEntry(
        catalog_id="snn_sentinel",
        module_id="snn_sentinel",
        title="SNN Sentinel",
        package="snn_sentinel.module",
        factory="SNNSentinel",
        tier="T1_CALIBRATED_NONLEARNED",
        research_tier=True,
        may_actuate_declared=False,
        description="Spiking sentinel — RESEARCH_SIM via ORGANISM_NEURO_SIM",
    ),
    CatalogEntry(
        catalog_id="generative_organism",
        module_id="generative_organism",
        title="Generative Evolution",
        package="generative.module",
        factory="GenerativeOrganismModule",
        tier="T3_LEARNED_UNCALIBRATED",
        research_tier=True,
        may_actuate_declared=False,
        description="Code/asset/skill evolution — RESEARCH_TIER until promote gates pass",
        promote="EXPLORATION",
    ),
    CatalogEntry(
        catalog_id="physical_research",
        module_id="physical_research",
        title="Physical Research",
        package="physical_research.module",
        factory="PhysicalResearchModule",
        tier="T3_LEARNED_UNCALIBRATED",
        research_tier=True,
        may_actuate_declared=False,
        description="RESEARCH_TIER molecular/physical twin — never actuates",
    ),
)


def catalog_as_dicts(
    *,
    registered_ids: set[str] | None = None,
    dynamic_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Static substrate catalog plus optional generative hot-registered entries."""
    reg = registered_ids or set()
    out: list[dict[str, Any]] = []
    for e in CATALOG:
        out.append(
            {
                "catalog_id": e.catalog_id,
                "module_id": e.module_id,
                "title": e.title,
                "tier": e.tier,
                "research_tier": e.research_tier,
                "research_badge": "RESEARCH_TIER" if e.research_tier else "",
                "may_actuate_declared": e.may_actuate_declared,
                "description": e.description,
                "registered": e.module_id in reg,
                "generative": e.catalog_id == "generative_organism",
            }
        )
    for d in dynamic_entries or []:
        row = dict(d)
        mid = str(row.get("module_id") or "")
        row.setdefault("registered", mid in reg)
        row.setdefault("generative", True)
        row.setdefault("research_badge", "RESEARCH_TIER" if row.get("research_tier", True) else "")
        out.append(row)
    return out


def instantiate(catalog_id: str) -> tuple[CatalogEntry, Any]:
    for e in CATALOG:
        if e.catalog_id == catalog_id:
            return e, _load(e.package, e.factory)
    raise KeyError(f"unknown catalog_id: {catalog_id}")


def find_entry(catalog_id: str) -> CatalogEntry | None:
    for e in CATALOG:
        if e.catalog_id == catalog_id:
            return e
    return None
