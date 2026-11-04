"""Bio-Digital Hybrid Cluster adapters for Organism (v1.4).

Maps Physarum / Mycelium RESEARCH_TIER substrates from
https://github.com/Recharged-Ideas/Bio-Digital_Hybrid_Cluster
into Organism SubstrateContracts. Exploration-only; never control actuation.

Live import via BIO_DIGITAL_HYBRID_ROOT (see vendor_loader / VENDOR.md).
See docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md.
"""
from __future__ import annotations

from bio_digital.bus_adapter import BioDigitalBusAdapter, ClusterMessageView
from bio_digital.gpu_twin import GpuTwinSimulator, gpu_twin_enabled, run_numpy_wave, torch_available
from bio_digital.hal import RUNTIME_RESEARCH_SIM, BioDigitalHAL, research_sim_enabled
from bio_digital.hypervisor_map import DrainPolicy, HypervisorMapper
from bio_digital.mycelium import MODULE_ID as MYCELIUM_ID
from bio_digital.mycelium import MyceliumModule
from bio_digital.slime_mold import MODULE_ID as SLIME_MOLD_ID
from bio_digital.slime_mold import SlimeMoldModule
from bio_digital.telemetry_bridge import EnvironmentStateView, NodeStatusView, TelemetryBridge
from bio_digital.twin_bridge import TwinBridge
from bio_digital.vendor_loader import hybrid_root_present, load_hybrid, resolve_hybrid_root

__all__ = [
    "MYCELIUM_ID",
    "RUNTIME_RESEARCH_SIM",
    "SLIME_MOLD_ID",
    "BioDigitalBusAdapter",
    "BioDigitalHAL",
    "ClusterMessageView",
    "DrainPolicy",
    "EnvironmentStateView",
    "GpuTwinSimulator",
    "HypervisorMapper",
    "MyceliumModule",
    "NodeStatusView",
    "SlimeMoldModule",
    "TelemetryBridge",
    "TwinBridge",
    "gpu_twin_enabled",
    "hybrid_root_present",
    "load_hybrid",
    "research_sim_enabled",
    "resolve_hybrid_root",
    "run_numpy_wave",
    "torch_available",
]

# v1.4 wet-lab stub (import bio_digital.wetlab explicitly)
