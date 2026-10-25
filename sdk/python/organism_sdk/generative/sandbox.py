"""Restricted sandbox for generative code — AST forbid + OS process jail.

v1.9: wall-clock timeout + RSS cap via child process (default).
v1.10: composes with organism_sdk.sandbox.OrganismSandbox (native runtime
containment). AST whitelist remains the first line of defense; ProcessJail
provides rlimits / optional namespaces for broader child work. Set
ORGANISM_SANDBOX_INPROCESS=1 to force in-process exec. Bio may_actuate never set.
Docker is never required.
"""
from __future__ import annotations

import ast
import json
import math
import multiprocessing as mp
import os
import traceback
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
    "may_actuate",
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
    isolated: bool = False
    timeout_s: float | None = None
    max_rss_mb: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": self.value if _jsonable(self.value) else repr(self.value),
            "error": self.error,
            "stdout_capture": self.stdout_capture,
            "isolated": self.isolated,
            "timeout_s": self.timeout_s,
            "max_rss_mb": self.max_rss_mb,
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


def validate_source(source: str) -> None:
    """Public AST gate — used by parent before isolation and by child re-check."""
    tree = ast.parse(source, mode="exec")
    _validate_ast(tree)


def _exec_body(source: str, entry: str, args: dict[str, Any]) -> SandboxResult:
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
    if not _jsonable(value):
        # Force JSON-safe crossing for process boundary / promote metrics.
        value = json.loads(json.dumps(value, default=repr))
    return SandboxResult(True, value=value)


def _child_worker(
    source: str,
    entry: str,
    args: dict[str, Any],
    max_rss_mb: int | None,
    q: Any,
) -> None:
    try:
        if max_rss_mb is not None and max_rss_mb > 0:
            try:
                import resource

                limit = int(max_rss_mb) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except Exception:
                pass
        result = _exec_body(source, entry, args)
        q.put({"ok": result.ok, "value": result.value, "error": result.error})
    except SandboxRefused as e:
        q.put({"ok": False, "value": None, "error": f"SandboxRefused: {e}"})
    except MemoryError:
        q.put({"ok": False, "value": None, "error": "MemoryError: RSS cap exceeded"})
    except Exception as e:
        q.put({"ok": False, "value": None, "error": f"{type(e).__name__}: {e}"})


class SafeSandbox:
    """Execute generative drafts under AST whitelist + optional OS process jail.

    Refuses arbitrary shell, imports, file I/O, dunder introspection, and
    bio-adjacent ``may_actuate`` bindings. Default isolation uses a child
    process with wall-clock timeout and optional RSS cap (Linux RLIMIT_AS).
    """

    def __init__(
        self,
        *,
        timeout_s: float | None = None,
        max_rss_mb: int | None = None,
        isolate: bool | None = None,
    ) -> None:
        env_timeout = os.environ.get("ORGANISM_SANDBOX_TIMEOUT_S")
        env_rss = os.environ.get("ORGANISM_SANDBOX_MAX_RSS_MB")
        env_inproc = os.environ.get("ORGANISM_SANDBOX_INPROCESS", "").lower() in ("1", "true", "yes")
        env_isolate = os.environ.get("ORGANISM_SANDBOX_ISOLATE", "1").lower() in ("1", "true", "yes")
        self.timeout_s = float(timeout_s if timeout_s is not None else (env_timeout or 2.0))
        self.max_rss_mb = int(max_rss_mb if max_rss_mb is not None else (env_rss or 256))
        if isolate is None:
            self.isolate = (not env_inproc) and env_isolate
        else:
            self.isolate = bool(isolate) and not env_inproc

    def run(
        self, source: str, *, entry: str = "main", args: dict[str, Any] | None = None
    ) -> SandboxResult:
        args = dict(args or {})
        try:
            validate_source(source)
        except SandboxRefused as e:
            return SandboxResult(
                False,
                error=f"SandboxRefused: {e}",
                isolated=False,
                timeout_s=self.timeout_s,
                max_rss_mb=self.max_rss_mb,
            )
        except SyntaxError as e:
            return SandboxResult(False, error=f"SyntaxError: {e}")

        if not self.isolate:
            try:
                result = _exec_body(source, entry, args)
            except SandboxRefused as e:
                result = SandboxResult(False, error=f"SandboxRefused: {e}")
            except Exception as e:
                result = SandboxResult(False, error=f"{type(e).__name__}: {e}")
            result.isolated = False
            result.timeout_s = self.timeout_s
            result.max_rss_mb = self.max_rss_mb
            return result

        return self._run_isolated(source, entry=entry, args=args)

    def _run_isolated(
        self, source: str, *, entry: str, args: dict[str, Any]
    ) -> SandboxResult:
        """OS process jail via spawn (thread-safe). Falls back to in-process AST jail."""
        ctx = mp.get_context("spawn")
        q: Any = ctx.Queue()
        proc = ctx.Process(
            target=_child_worker,
            args=(source, entry, args, self.max_rss_mb, q),
        )
        try:
            proc.start()
        except Exception as e:
            return self._inprocess_fallback(source, entry, args, note=f"start_failed:{e}")
        proc.join(self.timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(1.0)
            if proc.is_alive():
                proc.kill()
                proc.join(1.0)
            return SandboxResult(
                False,
                error=f"SandboxTimeout: exceeded {self.timeout_s}s",
                isolated=True,
                timeout_s=self.timeout_s,
                max_rss_mb=self.max_rss_mb,
            )
        try:
            payload = q.get_nowait()
        except Exception:
            return self._inprocess_fallback(
                source, entry, args, note=f"child_exit={proc.exitcode}"
            )
        return SandboxResult(
            bool(payload.get("ok")),
            value=payload.get("value"),
            error=payload.get("error"),
            isolated=True,
            timeout_s=self.timeout_s,
            max_rss_mb=self.max_rss_mb,
        )

    def _inprocess_fallback(
        self, source: str, entry: str, args: dict[str, Any], *, note: str
    ) -> SandboxResult:
        try:
            result = _exec_body(source, entry, args)
        except SandboxRefused as e:
            result = SandboxResult(False, error=f"SandboxRefused: {e}")
        except Exception as e:
            result = SandboxResult(False, error=f"{type(e).__name__}: {e}")
        result.isolated = False
        result.timeout_s = self.timeout_s
        result.max_rss_mb = self.max_rss_mb
        result.stdout_capture = f"fallback_inprocess:{note}"
        return result


def run_under_organism_jail(argv: list[str], **kwargs):
    """Delegate argv containment to the native OrganismSandbox ProcessJail."""
    from organism_sdk.sandbox import OrganismSandbox, SandboxPolicy

    policy = kwargs.pop("policy", None) or SandboxPolicy.generative()
    return OrganismSandbox().run(argv, policy=policy, **kwargs)
