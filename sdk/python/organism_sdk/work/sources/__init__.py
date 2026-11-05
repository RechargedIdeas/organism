"""Sources of the work agent (v1.12). Each one reads from outside and turns what it reads into Triggers.

The adapters here do I/O, which is why they live apart from the pure top-level modules of
`organism_sdk.work`. Only `store.py` does I/O among those.
"""

from organism_sdk.work.sources.github import GhCli, GhError, GitHubSource, RoundReport

__all__ = ["GhCli", "GhError", "GitHubSource", "RoundReport"]
