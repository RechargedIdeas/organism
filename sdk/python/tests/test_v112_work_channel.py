"""v1.12 W6, the GitHub reply channel: each reply posted once, in order, and only while writes are on."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.work.channels import (
    ChannelGone,
    GitHubChannel,
    marker,
    queue_reply,
    reply_handlers,
)
from organism_sdk.work.sources import GhCli
from organism_sdk.work.store import ReceiptStatus, WorkStore

FAKE_GH = Path(__file__).with_name("fake_gh.py")
REPO = "octo/cat"
ONE = f"repos/{REPO}/issues/1/comments"
TWO = f"repos/{REPO}/issues/2/comments"
THREAD_ONE = f"github:{REPO}#1"
THREAD_TWO = f"github:{REPO}#2"
GONE = "HTTP 410: Gone (https://api.github.com/repos/octo/cat/issues/1/comments)"


class FakeGh:
    """Points GhCli at the fake `gh`, and reads back each call it was asked to make."""

    def __init__(self, directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.fixture = directory / "fixture.json"
        self.log = directory / "calls.log"
        monkeypatch.setenv("FAKE_GH_FIXTURE", str(self.fixture))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))
        self.cli = GhCli(command=(sys.executable, str(FAKE_GH)))

    def serve(self, responses: dict[str, Any]) -> None:
        self.fixture.write_text(json.dumps({"responses": responses}), encoding="utf-8")

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def posts(self) -> list[str]:
        """The body field of each POST, in the order they were made."""
        return [call[-1] for call in self.calls() if call[1:3] == ["-X", "POST"]]


def status_of(store: WorkStore, receipt_id: str) -> ReceiptStatus:
    receipt = store.receipt(receipt_id)
    assert receipt is not None, receipt_id
    return receipt.status


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    return FakeGh(tmp_path, monkeypatch)


@pytest.fixture
def channel(fake: FakeGh) -> GitHubChannel:
    return GitHubChannel(gh=fake.cli)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[WorkStore]:
    with WorkStore(tmp_path / "work.sqlite") as handle:
        yield handle


def test_a_reply_is_posted_once_with_its_receipt_marker(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    fake.serve({ONE: {"pages": [[]]}})
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="done")
    report = store.run_due(reply_handlers(store, channel, enabled=True))
    assert report.completed == 1
    assert fake.posts() == ["body=done\n\n<!-- organism-receipt:r1 -->"]
    assert status_of(store, "r1") is ReceiptStatus.SENT


def test_a_reply_already_on_the_thread_is_not_posted_again(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    posted = {"body": f"done\n\n{marker('r1')}"}
    fake.serve({ONE: {"pages": [[posted]]}})
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="done")
    store.run_due(reply_handlers(store, channel, enabled=True))
    assert fake.posts() == []
    assert status_of(store, "r1") is ReceiptStatus.SENT


def test_replies_for_one_ticket_leave_in_the_order_written(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    fake.serve({ONE: {"pages": [[]]}})
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="first")
    queue_reply(store, ticket_id="t1", receipt_id="r2", conversation=THREAD_ONE, text="second")
    handlers = reply_handlers(store, channel, enabled=True)
    assert store.run_due(handlers).completed == 1  # only the first is queued to send
    assert store.run_due(handlers).completed == 1
    assert [body.partition("\n")[0] for body in fake.posts()] == ["body=first", "body=second"]


def test_a_gone_thread_drops_its_reply_and_the_next_one_still_goes(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    fake.serve(
        {
            ONE: {"pages": [[]], "post": {"error": GONE}},
            TWO: {"pages": [[]]},
        }
    )
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="gone")
    queue_reply(store, ticket_id="t1", receipt_id="r2", conversation=THREAD_TWO, text="next")
    handlers = reply_handlers(store, channel, enabled=True)
    store.run_due(handlers)
    store.run_due(handlers)
    first = store.receipt("r1")
    assert first is not None
    assert (first.status, first.reason) == (ReceiptStatus.DROPPED, "gone")
    assert status_of(store, "r2") is ReceiptStatus.SENT


def test_a_thread_gone_when_read_drops_its_reply(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    fake.serve({ONE: {"error": GONE}})
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="late")
    store.run_due(reply_handlers(store, channel, enabled=True))
    assert status_of(store, "r1") is ReceiptStatus.DROPPED
    assert fake.posts() == []


def test_send_reports_a_gone_thread_as_such(fake: FakeGh, channel: GitHubChannel) -> None:
    fake.serve({ONE: {"pages": [[]], "post": {"error": GONE}}})
    with pytest.raises(ChannelGone):
        channel.send(receipt="r1", conversation=THREAD_ONE, text="x")


def test_another_failure_keeps_the_reply_and_holds_the_ones_behind_it(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    fake.serve(
        {
            ONE: {"pages": [[]], "post": {"error": "HTTP 500: Server Error"}},
            TWO: {"pages": [[]]},
        }
    )
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="first")
    queue_reply(store, ticket_id="t1", receipt_id="r2", conversation=THREAD_TWO, text="second")
    report = store.run_due(reply_handlers(store, channel, enabled=True))
    assert report.failed == 1
    assert status_of(store, "r1") is ReceiptStatus.PENDING
    assert status_of(store, "r2") is ReceiptStatus.PENDING
    assert len(fake.posts()) == 1  # the second reply was never attempted
    assert "HTTP 500" in (store.pending_effects()[0].last_error or "")


def test_writes_are_off_by_default_and_no_call_reaches_gh(
    store: WorkStore, fake: FakeGh, channel: GitHubChannel
) -> None:
    fake.serve({ONE: {"pages": [[]]}})
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD_ONE, text="held")
    assert reply_handlers(store, channel, enabled=False) == {}
    assert store.run_due(reply_handlers(store, channel, enabled=False)).completed == 0
    assert fake.calls() == []
    assert status_of(store, "r1") is ReceiptStatus.PENDING


@pytest.mark.parametrize(
    "conversation",
    ["github:octo/cat", "octo/cat#1", "github:octo/cat#x", "github:octo/cat#1; rm"],
)
def test_only_a_github_thread_is_a_conversation(
    fake: FakeGh, channel: GitHubChannel, conversation: str
) -> None:
    with pytest.raises(ValueError, match="conversation"):
        channel.send(receipt="r1", conversation=conversation, text="x")
    assert fake.calls() == []


def test_the_marker_names_its_receipt() -> None:
    assert marker("t1:1") == "<!-- organism-receipt:t1:1 -->"
