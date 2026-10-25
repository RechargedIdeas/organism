"""Wave twin — GPU-labelled workload with mandatory CPU fallback (v1.3).

Same diffusion math on every backend:
  - ``torch_gpu``  — torch + CUDA when ``ORGANISM_BIO_GPU_TWIN=1`` and CUDA present
  - ``torch_cpu``  — torch on CPU when opted in and torch installed without CUDA
  - ``numpy_cpu``  — pure NumPy (default / no-torch path); **always** available
  - ``cpu_hal``    — lightweight HAL stub (explicit backend request)
  - ``gated``      — RESEARCH_SIM disabled

Product guarantee (``docs/CPU_EVERYWHERE.md``): missing torch/CUDA never skips
the wave workload and never hard-fails the process. Bio remains exploration-only.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

import numpy as np

from bio_digital.hal import BioDigitalHAL, research_sim_enabled
from bio_digital.limits import PHYSARUM_LIMITS
from organism_sdk.device import (
    RuntimeId,
    cuda_available,
    select_compute_backend,
    torch_available,
)

# 3x3 diffusion kernel (center 0.2, neighbors 0.1) — shared by numpy + torch
DIFFUSION_KERNEL = np.array(
    [[0.1, 0.1, 0.1], [0.1, 0.2, 0.1], [0.1, 0.1, 0.1]], dtype=np.float64
)

BackendName = Literal["torch_gpu", "torch_cpu", "numpy_cpu", "cpu_hal", "gated"]


def gpu_twin_enabled() -> bool:
    """Opt-in preference for accelerator backends; still requires RESEARCH_SIM."""
    if not research_sim_enabled():
        return False
    v = os.environ.get("ORGANISM_BIO_GPU_TWIN", "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


@dataclass
class TwinSimResult:
    execution_time_sec: float
    mean_bio_density: float
    devices_used: int
    backend: str  # BackendName
    research_sim: bool
    affects_control: bool = False
    exploration_only: bool = True
    runtime_id: str = "CPU_GENERAL"
    preferred_runtime: str = "CPU_GENERAL"
    fallback_from: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_time_sec": self.execution_time_sec,
            "mean_bio_density": self.mean_bio_density,
            "devices_used": self.devices_used,
            "backend": self.backend,
            "research_sim": self.research_sim,
            "affects_control": self.affects_control,
            "exploration_only": self.exploration_only,
            "runtime_id": self.runtime_id,
            "preferred_runtime": self.preferred_runtime,
            "fallback_from": self.fallback_from,
        }


def _replicate_pad2d(grid: np.ndarray) -> np.ndarray:
    """Pad H×W by 1 on each side with edge replicate (matches F.pad replicate)."""
    return np.pad(grid, ((1, 1), (1, 1)), mode="edge")


def _conv2d_diffusion(grid: np.ndarray, kernel: np.ndarray = DIFFUSION_KERNEL) -> np.ndarray:
    padded = _replicate_pad2d(grid)
    h, w = grid.shape
    out = np.zeros_like(grid)
    for i in range(h):
        for j in range(w):
            out[i, j] = float(np.sum(padded[i : i + 3, j : j + 3] * kernel))
    return out


def run_numpy_wave(
    *,
    grid_size: int = 32,
    iterations: int = 4,
    seed: int = 42,
    progress_callback: Callable[[int, str], None] | None = None,
) -> tuple[float, float]:
    """Same diffusion wave as the torch path, on CPU via NumPy."""
    cb = progress_callback or (lambda _p, _m: None)
    rng = np.random.default_rng(seed)
    grid = rng.random((grid_size, grid_size), dtype=np.float64)
    start = time.time()
    for step in range(max(1, iterations)):
        grid = _conv2d_diffusion(grid)
        cb(int((step + 1) / max(1, iterations) * 100), f"numpy_cpu step {step+1}/{iterations}")
    return round(time.time() - start, 4), float(grid.mean())


class GpuTwinSimulator:
    """RESEARCH_SIM wave twin — CPU always; GPU preferred only when opted in + present."""

    def __init__(self, *, seed: int = 42) -> None:
        self.seed = seed
        self.is_running = False

    def run_wave_simulation(
        self,
        grid_size: int = 32,
        iterations: int = 4,
        progress_callback: Callable[[int, str], None] | None = None,
        *,
        force_backend: BackendName | None = None,
    ) -> TwinSimResult:
        cb = progress_callback or (lambda _p, _m: None)
        if not research_sim_enabled():
            return TwinSimResult(
                execution_time_sec=0.0,
                mean_bio_density=0.0,
                devices_used=0,
                backend="gated",
                research_sim=False,
                runtime_id="CPU_GENERAL",
            )

        if force_backend == "cpu_hal":
            return self._run_cpu_hal(grid_size, iterations, cb)
        if force_backend == "numpy_cpu":
            return self._run_numpy(grid_size, iterations, cb, preferred=RuntimeId.CPU_GENERAL)
        if force_backend in {"torch_cpu", "torch_gpu"}:
            if torch_available():
                return self._run_torch(grid_size, iterations, cb, force_cpu=(force_backend == "torch_cpu"))
            # Same workload on numpy — never skip
            return self._run_numpy(
                grid_size,
                iterations,
                cb,
                preferred=RuntimeId.GPU_CUDA,
                fallback_from=RuntimeId.GPU_CUDA,
            )

        # Auto-select: prefer GPU only when opted in
        selection = select_compute_backend(
            prefer=RuntimeId.GPU_CUDA if gpu_twin_enabled() else RuntimeId.CPU_GENERAL,
            prefer_gpu=gpu_twin_enabled(),
        )
        if selection.backend == "torch_cuda":
            return self._run_torch(grid_size, iterations, cb, force_cpu=False)
        if selection.backend == "torch_cpu" and torch_available():
            return self._run_torch(grid_size, iterations, cb, force_cpu=True)
        # Default / no-torch / no-cuda: same wave on NumPy
        return self._run_numpy(
            grid_size,
            iterations,
            cb,
            preferred=selection.preferred,
            fallback_from=selection.fallback_from,
        )

    def _run_numpy(
        self,
        grid_size: int,
        iterations: int,
        cb: Callable[[int, str], None],
        *,
        preferred: RuntimeId = RuntimeId.CPU_GENERAL,
        fallback_from: RuntimeId | None = None,
    ) -> TwinSimResult:
        self.is_running = True
        elapsed, mean_density = run_numpy_wave(
            grid_size=grid_size,
            iterations=iterations,
            seed=self.seed,
            progress_callback=cb,
        )
        self.is_running = False
        return TwinSimResult(
            execution_time_sec=elapsed,
            mean_bio_density=round(mean_density, 4),
            devices_used=1,
            backend="numpy_cpu",
            research_sim=True,
            runtime_id=RuntimeId.CPU_GENERAL.value,
            preferred_runtime=preferred.value,
            fallback_from=fallback_from.value if fallback_from else None,
        )

    def _run_cpu_hal(
        self,
        grid_size: int,
        iterations: int,
        cb: Callable[[int, str], None],
    ) -> TwinSimResult:
        self.is_running = True
        start = time.time()
        hal = BioDigitalHAL(PHYSARUM_LIMITS, node_id="gpu-twin-cpu", backend="stub")
        density = 0.0
        for step in range(max(1, iterations)):
            if not self.is_running:
                break
            vol = 0.2 + 0.05 * (step % 3)
            try:
                hal.apply_potential("WAVE", min(vol, PHYSARUM_LIMITS.max_voltage))
            except ValueError:
                pass
            env = hal.read_telemetry()
            density = (density + (env.temp_c / 100.0) + vol) / 2.0
            cb(int((step + 1) / iterations * 100), f"cpu_hal step {step+1}/{iterations}")
        self.is_running = False
        return TwinSimResult(
            execution_time_sec=round(time.time() - start, 4),
            mean_bio_density=round(density, 4),
            devices_used=1,
            backend="cpu_hal",
            research_sim=True,
            runtime_id=RuntimeId.CPU_GENERAL.value,
        )

    def _run_torch(
        self,
        grid_size: int,
        iterations: int,
        cb: Callable[[int, str], None],
        *,
        force_cpu: bool = False,
    ) -> TwinSimResult:
        import torch
        import torch.nn.functional as F

        self.is_running = True
        torch.manual_seed(self.seed)
        devices: list[torch.device] = []
        if not force_cpu and cuda_available():
            for i in range(torch.cuda.device_count()):
                devices.append(torch.device(f"cuda:{i}"))
        if not devices:
            devices = [torch.device("cpu")]

        num_devices = len(devices)
        if grid_size <= num_devices:
            grid_size = num_devices + 8

        chunk = grid_size // num_devices
        shards = []
        for i, device in enumerate(devices):
            h = chunk + (grid_size % num_devices if i == num_devices - 1 else 0)
            shards.append(torch.rand(1, 1, h, grid_size, device=device))
        kernel = torch.tensor(
            [[DIFFUSION_KERNEL.tolist()]], dtype=torch.float32
        )
        kernels = [kernel.to(d) for d in devices]

        start = time.time()
        with torch.no_grad():
            for step in range(iterations):
                if not self.is_running:
                    break
                for i, _device in enumerate(devices):
                    padded = F.pad(shards[i], (1, 1, 1, 1), mode="replicate")
                    shards[i] = F.conv2d(padded, kernels[i])
                cb(
                    int((step + 1) / max(1, iterations) * 100),
                    f"torch step {step+1}/{iterations} on {num_devices} device(s)",
                )
        mean_density = sum(float(s.mean().item()) for s in shards) / num_devices
        self.is_running = False
        is_cuda = devices[0].type == "cuda"
        backend: BackendName = "torch_gpu" if is_cuda else "torch_cpu"
        preferred = RuntimeId.GPU_CUDA
        return TwinSimResult(
            execution_time_sec=round(time.time() - start, 4),
            mean_bio_density=round(mean_density, 4),
            devices_used=num_devices,
            backend=backend,
            research_sim=True,
            runtime_id=RuntimeId.GPU_CUDA.value if is_cuda else RuntimeId.CPU_GENERAL.value,
            preferred_runtime=preferred.value,
            fallback_from=None if is_cuda else preferred.value,
        )

    def stop(self) -> None:
        self.is_running = False
