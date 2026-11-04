"""Policy: the versioned rules for accepting work (002). Design record: docs/v1.12/WORK_AGENT.md.

A Policy is plain data. Its version is a digest of everything that decides admission:
the accept mode, the rules, and each Source's part. A change to any of them gives a new
version, and every Mandate records the version it was accepted under (001).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any


class AcceptMode(str, Enum):
    """What the gate does with inferred candidates (002)."""

    OFF = "off"
    OBSERVE = "observe"
    AUTO = "auto"


class Cell(str, Enum):
    """What an admission-table cell does with a message (002)."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    IGNORE = "ignore"


@dataclass(frozen=True)
class AdmissionRow:
    """The three cells of one receiving scope (002).

    The table's shape fixes what each cell may offer. An unaddressed message can be an
    inferred candidate or ignored, never an explicit request.
    """

    listed_unaddressed: Cell = Cell.INFERRED
    unlisted_addressed: Cell = Cell.IGNORE
    unlisted_unaddressed: Cell = Cell.IGNORE

    def __post_init__(self) -> None:
        if Cell.EXPLICIT in (self.listed_unaddressed, self.unlisted_unaddressed):
            raise ValueError("only an addressed message can be an explicit request")


@dataclass(frozen=True)
class Rule:
    """A kind of proactive work the team allows (002). Judged on every assessment."""

    id: str
    instruction: str
    enabled: bool = True


@dataclass(frozen=True)
class SourcePolicy:
    """A Source's part of the Policy (002): its allowed senders, its bots and its rows.

    Ids compare case-insensitively, so they are stored folded.
    """

    source: str
    allowed: frozenset[str] = frozenset()
    bots: frozenset[str] = frozenset()
    rows: Mapping[str, AdmissionRow] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed", frozenset(item.casefold() for item in self.allowed))
        object.__setattr__(self, "bots", frozenset(item.casefold() for item in self.bots))


@dataclass(frozen=True)
class Policy:
    """The rules, the accept mode and every Source's part (002)."""

    mode: AcceptMode = AcceptMode.OBSERVE
    rules: tuple[Rule, ...] = ()
    sources: tuple[SourcePolicy, ...] = ()

    def __post_init__(self) -> None:
        names = [part.source for part in self.sources]
        if len(set(names)) != len(names):
            raise ValueError("each Source has one part of the Policy")
        rule_ids = [rule.id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("rule ids are unique")
        # Ordering the Sources by name makes the version independent of how the Policy was built.
        object.__setattr__(
            self, "sources", tuple(sorted(self.sources, key=lambda part: part.source))
        )

    def source(self, name: str) -> SourcePolicy | None:
        """The Source's part of the Policy, or None when the Source has none."""
        return next((part for part in self.sources if part.source == name), None)

    @property
    def version(self) -> str:
        """The digest of this Policy. See `policy_version`."""
        return policy_version(self)


def policy_version(policy: Policy) -> str:
    """A digest of the whole Policy in one canonical form.

    The form has sorted keys, sorted sets, no whitespace and ASCII only. Changing it changes
    every version, so it is a breaking change to stored Mandates (docs/v1.12/WORK_AGENT.md, "Changing this record").
    """
    canonical = json.dumps(_plain(policy), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("ascii")).hexdigest()


def may_accept_inferred(policy: Policy, matched: Iterable[str]) -> bool:
    """A proactive accept needs auto mode and at least one matched rule that is enabled (002)."""
    if policy.mode is not AcceptMode.AUTO:
        return False
    enabled = {rule.id for rule in policy.rules if rule.enabled}
    return any(rule_id in enabled for rule_id in matched)


def _plain(value: Any) -> Any:
    """The JSON-ready form of a value: enums by value, sets sorted, mappings by key."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
