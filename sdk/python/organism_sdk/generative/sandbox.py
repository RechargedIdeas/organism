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
    ast.comprehension, ast.keyword, ast.IfExp, ast.JoinedStr, ast.FormattedValue,
)

# Expanded AST forbid list (v1.7.1) — names that must never appear in drafts.
_FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil", "ctypes",
    "importlib", "builtins", "eval", "exec", "open", "compile", "__import__",
    "input", "breakpoint", "memoryview", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "hasattr",
    "classmethod", "staticmethod", "property",
    "type", "object", "super",
    "pickle", "marshal", "shelve", "tempfile", "io", "codecs",
    "asyncio", "threading", "multiprocessing", "concurrent",
    "requests", "urllib", "http", "ftplib", "smtplib",
    "pty", "fcntl", "resource", "signal", "ctypes",
    "code", "codeop", "inspect", "gc", "sysconfig",
    "may_actuate",  # never bind bio actuation flag in sandbox body
}

_FORBIDDEN_ATTRS = {
    "__class__", "__mro__", "__subclasses__", "__bases__", "__globals__",
    "__code__", "__builtins__", "__dict__", "__reduce__", "__reduce_ex__",
    "system", "popen", "Popen", "call", "check_output", "run",
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
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxRefused(f"disallowed AST node: {type(node).__name__}")
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            raise SandboxRefused(f"disallowed async node: {type(node).__name__}")
        if isinstance(node, (ast.With, ast.Raise, ast.Try, ast.Assert, ast.Delete, ast.Global, ast.Nonlocal, ast.Lambda, ast.Yield, ast.YieldFrom, ast.ClassDef)):
            raise SandboxRefused(f"disallowed AST node: {type(node).__name__}")
        if not isinstance(node, _ALLOWED_NODES):
            raise SandboxRefused(f"disallowed AST node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SandboxRefused(f"forbidden name: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in _FORBIDDEN_ATTRS:
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

    Refuses arbitrary shell, imports, file I/O, dunder introspection, and
    bio-adjacent ``may_actuate`` bindings.
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
