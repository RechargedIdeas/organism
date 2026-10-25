"""Pluggable draft backends for generative code (template + LLM stub + hosted). CPU-only.

GeneratorBackend is the production protocol; DraftBackend remains the ABC alias
for backwards compatibility. Drafts are replayable via DraftReplayLog.
"""
from __future__ import annotations

import hashlib
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GeneratorBackend(Protocol):
    """Pluggable production protocol for generative code drafts."""

    name: str

    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        """Return Python source for a sandboxed ``main(**kwargs)`` entrypoint."""
        ...


class DraftBackend(ABC):
    """ABC form of GeneratorBackend (existing callers keep working)."""

    name: str = "base"

    @abstractmethod
    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        """Return Python source for a sandboxed ``main(**kwargs)`` entrypoint."""


# ---------------------------------------------------------------------------
# Template library — richer, named, deterministic Organism skill stubs
# ---------------------------------------------------------------------------

_TEMPLATE_LIBRARY: dict[str, str] = {
    "adder": """\
# Organism generative draft — template=adder digest={digest}
# intent: {safe_intent}
def main(x=0.0, y=0.0, **kwargs):
    \"\"\"Organism adder skill.\"\"\"
    score = float(x) + float(y)
    return {{'ok': True, 'skill': {skill!r}, 'score': score, 'digest': {digest!r}, 'template': 'adder'}}
""",
    "scorer": """\
# Organism generative draft — template=scorer digest={digest}
# intent: {safe_intent}
def main(x=0.0, y=0.0, **kwargs):
    \"\"\"Organism weighted scorer.\"\"\"
    a = abs(float(x)) + abs(float(y))
    b = a * 0.5 + len({skill!r}) * 0.01
    return {{'ok': True, 'skill': {skill!r}, 'score': b, 'digest': {digest!r}, 'template': 'scorer'}}
""",
    "navigator": """\
# Organism generative draft — template=navigator digest={digest}
# intent: {safe_intent}
def main(features=None, **kwargs):
    \"\"\"Organism navigator over a feature list.\"\"\"
    features = list(features or [0.1, 0.2, 0.3])
    acc = 0.0
    for i, v in enumerate(features):
        acc = acc + float(v) * (0.05 + (i % 5) * 0.01)
    return {{'ok': True, 'skill': {skill!r}, 'prediction': acc, 'digest': {digest!r}, 'template': 'navigator'}}
""",
    "filter": """\
# Organism generative draft — template=filter digest={digest}
# intent: {safe_intent}
def main(values=None, threshold=0.5, **kwargs):
    \"\"\"Organism threshold filter.\"\"\"
    values = list(values or [0.1, 0.6, 0.9])
    kept = [float(v) for v in values if float(v) >= float(threshold)]
    return {{'ok': True, 'skill': {skill!r}, 'score': len(kept), 'kept': kept, 'digest': {digest!r}, 'template': 'filter'}}
""",
    "aggregator": """\
# Organism generative draft — template=aggregator digest={digest}
# intent: {safe_intent}
def main(values=None, **kwargs):
    \"\"\"Organism mean aggregator.\"\"\"
    values = list(values or [1.0, 2.0, 3.0])
    nums = [float(v) for v in values]
    mean = sum(nums) / max(1, len(nums))
    return {{'ok': True, 'skill': {skill!r}, 'score': mean, 'n': len(nums), 'digest': {digest!r}, 'template': 'aggregator'}}
""",
    "classifier": """\
# Organism generative draft — template=classifier digest={digest}
# intent: {safe_intent}
def main(x=0.0, **kwargs):
    \"\"\"Organism binary classifier stub.\"\"\"
    score = 1.0 / (1.0 + abs(float(x)))
    label = 'pos' if score >= 0.5 else 'neg'
    return {{'ok': True, 'skill': {skill!r}, 'score': score, 'label': label, 'digest': {digest!r}, 'template': 'classifier'}}
""",
    "normalizer": """\
# Organism generative draft — template=normalizer digest={digest}
# intent: {safe_intent}
def main(values=None, **kwargs):
    \"\"\"Organism L1 normalizer.\"\"\"
    values = list(values or [1.0, 2.0, 3.0])
    nums = [float(v) for v in values]
    s = sum(abs(v) for v in nums) or 1.0
    normed = [v / s for v in nums]
    return {{'ok': True, 'skill': {skill!r}, 'score': sum(normed), 'values': normed, 'digest': {digest!r}, 'template': 'normalizer'}}
""",
    "ranker": """\
# Organism generative draft — template=ranker digest={digest}
# intent: {safe_intent}
def main(values=None, **kwargs):
    \"\"\"Organism descending ranker.\"\"\"
    values = list(values or [0.2, 0.9, 0.4])
    nums = [float(v) for v in values]
    order = sorted(range(len(nums)), key=lambda i: nums[i], reverse=True)
    return {{'ok': True, 'skill': {skill!r}, 'score': nums[order[0]] if order else 0.0, 'order': order, 'digest': {digest!r}, 'template': 'ranker'}}
""",
    "smoother": """\
# Organism generative draft — template=smoother digest={digest}
# intent: {safe_intent}
def main(values=None, alpha=0.5, **kwargs):
    \"\"\"Organism exponential smoother.\"\"\"
    values = list(values or [0.1, 0.5, 0.2, 0.8])
    a = float(alpha)
    if a < 0.0:
        a = 0.0
    if a > 1.0:
        a = 1.0
    out = []
    prev = 0.0
    for v in values:
        prev = a * float(v) + (1.0 - a) * prev
        out.append(prev)
    return {{'ok': True, 'skill': {skill!r}, 'score': out[-1] if out else 0.0, 'smoothed': out, 'digest': {digest!r}, 'template': 'smoother'}}
""",
    "gate": """\
# Organism generative draft — template=gate digest={digest}
# intent: {safe_intent}
def main(x=0.0, lo=0.0, hi=1.0, **kwargs):
    \"\"\"Organism soft gate between lo/hi.\"\"\"
    v = float(x)
    a = float(lo)
    b = float(hi)
    if b < a:
        a, b = b, a
    if v < a:
        score = 0.0
    elif v > b:
        score = 1.0
    else:
        score = (v - a) / ((b - a) or 1.0)
    return {{'ok': True, 'skill': {skill!r}, 'score': score, 'digest': {digest!r}, 'template': 'gate'}}
""",
}


def list_templates() -> list[str]:
    return sorted(_TEMPLATE_LIBRARY)


def _pick_template(intent: str, spec: dict[str, Any]) -> str:
    explicit = str(spec.get("template") or "").strip().lower()
    if explicit in _TEMPLATE_LIBRARY:
        return explicit
    intent_l = intent.lower()
    for name in ("navigator", "filter", "aggregator", "classifier", "normalizer", "ranker", "smoother", "gate", "adder", "scorer"):
        if name in intent_l or name in str(spec.get("skill_name") or "").lower():
            return name
    return "scorer"


class TemplateDraftBackend(DraftBackend):
    """Deterministic template-library backend — production-grade default, no network."""

    name = "template"

    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        spec = spec or {}
        skill = str(spec.get("skill_name") or "skill")
        digest = hashlib.sha256(intent.encode()).hexdigest()[:12]
        safe_intent = intent[:200].replace("\n", " ").replace('"', "'")
        tmpl_name = _pick_template(intent, spec)
        tmpl = _TEMPLATE_LIBRARY[tmpl_name]
        return tmpl.format(digest=digest, safe_intent=safe_intent, skill=skill)


class LLMStubBackend(DraftBackend):
    """Pluggable LLM-shaped stub — deterministic, offline, CPU-only.

    Production wiring can swap this for a real provider without changing the
    pipeline stages; promote gates remain mandatory either way.
    """

    name = "llm_stub"

    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        spec = spec or {}
        skill = str(spec.get("skill_name") or "llm_skill")
        seed = int(hashlib.sha256(f"{intent}:{skill}".encode()).hexdigest()[:8], 16)
        bias = (seed % 1000) / 1000.0
        lines = [
            f"# Organism generative draft — backend=llm_stub seed={seed}",
            "def main(features=None, **kwargs):",
            "    features = list(features or [0.1, 0.2, 0.3])",
            f"    acc = {bias}",
            "    for i, v in enumerate(features):",
            "        acc = acc + float(v) * (0.1 + (i % 3) * 0.01)",
            f"    return {{'ok': True, 'skill': {skill!r}, 'prediction': acc, 'backend': 'llm_stub'}}",
            "",
        ]
        return "\n".join(lines)


@dataclass
class DraftReplayEntry:
    entry_id: str
    backend: str
    intent: str
    spec: dict[str, Any]
    source: str
    source_digest: str
    at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "backend": self.backend,
            "intent": self.intent,
            "spec": self.spec,
            "source_digest": self.source_digest,
            "source_lines": len(self.source.splitlines()),
            "at": self.at,
        }


class DraftReplayLog:
    """Replayable draft journal — re-emit identical source from recorded intent/spec."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self._entries: list[DraftReplayEntry] = []
        self._lock = threading.RLock()
        if self.path and self.path.is_file():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for row in raw:
                self._entries.append(
                    DraftReplayEntry(
                        entry_id=row["entry_id"],
                        backend=row["backend"],
                        intent=row["intent"],
                        spec=row.get("spec") or {},
                        source=row.get("source") or "",
                        source_digest=row["source_digest"],
                        at=row["at"],
                    )
                )
        except Exception:
            self._entries = []

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for e in self._entries:
            d = e.as_dict()
            d["source"] = e.source
            payload.append(d)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def record(
        self,
        *,
        backend: str,
        intent: str,
        source: str,
        spec: dict[str, Any] | None = None,
    ) -> DraftReplayEntry:
        with self._lock:
            digest = hashlib.sha256(source.encode()).hexdigest()
            entry = DraftReplayEntry(
                entry_id=digest[:16],
                backend=backend,
                intent=intent,
                spec=dict(spec or {}),
                source=source,
                source_digest=digest,
                at=datetime.now(timezone.utc).isoformat(),
            )
            self._entries.append(entry)
            self._save()
            return entry

    def replay(self, entry_id: str) -> DraftReplayEntry:
        with self._lock:
            for e in self._entries:
                if e.entry_id == entry_id or e.source_digest.startswith(entry_id):
                    return e
            raise KeyError(f"unknown draft replay entry_id={entry_id}")

    def list_entries(self) -> list[dict[str, Any]]:
        return [e.as_dict() for e in self._entries]




class HostedLLMRefused(PermissionError):
    """Raised when hosted LLM is selected but not properly configured."""


def _extract_python_source(content: str) -> str:
    text = content.strip()
    if "```" in text:
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                body = part
                if body.startswith("python"):
                    body = body[6:]
                elif body.startswith("py"):
                    body = body[2:]
                return body.strip()
    return text


class HostedLLMBackend(DraftBackend):
    """Optional HTTP OpenAI-compatible chat backend — env-gated, never default-on.

    Required when enabled:
      ORGANISM_LLM_ENABLED=1
      ORGANISM_LLM_URL
      ORGANISM_LLM_API_KEY
    Optional: ORGANISM_LLM_MODEL (default gpt-4o-mini), ORGANISM_LLM_TIMEOUT_S (30).

    Keys stay in env/vault — never committed. CPU Everywhere: stdlib urllib only.
    """

    name = "hosted_llm"

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        import os

        self.url = (url if url is not None else os.environ.get("ORGANISM_LLM_URL", "")).strip()
        self.api_key = (
            api_key if api_key is not None else os.environ.get("ORGANISM_LLM_API_KEY", "")
        ).strip()
        self.model = (
            model if model is not None else os.environ.get("ORGANISM_LLM_MODEL", "gpt-4o-mini")
        ).strip() or "gpt-4o-mini"
        env_en = os.environ.get("ORGANISM_LLM_ENABLED", "").lower() in ("1", "true", "yes")
        self.enabled = bool(enabled) if enabled is not None else env_en
        env_to = os.environ.get("ORGANISM_LLM_TIMEOUT_S", "30")
        self.timeout_s = float(timeout_s if timeout_s is not None else env_to)

    def _check_ready(self) -> None:
        if not self.enabled:
            raise HostedLLMRefused(
                "hosted LLM disabled — set ORGANISM_LLM_ENABLED=1 (never default-on)"
            )
        if not self.url:
            raise HostedLLMRefused("ORGANISM_LLM_URL required for HostedLLMBackend")
        if not self.api_key:
            raise HostedLLMRefused("ORGANISM_LLM_API_KEY required for HostedLLMBackend")

    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        self._check_ready()
        import json
        import urllib.error
        import urllib.request

        spec = spec or {}
        skill = str(spec.get("skill_name") or "hosted_skill")
        system = (
            "You write a single Python function main(**kwargs) for the Organism sandbox. "
            "No imports, no file I/O, no os/sys/subprocess. Return only Python source."
        )
        user = (
            f"intent: {intent[:800]}\n"
            f"skill_name: {skill}\n"
            "Return exactly one def main(...): body that returns a dict with ok/score keys."
        )
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "organism-hosted-llm/1.9",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise HostedLLMRefused(f"HTTP {e.code}: {e.reason}") from e
        except Exception as e:
            raise HostedLLMRefused(f"{type(e).__name__}: {e}") from e
        try:
            content = raw["choices"][0]["message"]["content"]
        except Exception as e:
            raise HostedLLMRefused(f"malformed provider response: {e}") from e
        source = _extract_python_source(str(content))
        if "def main" not in source:
            raise HostedLLMRefused("provider response missing def main")
        safe_intent = intent[:120].replace("\n", " ")
        header = (
            f"# Organism generative draft — backend=hosted_llm model={self.model}\n"
            f"# intent: {safe_intent}\n"
        )
        return header + source


def resolve_backend(name: str | None = None) -> DraftBackend:
    """Factory for named backends (template | llm_stub | hosted_llm).

    ``hosted`` / ``hosted_llm`` never activates unless ORGANISM_LLM_ENABLED=1
    and URL/key are present — HostedLLMBackend.draft raises otherwise.
    Default remains offline template library (CPU Everywhere).
    """
    import os

    key = (name or os.environ.get("ORGANISM_GENERATIVE_BACKEND") or "template").strip().lower()
    if key in ("hosted_llm", "hosted", "openai"):
        return HostedLLMBackend()
    if key in ("llm_stub", "llm"):
        return LLMStubBackend()
    return TemplateDraftBackend()
