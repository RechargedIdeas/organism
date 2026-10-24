"""Species bio-limits mirrored from Hybrid shared models (no Qt deps)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BioLimits:
    min_temp_c: float
    max_temp_c: float
    min_humidity: float
    max_voltage: float
    co2_target_ppm: float


PHYSARUM_LIMITS = BioLimits(
    min_temp_c=20.0,
    max_temp_c=26.0,
    min_humidity=75.0,
    max_voltage=1.5,
    co2_target_ppm=400.0,
)

MYCELIUM_LIMITS = BioLimits(
    min_temp_c=18.0,
    max_temp_c=24.0,
    min_humidity=85.0,
    max_voltage=0.5,
    co2_target_ppm=800.0,
)

PHYSARUM_LOGIC_VOLTAGE = 1.2
MYCELIUM_SPIKE_THRESHOLD = 0.3
MYCELIUM_SYNAPTIC_WEIGHT = 1.25

SPECIES_PHYSARUM = "Physarum polycephalum"
SPECIES_MYCELIUM = "Pleurotus ostreatus"
