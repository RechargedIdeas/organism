"""v1.12 W5, network groundwork: the egress proxy decides each tunnel and relays the bytes.

The work executor's child cannot reach this proxy yet (WORK_AGENT.md, section 10), so these tests
use real loopback sockets, with an echo server on 127.0.0.1 as the upstream."""

from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Iterator

import pytest
from organism_sdk.sandbox.egress import Allow, EgressProxy, _is_local, decide

ALLOW = Allow(hosts=frozenset({"api.example.test"}))


@pytest.mark.parametrize(
    "target",
    ["api.example.test:443", "API.example.test:443", "api.example.test.:443"],
)
def test_an_allowed_host_and_port_may_tunnel(target: str) -> None:
    assert decide(target, ALLOW) is None


@pytest.mark.parametrize(
    "target",
    [
        "evil.example.test:443",
        "api.example.test:80",
        "api.example.test",
        ":443",
        "api.example.test:0",
        "api.example.test:65536",
        "api.example.test:44x",
        "api.example.test:４４３",  # full-width digits are not a port
        "api.example.test:443:443",
        "[::1]:443",
        "127.0.0.1:443",
    ],
)
def test_anything_else_is_refused(target: str) -> None:
    assert decide(target, ALLOW) is not None


def test_an_allowlist_entry_must_be_a_lower_case_host_name() -> None:
    with pytest.raises(ValueError):
        Allow(hosts=frozenset({"Api.example.test"}))
    with pytest.raises(ValueError):
        Allow(hosts=frozenset({"api.example.test:443"}))


def test_an_allowlist_port_must_be_a_port() -> None:
    with pytest.raises(ValueError):
        Allow(hosts=frozenset({"api.example.test"}), ports=frozenset({0}))


@pytest.mark.parametrize(
    "text",
    ["127.0.0.1", "10.1.2.3", "169.254.9.9", "::1", "fe80::1", "::ffff:127.0.0.1"],
)
def test_local_addresses_are_recognised(text: str) -> None:
    assert _is_local(ipaddress.ip_address(text))


def test_a_public_address_is_not_local() -> None:
    assert not _is_local(ipaddress.ip_address("93.184.216.34"))


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


def _read_head(sock: socket.socket) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(1024)
        if not chunk:
            break
        data += chunk
    return data


def _ask(address: tuple[str, int], request: bytes) -> bytes:
    with socket.create_connection(address, timeout=5) as sock:
        sock.sendall(request)
        return _read_head(sock)


def _connect(target: str) -> bytes:
    return f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode("ascii")


def test_a_tunnel_to_an_allowed_host_relays_bytes(echo_port: int) -> None:
    allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({echo_port}), local=True)
    with EgressProxy(allow) as proxy, socket.create_connection(proxy.address, timeout=5) as sock:
        sock.sendall(_connect(f"localhost:{echo_port}"))
        assert _read_head(sock).startswith(b"HTTP/1.1 200")
        sock.sendall(b"ping")
        assert sock.recv(4) == b"ping"


def test_a_host_off_the_list_gets_403(echo_port: int) -> None:
    allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({echo_port}), local=True)
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect("evil.example.test:443"))
    assert response.startswith(b"HTTP/1.1 403")


def test_a_port_off_the_list_gets_403(echo_port: int) -> None:
    allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({echo_port}), local=True)
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect(f"localhost:{echo_port + 1}"))
    assert response.startswith(b"HTTP/1.1 403")


def test_a_listed_name_that_resolves_to_loopback_is_refused_without_local(echo_port: int) -> None:
    allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({echo_port}))
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect(f"localhost:{echo_port}"))
    assert response.startswith(b"HTTP/1.1 403")


def test_a_request_that_is_not_connect_gets_405() -> None:
    with EgressProxy(ALLOW) as proxy:
        response = _ask(proxy.address, b"GET http://api.example.test/ HTTP/1.1\r\n\r\n")
    assert response.startswith(b"HTTP/1.1 405")


def test_a_malformed_request_line_gets_400() -> None:
    with EgressProxy(ALLOW) as proxy:
        response = _ask(proxy.address, b"nonsense\r\n\r\n")
    assert response.startswith(b"HTTP/1.1 400")


def test_a_head_past_the_limit_gets_400() -> None:
    padding = b"X-Pad: " + b"a" * 9000 + b"\r\n"
    request = b"CONNECT api.example.test:443 HTTP/1.1\r\n" + padding + b"\r\n"
    with EgressProxy(ALLOW) as proxy:
        response = _ask(proxy.address, request)
    assert response.startswith(b"HTTP/1.1 400")


def test_an_unreachable_upstream_gets_502() -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = int(closed.getsockname()[1])
    closed.close()
    allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({port}), local=True)
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect(f"localhost:{port}"))
    assert response.startswith(b"HTTP/1.1 502")
