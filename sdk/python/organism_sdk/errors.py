"""Organism SDK exceptions (A3.1, A3.3, Amendment 3.1)."""
from __future__ import annotations


class OrganismSDKError(Exception):
    """Base SDK error."""


class JustificationMissing(OrganismSDKError):
    """Raised when justify() returns None for a required action class (E-1)."""

    def __init__(self, action_class: str) -> None:
        self.action_class = action_class
        super().__init__(f"justification missing for action class: {action_class}")


class ModalityUnavailable(OrganismSDKError):
    """Raised when a declared modality is not present in PerceptionInput (E-2)."""

    def __init__(self, modality: str, *, required: bool) -> None:
        self.modality = modality
        self.required = required
        super().__init__(f"modality unavailable: {modality} (required={required})")


class SDKInvariantViolation(OrganismSDKError):
    """Raised when a caller violates an SDK invariant (SDK-6 etc.)."""


class TraceUnavailable(OrganismSDKError):
    """Raised when TraceEmitter cannot obtain authoritative router state (SDK-6)."""


class CapabilityScopeMissing(OrganismSDKError):
    """Workspace call rejected by local capability check (SDK-1)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"capability scope missing: {detail}")


class RegistrationRejected(OrganismSDKError):
    """Contract validation failed with ERROR severity."""

    def __init__(self, issues: list) -> None:
        self.issues = issues
        codes = [getattr(i, "code", str(i)) for i in issues]
        super().__init__(f"registration rejected: {codes}")


class DimensionMismatch(OrganismSDKError):
    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"dimension mismatch: expected {expected}, got {actual}")
