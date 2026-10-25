"""Shared status facts for CLI (`organism status`) and Desktop Home/Ops.

Both surfaces must agree on these config/runtime keys so operators can
cross-check `organism status` JSON against Desktop without drift.
"""
from __future__ import annotations

from typing import Any

from organism_sdk import __version__ as organism_version
from organism_sdk.device import accelerator_selection_summary, select_compute_backend
from organism_sdk.deploy.stack import MinimalStack

# Keys that CLI status and Desktop home_status must share (same values
# for the same DeployConfig before Desktop-only bio registration).
PARITY_KEYS: tuple[str, ...] = (
    "ok",
    "profile",
    "version",
    "organism_version",
    "cpu_everywhere",
    "prefer_gpu",
    "health_host",
    "health_port",
    "device_runtime",
    "device_backend",
)


def common_status_facts(stack: MinimalStack) -> dict[str, Any]:
    """Facts derived only from MinimalStack + device selection (no Desktop extras)."""
    st = stack.status()
    device = st.get("device") or {}
    if not device:
        device = select_compute_backend().as_dict()
    return {
        "ok": bool(st.get("ok", True)),
        "profile": st.get("profile"),
        "version": st.get("version"),
        "organism_version": organism_version,
        "cpu_everywhere": True,
        "prefer_gpu": st.get("prefer_gpu", False),
        "health_host": st.get("health_host"),
        "health_port": st.get("health_port"),
        "device": device,
        "device_runtime": device.get("runtime"),
        "device_backend": device.get("backend"),
        "router_level_config": st.get("router_level"),
        "module_count": st.get("module_count"),
        "workspace_bindings": st.get("workspace_bindings"),
        "accelerator_summary": accelerator_selection_summary(),
        "registered_ids": list(st.get("registered_ids") or []),
    }


def enrich_cli_status(stack: MinimalStack) -> dict[str, Any]:
    """Full CLI `organism status` payload: stack.status() + shared parity fields."""
    base = dict(stack.status())
    common = common_status_facts(stack)
    # Overlay shared keys without dropping stack-only fields (modules list, etc.).
    for k, v in common.items():
        if k == "device" and base.get("device"):
            continue
        base[k] = v
    return base
