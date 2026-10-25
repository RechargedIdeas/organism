"""Explicit SafetyPolicy — actuation denied until certified (v1.4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


class ActuationDenied(PermissionError):
    """Raised when wet-lab actuation is refused by policy or env."""


@dataclass(frozen=True)
class SafetyPolicy:
    """Operator-supplied policy object. Default denies all actuation."""

    actuation_certified: bool = False
    allow_gpio_open: bool = False
    max_voltage: float = 0.0
    allow_actuate_when_unhealthy: bool = False
    certifier: str = "unset"
    certificate_id: str | None = None
    certified_at: str | None = None
    notes: str = ""

    @classmethod
    def deny_all(cls, *, max_voltage: float = 0.0) -> "SafetyPolicy":
        return cls(actuation_certified=False, allow_gpio_open=False, max_voltage=max_voltage)

    @classmethod
    def certified(
        cls,
        *,
        certifier: str,
        certificate_id: str,
        max_voltage: float,
        allow_gpio_open: bool = True,
        notes: str = "",
    ) -> "SafetyPolicy":
        if not certifier or certifier == "unset":
            raise ValueError("certifier required for certified policy")
        if not certificate_id:
            raise ValueError("certificate_id required for certified policy")
        if max_voltage <= 0:
            raise ValueError("max_voltage must be positive when certified")
        return cls(
            actuation_certified=True,
            allow_gpio_open=allow_gpio_open,
            max_voltage=max_voltage,
            certifier=certifier,
            certificate_id=certificate_id,
            certified_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )

    def may_actuate(self, *, gpio_env: bool, substrate_healthy: bool) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        if not self.actuation_certified:
            return False, "policy_not_certified"
        if not gpio_env:
            return False, "ORGANISM_WETLAB_GPIO_not_set"
        if not self.allow_gpio_open:
            return False, "policy_disallows_gpio_open"
        if not substrate_healthy and not self.allow_actuate_when_unhealthy:
            return False, "substrate_unhealthy"
        return True, "ok"

    def as_dict(self) -> dict[str, object]:
        return {
            "actuation_certified": self.actuation_certified,
            "allow_gpio_open": self.allow_gpio_open,
            "max_voltage": self.max_voltage,
            "allow_actuate_when_unhealthy": self.allow_actuate_when_unhealthy,
            "certifier": self.certifier,
            "certificate_id": self.certificate_id,
            "certified_at": self.certified_at,
            "notes": self.notes,
        }
