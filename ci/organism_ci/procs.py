"""Child processes the runner started, so an interrupt can stop every one of them.

Gates run in their own process group (a new session on POSIX, a new process group on Windows).
That keeps a terminal Ctrl-C from reaching them, which is right in normal operation, but it means
they never see an interrupt. The runner has to kill them itself.

Blocking waits are not interruptible on Windows, so waits here wake every ``POLL_S`` seconds.
Python can then deliver Ctrl-C between polls.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

POLL_S = 0.5


class Interrupted(RuntimeError):
    """A process was requested after the run had already been interrupted."""


def kill_tree(proc: subprocess.Popen[bytes]) -> None:
    """Kill a child and everything it started. Safe to call after the child has exited."""
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run([str(taskkill), "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def wait_polling(proc: subprocess.Popen[bytes], timeout_s: float) -> int:
    """Return the exit code, or raise ``TimeoutExpired`` once ``timeout_s`` has passed."""
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(proc.args, timeout_s)
        try:
            return proc.wait(timeout=min(POLL_S, remaining))
        except subprocess.TimeoutExpired:
            continue


class LiveProcesses:
    """Every gate process that is running now.

    ``kill_all`` closes the registry, so a process that starts after an interrupt is killed at once
    instead of being left behind. ``reopen`` starts the next run.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen[bytes]] = set()
        self._closed = False

    def add(self, proc: subprocess.Popen[bytes]) -> None:
        with self._lock:
            if not self._closed:
                self._procs.add(proc)
                return
        kill_tree(proc)
        proc.wait()
        raise Interrupted("the run was interrupted before this process could start")

    def discard(self, proc: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._procs.discard(proc)

    def kill_all(self) -> None:
        with self._lock:
            self._closed = True
            procs = list(self._procs)
        for proc in procs:
            kill_tree(proc)

    def reopen(self) -> None:
        with self._lock:
            self._closed = False
            self._procs.clear()


LIVE = LiveProcesses()
