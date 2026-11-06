"""NLP-CLI as an Organism module (see docs/integrations/NLP_CLI_ON_ORGANISM.md).

The router is the Rust binary ``nlp-cli``. This adapter calls it with ``route --json``, reads one decision,
and maps it onto the substrate:

- the router is a ``SubstrateContract`` that proposes tool calls (``OutputForm.TOOL_CALL``) and never
  actuates (``may_actuate=False``);
- each tool in the NLP-CLI spec is a ``ToolContract``, with its risk level mapped to Organism's scale;
- ``dispatch`` hands a proposed call to a ``ToolHost``. The host, not the router, decides: it checks the
  contract, the arguments, the path scope and the confirmation. A router decision is a proposal only.

The adapter runs no tool. Each handler is supplied by the product, so the executors stay with NLP-CLI or
with whatever runs the tools.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from organism_sdk.canonical import canonical_text
from organism_sdk.contract import (
    BudgetClass,
    CapabilityScopes,
    DataType,
    DegradationKind,
    Determinism,
    EmissionSignature,
    EscalationKind,
    FailureMode,
    FailureSignature,
    HardwareRequirement,
    HealthEscalationPolicy,
    HealthProbe,
    HealthRpc,
    Identity,
    JustificationKind,
    Lifecycle,
    MaxSafetyTier,
    MetabolicProfile,
    Modality,
    ModuleRole,
    OutputForm,
    PerceptionSignature,
    RecoveryKind,
    RecoveryProcedure,
    ReliabilityTier,
    ResourceVector,
    SafetyDeclaration,
    Shape,
    SubstrateContract,
    ToolConfinement,
    ToolConfirmation,
    ToolContract,
    ToolNetwork,
    UncertaintyKind,
)
from organism_sdk.tool_host import CallResult, Confirm, Handler, ToolHost

SPEC_FORMAT = "nlpcli-tools"
SPEC_VERSION = 1
MODULE_AUTHOR = "nlp-cli"
MODULE_LICENSE = "UNLICENSED"
HEALTH_METHOD = "organism.nlp_cli.Router/Health"
DECISIONS = frozenset({"execute", "confirm", "no_tool", "declined", "abstain"})
_PROPOSALS = frozenset({"execute", "confirm"})

# NLP-CLI risk level -> (Organism tier, confirmation, network, confinement). See the mapping doc, section 3.
_RISK: dict[str, tuple[MaxSafetyTier, ToolConfirmation, ToolNetwork, ToolConfinement]] = {
    "read": (MaxSafetyTier.LOW, ToolConfirmation.NONE, ToolNetwork.NONE, ToolConfinement.NONE),
    "write": (MaxSafetyTier.MEDIUM, ToolConfirmation.ALWAYS, ToolNetwork.NONE, ToolConfinement.SCOPED),
    "execute": (MaxSafetyTier.HIGH, ToolConfirmation.ALWAYS, ToolNetwork.LOCAL, ToolConfinement.SCOPED),
    "destructive": (MaxSafetyTier.HIGH, ToolConfirmation.ALWAYS, ToolNetwork.NONE, ToolConfinement.STRICT),
}
# A push leaves the machine, so it needs internet access, which requires STRICT confinement.
_INTERNET_TOOLS = frozenset({"git_push"})
_SLOT_SCHEMAS: dict[str, dict[str, Any]] = {
    "path": {"type": "string", "minLength": 1, "maxLength": 512},
    "text": {"type": "string", "minLength": 1, "maxLength": 512},
    "message": {"type": "string", "minLength": 1, "maxLength": 512},
    "command": {"type": "string", "minLength": 1, "maxLength": 512},
}


class RouterError(RuntimeError):
    """The router could not give a usable decision. Nothing should run."""


@dataclass(frozen=True)
class RouteResult:
    action: str
    tool: str | None = None
    args: Mapping[str, str] = field(default_factory=dict)
    tier: str = ""
    confidence: float | None = None
    risk: str | None = None
    best_label: str | None = None
    reason: str = ""


def load_spec(path: str | Path) -> dict[str, Any]:
    """Read an NLP-CLI tool spec and check its format and version."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != SPEC_FORMAT or data.get("version") != SPEC_VERSION:
        raise RouterError(f"{path}: not an {SPEC_FORMAT} version {SPEC_VERSION} spec")
    if not isinstance(data.get("tools"), list):
        raise RouterError(f"{path}: spec has no tools list")
    return data


def model_digest(model: str | Path) -> bytes:
    """The SHA-256 of a model file, as raw bytes, checked against its ``.sha256`` sidecar.

    ``nlp-cli train`` writes the sidecar in ``sha256sum`` format. A missing sidecar, a sidecar that does not
    hold a digest, or a file whose bytes differ from it is refused. So a contract never names a digest that
    the file does not have, and the value is computed from the file, not copied from the sidecar.
    """
    path = Path(model)
    sidecar = path.with_name(path.name + ".sha256")
    try:
        fields = sidecar.read_text(encoding="utf-8").split()
    except OSError as exc:
        raise RouterError(f"no digest sidecar for {path.name}: {exc.strerror}") from exc
    if not fields or len(fields[0]) != 64:
        raise RouterError(f"{sidecar.name} does not start with a SHA-256 digest")
    try:
        claimed = bytes.fromhex(fields[0])
    except ValueError as exc:
        raise RouterError(f"{sidecar.name} does not hold hexadecimal digits") from exc
    try:
        actual = hashlib.sha256(path.read_bytes()).digest()
    except OSError as exc:
        raise RouterError(f"cannot read {path.name}: {exc.strerror}") from exc
    if actual != claimed:
        raise RouterError(f"{path.name} does not match {sidecar.name}; retrain or restore the model")
    return actual


def _has_path(slots: Sequence[Mapping[str, Any]]) -> bool:
    return any(slot.get("kind") == "path" for slot in slots)


def tool_contracts(spec: Mapping[str, Any]) -> list[ToolContract]:
    """One ``ToolContract`` per tool in the spec, with the risk mapping from the mapping doc."""
    contracts: list[ToolContract] = []
    for tool in spec["tools"]:
        name = str(tool["name"])
        risk = str(tool["risk"])
        if risk not in _RISK:
            raise RouterError(f"{name}: unknown risk level {risk}")
        slots = list(tool.get("slots", []))
        properties: dict[str, Any] = {}
        for slot in slots:
            kind = str(slot.get("kind"))
            if kind not in _SLOT_SCHEMAS:
                raise RouterError(f"{name}: unknown slot kind {kind}")
            properties[str(slot["name"])] = dict(_SLOT_SCHEMAS[kind])
        schema = {
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
            "additionalProperties": False,
        }
        level, confirmation, network, confinement = _RISK[risk]
        if name in _INTERNET_TOOLS:
            network, confinement = ToolNetwork.INTERNET, ToolConfinement.STRICT
        if _has_path(slots) and confinement == ToolConfinement.NONE:
            confinement = ToolConfinement.SCOPED
        contracts.append(
            ToolContract(
                name=name,
                schema_json=canonical_text(schema),
                risk_tier=level,
                confirmation=confirmation,
                network=network,
                confinement=confinement,
            )
        )
    return contracts


def path_args(spec: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """The path arguments of each tool, for ``ToolHost.register``."""
    return {
        str(tool["name"]): tuple(str(slot["name"]) for slot in tool.get("slots", []) if slot.get("kind") == "path")
        for tool in spec["tools"]
    }


def register_tools(host: ToolHost, spec: Mapping[str, Any], handlers: Mapping[str, Handler]) -> list[str]:
    """Register the tools that have a handler. A tool without one is not served, so a call to it is refused."""
    paths = path_args(spec)
    registered: list[str] = []
    for contract in tool_contracts(spec):
        handler = handlers.get(contract.name)
        if handler is None:
            continue
        host.register(contract, handler, path_args=paths.get(contract.name, ()))
        registered.append(contract.name)
    return registered


def parse_result(payload: Any) -> RouteResult:
    """Turn one ``route --json`` decision into a ``RouteResult``. Unknown shapes raise ``RouterError``."""
    if not isinstance(payload, dict) or payload.get("action") not in DECISIONS:
        raise RouterError("router output is not a known decision")
    action = str(payload["action"])
    tier = str(payload.get("tier", ""))
    if action in _PROPOSALS:
        tool = payload.get("tool")
        args = payload.get("args", {})
        if not isinstance(tool, str) or not isinstance(args, dict):
            raise RouterError(f"{action} decision has no tool or arguments")
        return RouteResult(
            action=action,
            tool=tool,
            args={str(k): str(v) for k, v in args.items()},
            tier=tier,
            confidence=float(payload.get("confidence", 0.0)),
            risk=payload.get("risk"),
        )
    if action == "abstain":
        best = payload.get("best_label")
        confidence = payload.get("confidence")
        return RouteResult(
            action=action,
            tier=tier,
            best_label=best if isinstance(best, str) else None,
            confidence=float(confidence) if confidence is not None else None,
            reason=str(payload.get("reason", "")),
        )
    if action == "declined":
        return RouteResult(action=action, tier=tier, reason=str(payload.get("reason", "")))
    return RouteResult(action=action, tier=tier, confidence=float(payload.get("confidence", 0.0)))


Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def _subprocess_runner(timeout_s: float) -> Runner:
    def run(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            check=False,
        )

    return run


class NlpCliRouter:
    """Calls the ``nlp-cli`` binary for one decision per request.

    Exit codes from the binary report the decision, so a non-zero code is not an error here. Only output
    that is not a decision is an error.
    """

    def __init__(
        self,
        binary: str | Path,
        spec: str | Path,
        model: str | Path | None = None,
        *,
        runner: Runner | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._binary = str(binary)
        self._spec_path = str(spec)
        self._model_path = str(model) if model is not None else None
        self._spec = load_spec(spec)
        self._runner: Runner = runner if runner is not None else _subprocess_runner(timeout_s)

    @property
    def spec(self) -> dict[str, Any]:
        return self._spec

    def route(self, text: str) -> RouteResult:
        if not text.strip():
            raise RouterError("empty request")
        if text.lstrip().startswith("-"):
            # The binary would read a leading dash as an option, so the request is refused, not guessed at.
            raise RouterError("a request may not start with '-'")
        argv = [self._binary, "route", "--json", "--spec", self._spec_path]
        if self._model_path is not None:
            argv += ["--model", self._model_path]
        argv.append(text)
        proc = self._runner(argv)
        try:
            payload = json.loads(proc.stdout)
        except (ValueError, TypeError) as exc:
            detail = (proc.stderr or "").strip()[:200]
            raise RouterError(f"router output is not JSON (exit {proc.returncode}): {detail}") from exc
        return parse_result(payload)


def dispatch(result: RouteResult, host: ToolHost, *, confirm: Confirm | None = None) -> CallResult | None:
    """Ask the host to run what the router proposed. Only ``execute`` and ``confirm`` reach the host.

    The host decides. A proposal for an unregistered tool, invalid arguments, an out-of-scope path or a
    missing confirmation is refused by the host, whatever the router said.
    """
    if result.action not in _PROPOSALS or result.tool is None:
        return None
    return host.call(result.tool, dict(result.args), confirm=confirm)


def router_contract(*, version: str, artifact_digest: bytes = b"") -> SubstrateContract:
    """The router's substrate contract. Declared as learned and calibrated (T2), and as unable to actuate.

    ``artifact_digest`` is the SHA-256 of the model file the router loads, as raw bytes. Leave it empty
    only while no model is bound to the contract.
    """
    return SubstrateContract(
        identity=Identity(
            module_id="nlp_cli_router",
            version=version,
            author=MODULE_AUTHOR,
            license=MODULE_LICENSE,
            role=ModuleRole.PREDICTION,
            artifact_digest=artifact_digest,
        ),
        perception=PerceptionSignature(
            modalities=(Modality.TEXT,),
            required_modalities=(Modality.TEXT,),
            shapes={"TEXT": Shape(dims=(1,), dtype=DataType.INT64)},
        ),
        emission=EmissionSignature(
            output_form=OutputForm.TOOL_CALL,
            shape=Shape(dims=(1,), dtype=DataType.INT64),
            uncertainty=UncertaintyKind.NONE,
            determinism=Determinism.DETERMINISTIC,
            requires_justification_for=(JustificationKind.HUMAN_CONFIRMATION,),
        ),
        metabolic=MetabolicProfile(
            latency_p50_ms=20.0,
            latency_p95_ms=80.0,
            latency_p99_ms=200.0,
            energy_per_inference_j=0.0001,
            memory_footprint_mb=4.0,
            memory_peak_mb=8.0,
            metabolic_budget_class=BudgetClass.LEAN,
            declared_share=ResourceVector(cpu_cores=0.1, memory_mb=8.0),
            requires_special_hardware=HardwareRequirement.NONE,
        ),
        failure=FailureSignature(
            modes=(
                FailureMode(
                    name="crash",
                    observable_signal="router.health",
                    expected_degradation=DegradationKind.CRASH,
                    detection_latency_budget_ms=500.0,
                ),
            ),
            probe=HealthProbe(HealthRpc(method_fqn=HEALTH_METHOD, timeout_ms=200)),
            recovery=RecoveryProcedure(kind=RecoveryKind.RESTART, max_attempts=3),
            escalation=HealthEscalationPolicy(
                kind=EscalationKind.PROBE_OR_DURATION,
                consecutive_probe_failures=2,
                degraded_duration_ms=5000,
                escalate_on_probe_timeout=True,
                escalate_on_probe_unreachable=False,
                probe_interval_ms=1000,
            ),
        ),
        safety=SafetyDeclaration(
            reliability_tier=ReliabilityTier.T2_LEARNED_CALIBRATED,
            may_actuate=False,
            requires_causal_certificate=False,
            requires_cross_check=False,
            max_safety_tier=MaxSafetyTier.HIGH,
        ),
        lifecycle=Lifecycle(hot_swap_supported=True, shadow_validation_required=True),
        capabilities=CapabilityScopes(
            read_roles=(ModuleRole.PREDICTION.value.lower(),),
            write_roles=(),
            read_tags=("workspace",),
            write_tags=(),
            can_emit_control_affecting=False,
        ),
    )
