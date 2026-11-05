"""The executor's settings (v1.12 W5). Design record: docs/v1.12/WORK_AGENT.md.

The settings are a mapping, either the JSON object of an executor file or the `work.executor`
section of the deploy config:

- ``root``: the directory that holds each Ticket's own directory. Required.
- ``argv``: the CLI's argv, a non-empty list of strings. The element ``{task}`` is replaced by the
  Ticket's task. Required.
- ``prepare``: an optional argv run first in the Ticket's directory, such as a clone.
- ``slots``: worker slots, at least two. One stays free for a person's message. Defaults to two.

Any other shape is refused with ValueError, and the message names the field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from organism_sdk.work.executors.process import ProcessExecutor, Slots

DEFAULT_SLOTS = 2


def load_executor(path: Path) -> ProcessExecutor:
    """Build the ProcessExecutor that an executor file describes."""
    return executor_from_settings(json.loads(path.read_text(encoding="utf-8")))


def executor_from_settings(settings: object) -> ProcessExecutor:
    """Build the ProcessExecutor that a settings mapping describes. Raises ValueError for any
    other shape."""
    if type(settings) is not dict:  # a JSON object, or a deploy section copied as a dict
        raise ValueError("the executor settings must be a mapping")
    root = settings.get("root")
    if not isinstance(root, str) or not root:
        raise ValueError("'root' must be a directory path")
    prepare = None if settings.get("prepare") is None else _argv(settings["prepare"], "prepare")
    slots = settings.get("slots", DEFAULT_SLOTS)
    # `type(...) is int` also refuses True and False, which are ints to isinstance.
    if type(slots) is not int or slots < 2:
        raise ValueError("'slots' must be an integer of at least 2: one stays free for a person")
    return ProcessExecutor(
        Path(root),
        argv=_argv(settings.get("argv"), "argv"),
        prepare=prepare,
        slots=Slots(slots),
    )


def _argv(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"'{name}' must be a non-empty list of strings")
    return list(value)
