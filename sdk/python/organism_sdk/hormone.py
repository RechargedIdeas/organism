"""Artifact G — HormoneBus (declared channel; workspace hormone_state is SoT).

Structural Answer 1: bus = low-latency mirror of last workspace hormone_state;
never an unaudited second SoT. Consumers that read the bus emit HormoneTraceEntry
with staleness_ms (Axiom 6).
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.hypervector import Hypervector
from organism_sdk.trace import HormoneTraceEntry, TraceEmitter
from organism_sdk.workspace import BindingRecord, WorkspaceClient

HormoneName = Literal["CORTISOL", "DOPAMINE", "OXYTOCIN", "MELATONIN"]
ReceptorScope = Literal["GLOBAL", "ROLE_SCOPED", "LEVEL_SCOPED"]
ReceptorResponse = Literal["THRESHOLD_GATE", "CONTINUOUS_MODULATION", "BINARY_SWITCH"]

HORMONE_STATE_TAG = "hormone_state"
HORMONE_MODULE_ID = "hormone_bus"


@dataclass
class HormoneCoefficients:
    """Declared release coefficients (HormoneBus contract; not learned)."""

    alpha: float = 0.6  # cortisol stress
    beta: float = 0.5  # cortisol 1-viability
    gamma: float = 0.3  # cortisol crisis_precursor_count
    stress_threshold: float = 0.4
    delta: float = 0.8  # dopamine
    reward_baseline: float = 0.0
    epsilon: float = 0.5  # oxytocin
    zeta: float = 1.0  # melatonin
    half_life_s: dict[str, float] = field(
        default_factory=lambda: {
            "CORTISOL": 30.0,
            "DOPAMINE": 10.0,
            "OXYTOCIN": 20.0,
            "MELATONIN": 60.0,
        }
    )


@dataclass
class HormoneLevels:
    cortisol: float = 0.0
    dopamine: float = 0.0
    oxytocin: float = 0.0
    melatonin: float = 0.0
    released_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = HORMONE_MODULE_ID
    window_id: str = ""

    def clamp(self) -> HormoneLevels:
        def c(x: float) -> float:
            return max(0.0, min(1.0, float(x)))

        return HormoneLevels(
            cortisol=c(self.cortisol),
            dopamine=c(self.dopamine),
            oxytocin=c(self.oxytocin),
            melatonin=c(self.melatonin),
            released_at=self.released_at,
            source=self.source,
            window_id=self.window_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cortisol": self.cortisol,
            "dopamine": self.dopamine,
            "oxytocin": self.oxytocin,
            "melatonin": self.melatonin,
            "released_at": self.released_at.isoformat(),
            "source": self.source,
            "window_id": self.window_id,
        }

    def digest(self) -> str:
        body = json.dumps(
            {
                "cortisol": round(self.cortisol, 6),
                "dopamine": round(self.dopamine, 6),
                "oxytocin": round(self.oxytocin, 6),
                "melatonin": round(self.melatonin, 6),
                "window_id": self.window_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class HormoneReceptor:
    hormone: HormoneName
    response: ReceptorResponse
    threshold: float | None = None
    gain: float | None = None
    target_parameter: str = ""


@dataclass
class HormoneReading:
    """What a consumer saw from the bus (for Axiom 6 replay)."""

    levels: HormoneLevels
    staleness_ms: float
    source: str  # hormone_bus_mirror | workspace_fallback
    digest: str


def cortisol_release(
    *,
    stress_load: float,
    viability_score: float,
    crisis_precursor_count: float,
    coeffs: HormoneCoefficients,
) -> float:
    return (
        coeffs.alpha * max(0.0, stress_load - coeffs.stress_threshold)
        + coeffs.beta * max(0.0, 1.0 - viability_score)
        + coeffs.gamma * max(0.0, crisis_precursor_count)
    )


def dopamine_release(*, mean_recent_reward: float, coeffs: HormoneCoefficients) -> float:
    return coeffs.delta * max(0.0, mean_recent_reward - coeffs.reward_baseline)


def oxytocin_release(*, adapter_acceptance_rate: float, coeffs: HormoneCoefficients) -> float:
    return coeffs.epsilon * max(0.0, min(1.0, adapter_acceptance_rate))


def melatonin_release(*, circadian_phase: float, coeffs: HormoneCoefficients) -> float:
    """circadian_phase in [0,1]; rest window near 1."""
    return coeffs.zeta * max(0.0, min(1.0, circadian_phase))


def apply_decay(level: float, half_life_s: float, dt_s: float) -> float:
    if half_life_s <= 0:
        return level
    return level * math.pow(0.5, dt_s / half_life_s)


class HormoneBus:
    """Declared channel. Workspace binding is SoT; bus mirrors last write."""

    def __init__(
        self,
        workspace: WorkspaceClient,
        *,
        trace: TraceEmitter | None = None,
        coeffs: HormoneCoefficients | None = None,
        role_seed: int = 0x48_4F_52_4D,  # 'HORM'
    ) -> None:
        self._ws = workspace
        self._trace = trace
        self.coeffs = coeffs or HormoneCoefficients()
        self._lock = threading.RLock()
        self._mirror: HormoneLevels = HormoneLevels()
        self._mirror_written_at: datetime | None = None
        self._workspace_binding_id: uuid.UUID | None = None
        self._role = Hypervector.random(seed=role_seed)
        self._filler_base = Hypervector.random(seed=role_seed ^ 0xFFFF)
        self._alive = True
        self._window_seq = 0

    @property
    def alive(self) -> bool:
        return self._alive

    def kill_mirror(self) -> None:
        """Category K5: kill bus mirror; consumers fall back to workspace."""
        with self._lock:
            self._alive = False

    def restore_mirror(self) -> None:
        with self._lock:
            self._alive = True

    def compute_release(
        self,
        *,
        stress_load: float = 0.0,
        viability_score: float = 1.0,
        crisis_precursor_count: float = 0.0,
        mean_recent_reward: float = 0.0,
        adapter_acceptance_rate: float = 0.0,
        circadian_phase: float = 0.0,
        dt_s: float = 1.0,
        source: str = HORMONE_MODULE_ID,
    ) -> HormoneLevels:
        with self._lock:
            prev = self._mirror
            c = apply_decay(prev.cortisol, self.coeffs.half_life_s["CORTISOL"], dt_s)
            d = apply_decay(prev.dopamine, self.coeffs.half_life_s["DOPAMINE"], dt_s)
            o = apply_decay(prev.oxytocin, self.coeffs.half_life_s["OXYTOCIN"], dt_s)
            m = apply_decay(prev.melatonin, self.coeffs.half_life_s["MELATONIN"], dt_s)
            c += cortisol_release(
                stress_load=stress_load,
                viability_score=viability_score,
                crisis_precursor_count=crisis_precursor_count,
                coeffs=self.coeffs,
            )
            d += dopamine_release(mean_recent_reward=mean_recent_reward, coeffs=self.coeffs)
            o += oxytocin_release(
                adapter_acceptance_rate=adapter_acceptance_rate, coeffs=self.coeffs
            )
            m += melatonin_release(circadian_phase=circadian_phase, coeffs=self.coeffs)
            self._window_seq += 1
            return HormoneLevels(
                cortisol=c,
                dopamine=d,
                oxytocin=o,
                melatonin=m,
                released_at=datetime.now(timezone.utc),
                source=source,
                window_id=f"w{self._window_seq}",
            ).clamp()

    def write_telemetry_window(self, levels: HormoneLevels) -> BindingRecord:
        """SoT write: FULL-salience hormone_state binding every telemetry window."""
        levels = levels.clamp()
        # Stable-ish filler from digest bits
        dig = bytes.fromhex(levels.digest())
        filler = self._filler_base
        # XOR digest into a small perturbation via random seeded hv
        seed = int.from_bytes(dig[:8], "big") ^ 0xCAFE
        filler = Hypervector.random(seed=seed)
        hv = self._role.bind(filler)
        # Unbind prior hormone_state (single SoT binding)
        prior = self._ws.read_by_tag([HORMONE_STATE_TAG])
        for b in prior:
            self._ws.unbind(b.binding_id)
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=hv,
            role=self._role,
            filler=filler,
            tags=(HORMONE_STATE_TAG,),
            module_id=HORMONE_MODULE_ID,
            salience=1.0,
            fidelity="FULL",
            payload=levels.as_dict(),
            affects_control=True,
        )
        result = self._ws.write(rec)
        if result.status != "ACCEPTED":
            raise RuntimeError(f"hormone_state write rejected: {result.reason_code}")
        with self._lock:
            self._mirror = levels
            self._mirror_written_at = levels.released_at
            self._workspace_binding_id = rec.binding_id
            self._alive = True
        return self._ws.read_by_binding_id(rec.binding_id)  # type: ignore[return-value]

    def read_workspace_hormone_state(self) -> HormoneLevels | None:
        bindings = self._ws.read_by_tag([HORMONE_STATE_TAG])
        if not bindings:
            return None
        # Prefer newest
        bindings = sorted(bindings, key=lambda b: b.created_at, reverse=True)
        payload = bindings[0].payload or {}
        return HormoneLevels(
            cortisol=float(payload.get("cortisol", 0.0)),
            dopamine=float(payload.get("dopamine", 0.0)),
            oxytocin=float(payload.get("oxytocin", 0.0)),
            melatonin=float(payload.get("melatonin", 0.0)),
            released_at=_parse_dt(payload.get("released_at")),
            source=str(payload.get("source", HORMONE_MODULE_ID)),
            window_id=str(payload.get("window_id", "")),
        )

    def read_mirror(self, *, now: datetime | None = None, consumer: str = "router") -> HormoneReading:
        """Low-latency mirror read. Falls back to workspace if mirror killed."""
        now = now or datetime.now(timezone.utc)
        with self._lock:
            if self._alive and self._mirror_written_at is not None:
                levels = self._mirror
                written = self._mirror_written_at
                source = "hormone_bus_mirror"
            else:
                levels = self.read_workspace_hormone_state() or HormoneLevels()
                written = levels.released_at
                source = "workspace_fallback"
        staleness_ms = max(0.0, (now - written).total_seconds() * 1000.0)
        reading = HormoneReading(
            levels=levels,
            staleness_ms=staleness_ms,
            source=source,
            digest=levels.digest(),
        )
        if self._trace is not None:
            self._trace.emit_hormone(
                HormoneTraceEntry(
                    hormone_state_digest=reading.digest,
                    cortisol=levels.cortisol,
                    dopamine=levels.dopamine,
                    oxytocin=levels.oxytocin,
                    melatonin=levels.melatonin,
                    staleness_ms=staleness_ms,
                    source=source,
                )
            )
        return reading


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def modulate_parameter(
    receptors: list[HormoneReceptor],
    levels: HormoneLevels,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Apply receptor modulation. Never called on safety shield params."""
    out = dict(params)
    level_map = {
        "CORTISOL": levels.cortisol,
        "DOPAMINE": levels.dopamine,
        "OXYTOCIN": levels.oxytocin,
        "MELATONIN": levels.melatonin,
    }
    for r in receptors:
        lv = level_map[r.hormone]
        key = r.target_parameter
        if not key:
            continue
        if r.response == "THRESHOLD_GATE":
            thr = 0.8 if r.threshold is None else r.threshold
            out[key] = bool(lv >= thr)
        elif r.response == "BINARY_SWITCH":
            thr = 0.5 if r.threshold is None else r.threshold
            out[key] = bool(lv >= thr)
        elif r.response == "CONTINUOUS_MODULATION":
            gain = 1.0 if r.gain is None else r.gain
            base = float(out.get(key, 0.0))
            out[key] = base * (1.0 + gain * lv)
    return out


# Safety shield: hormones may be read but never grant extra permissions.
SAFETY_SHIELD_PARAMS = frozenset(
    {
        "permit_forbidden_actuation",
        "bypass_safety",
        "override_shield",
        "allow_critical_without_t0",
    }
)


def apply_hormone_to_module_params(
    receptors: list[HormoneReceptor],
    levels: HormoneLevels,
    params: dict[str, Any],
) -> dict[str, Any]:
    """SDK pre-handle modulation. Rejects any attempt to override the shield."""
    for r in receptors:
        if r.target_parameter in SAFETY_SHIELD_PARAMS:
            raise PermissionError(
                f"hormone receptor may not target safety shield param {r.target_parameter}"
            )
    modulated = modulate_parameter(receptors, levels, params)
    for k in SAFETY_SHIELD_PARAMS:
        if k in modulated and modulated.get(k) and not params.get(k):
            raise PermissionError(f"hormone must not enable safety shield param {k}")
    return modulated
