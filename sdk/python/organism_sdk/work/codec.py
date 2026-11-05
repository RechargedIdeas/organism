"""Encoding of the work domain for storage (v1.12). Design record: docs/v1.12/WORK_AGENT.md.

Pure. It turns the domain's dataclasses and enums into JSON-ready values and back. The
decoder reads each field's type from the dataclass annotations, so a new field needs no
change here.
"""

from __future__ import annotations

import json
import types
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from typing import Any, TypeVar, Union, cast, get_args, get_origin, get_type_hints

T = TypeVar("T")


def encode(value: Any) -> Any:
    """The JSON-ready form of a value: enums by value, dataclasses by field, sets sorted."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: encode(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, frozenset | set):
        return sorted(encode(item) for item in value)
    if isinstance(value, tuple | list):
        return [encode(item) for item in value]
    return value


def decode(hint: Any, data: Any) -> Any:
    """Rebuild a value of the annotated type `hint` from its JSON-ready form."""
    if data is None:
        return None
    origin = get_origin(hint)
    if origin in (Union, types.UnionType):
        (member,) = [arg for arg in get_args(hint) if arg is not type(None)]
        return decode(member, data)
    if origin is tuple:
        (item, _) = get_args(hint)
        return tuple(decode(item, value) for value in data)
    if origin in (frozenset, set):
        (item,) = get_args(hint)
        return frozenset(decode(item, value) for value in data)
    if origin in (Mapping, dict):
        key_hint, value_hint = get_args(hint)
        return {decode(key_hint, key): decode(value_hint, value) for key, value in data.items()}
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(data)
    if is_dataclass(hint):
        hints = get_type_hints(hint)
        constructor: Any = hint
        # A field the stored form lacks takes its default, so a row written before the field
        # existed still reads. A field with no default must be present.
        return constructor(
            **{
                item.name: decode(hints[item.name], data[item.name])
                for item in fields(hint)
                if item.name in data
                or (item.default is MISSING and item.default_factory is MISSING)
            }
        )
    return data


def to_text(value: Any) -> str:
    """The canonical JSON text of a value: sorted keys, no whitespace."""
    return json.dumps(encode(value), sort_keys=True, separators=(",", ":"))


def from_text(hint: type[T], text: str) -> T:
    """The value of type `hint` that `to_text` wrote."""
    return cast(T, decode(hint, json.loads(text)))
