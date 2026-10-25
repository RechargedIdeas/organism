"""Organism Desktop — first-party control plane (v1.5)."""
from __future__ import annotations

__version__ = "1.5.0"

from organism_desktop.nav import PANELS, panel_ids
from organism_desktop.service import DesktopService, ActuationRefused

__all__ = ["DesktopService", "ActuationRefused", "PANELS", "panel_ids", "__version__"]
