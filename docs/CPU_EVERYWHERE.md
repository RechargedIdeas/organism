# CPU Everywhere — product guarantee (v1.3)

**Guarantee:** Every Organism software / RESEARCH_SIM workload runs on
`RuntimeId.CPU_GENERAL` when no accelerator is present. Preferring GPU, ROCm,
Metal, NPU, or neuromorphic silicon **never hard-fails the process**.

## Policy

| Rule | Detail |
|---|---|
| Default runtime | `CPU_GENERAL` |
| Accelerator prefer | Soft: use if present; else CPU fallback with `fallback_from` recorded |
| `MetabolicProfile.requires_gpu` | Soft preference via `resolve_requires_gpu()` — never raises |
| Missing torch / CUDA | Wave twin runs the **same** diffusion math on NumPy (`numpy_cpu`) |
| Neuromorphic | Spike-rate RESEARCH_SIM always on CPU; `ORGANISM_NEURO_SIM=1` only admits dispatch |
| Physical / bio | HAL + twin stubs on CPU; `may_actuate=False`; wet-lab GPIO still external |
| Router exclusion | `hardware_capability_missing` excludes **production dispatch** only — does not crash |

`HardwareRequirement` values hostable on CPU under RESEARCH_SIM:
`NONE`, `NEUROMORPHIC`, `PHYSICAL_SUBSTRATE`, `EVENT_CAMERA`, `TPU_NPU`
(see `organism_sdk.device.CPU_HOSTABLE_HARDWARE`).

## Backends (bio wave twin)

| Backend | When |
|---|---|
| `numpy_cpu` | Default; also when GPU preferred but torch/CUDA absent |
| `torch_cpu` | `ORGANISM_BIO_GPU_TWIN=1` + torch, no CUDA |
| `torch_gpu` | Opt-in + CUDA present |
| `cpu_hal` | Explicit HAL stub (`force_backend="cpu_hal"`) |
| `gated` | `ORGANISM_BIO_DIGITAL_SIM` off |

## API

```python
from organism_sdk.device import select_compute_backend, resolve_requires_gpu, RuntimeId

sel = select_compute_backend(prefer=RuntimeId.GPU_CUDA)  # → CPU if no CUDA
sel = resolve_requires_gpu(True)  # never raises
```

Env:

| Var | Effect |
|---|---|
| `ORGANISM_BIO_GPU_TWIN=1` | Prefer GPU for bio wave twin when present |
| `ORGANISM_PREFER_GPU=1` | Generic prefer-GPU for `select_compute_backend` |
| `ORGANISM_NEURO_SIM=1` | Admit NEUROMORPHIC into router caps (CPU sim still used) |
| `ORGANISM_NEURO_HW=1` | Claim real neuromorphic silicon present |

## CI

Blocking gate: **`cpu:everywhere`**
(`sdk/python/tests/test_cpu_everywhere.py` + `modules/bio_digital/tests/test_gpu_twin.py`).

## Out of scope (unchanged)

Real neuromorphic silicon, wet-lab GPIO actuation, production WAN BFT/TPM.
Those remain simulators / exploration-only and still run their **software**
paths on CPU.
