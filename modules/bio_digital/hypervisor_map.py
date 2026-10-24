"""Hypervisor Active/Standby → Organism hot-swap / DrainPolicy / apoptosis."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from organism_sdk.apoptosis import ApoptosisService
from organism_sdk.module import OrganismModule
from organism_sdk.registry import RegistryClient
from organism_sdk.trace import LifecycleTraceEntry, TraceEmitter
from organism_sdk.workspace import WorkspaceClient

Role = Literal["ACTIVE", "STANDBY"]


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

    def bind_roles(self, *, active_id: str, standby_id: str) -> None:
        self.active_id = active_id
        self.standby_id = standby_id

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
                self.active_id = self.standby_id
                self.standby_id = None
                return FailoverResult(True, self.active_id, None, f"apoptosis_promote_from:{old}")

        # Default Hybrid path: registry hot_swap after drain (standby becomes active slot).
        hs = self.registry.hot_swap(
            self.active_id,
            new_version="standby-promoted",
            strategy=strategy,
            drain_timeout_s=self.drain.drain_timeout_s,
        )
        if not hs.accepted:
            # Hot-swap may be unsupported; still allow logical role flip for research modules
            # that declared hot_swap_supported=True after register — if rejected, report.
            return FailoverResult(False, self.active_id, self.standby_id, "hot_swap_rejected")

        self.trace.emit_lifecycle(
            LifecycleTraceEntry(
                module_id=self.standby_id,
                from_state="STANDBY",
                to_state="ACTIVE",
                event="hypervisor_hot_swap",
                on_drain_outcome="completed",
            )
        )
        self.active_id = self.standby_id
        self.standby_id = None
        return FailoverResult(True, self.active_id, None, "hot_swap")
