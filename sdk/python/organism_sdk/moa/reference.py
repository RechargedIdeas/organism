"""Reference MoA experts: rule-based, CPU-only, deterministic (v1.11).

These are the first two experts from the upgrade plan. They are stand-ins that
exercise the MoA machinery without model weights. A learned SLM backend plugs in
behind the same ``Expert`` protocol and declares tier T2 once it is calibrated.

Confidence semantics:
- ``intent_classifier``: share of matched keyword evidence that supports the best
  intent. This is a rule margin, not a calibrated probability.
- ``extractor``: 1.0 if any entity was found, else 0.0.
"""

from __future__ import annotations

import json
import re
from typing import Any

from organism_sdk.contract import ModuleRole
from organism_sdk.moa.experts import BaseExpert, CapabilityDescriptor, ExpertOutput

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "schedule": ("schedule", "meeting", "calendar", "book", "appointment"),
    "remind": ("remind", "reminder", "remember", "don't forget"),
    "summarize": ("summarize", "summary", "tldr", "shorten"),
    "translate": ("translate", "translation", "in french", "in spanish"),
}
NO_INTENT = "none"

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?\b")
EXTRACT_KEYS = ("dates", "emails", "numbers")


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def _well_formed(payload: str, required_keys: tuple[str, ...]) -> bool:
    try:
        body: Any = json.loads(payload)
    except json.JSONDecodeError:
        return False
    return isinstance(body, dict) and tuple(sorted(body)) == tuple(sorted(required_keys))


class IntentClassifier(BaseExpert):
    """Classifies a query into one of a fixed set of intents by keyword evidence."""

    def __init__(self) -> None:
        keywords = _dedupe([kw for kws in INTENT_KEYWORDS.values() for kw in kws])
        super().__init__(
            CapabilityDescriptor(
                expert_id="intent_classifier",
                domain="intent",
                task_forms=("pattern_recognition",),
                keywords=tuple(keywords),
                role=ModuleRole.PREDICTION,
                expected_latency_ms=3.0,
            )
        )

    def answer(self, query: str, form: str | None = None) -> ExpertOutput:
        text = query.lower()
        hits = {
            intent: [kw for kw in kws if _contains(text, kw)]
            for intent, kws in INTENT_KEYWORDS.items()
        }
        total = sum(len(v) for v in hits.values())
        if total == 0:
            payload = json.dumps({"intent": NO_INTENT, "matched": []}, sort_keys=True)
            return ExpertOutput(self.descriptor.expert_id, payload, 0.0, schema_valid=True)

        best = min(hits, key=lambda intent: (-len(hits[intent]), intent))
        payload = json.dumps({"intent": best, "matched": hits[best]}, sort_keys=True)
        confidence = len(hits[best]) / total
        valid = json.loads(payload)["intent"] in INTENT_KEYWORDS
        return ExpertOutput(self.descriptor.expert_id, payload, confidence, schema_valid=valid)


class Extractor(BaseExpert):
    """Extracts ISO dates, email addresses, and numbers, in order of appearance."""

    def __init__(self) -> None:
        super().__init__(
            CapabilityDescriptor(
                expert_id="extractor",
                domain="extraction",
                task_forms=("feature_extraction",),
                # "find" is not a keyword: it is too generic and routed "find me a hiking trail"
                # to this expert (held-out precision 0.78). Targets such as "dates" carry the signal.
                keywords=("extract", "dates", "emails", "numbers"),
                role=ModuleRole.FEATURE_EXTRACTOR,
                expected_latency_ms=4.0,
            )
        )

    def answer(self, query: str, form: str | None = None) -> ExpertOutput:
        dates = _DATE.findall(query)
        rest = _EMAIL.sub(" ", _DATE.sub(" ", query))
        emails = _EMAIL.findall(query)
        numbers = _NUMBER.findall(rest)
        found = {"dates": _dedupe(dates), "emails": _dedupe(emails), "numbers": _dedupe(numbers)}
        payload = json.dumps(found, sort_keys=True)
        confidence = 1.0 if any(found.values()) else 0.0
        return ExpertOutput(
            self.descriptor.expert_id,
            payload,
            confidence,
            schema_valid=_well_formed(payload, EXTRACT_KEYS),
        )


def reference_experts() -> list[BaseExpert]:
    """The two reference experts, in a fixed order."""
    return [IntentClassifier(), Extractor()]
