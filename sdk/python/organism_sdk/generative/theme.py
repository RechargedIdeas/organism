"""Desktop theme apply from Organism appearance palette (v1.8).

Looks promote → shell accents. Offscreen-safe: only QSS strings / widget
accents; never requires a display beyond Qt offscreen.
"""
from __future__ import annotations

from typing import Any


DEFAULT_PALETTE: dict[str, str] = {
    "primary": "#0a7a5c",
    "accent": "#3db8ff",
    "background": "#121212",
    "foreground": "#f2f2f2",
}


def normalize_palette(palette: dict[str, Any] | None) -> dict[str, str]:
    """Return a complete palette with hex colors; fall back to defaults."""
    src = dict(palette or {})
    out = dict(DEFAULT_PALETTE)
    for key in ("primary", "accent", "background", "foreground"):
        val = src.get(key)
        if isinstance(val, str) and val.startswith("#") and len(val) in (4, 7):
            out[key] = val
    return out


def shell_accent_qss(palette: dict[str, Any] | None) -> str:
    """QSS for MainWindow shell accents driven by Organism appearance."""
    p = normalize_palette(palette)
    return (
        f"QLabel#brand_sub {{ color: {p['accent']}; }}"
        f"QLabel#shell_cpu_badge {{"
        f" background:{p['primary']}; color:{p['foreground']};"
        f" font-weight:bold; padding:4px 8px; border-radius:4px;"
        f"}}"
        f"QListWidget#nav_list::item:selected {{"
        f" background:{p['primary']}; color:{p['foreground']};"
        f"}}"
        f"QListWidget#nav_list::item:hover {{"
        f" background:{p['accent']}; color:{p['background']};"
        f"}}"
        f"QStatusBar {{ color: {p['foreground']}; }}"
    )


def theme_apply_payload(appearance: dict[str, Any] | None) -> dict[str, Any]:
    """Service/Desktop payload after looks promote/apply."""
    appearance = appearance or {}
    palette = normalize_palette(appearance.get("palette"))
    return {
        "ok": True,
        "applied": True,
        "theme_id": appearance.get("theme_id"),
        "pack_id": appearance.get("pack_id"),
        "revision": appearance.get("revision"),
        "palette": palette,
        "qss": shell_accent_qss(palette),
        "cpu_everywhere": True,
        "may_actuate": False,
    }
