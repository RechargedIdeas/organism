"""The GitHub reply channel (v1.12 W6). Design record: docs/v1.12/WORK_AGENT.md.

A reply is a comment on the Issue or pull request of a Thread, posted through `gh api`. Each
reply ends with a hidden marker that names its receipt. Before posting, the channel reads the
thread's comments. A reply whose marker is already there was posted before, so it is not posted
again. This covers a crash between the post and the store recording it.

Only a 410 answer means the thread is gone. Any other failure is raised for the store to retry.
"""

from __future__ import annotations

import re

from organism_sdk.work.sources.github import GhCli, GhError

GONE = 410
_CONVERSATION = re.compile(r"github:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[0-9]+)")


class ChannelGone(RuntimeError):
    """The thread a reply was for is gone: GitHub answered 410. The reply will not be sent."""


def marker(receipt: str) -> str:
    """The hidden marker that names a receipt. It is an HTML comment, so it is not shown."""
    return f"<!-- organism-receipt:{receipt} -->"


class GitHubChannel:
    """Posts replies to Threads of the form `github:owner/name#number`."""

    def __init__(self, *, gh: GhCli | None = None) -> None:
        self.gh = gh or GhCli()

    def send(self, *, receipt: str, conversation: str, text: str) -> None:
        """Post the reply unless its marker is already on the thread. Raises ChannelGone on a 410."""
        repo, number = _conversation(conversation)
        path = f"repos/{repo}/issues/{number}/comments"
        stamp = marker(receipt)
        try:
            if any(stamp in str(item.get("body") or "") for item in self.gh.items(path)):
                return
            self.gh.post(path, body=f"{text}\n\n{stamp}")
        except GhError as error:
            if error.status == GONE:
                raise ChannelGone(str(error)) from error
            raise


def _conversation(text: str) -> tuple[str, int]:
    match = _CONVERSATION.fullmatch(text)
    if match is None:
        raise ValueError(f"conversation must be github:owner/name#number, got {text!r}")
    return match["repo"], int(match["number"])
