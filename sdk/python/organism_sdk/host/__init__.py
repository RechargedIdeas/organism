"""Host environment detection — bare metal / VM / container (Docker optional)."""
from __future__ import annotations

from organism_sdk.host.detect import (
    HOST_KINDS,
    HostFacts,
    detect_host,
    host_kind_label,
)

__all__ = [
    "HOST_KINDS",
    "HostFacts",
    "detect_host",
    "host_kind_label",
]
