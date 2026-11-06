"""Path scope: keeps a tool's file access inside one folder on any platform (gap G2, partly).

This is a host-side check, not an operating-system sandbox. The host runs it before a tool touches a
path, so it works on Windows, macOS and Linux alike, where the Linux jail in ``sandbox/`` does not. It
refuses:

- absolute paths, drive-relative paths (``C:x``) and UNC paths;
- any ``..`` component;
- names with a colon, which on NTFS is an alternate data stream or a drive;
- Windows device names (``CON``, ``NUL``, ``COM1`` and so on), with or without an extension;
- a path whose real location, after following symbolic links and junctions, lies outside the root.

It does not stop a tool that opens its own paths. A tool that runs code needs an OS-level confinement
on top of this check; that remains open.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
    | {"COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"}
)
_DRIVE = re.compile(r"^[A-Za-z]:")
_SEPARATORS = re.compile(r"[\\/]+")
_CONTROL = re.compile(r"[\x00-\x1f]")


class PathEscape(ValueError):
    """A requested path is not inside the scope. The message says which rule refused it."""


class PathScope:
    """A folder that tool paths must stay inside. Construct once; ``resolve`` is the only way in."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        real = Path(os.path.realpath(root))
        if not real.is_dir():
            raise ValueError("path scope root must be an existing directory")
        self._root = real

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, relative: str) -> Path:
        """The real path for ``relative`` under the root. Raises ``PathEscape`` for any path outside it."""
        if not isinstance(relative, str) or not relative:
            raise PathEscape("path is empty")
        if _CONTROL.search(relative):
            raise PathEscape("path has a control character")
        if relative.startswith(("/", "\\")) or _DRIVE.match(relative):
            raise PathEscape("absolute or drive path is not allowed")
        parts = [part for part in _SEPARATORS.split(relative) if part not in ("", ".")]
        for part in parts:
            if part == "..":
                raise PathEscape("'..' is not allowed")
            if ":" in part:
                raise PathEscape("a colon in a name is not allowed")
            stem = part.rstrip(" .").split(".", 1)[0].upper()
            if stem in _RESERVED:
                raise PathEscape("Windows device names are not allowed")
        candidate = os.path.join(self._root, *parts) if parts else str(self._root)
        real = Path(os.path.realpath(candidate))
        if not self.contains(real):
            raise PathEscape("path leads outside the scope through a link")
        return real

    def contains(self, path: str | os.PathLike[str]) -> bool:
        """True when ``path`` is the root or lies below it. Compares case-insensitively on Windows."""
        target = os.path.normcase(os.path.realpath(path))
        root = os.path.normcase(str(self._root))
        if target == root:
            return True
        return target.startswith(root.rstrip(os.sep) + os.sep)
