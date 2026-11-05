"""v1.12 W5, enforced network: the work executor's child reaches only its allowlist, through the proxy.

The probe runs inside the jail, on Linux, where the network namespace and the bridge exist. It makes
three checks. A direct connection to a server on the host must fail, because the child has no route
out. A tunnel to an allowlisted host through the bridge must succeed and carry bytes. A tunnel to a
host off the list must get 403. The baseline shows the same direct connection succeeds without
enforcement, so the first check is not passing for some other reason. Test keys only (decision S1).
"""

from __future__ import annotations

import socket
import sys
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from organism_sdk.sandbox import egress_bridge
from organism_sdk.sandbox.egress import Allow
from organism_sdk.sandbox.jail import ProcessJail
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.work.executors.process import ProcessExecutor, Slots

LINUX = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="network namespaces are Linux only"
)

PROBE = r"""
import socket, sys
echo, outside = int(sys.argv[1]), int(sys.argv[2])

def head(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(1024)
        if not chunk:
            break
        data += chunk
    return data

try:
    socket.create_connection(("127.0.0.1", outside), timeout=3).close()
    print("direct:reached")
except OSError:
    print("direct:blocked")

def connect(target):
    sock = socket.create_connection(("127.0.0.1", 3128), timeout=5)
    sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    return sock, head(sock)

sock, answer = connect(f"localhost:{echo}")
if answer.startswith(b"HTTP/1.1 200"):
    sock.sendall(b"ping")
    print("tunnel:200 echo:" + sock.recv(4).decode())
else:
    print("tunnel:" + answer.split(b"\r\n")[0].decode())
sock.close()

sock, answer = connect("evil.example.test:443")
print("denied:" + answer.split(b" ")[1].decode())
sock.close()
"""

DIRECT = (
    "import socket, sys\n"
    "socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=3).close()\n"
    "print('reached')\n"
)


def _echo(conn: socket.socket) -> None:
    with conn:
        while data := conn.recv(4096):
            conn.sendall(data)


@pytest.fixture
def echo_port() -> Iterator[int]:
    server = socket.create_server(("127.0.0.1", 0))

    def accept_forever() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=_echo, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_forever, daemon=True).start()
    yield int(server.getsockname()[1])
    server.close()


def _local(port: int) -> Allow:
    """The allowlist the probe is checked against. `local` lets the test's loopback server answer."""
    return Allow(hosts=frozenset({"localhost"}), ports=frozenset({port}), local=True)


def _enforced() -> SandboxPolicy:
    return SandboxPolicy(
        timeout_s=30,
        label="bridge-test",
        network_allowlist=["localhost"],
        allow_network=True,
        enforce_network=True,
    )


@LINUX
def test_the_child_reaches_an_allowlisted_host_through_the_bridge(echo_port: int) -> None:
    jail = ProcessJail(_enforced(), proxy_allow=_local(echo_port))
    result = jail.run([sys.executable, "-c", PROBE, str(echo_port), str(echo_port)])
    assert result.ok, result.stderr
    assert "tunnel:200 echo:ping" in result.stdout


@LINUX
def test_the_child_cannot_reach_the_host_directly(echo_port: int) -> None:
    jail = ProcessJail(_enforced(), proxy_allow=_local(echo_port))
    result = jail.run([sys.executable, "-c", PROBE, str(echo_port), str(echo_port)])
    assert result.ok, result.stderr
    assert "direct:blocked" in result.stdout


@LINUX
def test_a_host_off_the_list_is_refused_by_the_proxy(echo_port: int) -> None:
    jail = ProcessJail(_enforced(), proxy_allow=_local(echo_port))
    result = jail.run([sys.executable, "-c", PROBE, str(echo_port), str(echo_port)])
    assert result.ok, result.stderr
    assert "denied:403" in result.stdout


@LINUX
def test_without_enforcement_the_same_direct_connection_reaches_the_host(echo_port: int) -> None:
    jail = ProcessJail(SandboxPolicy(timeout_s=20, label="bridge-test"))
    result = jail.run([sys.executable, "-c", DIRECT, str(echo_port)])
    assert result.ok, result.stderr
    assert result.stdout.strip() == "reached"


@LINUX
def test_the_work_executor_runs_its_cli_behind_the_proxy(tmp_path: Path, echo_port: int) -> None:
    policy = replace(
        SandboxPolicy.work_executor(),
        env_allowlist=None,
        timeout_s=60.0,
        network_allowlist=["localhost"],
    )
    executor = ProcessExecutor(
        tmp_path,
        argv=[sys.executable, "-c", PROBE, str(echo_port), str(echo_port)],
        slots=Slots(2),
        policy=policy,
        jail=lambda profile: ProcessJail(profile, proxy_allow=_local(echo_port)),
    )
    execution = executor.run("ticket-bridge")
    assert execution.ok, execution.refused or execution.stderr
    assert "tunnel:200 echo:ping" in execution.stdout
    assert "direct:blocked" in execution.stdout
    assert "denied:403" in execution.stdout


def test_the_work_executor_profile_enforces_its_allowlist() -> None:
    policy = SandboxPolicy.work_executor()
    assert policy.enforce_network is True
    assert "api.anthropic.com" in policy.network_allowlist


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="this host can enforce it")
def test_enforcement_refuses_where_this_host_cannot_run_it() -> None:
    policy = SandboxPolicy(timeout_s=20, label="bridge-test", enforce_network=True)
    result = ProcessJail(policy).run([sys.executable, "-c", "print('ran')"])
    assert result.ok is False
    assert "Linux" in (result.refused or "")
    assert result.stdout == ""


def test_the_bridge_needs_a_command_after_a_separator() -> None:
    assert egress_bridge.main(["--listen", "127.0.0.1:1", "--upstream", "x"]) == 2
    assert egress_bridge.main(["--listen", "127.0.0.1:1", "--upstream", "x", "--"]) == 2


def test_a_bridge_that_cannot_bind_does_not_start_its_command(tmp_path: Path) -> None:
    taken = socket.create_server(("127.0.0.1", 0))
    marker = tmp_path / "ran"
    try:
        port = int(taken.getsockname()[1])
        status = egress_bridge.main(
            [
                "--listen",
                f"127.0.0.1:{port}",
                "--upstream",
                "x",
                "--",
                sys.executable,
                "-c",
                f"open({str(marker)!r}, 'w').close()",
            ]
        )
    finally:
        taken.close()
    assert status == 111
    assert not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the bridge uses Unix sockets")
def test_a_client_is_told_when_the_proxy_socket_is_gone(tmp_path: Path) -> None:
    client, far = socket.socketpair()
    with far:
        egress_bridge._serve(client, str(tmp_path / "gone.sock"))
        answer = far.recv(256)
    assert answer.startswith(b"HTTP/1.1 502")
