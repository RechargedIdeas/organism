"""Rule assessment: which of the Policy's rules a Trigger matches (002). Design record: docs/v1.12/WORK_AGENT.md.

Pure and deterministic. A rule is matched by its pattern alone, searched case-insensitively in
the Trigger's text. A rule without a pattern is never matched here, because judging it needs a
model, which is not adopted yet (W-D2). The same Trigger always gives the same answer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from organism_sdk.work.domain import Trigger
from organism_sdk.work.policy import Rule


@dataclass(frozen=True)
class Assessment:
    """The ids of the enabled rules a Trigger matched, sorted."""

    matched: tuple[str, ...] = ()


class RuleAssessor:
    """Matches Triggers against the enabled rules that have a pattern. Build one per Policy."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        self._patterns: dict[str, re.Pattern[str]] = {
            rule.id: re.compile(rule.pattern, re.IGNORECASE)
            for rule in rules
            if rule.enabled and rule.pattern is not None
        }

    def assess(self, trigger: Trigger) -> Assessment:
        hits = sorted(
            rule_id for rule_id, pattern in self._patterns.items() if pattern.search(trigger.text)
        )
        return Assessment(matched=tuple(hits))
