"""CPU-everywhere compute selection (v1.3 product guarantee).

Every RESEARCH_SIM / software-sim workload must run on ``CPU_GENERAL`` when no
accelerator is present. Preferring GPU/NPU/neuromorphic never hard-fails the
process; selection soft-falls back to CPU.

See ``docs/CPU_EVERYWHERE.md``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class RuntimeId(str, Enum):
    """Mirrors proto ``organism.v1.RuntimeId`` (software subset)."""

    CPU_GENERAL = "CPU_GENERAL"
    GPU_CUDA = "GPU_CUDA"
    GPU_ROCM = "GPU_ROCM"
    GPU_METAL = "GPU_METAL"
    NPU = "NPU"
    NEUROMORPHIC = "NEUROMORPHIC"
    WASM = "WASM"


# HardwareRequirement values that RESEARCH_SIM can host on CPU_GENERAL.
CPU_HOSTABLE_HARDWARE: frozenset[str] = frozenset(
    {
        "NONE",
        "NEUROMORPHIC",  # software spike / neuro_sim
        "PHYSICAL_SUBSTRATE",  # bio_digital / physical_research stubs
        "EVENT_CAMERA",  # software event stream if provided
        "TPU_NPU",  # CPU numeric fallback for research sims
    }
)

ACCELERATOR_RUNTIMES: frozenset[str] = frozenset(
    {
        RuntimeId.GPU_CUDA.value,
        RuntimeId.GPU_ROCM.value,
        RuntimeId.GPU_METAL.value,
        RuntimeId.NPU.value,
        RuntimeId.NEUROMORPHIC.value,
    }
)


@dataclass(frozen=True)
class DeviceSelection:
    """Resolved compute target. ``fallback_from`` set when accelerator absent."""

    runtime: RuntimeId
    backend: str  # e.g. "numpy_cpu", "torch_cuda", "research_sim_cpu"
    preferred: RuntimeId
    accelerator_present: bool
    fallback_from: RuntimeId | None = None
    notes: str = ""

    @property
    def is_cpu(self) -> bool:
        return self.runtime == RuntimeId.CPU_GENERAL

    def as_dict(self) -> dict[str, object]:
        return {
            "runtime": self.runtime.value,
            "backend": self.backend,
            "preferred": self.preferred.value,
            "accelerator_present": self.accelerator_present,
            "fallback_from": self.fallback_from.value if self.fallback_from else None,
            "notes": self.notes,
        }


def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def cuda_available() -> bool:
    if not torch_available():
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def prefer_accelerator() -> bool:
    """True when env asks to prefer GPU/accelerator if present."""
    v = os.environ.get("ORGANISM_BIO_GPU_TWIN", "0").strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    v2 = os.environ.get("ORGANISM_PREFER_GPU", "0").strip().lower()
    return v2 in {"1", "true", "yes", "on"}


def probe_accelerators() -> set[str]:
    """Detect present accelerators; never raises."""
    found: set[str] = set()
    try:
        if cuda_available():
            found.add(RuntimeId.GPU_CUDA.value)
    except Exception:
        pass
    # ROCm / Metal / NPU: probe softly; absence is fine
    try:
        if torch_available():
            import torch

            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                found.add(RuntimeId.GPU_METAL.value)
    except Exception:
        pass
    # Neuromorphic silicon: only via ORGANISM_NEURO_SIM (software) or real HW flag
    if os.environ.get("ORGANISM_NEURO_HW", "").strip() in {"1", "true", "TRUE", "yes"}:
        found.add(RuntimeId.NEUROMORPHIC.value)
    return found


def cpu_can_host(hardware_requirement: str | None) -> bool:
    """Whether CPU_GENERAL may host this HardwareRequirement under RESEARCH_SIM."""
    hw = (hardware_requirement or "NONE").upper()
    if hw in {"", "UNSPECIFIED", "HW_UNSPECIFIED", "HW_NONE"}:
        return True
    if hw.startswith("HW_"):
        hw = hw[3:]
    return hw in CPU_HOSTABLE_HARDWARE


def select_compute_backend(
    *,
    prefer: RuntimeId | str | None = None,
    prefer_gpu: bool | None = None,
) -> DeviceSelection:
    """Pick a runnable backend. Missing accelerators → CPU_GENERAL (never raises)."""
    if prefer is None:
        want = RuntimeId.GPU_CUDA if (prefer_gpu if prefer_gpu is not None else prefer_accelerator()) else RuntimeId.CPU_GENERAL
    elif isinstance(prefer, RuntimeId):
        want = prefer
    else:
        try:
            want = RuntimeId(str(prefer))
        except ValueError:
            want = RuntimeId.CPU_GENERAL

    present = probe_accelerators()

    if want == RuntimeId.CPU_GENERAL:
        return DeviceSelection(
            runtime=RuntimeId.CPU_GENERAL,
            backend="numpy_cpu",
            preferred=want,
            accelerator_present=bool(present & ACCELERATOR_RUNTIMES),
            notes="cpu_everywhere_default",
        )

    if want == RuntimeId.GPU_CUDA:
        if RuntimeId.GPU_CUDA.value in present and torch_available():
            return DeviceSelection(
                runtime=RuntimeId.GPU_CUDA,
                backend="torch_cuda",
                preferred=want,
                accelerator_present=True,
                notes="cuda_preferred",
            )
        if torch_available():
            return DeviceSelection(
                runtime=RuntimeId.CPU_GENERAL,
                backend="torch_cpu",
                preferred=want,
                accelerator_present=False,
                fallback_from=want,
                notes="torch_present_no_cuda_cpu_fallback",
            )
        return DeviceSelection(
            runtime=RuntimeId.CPU_GENERAL,
            backend="numpy_cpu",
            preferred=want,
            accelerator_present=False,
            fallback_from=want,
            notes="no_torch_numpy_cpu_fallback",
        )

    if want in (RuntimeId.GPU_ROCM, RuntimeId.GPU_METAL, RuntimeId.NPU):
        if want.value in present:
            return DeviceSelection(
                runtime=want,
                backend=want.value.lower(),
                preferred=want,
                accelerator_present=True,
            )
        return DeviceSelection(
            runtime=RuntimeId.CPU_GENERAL,
            backend="numpy_cpu",
            preferred=want,
            accelerator_present=False,
            fallback_from=want,
            notes=f"{want.value}_absent_cpu_fallback",
        )

    if want == RuntimeId.NEUROMORPHIC:
        # Software RESEARCH_SIM always available on CPU
        return DeviceSelection(
            runtime=RuntimeId.CPU_GENERAL,
            backend="research_sim_cpu",
            preferred=want,
            accelerator_present=RuntimeId.NEUROMORPHIC.value in present,
            fallback_from=None if RuntimeId.NEUROMORPHIC.value in present else want,
            notes="neuromorphic_research_sim_cpu",
        )

    return DeviceSelection(
        runtime=RuntimeId.CPU_GENERAL,
        backend="numpy_cpu",
        preferred=RuntimeId.CPU_GENERAL,
        accelerator_present=False,
        notes="unknown_prefer_cpu",
    )


def resolve_requires_gpu(requires_gpu: bool) -> DeviceSelection:
    """MetabolicProfile.requires_gpu never crashes — soft-select CPU when absent."""
    if not requires_gpu:
        return select_compute_backend(prefer=RuntimeId.CPU_GENERAL)
    return select_compute_backend(prefer=RuntimeId.GPU_CUDA, prefer_gpu=True)


def research_sim_runtimes() -> frozenset[str]:
    """Runtimes that may execute RESEARCH_SIM / software-sim on this box."""
    return frozenset({RuntimeId.CPU_GENERAL.value, RuntimeId.WASM.value}) | frozenset(
        probe_accelerators()
    )


def assert_never_hard_fail_missing_gpu(exc: BaseException | None = None) -> None:
    """Documentation hook / test helper: GPU absence is not a process failure."""
    if exc is not None and "cuda" in str(exc).lower() and "no gpu" in str(exc).lower():
        raise AssertionError("CPU-everywhere violated: hard-failed on missing GPU") from exc
