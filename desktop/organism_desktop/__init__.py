"""Organism Desktop — first-party control plane (v1.10.0)."""
from __future__ import annotations

__version__ = "1.10.0"

from organism_desktop.nav import PANELS, panel_ids
from organism_desktop.service import DESKTOP_VERSION, ActuationRefused, DesktopService

__all__ = [
    "DESKTOP_VERSION",
    "PANELS",
    "ActuationRefused",
    "DesktopService",
    "__version__",
    "panel_ids",
]
