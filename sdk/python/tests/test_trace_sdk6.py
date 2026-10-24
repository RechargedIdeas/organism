"""SDK-6 TraceEmitter auto-population."""
import pytest
from organism_sdk.errors import SDKInvariantViolation
from organism_sdk.trace import RoutingTraceEntry, TraceEmitter


class FakeRouter:
    def current_policy_id(self) -> str:
        return "policy-1"

    def current_policy_digest(self) -> bytes:
        return b"\x11" * 32

    def current_level(self) -> str:
        return "L0"


def test_stub_without_router():
    em = TraceEmitter()  # M1 stub
    em.emit_routing(RoutingTraceEntry(task_id="t1", form="control_actuation"))
    assert len(em.entries) == 1


def test_auto_populate():
    em = TraceEmitter(FakeRouter())
    entry = RoutingTraceEntry(task_id="t1", form="x")
    em.emit_routing(entry)
    assert entry.policy_id == "policy-1"
    assert entry.level == "L0"
    assert entry.policy_digest == b"\x11" * 32


def test_caller_override_rejected():
    em = TraceEmitter(FakeRouter())
    entry = RoutingTraceEntry(task_id="t1", form="x", policy_id="evil")
    with pytest.raises(SDKInvariantViolation):
        em.emit_routing(entry)
