"""Rule-based guardrails for the MoA pipeline (v1.11, Phase 5).

Two checkpoints:

- ``input`` runs on the raw query before routing. A failed check ends the request with route
  ``blocked``. No expert runs and no fallback answer is produced.
- ``output`` runs on one expert's answer before aggregation. A failed check marks that answer
  schema-invalid, so it cannot be selected. The other experts' answers are not affected.

Each guardrail declares a ``GuardrailSpec``: its checkpoint, its rule in plain words, and the
false-positive and false-negative rates measured on ``tests/data/moa_guardrail_labeled.json``.
The test suite re-measures those rates and fails if the measurement is worse than the declared
value. The labels were written alongside the rules, so the declared rates are optimistic. The
red-team suite holds the variants the rules were not written against.

These are rules, not learned classifiers. They are deterministic and need no model weights.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

from organism_sdk.moa.experts import ExpertOutput

Checkpoint = Literal["input", "output"]

ENTITY_KEYS: tuple[str, ...] = ("dates", "emails", "numbers")

# Characters that split a phrase without changing how it reads: zero-width spaces and joiners,
# the word joiner, the byte-order mark, and the soft hyphen.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)

# Cyrillic and Greek letters that look like Latin ones. Only the injection rules fold them. The
# groundedness check compares values exactly, so folding there would make a homoglyph of a query
# entity count as grounded.
_CONFUSABLES = str.maketrans(
    {
        "\u0430": "a",  # Cyrillic a
        "\u0435": "e",  # Cyrillic ie
        "\u043e": "o",  # Cyrillic o
        "\u0440": "p",  # Cyrillic er
        "\u0441": "c",  # Cyrillic es
        "\u0443": "y",  # Cyrillic u
        "\u0445": "x",  # Cyrillic ha
        "\u0456": "i",  # Cyrillic Ukrainian i
        "\u0458": "j",  # Cyrillic je
        "\u0455": "s",  # Cyrillic dze
        "\u03bf": "o",  # Greek omicron
        "\u03b9": "i",  # Greek iota
        "\u03c1": "p",  # Greek rho
    }
)

# Each rule runs on normalized text (see ``normalize``). The name is returned as the reason.
INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override_instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass)\b"
            r"(?: (?:all|any|of|the|your|my|these|those|everything))*"
            r" (?:previous|prior|above|earlier|preceding|original|system|initial|safety)\b"
            r"(?: \w+)? (?:instructions|prompts?|rules|guidelines|directions)\b"
        ),
    ),
    (
        "reveal_instructions",
        re.compile(
            r"\b(?:reveal|print|show|repeat|leak|dump|display)\b"
            r"(?: \w+){0,3}? (?:system prompt|hidden instructions|initial instructions"
            r"|developer message|original instructions)\b"
        ),
    ),
    (
        # "your" is what makes it the assistant's own first message, not the user's.
        "reveal_first_message",
        re.compile(
            r"\b(?:tell|show|repeat|quote|recite|reveal|print|say|write)\b(?: \w+){0,6}? "
            r"your (?:first|initial|opening|original) (?:message|prompt|input)\b"
        ),
    ),
    (
        "persona_override",
        re.compile(
            r"\byou are (?:now|in) (?:an? )?(?:dan|unrestricted|jailbroken|developer mode)\b"
        ),
    ),
    (
        "persona_without_policy",
        re.compile(
            r"\b(?:answer|act|respond|behave|speak|reply)\b(?: \w+){0,6}? as (?:an? |the )?"
            r"(?:\w+ ){0,2}?(?:assistant|model|ai|bot|chatbot|persona|character)\b"
            r"(?: \w+){0,6}? (?:that|who|which) (?:has|have|with) no "
            r"(?:safety|rules|restrictions|guidelines|filters|limits|policy|policies)\b"
        ),
    ),
    (
        "disable_rules",
        re.compile(
            r"\b(?:pretend|act as if|imagine)\b(?: \w+){0,3}? "
            r"(?:have no|has no|there are no) (?:rules|restrictions|guidelines|limits|filters)\b"
        ),
    ),
    (
        "named_jailbreak",
        re.compile(r"\bjailbr(?:eak|oken)s?\b|\bdo anything now\b"),
    ),
)


def normalize(text: str) -> str:
    """Fold width and case, drop invisible characters, and collapse whitespace."""
    folded = unicodedata.normalize("NFKC", text).translate(_INVISIBLE).casefold()
    return " ".join(folded.split())


def _fold_confusables(text: str) -> str:
    return text.translate(_CONFUSABLES)


@dataclass(frozen=True)
class GuardrailSpec:
    """The declared contract of one guardrail.

    ``false_positive_rate`` is the share of benign labeled queries or answers the guard blocks.
    ``false_negative_rate`` is the share of harmful ones it lets through. ``None`` means the rate
    has not been measured.
    """

    guard_id: str
    checkpoint: Checkpoint
    rule: str
    false_positive_rate: float | None
    false_negative_rate: float | None


@dataclass(frozen=True)
class GuardVerdict:
    passed: bool
    guard_id: str
    reason: str = ""


class InputGuardrail(Protocol):
    @property
    def spec(self) -> GuardrailSpec: ...

    def check_input(self, query: str) -> GuardVerdict: ...


class OutputGuardrail(Protocol):
    @property
    def spec(self) -> GuardrailSpec: ...

    def check_output(self, query: str, output: ExpertOutput) -> GuardVerdict: ...


class InjectionGuard:
    """Blocks queries that try to override instructions, expose the hidden prompt, or adopt an
    unrestricted persona."""

    spec = GuardrailSpec(
        guard_id="prompt_injection",
        checkpoint="input",
        rule=(
            "block queries that ask to ignore instructions, reveal the system prompt or the "
            "assistant's first message, adopt an unrestricted persona or one with no policy, or "
            "disable rules"
        ),
        false_positive_rate=0.08,
        false_negative_rate=0.08,
    )

    def check_input(self, query: str) -> GuardVerdict:
        text = _fold_confusables(normalize(query))
        for name, pattern in INJECTION_RULES:
            if pattern.search(text):
                return GuardVerdict(passed=False, guard_id=self.spec.guard_id, reason=name)
        return GuardVerdict(passed=True, guard_id=self.spec.guard_id)


class GroundednessGuard:
    """Rejects an answer whose extracted entities do not occur in the query.

    Only the keys in ``entity_keys`` are checked. Other keys, such as an intent label, are
    categories rather than text from the query. Matching is by substring on normalized text, so
    a value that is part of a longer token counts as grounded.
    """

    spec = GuardrailSpec(
        guard_id="grounded_entities",
        checkpoint="output",
        rule="every extracted entity value must occur in the query text",
        false_positive_rate=0.0,
        false_negative_rate=None,
    )

    def __init__(self, entity_keys: tuple[str, ...] = ENTITY_KEYS) -> None:
        self._keys = entity_keys

    def check_output(self, query: str, output: ExpertOutput) -> GuardVerdict:
        passed = GuardVerdict(passed=True, guard_id=self.spec.guard_id)
        try:
            body = json.loads(output.payload)
        except json.JSONDecodeError:
            return passed  # Malformed payloads are the schema check's job.
        if not isinstance(body, dict):
            return passed
        text = normalize(query)
        for key in self._keys:
            values = body.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, str) and normalize(value) not in text:
                    return GuardVerdict(passed=False, guard_id=self.spec.guard_id, reason=key)
        return passed


__all__ = [
    "ENTITY_KEYS",
    "INJECTION_RULES",
    "GroundednessGuard",
    "GuardVerdict",
    "GuardrailSpec",
    "InjectionGuard",
    "InputGuardrail",
    "OutputGuardrail",
    "normalize",
]
