"""Environment variables that hold secrets, kept outside the repository (v1.12).

Where the OS has a credential store, values go there: Windows Credential Manager, through
`envstore_windows`, which needs no new dependency. Elsewhere a value goes to one JSON file under the
user's config directory, readable by its owner only. Nothing is written into the repository tree.

A value leaves this module as text only when a caller asks for it with `Secret.reveal()`. `Secret`
shows a mask in `repr`, `str` and `format`, and does not pickle. Errors name a variable or a file,
never a value, and are raised `from None`, so no chained traceback carries one.

A process reads the store once, at start, with `apply_to_environ`. A variable the environment
already sets wins over the store, so an `Environment=` line or a shell export still overrides it.
`without_stored` drops every stored name from an environment a child process inherits.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r"[A-Z_][A-Z0-9_]{0,127}")
MAX_VALUE_BYTES = 2048  # Windows Credential Manager caps a blob at 2560 bytes
MASK = "********"
FILE_FORMAT = 1


class EnvStoreError(Exception):
    """A store failure. The message names a variable or a file, never a value."""


class Secret:
    """A stored value. Only `reveal()` returns its text."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Secret({MASK!r})"

    def __str__(self) -> str:
        return MASK

    def __format__(self, spec: str) -> str:
        return MASK

    def __reduce__(self) -> str:
        raise TypeError("a Secret is not pickled")


def check_name(name: str) -> str:
    # The name is not echoed: a value pasted into the name field must not reach an error message.
    if not NAME_PATTERN.fullmatch(name):
        raise EnvStoreError(
            "a variable name uses uppercase letters, digits and underscores, "
            "and does not start with a digit"
        )
    return name


def check_value(value: str) -> str:
    if not value:
        raise EnvStoreError("the value is empty")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise EnvStoreError("the value is not valid UTF-8") from None
    if "\x00" in value:
        raise EnvStoreError("the value contains a NUL character, which an environment cannot hold")
    if size > MAX_VALUE_BYTES:
        raise EnvStoreError(f"the value is larger than {MAX_VALUE_BYTES} bytes")
    return value


class Backend(Protocol):
    def names(self) -> list[str]: ...

    def read(self, name: str) -> str | None: ...

    def write(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> bool: ...


class FileBackend:
    """Every variable in one JSON file. A write replaces the whole file, so a reader never sees half.

    Concurrent writers are not coordinated: the last write wins. The panel is the only writer.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def names(self) -> list[str]:
        return sorted(self._load())

    def read(self, name: str) -> str | None:
        return self._load().get(name)

    def write(self, name: str, value: str) -> None:
        variables = self._load()
        variables[name] = value
        self._save(variables)

    def delete(self, name: str) -> bool:
        variables = self._load()
        if name not in variables:
            return False
        del variables[name]
        self._save(variables)
        return True

    def _load(self) -> dict[str, str]:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as error:
            raise EnvStoreError(f"the store file {self.path} cannot be read: {error}") from None
        if os.name == "posix" and self.path.stat().st_mode & 0o077:
            os.chmod(self.path, 0o600)
        try:
            document = json.loads(raw)
        except ValueError:
            raise EnvStoreError(f"{self.path} is not a store file") from None
        variables = document.get("variables") if isinstance(document, dict) else None
        if (
            not isinstance(document, dict)
            or document.get("format") != FILE_FORMAT
            or not isinstance(variables, dict)
            or not all(isinstance(value, str) for value in variables.values())
        ):
            raise EnvStoreError(f"{self.path} is not a store file")
        return dict(variables)

    def _save(self, variables: dict[str, str]) -> None:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(directory, 0o700)
        body = json.dumps({"format": FILE_FORMAT, "variables": variables}, indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".env-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise


def default_file_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "organism" / "env.json"


def default_backend() -> Backend:
    if sys.platform == "win32":
        from organism_sdk.envstore_windows import CredentialManager

        return CredentialManager()
    return FileBackend(default_file_path())


class EnvStore:
    """Named secret variables over one backend. Names are checked here, values on the way in."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    def names(self) -> list[str]:
        return sorted(self.backend.names())

    def get(self, name: str) -> Secret | None:
        value = self.backend.read(check_name(name))
        return None if value is None else Secret(value)

    def put(self, name: str, value: str) -> None:
        self.backend.write(check_name(name), check_value(value))

    def remove(self, name: str) -> bool:
        return self.backend.delete(check_name(name))


_stored_names: frozenset[str] = frozenset()


def apply_to_environ(
    store: EnvStore | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> list[str]:
    """Set each stored variable that `environ` does not set. Returns the names it set, never values.

    A store that cannot be read is logged, and the process starts without it. Every stored name is
    remembered, whether or not it was set here, so `without_stored` keeps it from children.
    """
    global _stored_names
    target: MutableMapping[str, str] = os.environ if environ is None else environ
    try:
        active = EnvStore(default_backend()) if store is None else store
        names = active.names()
        _stored_names = frozenset(names)
        applied: list[str] = []
        for name in names:
            if name in target:
                continue
            secret = active.get(name)
            if secret is None:
                continue
            target[name] = secret.reveal()
            applied.append(name)
    except EnvStoreError as error:
        logger.warning("environment store not applied: %s", error)
        return []
    if applied:
        logger.info("environment store applied: %s", ", ".join(applied))
    return applied


def without_stored(env: Mapping[str, str]) -> dict[str, str]:
    """A copy of `env` without the stored variables, for a child that must not receive them."""
    return {key: value for key, value in env.items() if key not in _stored_names}
