"""Local, on-device CI pipeline for Organism.

The pipeline runs from ``ci/run.py``. It reads gate definitions from ``ci/gates.yaml``
and settings from ``ci/pipeline.toml``, then runs preflight checks, hygiene checks,
lint and type ratchets, and the blocking gates for the selected tier.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
