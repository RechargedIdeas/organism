"""v1.3 — CPU-everywhere product guarantee (cpu:everywhere gate)."""
from __future__ import annotations

import os

import pytest

from organism_sdk.device import (
    CPU_HOSTABLE_HARDWARE,
    RuntimeId,
    assert_never_hard_fail_missing_gpu,
    cpu_can_host,
    prefer_accelerator,
    resolve_requires_gpu,
    select_compute_backend,
    torch_available,
)
from organism_sdk.neuro_sim import (
    CPU_RESEARCH_SIM_BACKEND,
    hardware_caps_with_sim,
    neuromorphic_cpu_backend,
    neuro_sim_enabled,
)


def test_default_selection_is_cpu(monkeypatch):
    monkeypatch.delenv("ORGANISM_BIO_GPU_TWIN", raising=False)
    monkeypatch.delenv("ORGANISM_PREFER_GPU", raising=False)
    sel = select_compute_backend()
    assert sel.runtime == RuntimeId.CPU_GENERAL
    assert sel.is_cpu
    assert sel.backend in {"numpy_cpu", "research_sim_cpu"}


def test_prefer_gpu_falls_back_to_cpu_without_cuda(monkeypatch):
    monkeypatch.setenv("ORGANISM_PREFER_GPU", "1")
    monkeypatch.setattr("organism_sdk.device.cuda_available", lambda: False)
    monkeypatch.setattr("organism_sdk.device.probe_accelerators", lambda: set())
    # Leave torch_available as real; either torch_cpu or numpy_cpu is fine
    sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)
    assert sel.runtime == RuntimeId.CPU_GENERAL
    assert sel.fallback_from == RuntimeId.GPU_CUDA
    assert sel.backend in {"numpy_cpu", "torch_cpu"}


def test_requires_gpu_never_raises():
    sel = resolve_requires_gpu(True)
    assert sel.runtime in {RuntimeId.CPU_GENERAL, RuntimeId.GPU_CUDA}
    # Must be a successful selection object, not an exception
    assert sel.backend


def test_cpu_can_host_all_research_hardware():
    for hw in CPU_HOSTABLE_HARDWARE:
        assert cpu_can_host(hw), hw
    assert cpu_can_host("NONE")
    assert cpu_can_host(None)
    assert cpu_can_host("HW_NEUROMORPHIC")


def test_neuromorphic_research_sim_is_cpu():
    sel = neuromorphic_cpu_backend()
    assert sel.runtime == RuntimeId.CPU_GENERAL
    assert sel.backend == CPU_RESEARCH_SIM_BACKEND or sel.backend == "research_sim_cpu"


def test_neuro_sim_caps_additive(monkeypatch):
    monkeypatch.delenv("ORGANISM_NEURO_SIM", raising=False)
    assert "NEUROMORPHIC" not in hardware_caps_with_sim({"NONE"})
    monkeypatch.setenv("ORGANISM_NEURO_SIM", "1")
    assert "NEUROMORPHIC" in hardware_caps_with_sim({"NONE"})
    assert neuro_sim_enabled()


def test_snn_spike_sim_runs_on_cpu_without_hw():
    from snn_sentinel.module import SNNSentinel
    from organism_sdk.workspace import WorkspaceClient

    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    snn = SNNSentinel(workspace=ws, hardware_present=False)
    assert snn.hardware_present is False
    result = snn.simulate_spikes(150.0)
    assert result["wake"] is True
    assert result["hardware_present"] is False
    assert "rate_hz" in result


def test_gpu_twin_wave_on_cpu_under_prefer(monkeypatch):
    monkeypatch.setenv("ORGANISM_BIO_DIGITAL_SIM", "1")
    monkeypatch.setenv("ORGANISM_BIO_GPU_TWIN", "1")
    from bio_digital.gpu_twin import GpuTwinSimulator

    r = GpuTwinSimulator(seed=3).run_wave_simulation(grid_size=10, iterations=2)
    assert r.backend in {"numpy_cpu", "torch_cpu", "torch_gpu"}
    assert r.research_sim is True
    assert r.affects_control is False
    if r.backend != "torch_gpu":
        assert r.runtime_id == "CPU_GENERAL"


def test_bio_modules_may_actuate_false():
    from bio_digital.slime_mold import SlimeMoldModule
    from bio_digital.mycelium import MyceliumModule

    for mod in (SlimeMoldModule(), MyceliumModule()):
        c = mod.declare_contract()
        assert c.safety.may_actuate is False


def test_missing_gpu_is_not_process_failure():
    assert_never_hard_fail_missing_gpu(None)
    sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)
    assert sel is not None


def test_prefer_accelerator_env(monkeypatch):
    monkeypatch.delenv("ORGANISM_BIO_GPU_TWIN", raising=False)
    monkeypatch.delenv("ORGANISM_PREFER_GPU", raising=False)
    assert prefer_accelerator() is False
    monkeypatch.setenv("ORGANISM_PREFER_GPU", "1")
    assert prefer_accelerator() is True


def test_torch_probe_is_bool():
    assert isinstance(torch_available(), bool)


def test_organism_torch_zero_forces_numpy(monkeypatch):
    monkeypatch.setenv("ORGANISM_TORCH", "0")
    monkeypatch.setenv("ORGANISM_PREFER_GPU", "1")
    from organism_sdk import device as dev

    assert dev.torch_opt_in_allowed() is False
    assert dev.torch_available() is False
    sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)
    assert sel.runtime == RuntimeId.CPU_GENERAL
    assert sel.backend == "numpy_cpu"


def test_prefer_gpu_with_mocked_no_cuda(monkeypatch):
    """Never skip: mock cuda absent even if box has GPU."""
    monkeypatch.setenv("ORGANISM_PREFER_GPU", "1")
    monkeypatch.setenv("ORGANISM_TORCH", "1")
    monkeypatch.setattr("organism_sdk.device.torch_available", lambda: True)
    monkeypatch.setattr("organism_sdk.device.cuda_available", lambda: False)
    monkeypatch.setattr("organism_sdk.device.probe_accelerators", lambda: set())
    sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)
    assert sel.runtime == RuntimeId.CPU_GENERAL
    assert sel.fallback_from == RuntimeId.GPU_CUDA
    assert sel.backend == "torch_cpu"


def test_prefer_gpu_with_mocked_cuda(monkeypatch):
    monkeypatch.setenv("ORGANISM_PREFER_GPU", "1")
    monkeypatch.setenv("ORGANISM_TORCH", "1")
    monkeypatch.setattr("organism_sdk.device.torch_available", lambda: True)
    monkeypatch.setattr("organism_sdk.device.cuda_available", lambda: True)
    monkeypatch.setattr(
        "organism_sdk.device.probe_accelerators",
        lambda: {RuntimeId.GPU_CUDA.value},
    )
    sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)
    assert sel.runtime == RuntimeId.GPU_CUDA
    assert sel.backend == "torch_cuda"
    assert sel.accelerator_present is True


def test_no_torch_mocked_stays_numpy(monkeypatch):
    monkeypatch.setenv("ORGANISM_PREFER_GPU", "1")
    monkeypatch.setattr("organism_sdk.device.torch_available", lambda: False)
    monkeypatch.setattr("organism_sdk.device.cuda_available", lambda: False)
    monkeypatch.setattr("organism_sdk.device.probe_accelerators", lambda: set())
    sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)
    assert sel.backend == "numpy_cpu"
    assert sel.runtime == RuntimeId.CPU_GENERAL


def test_accelerator_selection_summary_keys():
    from organism_sdk.device import accelerator_selection_summary

    s = accelerator_selection_summary()
    assert s["default_runtime"] == "CPU_GENERAL"
    assert "torch_available" in s
    assert "cuda_available" in s
    assert s["policy"] == "cuda_only_when_opt_in_and_present_else_cpu"
