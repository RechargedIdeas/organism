"""OrganismSandbox — native runtime containment for self + child work."""
from __future__ import annotations

import json
import os
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any, Sequence

from organism_sdk.sandbox.audit import SandboxAuditEvent, SandboxAuditLog
from organism_sdk.sandbox.jail import JailResult, ProcessJail, capabilities
from organism_sdk.sandbox.policy import SandboxPolicy


@dataclass
class SandboxStatus:
    native: bool = True
    docker_required: bool = False
    cpu_everywhere: bool = True
    capabilities: dict[str, Any] = field(default_factory=dict)
    default_policy: dict[str, Any] = field(default_factory=dict)
    self_policy: dict[str, Any] = field(default_factory=dict)
    generative_policy: dict[str, Any] = field(default_factory=dict)
    recent_audit: list[dict[str, Any]] = field(default_factory=list)
    in_jail: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "native": self.native,
            "docker_required": self.docker_required,
            "cpu_everywhere": self.cpu_everywhere,
            "capabilities": dict(self.capabilities),
            "default_policy": dict(self.default_policy),
            "self_policy": dict(self.self_policy),
            "generative_policy": dict(self.generative_policy),
            "recent_audit": list(self.recent_audit),
            "in_jail": self.in_jail,
        }


@dataclass
class SelfCheckResult:
    ok: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    status: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checks": self.checks, "status": self.status}


class OrganismSandbox:
    """Custom, natively integrated Organism sandbox runtime.

    - Process jail for child work (rlimits + optional Linux namespaces)
    - Self-sandbox mode for worker pool / generative / soak / federation children
    - Composes with generative SafeSandbox (AST + this jail)
    - Never requires Docker; works bare metal, VMs, and any container system
    """

    def __init__(
        self,
        policy: SandboxPolicy | None = None,
        *,
        audit: SandboxAuditLog | None = None,
        tracer: Any | None = None,
    ) -> None:
        self.policy = policy or SandboxPolicy.from_env()
        self.audit = audit or SandboxAuditLog()
        if tracer is not None:
            self.audit.attach_tracer(tracer)
        self._jail = ProcessJail(self.policy)

    def status(self) -> SandboxStatus:
        import os

        return SandboxStatus(
            native=True,
            docker_required=False,
            cpu_everywhere=True,
            capabilities=capabilities(),
            default_policy=SandboxPolicy.from_env().as_dict(),
            self_policy=SandboxPolicy.self_containment().as_dict(),
            generative_policy=SandboxPolicy.generative().as_dict(),
            recent_audit=self.audit.recent(20),
            in_jail=os.environ.get("ORGANISM_IN_JAIL", "").lower() in ("1", "true", "yes"),
        )

    def run(
        self,
        argv: Sequence[str],
        *,
        policy: SandboxPolicy | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        input_bytes: bytes | None = None,
    ) -> JailResult:
        pol = policy or self.policy
        jail = ProcessJail(pol) if policy is not None else self._jail
        result = jail.run(argv, env=env, cwd=cwd, input_bytes=input_bytes)
        self.audit.record(
            SandboxAuditEvent(
                action="refuse" if result.refused else ("timeout" if result.timed_out else ("ok" if result.ok else "error")),
                label=pol.label,
                ok=result.ok and not result.refused,
                detail=result.refused or (result.stderr[:500] if result.stderr else ""),
                policy=pol.as_dict(),
                pid=result.pid,
                exit_code=result.exit_code,
                namespaces_used=list(result.namespaces_used),
                degraded=list(result.degraded),
                duration_ms=result.duration_ms,
            )
        )
        return result

    def run_python(
        self,
        source: str,
        *,
        policy: SandboxPolicy | None = None,
        argv_extra: Sequence[str] | None = None,
    ) -> JailResult:
        """Run a Python source string inside the jail (interpreter = sys.executable)."""
        pol = policy or self.policy
        argv = [sys.executable, "-c", source, *(argv_extra or ())]
        return self.run(argv, policy=pol)

    def wrap_self(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> JailResult:
        """Self-sandbox: wrap Organism worker / soak / federation child under self policy."""
        pol = SandboxPolicy.self_containment()
        return self.run(argv, policy=pol, env=env, cwd=cwd)

    def self_check(self) -> SelfCheckResult:
        """Verify jail can spawn, apply policy refuse, and report capabilities."""
        checks: list[dict[str, Any]] = []
        st = self.status().as_dict()

        # 1) capabilities present
        caps = st["capabilities"]
        checks.append(
            {
                "id": "capabilities",
                "ok": bool(caps.get("spawn")) and caps.get("docker_required") is False,
                "detail": caps,
            }
        )

        # 2) trivial python child
        r = self.run_python(
            "print('organism_sandbox_ok')",
            policy=SandboxPolicy(
                timeout_s=5.0,
                max_rss_mb=256,
                cpu_time_s=5,
                max_fds=64,
                max_nproc=16,
                use_namespaces=True,
                label="self_check_ok",
            ),
        )
        checks.append(
            {
                "id": "spawn_python",
                "ok": r.ok and "organism_sandbox_ok" in r.stdout,
                "detail": r.as_dict(),
            }
        )

        # 3) shell escape refused
        refused = self.run(
            ["/bin/sh", "-c", "echo pwned"],
            policy=SandboxPolicy(label="self_check_refuse", deny_shell_escape=True),
        )
        checks.append(
            {
                "id": "refuse_shell",
                "ok": (not refused.ok) and bool(refused.refused),
                "detail": refused.as_dict(),
            }
        )

        # 4) timeout works
        tpol = SandboxPolicy(
            timeout_s=0.3,
            max_rss_mb=256,
            cpu_time_s=2,
            use_namespaces=False,
            label="self_check_timeout",
        )
        timed = self.run_python("import time; time.sleep(5)", policy=tpol)
        checks.append(
            {
                "id": "timeout",
                "ok": timed.timed_out or (timed.exit_code not in (0, None) and not timed.ok),
                "detail": timed.as_dict(),
            }
        )

        self.audit.record(
            SandboxAuditEvent(
                action="self_check",
                label="self_check",
                ok=all(c["ok"] for c in checks),
                detail=json.dumps([c["id"] for c in checks]),
            )
        )
        ok = all(c["ok"] for c in checks)
        return SelfCheckResult(ok=ok, checks=checks, status=st)

    def run_generative_source(
        self,
        source: str,
        *,
        entry: str = "main",
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute generative source via SafeSandbox composed with this runtime jail."""
        from organism_sdk.generative.sandbox import SafeSandbox

        sb = SafeSandbox(
            timeout_s=SandboxPolicy.generative().timeout_s,
            max_rss_mb=SandboxPolicy.generative().max_rss_mb,
            isolate=True,
        )
        # Attach audit marker
        self.audit.record(
            SandboxAuditEvent(
                action="run",
                label="generative_compose",
                ok=True,
                detail=f"entry={entry}",
                policy=SandboxPolicy.generative().as_dict(),
            )
        )
        result = sb.run(source, entry=entry, args=args)
        payload = result.as_dict()
        payload["runtime_sandbox"] = "organism_native"
        payload["docker_required"] = False
        return payload
