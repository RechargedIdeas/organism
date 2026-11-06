"""Tool host: runs a tool only as its contract allows (gaps A2, A3 and G1).

A product owns its tools' code. The host owns the rules around each call:

1. the tool is registered, and its name is in the contract (unknown names are refused);
2. the arguments match the contract's JSON Schema (a subset; any keyword outside it is refused at
   registration, so the host fails closed);
3. every path argument resolves inside the path scope (``pathscope.PathScope``);
4. a call the contract says needs confirmation gets it, from a callback that returns the approver's
   identity, and records a ``HUMAN_CONFIRMATION`` justification (A3);
5. the handler runs, and the call is appended to a hash-chained audit record.

Refusals raise ``ToolRefused``. A declined confirmation returns ``CallResult(ok=False)``. Neither ever
runs the handler. The host runs no tool itself: each handler is supplied by the product.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from organism_sdk.canonical import CanonicalError, canonical_text
from organism_sdk.contract import Severity, ToolConfinement, ToolConfirmation, ToolContract
from organism_sdk.pathscope import PathEscape, PathScope

_GENESIS = "0" * 64
_SUPPORTED_KEYWORDS = frozenset(
    {"$schema", "title", "description", "type", "properties", "required", "additionalProperties", "enum",
     "minLength", "maxLength"}
)
_SCALAR_TYPES = frozenset({"string", "integer", "boolean"})


class ToolRefused(RuntimeError):
    """The call breaks the contract. The handler did not run."""


class ToolRegistrationError(ValueError):
    """The contract or its schema cannot be served. Nothing was registered."""


@dataclass(frozen=True)
class Confirmation:
    """A person's confirmation of one call. ``args_digest`` ties it to the arguments shown."""

    tool: str
    args_digest: str
    approver: str


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    tool: str
    args_digest: str
    outcome: str
    prev: str
    digest: str


@dataclass(frozen=True)
class CallResult:
    tool: str
    ok: bool
    outcome: str
    output: str = ""
    confirmation: Confirmation | None = None


Handler = Callable[[Mapping[str, Any]], str]
Confirm = Callable[[str, Mapping[str, Any]], "str | None"]


@dataclass
class _Registered:
    contract: ToolContract
    schema: dict[str, Any]
    handler: Handler
    path_args: tuple[str, ...]
    confirmed_once: bool = False


def check_schema(schema: Mapping[str, Any]) -> None:
    """Raise ``ToolRegistrationError`` for any schema the validator cannot enforce exactly."""
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        raise ToolRegistrationError("the root of a tool schema must be an object")
    unknown = sorted(set(schema) - _SUPPORTED_KEYWORDS)
    if unknown:
        raise ToolRegistrationError(f"unsupported schema keywords: {', '.join(unknown)}")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ToolRegistrationError("properties must be an object")
    for name, prop in properties.items():
        if not isinstance(prop, Mapping):
            raise ToolRegistrationError(f"property {name} must be an object")
        bad = sorted(set(prop) - _SUPPORTED_KEYWORDS)
        if bad:
            raise ToolRegistrationError(f"property {name} uses unsupported keywords: {', '.join(bad)}")
        if prop.get("type") not in _SCALAR_TYPES:
            raise ToolRegistrationError(f"property {name} must have a scalar type")
    for name in schema.get("required", []):
        if name not in properties:
            raise ToolRegistrationError(f"required property {name} is not declared")


def validate_args(schema: Mapping[str, Any], args: Mapping[str, Any]) -> list[str]:
    """Problems with ``args`` against ``schema``. An empty list means the arguments are valid."""
    problems: list[str] = []
    properties: Mapping[str, Any] = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in args:
            problems.append(f"missing {name}")
    if schema.get("additionalProperties") is False:
        for name in args:
            if name not in properties:
                problems.append(f"unexpected {name}")
    for name, value in args.items():
        prop = properties.get(name)
        if prop is None:
            continue
        kind = prop["type"]
        if kind == "string" and not isinstance(value, str):
            problems.append(f"{name} must be a string")
            continue
        if kind == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            problems.append(f"{name} must be an integer")
            continue
        if kind == "boolean" and not isinstance(value, bool):
            problems.append(f"{name} must be a boolean")
            continue
        if "enum" in prop and value not in prop["enum"]:
            problems.append(f"{name} is not an allowed value")
        if isinstance(value, str):
            if "minLength" in prop and len(value) < prop["minLength"]:
                problems.append(f"{name} is shorter than {prop['minLength']}")
            if "maxLength" in prop and len(value) > prop["maxLength"]:
                problems.append(f"{name} is longer than {prop['maxLength']}")
    return problems


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _args_digest(args: Mapping[str, Any]) -> str:
    try:
        return _digest(canonical_text(dict(args)))
    except CanonicalError:
        return _digest(repr(sorted((str(k), repr(v)) for k, v in args.items())))


def verify_chain(records: list[AuditRecord]) -> bool:
    """True when every record's digest and link to the previous record are intact."""
    prev = _GENESIS
    for expected_seq, record in enumerate(records, start=1):
        if record.seq != expected_seq or record.prev != prev:
            return False
        body = canonical_text(
            {"seq": record.seq, "tool": record.tool, "args_digest": record.args_digest,
             "outcome": record.outcome, "prev": record.prev}
        )
        if _digest(body) != record.digest:
            return False
        prev = record.digest
    return True


class ToolHost:
    """Serves registered tools under their contracts. Not thread-safe; one host per session."""

    def __init__(
        self,
        scope: PathScope | None = None,
        sink: Callable[[AuditRecord], None] | None = None,
    ) -> None:
        self._scope = scope
        self._sink = sink
        self._tools: dict[str, _Registered] = {}
        self._audit: list[AuditRecord] = []

    def tools(self) -> list[str]:
        return sorted(self._tools)

    def register(self, contract: ToolContract, handler: Handler, *, path_args: tuple[str, ...] = ()) -> None:
        errors = [issue for issue in contract.validate() if issue.severity == Severity.ERROR]
        if errors:
            raise ToolRegistrationError(f"{contract.name}: {errors[0].code}")
        if contract.name in self._tools:
            raise ToolRegistrationError(f"tool {contract.name} is already registered")
        try:
            schema = json.loads(contract.schema_json)
        except ValueError as exc:
            raise ToolRegistrationError(f"{contract.name}: schema is not JSON") from exc
        check_schema(schema)
        for name in path_args:
            if name not in schema.get("properties", {}):
                raise ToolRegistrationError(f"{contract.name}: path argument {name} is not declared")
        if path_args and contract.confinement == ToolConfinement.NONE:
            raise ToolRegistrationError(f"{contract.name}: path arguments need SCOPED or STRICT confinement")
        self._tools[contract.name] = _Registered(contract, schema, handler, tuple(path_args))

    def call(
        self,
        name: str,
        args: Mapping[str, Any],
        *,
        confirm: Confirm | None = None,
    ) -> CallResult:
        """Run ``name`` with ``args`` if the contract allows it. See the module docstring for the order."""
        tool = self._tools.get(name)
        if tool is None:
            self._record(name, args, "refused_unknown")
            raise ToolRefused(f"unknown tool {name}")
        problems = validate_args(tool.schema, args)
        if problems:
            self._record(name, args, "refused_invalid")
            raise ToolRefused(f"{name}: " + "; ".join(problems))

        resolved: dict[str, Any] = dict(args)
        for path_arg in tool.path_args:
            if self._scope is None:
                self._record(name, args, "refused_scope")
                raise ToolRefused(f"{name}: no path scope is configured")
            try:
                resolved[path_arg] = str(self._scope.resolve(str(args[path_arg])))
            except PathEscape as exc:
                self._record(name, args, "refused_path")
                raise ToolRefused(f"{name}: {path_arg}: {exc}") from exc

        confirmation: Confirmation | None = None
        needs = tool.contract.confirmation == ToolConfirmation.ALWAYS or (
            tool.contract.confirmation == ToolConfirmation.ON_FIRST_USE and not tool.confirmed_once
        )
        if needs:
            if confirm is None:
                self._record(name, args, "refused_unconfirmed")
                raise ToolRefused(f"{name} needs a person's confirmation and none was given")
            approver = confirm(name, dict(resolved))
            if not approver:
                self._record(name, args, "declined")
                return CallResult(tool=name, ok=False, outcome="declined")
            confirmation = Confirmation(tool=name, args_digest=_args_digest(resolved), approver=approver)
            if tool.contract.confirmation == ToolConfirmation.ON_FIRST_USE:
                tool.confirmed_once = True

        try:
            output = tool.handler(resolved)
        except Exception as exc:  # noqa: BLE001 - the handler is product code; record the failure and report it
            self._record(name, args, "failed")
            return CallResult(tool=name, ok=False, outcome="failed", output=str(exc), confirmation=confirmation)
        self._record(name, args, "ran")
        return CallResult(tool=name, ok=True, outcome="ran", output=output, confirmation=confirmation)

    def audit(self) -> list[AuditRecord]:
        return list(self._audit)

    def _record(self, tool: str, args: Mapping[str, Any], outcome: str) -> None:
        prev = self._audit[-1].digest if self._audit else _GENESIS
        seq = len(self._audit) + 1
        args_digest = _args_digest(args)
        body = canonical_text({"seq": seq, "tool": tool, "args_digest": args_digest, "outcome": outcome, "prev": prev})
        record = AuditRecord(seq, tool, args_digest, outcome, prev, _digest(body))
        self._audit.append(record)
        if self._sink is not None:
            self._sink(record)
