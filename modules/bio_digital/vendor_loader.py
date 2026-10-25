"""Resolve and optionally import Bio-Digital Hybrid Cluster (live path).

When BIO_DIGITAL_HYBRID_ROOT points at a checkout (default
/workspace/Bio-Digital_Hybrid_Cluster if that directory exists), load real
Hybrid HAL / slime_mold / mycelium modules. Otherwise fall back to Organism
stubs so the default suite never requires Hybrid.

Hybrid `src.shared.constants` imports PySide6 only for Qt color constants used
by Studio. Organism never needs Studio; if PySide6 is absent we install a
minimal QColor shim so core (HAL, slime, mycelium, models, metrics) can import.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_HYBRID_ROOT = Path("/workspace/Bio-Digital_Hybrid_Cluster")


def resolve_hybrid_root() -> Path | None:
    """Return Hybrid checkout path or None if unavailable."""
    raw = os.environ.get("BIO_DIGITAL_HYBRID_ROOT", "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        return p if p.is_dir() else None
    if DEFAULT_HYBRID_ROOT.is_dir():
        return DEFAULT_HYBRID_ROOT.resolve()
    return None


def hybrid_root_present() -> bool:
    return resolve_hybrid_root() is not None


def _ensure_pyside6_shim() -> bool:
    """Install a tiny PySide6.QtGui.QColor shim if real PySide6 is missing.

    Returns True if a shim was installed, False if real PySide6 is available.
    """
    try:
        import PySide6  # noqa: F401
        return False
    except ImportError:
        pass

    class _QColor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QColor = _QColor  # type: ignore[attr-defined]
    pyside = types.ModuleType("PySide6")
    pyside.QtGui = qtgui  # type: ignore[attr-defined]
    sys.modules.setdefault("PySide6", pyside)
    sys.modules.setdefault("PySide6.QtGui", qtgui)
    return True


def _fast_delays_enabled() -> bool:
    """Skip Hybrid wall-clock biology sleeps unless real delays requested."""
    v = os.environ.get("ORGANISM_BIO_DIGITAL_REAL_DELAYS", "0").strip().lower()
    return v not in {"1", "true", "yes", "on"}


def _patch_hybrid_delays(root: Path) -> None:
    if not _fast_delays_enabled():
        return
    # Patch both constants module and already-bound names on species modules.
    try:
        const = importlib.import_module("src.shared.constants")
        const.PHYSARUM_WAVE_PROPAGATION_DELAY = 0.0
        const.MYCELIUM_PROPAGATION_DELAY = 0.0
    except Exception:
        return
    for mod_name in ("src.core.slime_mold", "src.core.mycelium"):
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "PHYSARUM_WAVE_PROPAGATION_DELAY"):
                mod.PHYSARUM_WAVE_PROPAGATION_DELAY = 0.0
            if hasattr(mod, "MYCELIUM_PROPAGATION_DELAY"):
                mod.MYCELIUM_PROPAGATION_DELAY = 0.0
        except Exception:
            continue


@dataclass
class HybridBundle:
    """Loaded Hybrid symbols or stub mode marker."""

    mode: str  # "live" | "stub"
    root: Path | None
    shimmed_pyside6: bool = False
    SimulatedSensorSubsystem: Any = None
    SimulatedGalvanicActuator: Any = None
    SlimeMoldNode: Any = None
    MyceliumNode: Any = None
    EnvironmentState: Any = None
    NodeStatus: Any = None
    BioLimits: Any = None
    metrics_mod: Any = None
    error: str | None = None

    @property
    def is_live(self) -> bool:
        return self.mode == "live"


_CACHE: HybridBundle | None = None


def clear_hybrid_cache() -> None:
    global _CACHE
    _CACHE = None


def load_hybrid(*, force_reload: bool = False) -> HybridBundle:
    """Import Hybrid core when root present; else stub bundle."""
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE

    root = resolve_hybrid_root()
    if root is None:
        _CACHE = HybridBundle(mode="stub", root=None, error="hybrid_root_missing")
        return _CACHE

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    shimmed = _ensure_pyside6_shim()
    try:
        from src.core.hal import (  # type: ignore
            SimulatedGalvanicActuator,
            SimulatedSensorSubsystem,
        )
        from src.core.slime_mold import SlimeMoldNode  # type: ignore
        from src.core.mycelium import MyceliumNode  # type: ignore
        from src.shared.models import BioLimits, EnvironmentState, NodeStatus  # type: ignore
        from src.api import metrics as metrics_mod  # type: ignore
    except Exception as exc:
        _CACHE = HybridBundle(
            mode="stub",
            root=root,
            shimmed_pyside6=shimmed,
            error=f"hybrid_import_failed:{type(exc).__name__}:{exc}",
        )
        return _CACHE

    _patch_hybrid_delays(root)
    _CACHE = HybridBundle(
        mode="live",
        root=root,
        shimmed_pyside6=shimmed,
        SimulatedSensorSubsystem=SimulatedSensorSubsystem,
        SimulatedGalvanicActuator=SimulatedGalvanicActuator,
        SlimeMoldNode=SlimeMoldNode,
        MyceliumNode=MyceliumNode,
        EnvironmentState=EnvironmentState,
        NodeStatus=NodeStatus,
        BioLimits=BioLimits,
        metrics_mod=metrics_mod,
    )
    return _CACHE
