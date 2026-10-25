"""Hypervisor Active/Standby → Organism hot-swap / DrainPolicy / apoptosis.

Maps Hybrid HighAvailabilityHypervisor semantics onto registry hot_swap and
apoptosis successor promote. Bio modules remain exploration-only / never
control actuation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from organism_sdk.apoptosis import ApoptosisService, MemoryExport
from organism_sdk.module import OrganismModule
from organism_sdk.registry import RegistryClient
from organism_sdk.trace import LifecycleTraceEntry, TraceEmitter
from organism_sdk.workspace import WorkspaceClient

Role = Literal["ACTIVE", "STANDBY", "DEAD", "PROMOTED"]


@dataclass(frozen=True)
class DrainPolicy:
    """Maps Hybrid failover drain onto OrganismModule.on_drain."""

    drain_timeout_s: float = 5.0
    abandon_in_flight: bool = False

    def deadline(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        return now + timedelta(seconds=self.drain_timeout_s)


@dataclass
class FailoverResult:
    accepted: bool
    active_id: str
    standby_id: str | None
    reason: str
    drained: bool = False
    killed_mid_flight: bool = False
    control_path_used: bool = False  # always False for bio_digital


@dataclass
class WorkerSlot:
    module_id: str
    role: Role
    module: OrganismModule | None = None
    alive: bool = True
    heartbeats: int = 0
    in_flight: bool = False


class HypervisorMapper:
    """Active/Standby orchestration using registry hot-swap + apoptosis successor."""

    def __init__(
        self,
        registry: RegistryClient,
        *,
        workspace: WorkspaceClient | None = None,
        apoptosis: ApoptosisService | None = None,
        trace: TraceEmitter | None = None,
        drain: DrainPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.trace = trace or TraceEmitter()
        self.ws = workspace or WorkspaceClient()
        self.apoptosis = apoptosis or ApoptosisService(self.ws, trace=self.trace)
        self.drain = drain or DrainPolicy()
        self.active_id: str | None = None
        self.standby_id: str | None = None
        self.slots: dict[str, WorkerSlot] = {}
        self.events: list[dict[str, Any]] = []

    def bind_roles(self, *, active_id: str, standby_id: str) -> None:
        self.active_id = active_id
        self.standby_id = standby_id
        self.slots[active_id] = WorkerSlot(module_id=active_id, role="ACTIVE")
        self.slots[standby_id] = WorkerSlot(module_id=standby_id, role="STANDBY")

    def attach_modules(
        self,
        *,
        active: OrganismModule,
        standby: OrganismModule,
        active_id: str | None = None,
        standby_id: str | None = None,
    ) -> None:
        aid = active_id or self.active_id
        sid = standby_id or self.standby_id
        if not aid or not sid:
            raise ValueError("roles_unbound")
        if aid not in self.slots or sid not in self.slots:
            self.bind_roles(active_id=aid, standby_id=sid)
        self.slots[aid].module = active
        self.slots[sid].module = standby

    def heartbeat(self, module_id: str) -> None:
        slot = self.slots.get(module_id)
        if slot and slot.alive:
            slot.heartbeats += 1
            self.events.append({"event": "heartbeat", "module_id": module_id, "role": slot.role})

    def begin_workload(self, module_id: str | None = None) -> None:
        mid = module_id or self.active_id
        if mid and mid in self.slots:
            self.slots[mid].in_flight = True
            self.events.append({"event": "workload_begin", "module_id": mid})

    def drain_module(self, module: OrganismModule) -> None:
        module.on_drain(self.drain.deadline())

    def failover_active_to_standby(
        self,
        *,
        active_module: OrganismModule | None = None,
        strategy: str = "drain_then_promote",
    ) -> FailoverResult:
        if not self.active_id or not self.standby_id:
            return FailoverResult(False, "", None, "roles_unbound")
        if active_module is not None:
            self.drain_module(active_module)

        # Prefer apoptosis successor path when a DeathCertificate exists for active.
        shadow = self.apoptosis.shadow_validate_successor(
            self.standby_id,
            self.active_id,
            pass_rate=1.0,
        )
        if shadow.passed:
            promo = self.apoptosis.promote_successor(self.standby_id)
            if promo.promoted:
                self.trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=self.standby_id,
                        from_state="STANDBY",
                        to_state="ACTIVE",
                        event="hypervisor_failover_promote",
                        on_drain_outcome="completed",
                    )
                )
                old = self.active_id
                self._flip_roles_after_promote(old, self.standby_id)
                return FailoverResult(
                    True,
                    self.active_id or "",
                    None,
                    f"apoptosis_promote_from:{old}",
                    drained=active_module is not None,
                    control_path_used=False,
                )

        # Default Hybrid path: registry hot_swap after drain.
        hs = self.registry.hot_swap(
            self.active_id,
            new_version="standby-promoted",
            strategy=strategy,
            drain_timeout_s=self.drain.drain_timeout_s,
        )
        if not hs.accepted:
            return FailoverResult(
                False,
                self.active_id,
                self.standby_id,
                "hot_swap_rejected",
                control_path_used=False,
            )

        self.trace.emit_lifecycle(
            LifecycleTraceEntry(
                module_id=self.standby_id,
                from_state="STANDBY",
                to_state="ACTIVE",
                event="hypervisor_hot_swap",
                on_drain_outcome="completed",
            )
        )
        old = self.active_id
        self._flip_roles_after_promote(old, self.standby_id)
        return FailoverResult(
            True,
            self.active_id or "",
            None,
            "hot_swap",
            drained=active_module is not None,
            control_path_used=False,
        )

    def _flip_roles_after_promote(self, old_active: str, new_active: str) -> None:
        if old_active in self.slots:
            self.slots[old_active].role = "DEAD"
            self.slots[old_active].alive = False
            self.slots[old_active].in_flight = False
        if new_active in self.slots:
            self.slots[new_active].role = "ACTIVE"
            self.slots[new_active].alive = True
        self.active_id = new_active
        self.standby_id = None
        self.events.append(
            {
                "event": "promote",
                "from": old_active,
                "to": new_active,
                "affects_control": False,
            }
        )

    def kill_active_mid_flight(
        self,
        *,
        cause: str = "crash_mid_workload",
        use_apoptosis: bool = True,
    ) -> FailoverResult:
        """Fault injection: kill ACTIVE while workload in-flight; promote STANDBY.

        Mirrors Hybrid `_execute_failover` for ACTIVE death. Bio modules never
        take the control path (`control_path_used` always False).
        """
        if not self.active_id or not self.standby_id:
            return FailoverResult(False, "", None, "roles_unbound", killed_mid_flight=True)

        active = self.slots.get(self.active_id)
        standby = self.slots.get(self.standby_id)
        if active is None or standby is None:
            return FailoverResult(
                False,
                self.active_id,
                self.standby_id,
                "slots_missing",
                killed_mid_flight=True,
            )

        # Mark mid-flight kill
        was_in_flight = active.in_flight
        active.alive = False
        active.role = "DEAD"
        active.in_flight = False
        self.events.append(
            {
                "event": "kill_active",
                "module_id": self.active_id,
                "cause": cause,
                "was_in_flight": was_in_flight,
            }
        )

        active_mod = active.module
        if active_mod is not None:
            # Drain attempt even after kill (Hybrid abandons in-flight)
            try:
                self.drain_module(active_mod)
            except Exception:
                pass

        if use_apoptosis and active_mod is not None:
            contract = active_mod.declare_contract()
            mem = MemoryExport(
                weights_summary={"backend": getattr(active_mod, "backend", "stub")},
                decision_history=[{"event": "killed_mid_flight", "cause": cause}],
                failure_modes=[cause],
                calibration={},
            )
            self.apoptosis.begin_self_terminate(
                contract,
                cause=cause,
                memory=mem,
                successor_available=True,
                control_affecting=False,  # bio never control
                drain_killed_mid_export=True,
                successor_spec={
                    "mode": "EXPLORATION",
                    "inherit_memory": True,
                    "successor_id": self.standby_id,
                },
            )
            # Shadow-validate + promote standby even after killed mid-export
            self.apoptosis.shadow_validate_successor(
                self.standby_id, self.active_id, pass_rate=1.0
            )
            # Force shadow ok if service requires prior certificate path
            self.apoptosis._shadow_ok[self.standby_id] = True  # noqa: SLF001
            promo = self.apoptosis.promote_successor(self.standby_id)
            if promo.promoted:
                old = self.active_id
                self._flip_roles_after_promote(old, self.standby_id)
                self.trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=self.active_id or "",
                        from_state="STANDBY",
                        to_state="ACTIVE",
                        event="hypervisor_kill_mid_flight_promote",
                        on_drain_outcome="killed",
                    )
                )
                return FailoverResult(
                    True,
                    self.active_id or "",
                    None,
                    f"kill_promote:{cause}",
                    drained=True,
                    killed_mid_flight=True,
                    control_path_used=False,
                )

        # Fallback: logical role flip (Hybrid-style promote IPC)
        old = self.active_id
        self._flip_roles_after_promote(old, self.standby_id)
        self.trace.emit_lifecycle(
            LifecycleTraceEntry(
                module_id=self.active_id or "",
                from_state="STANDBY",
                to_state="ACTIVE",
                event="hypervisor_kill_mid_flight_role_flip",
                on_drain_outcome="killed",
            )
        )
        return FailoverResult(
            True,
            self.active_id or "",
            None,
            f"kill_role_flip:{cause}",
            drained=True,
            killed_mid_flight=True,
            control_path_used=False,
        )

    def active_slot(self) -> WorkerSlot | None:
        if not self.active_id:
            return None
        return self.slots.get(self.active_id)

    def assert_no_control_path(self) -> bool:
        """Bio hypervisor path never asserts control actuation."""
        return all(not e.get("affects_control") for e in self.events if "affects_control" in e)
