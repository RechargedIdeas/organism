"""Canonical JSON writer (gap C3). Pure: no imports beyond the standard library.

The rule is language neutral and pinned by ``conformance/vectors/canonical.json``. Every SDK must write
the same bytes for the same value. See ``docs/INTEROP.md``, "Canonical JSON".

* Objects: keys sorted by Unicode code point (the same order as their UTF-8 bytes), no duplicate keys.
* No whitespace outside strings. Separators are ``,`` and ``:``.
* Output is UTF-8. Non-ASCII characters are written as themselves, never as ``\\u`` escapes.
* Strings: ``"`` and ``\\`` are escaped. ``\\b \\f \\n \\r \\t`` use their short escape. Every other character
  below U+0020 is ``\\u00xx`` in lower-case hex. ``/``, U+007F and everything above are written as they are.
  A lone surrogate is rejected.
* Numbers: integers only, written in base 10 with no sign for zero and no leading zeros. The range is
  -(2**53 - 1) to 2**53 - 1, so every language (including ones whose number type is a double) reads the
  same value. Floats are rejected, even when whole (``1.0``), so there is no float text to agree on.
  NaN and the infinities are rejected with their own code.
* ``true``, ``false`` and ``null`` are written in lower case.

Rejections raise :class:`CanonicalError`; its ``code`` is part of the contract.
"""
from __future__ import annotations

import math
from typing import Any

MAX_SAFE_INTEGER = 2**53 - 1

# Error codes (part of the contract).
FLOAT_NOT_ALLOWED = "float_not_allowed"
NON_FINITE_NUMBER = "non_finite_number"
INTEGER_OUT_OF_RANGE = "integer_out_of_range"
NON_STRING_KEY = "non_string_key"
INVALID_STRING = "invalid_string"
UNSUPPORTED_TYPE = "unsupported_type"

_SHORT_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


class CanonicalError(ValueError):
    """The value has no canonical form. ``code`` is one of the codes above."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def canonical_text(value: Any) -> str:
    """Return the canonical JSON text of ``value`` (dict, list, tuple, str, int, bool, None)."""
    out: list[str] = []
    _write(value, out)
    return "".join(out)


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical JSON text of ``value`` encoded as UTF-8."""
    return canonical_text(value).encode("utf-8")


def _write(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(INTEGER_OUT_OF_RANGE, str(value))
        out.append(str(int(value)))
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CanonicalError(NON_FINITE_NUMBER)
        raise CanonicalError(FLOAT_NOT_ALLOWED, repr(value))
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalError(NON_STRING_KEY, repr(key))
        out.append("{")
        for i, key in enumerate(sorted(value)):  # str order is code point order
            if i:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _write(value[key], out)
        out.append("}")
    else:
        raise CanonicalError(UNSUPPORTED_TYPE, type(value).__name__)


def _string(s: str) -> str:
    parts = ['"']
    for ch in s:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise CanonicalError(INVALID_STRING, "lone surrogate")
        short = _SHORT_ESCAPES.get(ch)
        if short is not None:
            parts.append(short)
        elif cp < 0x20:
            parts.append(f"\\u{cp:04x}")
        else:
            parts.append(ch)
    parts.append('"')
    return "".join(parts)
