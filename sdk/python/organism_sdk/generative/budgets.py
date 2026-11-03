"""Wall-clock budgets (ms) for the generative evolve path.

Evolve runs untrusted drafts in a child process started with ``spawn`` (see ``sandbox.py``), so
its cost is dominated by process start-up. On this Windows machine that start-up is about 400 ms:
15 measured evolves had a median of 440 ms, a p95 of 452 ms, and a maximum of 501 ms. The POSIX
budget of 250 ms therefore cannot hold on Windows. Windows gets a budget at about twice the
observed maximum. POSIX keeps 250 ms. Linux has not been measured on this machine, so its budget
stays as it was until a Linux run shows otherwise.
"""

from __future__ import annotations

import sys

EVOLVE_BUDGET_MS = 1000.0 if sys.platform == "win32" else 250.0
