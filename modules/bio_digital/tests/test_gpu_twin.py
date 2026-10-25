"""Wave twin — CPU always; GPU prefer-only; no torch skip (v1.3)."""
from __future__ import annotations

from bio_digital.gpu_twin import (
    GpuTwinSimulator,
    gpu_twin_enabled,
    run_numpy_wave,
    torch_available,
)


def test_numpy_cpu_wave_default(monkeypatch):
    monkeypatch.delenv("ORGANISM_BIO_GPU_TWIN", raising=False)
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    assert gpu_twin_enabled() is False
    sim = GpuTwinSimulator(seed=1)
    result = sim.run_wave_simulation(grid_size=16, iterations=3)
    assert result.backend == "numpy_cpu"
    assert result.runtime_id == "CPU_GENERAL"
    assert result.research_sim is True
    assert result.affects_control is False
    assert result.exploration_only is True
    assert result.devices_used == 1
    assert result.mean_bio_density >= 0.0


def test_gpu_labelled_workload_runs_on_cpu_without_torch(monkeypatch):
    """ORGANISM_BIO_GPU_TWIN=1 without torch → same wave on numpy_cpu, never skip."""
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    monkeypatch.setenv("ORGANISM_BIO_GPU_TWIN", "1")
    assert gpu_twin_enabled()
    sim = GpuTwinSimulator(seed=0)
    # Force the torch-labelled path; without torch must fall back to numpy
    r = sim.run_wave_simulation(grid_size=16, iterations=2, force_backend="torch_gpu")
    if torch_available():
        assert r.backend in {"torch_cpu", "torch_gpu", "numpy_cpu"}
    else:
        assert r.backend == "numpy_cpu"
        assert r.fallback_from == "GPU_CUDA"
    assert r.research_sim is True
    assert r.affects_control is False
    assert r.devices_used >= 1


def test_opt_in_auto_selects_cpu_when_no_accelerator(monkeypatch):
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    monkeypatch.setenv("ORGANISM_BIO_GPU_TWIN", "1")
    sim = GpuTwinSimulator(seed=7)
    r = sim.run_wave_simulation(grid_size=12, iterations=2)
    assert r.backend in {"numpy_cpu", "torch_cpu", "torch_gpu"}
    assert r.research_sim is True
    # Without real CUDA we must land on CPU runtime
    if r.backend != "torch_gpu":
        assert r.runtime_id == "CPU_GENERAL"


def test_gpu_path_gated_when_sim_disabled(monkeypatch):
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "0")
    monkeypatch.setenv("ORGANISM_BIO_GPU_TWIN", "1")
    sim = GpuTwinSimulator()
    r = sim.run_wave_simulation(iterations=1)
    assert r.backend == "gated"
    assert r.research_sim is False
    assert r.affects_control is False


def test_cpu_hal_force_backend(monkeypatch):
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    sim = GpuTwinSimulator(seed=1)
    r = sim.run_wave_simulation(iterations=2, force_backend="cpu_hal")
    assert r.backend == "cpu_hal"
    assert r.runtime_id == "CPU_GENERAL"


def test_numpy_wave_math_deterministic():
    t1, m1 = run_numpy_wave(grid_size=8, iterations=3, seed=99)
    t2, m2 = run_numpy_wave(grid_size=8, iterations=3, seed=99)
    assert m1 == m2
    assert t1 >= 0.0 and t2 >= 0.0


def test_torch_available_is_probe_not_requirement():
    avail = torch_available()
    assert isinstance(avail, bool)
    # Probe must not be a gate — suite runs either way
