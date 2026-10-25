"""Phase 4 — optional GPU twin gated; CPU HAL twin always works."""
from __future__ import annotations

import pytest

from bio_digital.gpu_twin import (
    GpuTwinSimulator,
    gpu_twin_enabled,
    torch_available,
)


def test_cpu_hal_twin_default(monkeypatch):
    monkeypatch.delenv("ORGANISM_BIO_GPU_TWIN", raising=False)
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    assert gpu_twin_enabled() is False
    sim = GpuTwinSimulator(seed=1)
    result = sim.run_wave_simulation(grid_size=16, iterations=3)
    assert result.backend == "cpu_hal"
    assert result.research_sim is True
    assert result.affects_control is False
    assert result.exploration_only is True
    assert result.devices_used == 1
    assert result.mean_bio_density >= 0.0


def test_gpu_path_gated_without_opt_in(monkeypatch):
    monkeypatch.delenv("ORGANISM_BIO_GPU_TWIN", raising=False)
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    sim = GpuTwinSimulator()
    r = sim.run_wave_simulation(iterations=2)
    assert r.backend != "torch_gpu" or gpu_twin_enabled()
    # Without opt-in we must not require torch
    assert r.backend == "cpu_hal"


def test_gpu_path_gated_when_sim_disabled(monkeypatch):
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "0")
    monkeypatch.setenv("ORGANISM_BIO_GPU_TWIN", "1")
    sim = GpuTwinSimulator()
    r = sim.run_wave_simulation(iterations=1)
    assert r.backend == "gated"
    assert r.research_sim is False
    assert r.affects_control is False


def test_torch_path_when_available_and_enabled(monkeypatch):
    if not torch_available():
        pytest.skip("torch not installed — GPU path skip-clean")
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    monkeypatch.setenv("ORGANISM_BIO_GPU_TWIN", "1")
    assert gpu_twin_enabled()
    sim = GpuTwinSimulator(seed=0)
    r = sim.run_wave_simulation(grid_size=16, iterations=2)
    assert r.backend in {"torch_cpu", "torch_gpu"}
    assert r.research_sim is True
    assert r.affects_control is False
    assert r.devices_used >= 1


def test_torch_unavailable_reports_cleanly():
    # Document skip-clean: torch_available is a pure probe
    avail = torch_available()
    assert isinstance(avail, bool)
