"""Bio-Digital Hybrid Cluster adapters for Organism (v1.2).

Maps Physarum / Mycelium RESEARCH_TIER substrates from
https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster
into Organism SubstrateContracts. Exploration-only; never control actuation.

Live import via BIO_DIGITAL_HYBRID_ROOT (see vendor_loader / VENDOR.md).
See docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md.
"""
from __future__ import annotations

from bio_digital.slime_mold import SlimeMoldModule, MODULE_ID as SLIME_MOLD_ID
from bio_digital.mycelium import MyceliumModule, MODULE_ID as MYCELIUM_ID
from bio_digital.hal import BioDigitalHAL, research_sim_enabled, RUNTIME_RESEARCH_SIM
from bio_digital.bus_adapter import BioDigitalBusAdapter, ClusterMessageView
from bio_digital.twin_bridge import TwinBridge
from bio_digital.hypervisor_map import DrainPolicy, HypervisorMapper
from bio_digital.vendor_loader import load_hybrid, resolve_hybrid_root, hybrid_root_present
from bio_digital.telemetry_bridge import TelemetryBridge, NodeStatusView, EnvironmentStateView

__all__ = [
    "SlimeMoldModule",
    "MyceliumModule",
    "SLIME_MOLD_ID",
    "MYCELIUM_ID",
    "BioDigitalHAL",
    "research_sim_enabled",
    "RUNTIME_RESEARCH_SIM",
    "BioDigitalBusAdapter",
    "ClusterMessageView",
    "TwinBridge",
    "DrainPolicy",
    "HypervisorMapper",
    "load_hybrid",
    "resolve_hybrid_root",
    "hybrid_root_present",
    "TelemetryBridge",
    "NodeStatusView",
    "EnvironmentStateView",
]
