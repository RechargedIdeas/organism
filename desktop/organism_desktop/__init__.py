"""Organism Desktop — first-party control plane (v1.6)."""
from __future__ import annotations

__version__ = "1.6.1"

from organism_desktop.nav import PANELS, panel_ids
from organism_desktop.service import ActuationRefused, DESKTOP_VERSION, DesktopService

__all__ = [
    "DesktopService",
    "ActuationRefused",
    "DESKTOP_VERSION",
    "PANELS",
    "panel_ids",
    "__version__",
]
