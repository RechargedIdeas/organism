"""Restricted sandbox for generative code — no arbitrary shell, no bio actuation."""
from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any


class SandboxRefused(PermissionError):
    """Raised when generated code attempts a disallowed operation."""


_ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign,
    ast.Return, ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass,
    ast.FunctionDef, ast.arguments, ast.arg, ast.Call, ast.Name, ast.Load,
    ast.Store, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp,
    ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.DictComp,
    ast.GeneratorExp, ast.Subscript, ast.Slice, ast.Attribute,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.comprehension, ast.keyword,
)

_FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil", "ctypes",
    "importlib", "builtins", "eval", "exec", "open", "compile", "__import__",
    "input", "breakpoint", "memoryview", "globals", "locals", "vars",
}


@dataclass
class SandboxResult:
    ok: bool
    value: Any = None
    error: str | None = None
    stdout_capture: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": self.value if _jsonable(self.value) else repr(self.value),
            "error": self.error,
            "stdout_capture": self.stdout_capture,
        }


def _jsonable(v: Any) -> bool:
    return isinstance(v, (type(None), bool, int, float, str, list, dict, tuple))


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise SandboxRefused(f"disallowed AST node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SandboxRefused(f"forbidden name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise SandboxRefused(f"forbidden attribute: {node.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_NAMES:
                raise SandboxRefused(f"forbidden call: {node.func.id}")


_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs, "min": min, "max": max, "sum": sum, "len": len, "range": range,
    "enumerate": enumerate, "zip": zip, "sorted": sorted, "reversed": reversed,
    "list": list, "dict": dict, "tuple": tuple, "set": set, "float": float,
    "int": int, "str": str, "bool": bool, "round": round, "pow": pow,
    "True": True, "False": False, "None": None,
    "math": math,
}


class SafeSandbox:
    """Execute generative drafts under a restricted AST + builtins whitelist.

    Refuses arbitrary shell, imports, file I/O, and dunder introspection.
    """

    def run(
        self, source: str, *, entry: str = "main", args: dict[str, Any] | None = None
    ) -> SandboxResult:
        try:
            tree = ast.parse(source, mode="exec")
            _validate_ast(tree)
            code = compile(tree, "<organism_sandbox>", "exec")
            glb: dict[str, Any] = {"__builtins__": dict(_SAFE_BUILTINS)}
            loc: dict[str, Any] = {}
            exec(code, glb, loc)  # intentional restricted sandbox
            ns = {**glb, **loc}
            if entry not in ns or not callable(ns[entry]):
                return SandboxResult(False, error=f"entry {entry!r} missing or not callable")
            value = ns[entry](**(args or {}))
            return SandboxResult(True, value=value)
        except SandboxRefused as e:
            return SandboxResult(False, error=f"SandboxRefused: {e}")
        except Exception as e:
            return SandboxResult(False, error=f"{type(e).__name__}: {e}")
