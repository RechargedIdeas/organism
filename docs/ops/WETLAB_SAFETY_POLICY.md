# Wet-lab Safety Policy (v1.4)

**Default:** Actuation is **denied**. Bio / wet-lab modules declare
`may_actuate=False`. No real GPIO device is opened unless **both**:

1. `ORGANISM_WETLAB_GPIO=1`, and
2. An explicit `SafetyPolicy` object with `actuation_certified=True` is supplied.

Even then, on boxes without a device node, open is a **no-op** (returns
`device_missing`) — Organism never invents hardware.

## Certified policy object

```python
from bio_digital.wetlab import SafetyPolicy, WetLabHAL
from bio_digital.limits import PHYSARUM_LIMITS

policy = SafetyPolicy(
    actuation_certified=False,  # default — DENY
    max_voltage=PHYSARUM_LIMITS.max_voltage,
    allow_gpio_open=False,
    certifier="unset",
    certificate_id=None,
)
```

To certify (operator responsibility — not automatic):

```python
policy = SafetyPolicy.certified(
    certifier="lab-operator@example",
    certificate_id="WL-2026-001",
    max_voltage=PHYSARUM_LIMITS.max_voltage,
)
```

Certification does **not** turn on GPIO by itself; `ORGANISM_WETLAB_GPIO=1`
must also be set in the process environment.

## Clamps

All voltages are clamped / rejected against `BioLimits.max_voltage`.
Temperature / humidity / CO₂ out of species limits mark `is_healthy=False`
and refuse actuation commands while unhealthy (unless
`policy.allow_actuate_when_unhealthy` — default False).

## Control path

Wet-lab HAL is **exploration-only**. Telemetry may feed workspace /
`hormone_state` with `affects_control=False`. It must never be a sole
justification for production router DISPATCH of actuators.

## Out of scope

- Real bioreactor GPIO drivers as a required dependency
- PySide6 studio / OpenGL twin UI
