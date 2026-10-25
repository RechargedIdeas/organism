"""Panel widgets for Organism Desktop."""
from __future__ import annotations

from organism_desktop.panels.bio import BioPanel
from organism_desktop.panels.catalog import CatalogPanel
from organism_desktop.panels.contracts import ContractsPanel
from organism_desktop.panels.docs import DocsPanel
from organism_desktop.panels.home import HomePanel
from organism_desktop.panels.metamodel import MetamodelPanel
from organism_desktop.panels.ops import OpsPanel
from organism_desktop.panels.physiology import PhysiologyPanel
from organism_desktop.panels.pipelines import PipelinesPanel
from organism_desktop.panels.registry import RegistryPanel
from organism_desktop.panels.traces import TracesPanel
from organism_desktop.panels.workspace import WorkspacePanel

PANEL_CLASSES = {
    "home": HomePanel,
    "registry": RegistryPanel,
    "catalog": CatalogPanel,
    "workspace": WorkspacePanel,
    "pipelines": PipelinesPanel,
    "physiology": PhysiologyPanel,
    "metamodel": MetamodelPanel,
    "bio": BioPanel,
    "traces": TracesPanel,
    "contracts": ContractsPanel,
    "ops": OpsPanel,
    "docs": DocsPanel,
}

__all__ = ["PANEL_CLASSES"]
