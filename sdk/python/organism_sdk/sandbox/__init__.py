"""Organism native sandbox runtime — process jail + self-containment.

Docker is never required. Works bare metal, VMs, and any container system.
Composes with generative SafeSandbox (AST whitelist + OS jail).
"""
from __future__ import annotations

from organism_sdk.sandbox.audit import SandboxAuditEvent, SandboxAuditLog
from organism_sdk.sandbox.jail import JailRefused, JailResult, ProcessJail, capabilities
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.sandbox.runtime import OrganismSandbox, SandboxStatus, SelfCheckResult

__all__ = [
    "SandboxPolicy",
    "ProcessJail",
    "JailResult",
    "JailRefused",
    "capabilities",
    "SandboxAuditLog",
    "SandboxAuditEvent",
    "OrganismSandbox",
    "SandboxStatus",
    "SelfCheckResult",
]
