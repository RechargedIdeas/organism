"""Optional multi-GPU / CPU wave twin behind RESEARCH_SIM.

If torch is available, runs a small diffusion wave sim (Hybrid BiologicalTensorSimulator
shape). Otherwise provides a CPU HAL twin stub and reports GPU path as gated.
Never required for the default suite; never on the control path.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from bio_digital.hal import BioDigitalHAL, research_sim_enabled
from bio_digital.limits import PHYSARUM_LIMITS

DIFFUSION_KERNEL = [
    [[[0.1, 0.1, 0.1], [0.1, 0.2, 0.1], [0.1, 0.1, 0.1]]]
]


def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def gpu_twin_enabled() -> bool:
    """Opt-in GPU/torch twin; still requires RESEARCH_SIM."""
    if not research_sim_enabled():
        return False
    v = os.environ.get("ORGANISM_BIO_GPU_TWIN", "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


@dataclass
class TwinSimResult:
    execution_time_sec: float
    mean_bio_density: float
    devices_used: int
    backend: str  # "torch_gpu" | "torch_cpu" | "cpu_hal" | "gated"
    research_sim: bool
    affects_control: bool = False
    exploration_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_time_sec": self.execution_time_sec,
            "mean_bio_density": self.mean_bio_density,
            "devices_used": self.devices_used,
            "backend": self.backend,
            "research_sim": self.research_sim,
            "affects_control": self.affects_control,
            "exploration_only": self.exploration_only,
        }


class GpuTwinSimulator:
    """RESEARCH_SIM wave twin — torch when present+enabled, else CPU HAL stub."""

    def __init__(self, *, seed: int = 42) -> None:
        self.seed = seed
        self.is_running = False

    def run_wave_simulation(
        self,
        grid_size: int = 32,
        iterations: int = 4,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> TwinSimResult:
        cb = progress_callback or (lambda _p, _m: None)
        if not research_sim_enabled():
            return TwinSimResult(
                execution_time_sec=0.0,
                mean_bio_density=0.0,
                devices_used=0,
                backend="gated",
                research_sim=False,
            )

        if gpu_twin_enabled() and torch_available():
            return self._run_torch(grid_size, iterations, cb)

        # CPU HAL twin — always available, default suite path
        return self._run_cpu_hal(grid_size, iterations, cb)

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
            # Pseudo wave: mix env + electrode stim as density proxy
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
        )

    def _run_torch(
        self,
        grid_size: int,
        iterations: int,
        cb: Callable[[int, str], None],
    ) -> TwinSimResult:
        import torch
        import torch.nn.functional as F

        self.is_running = True
        torch.manual_seed(self.seed)
        devices: list[torch.device] = []
        if torch.cuda.is_available():
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
        kernel = torch.tensor(DIFFUSION_KERNEL, dtype=torch.float32)
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
        backend = "torch_gpu" if devices[0].type == "cuda" else "torch_cpu"
        return TwinSimResult(
            execution_time_sec=round(time.time() - start, 4),
            mean_bio_density=round(mean_density, 4),
            devices_used=num_devices,
            backend=backend,
            research_sim=True,
        )

    def stop(self) -> None:
        self.is_running = False
