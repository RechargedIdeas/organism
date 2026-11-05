"""v1.12 W5, network groundwork: a child in its own network namespace cannot reach host loopback.

A proxy route to the egress proxy depends on this, since the child may reach nothing else. Linux
only, because the work executor runs only on Linux (`containment_gap`).

The baseline runs the same probe without a namespace, so a child that cannot start at all fails
the test instead of passing it, and a namespace that did not take effect shows as "reached"."""

from __future__ import annotations

import socket
import sys
from collections.abc import Iterator

import pytest
from organism_sdk.sandbox.jail import JailResult, ProcessJail
from organism_sdk.sandbox.policy import SandboxPolicy

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")

PROBE = (
    "import socket, sys\n"
    "try:\n"
    "    socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=3)\n"
    "except OSError:\n"
    "    print('blocked')\n"
    "else:\n"
    "    print('reached')\n"
)


@pytest.fixture
def host_port() -> Iterator[int]:
    server = socket.create_server(("127.0.0.1", 0))
    yield int(server.getsockname()[1])
    server.close()


def probe(port: int, monkeypatch: pytest.MonkeyPatch, *, full_ns: bool) -> tuple[str, JailResult]:
    if full_ns:
        monkeypatch.setenv("ORGANISM_JAIL_FULL_NS", "1")
    else:
        monkeypatch.delenv("ORGANISM_JAIL_FULL_NS", raising=False)
    policy = SandboxPolicy(timeout_s=20, label="netns-probe")
    result = ProcessJail(policy).run([sys.executable, "-c", PROBE, str(port)])
    assert result.ok, result.stderr
    return result.stdout.strip(), result


def test_without_a_network_namespace_the_child_reaches_host_loopback(
    host_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, _ = probe(host_port, monkeypatch, full_ns=False)
    assert output == "reached"


def test_in_a_network_namespace_the_child_cannot_reach_host_loopback(
    host_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, result = probe(host_port, monkeypatch, full_ns=True)
    assert "net" in result.namespaces_attempted
    assert output == "blocked"
