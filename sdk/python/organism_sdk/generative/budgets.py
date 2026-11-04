"""Wall-clock budgets (ms) for the generative evolve path.

Evolve runs untrusted drafts in a child process started with ``spawn`` (see ``sandbox.py``), so
its cost is dominated by process start-up and varies by platform. Measured under gate isolation
(``ORGANISM_SANDBOX_ISOLATE=1``), the desktop evolve path, which the desktop tests assert on, took
1054-1462 ms over 13 runs on this Windows machine and 612-697 ms over 6 runs on WSL Ubuntu. The
budgets are about 1.4 times the slowest of those: 2000 ms on Windows and 1000 ms elsewhere. The
bare SDK path is faster (about 400 ms on Windows, 580 ms on WSL), so it passes with room to spare.
Tighter budgets flaked on single samples, so change these only from a new set of measurements.
"""

from __future__ import annotations

import sys

EVOLVE_BUDGET_MS = 2000.0 if sys.platform == "win32" else 1000.0
