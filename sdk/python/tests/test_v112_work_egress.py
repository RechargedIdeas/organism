"""v1.12 W5, network groundwork: the egress proxy decides each tunnel and relays the bytes.

The work executor's child cannot reach this proxy yet (WORK_AGENT.md, section 10), so these tests
use real loopback sockets, with an echo server on 127.0.0.1 as the upstream."""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from organism_sdk.sandbox import egress
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


@pytest.fixture
def dials(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record each set of addresses the proxy tries to dial. Every dial fails, so none reaches a host."""
    dialled: list[list[str]] = []

    def dial(addresses: list[str], port: int) -> socket.socket | None:
        dialled.append(addresses)
        return None

    monkeypatch.setattr(egress, "_dial", dial)
    return dialled


@pytest.mark.parametrize(
    "target",
    [
        "evil.example.test:443",
        "api.example.test:80",
        ":443",
        "api.example.test:443:443",
        "api.example.test:+443",
    ],
)
def test_a_refused_connect_never_dials(dials: list[list[str]], target: str) -> None:
    allow = Allow(hosts=frozenset({"api.example.test"}))
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect(target))
    assert response.startswith(b"HTTP/1.1 403")
    assert dials == []


def _resolves(monkeypatch: pytest.MonkeyPatch, host: str, *lookups: list[str]) -> list[str]:
    """Make `host` resolve to each list of addresses in turn, one list per lookup.

    Other names resolve as usual. Returns the names looked up for `host`, so a test can count them.
    """
    real = socket.getaddrinfo
    asked: list[str] = []

    def lookup(name: str, port: int, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        if name != host:
            return real(name, port, *args, **kwargs)
        asked.append(name)
        found: list[tuple[Any, ...]] = []
        for address in lookups[min(len(asked), len(lookups)) - 1]:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            found.append((family, socket.SOCK_STREAM, 6, "", (address, port)))
        return found

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    return asked


# A listed name that answers with any private address is refused, even beside a public one.
@pytest.mark.parametrize(
    "addresses",
    [
        ["10.0.0.5"],
        ["192.168.1.9"],
        ["169.254.169.254"],
        ["::ffff:10.0.0.5"],
        ["fd00::5"],
        ["8.8.8.8", "127.0.0.1"],
    ],
)
def test_a_listed_name_that_resolves_to_a_private_address_is_refused(
    monkeypatch: pytest.MonkeyPatch, dials: list[list[str]], addresses: list[str]
) -> None:
    allow = Allow(hosts=frozenset({"api.example.test"}))
    asked = _resolves(monkeypatch, "api.example.test", addresses)
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect("api.example.test:443"))
    assert response.startswith(b"HTTP/1.1 403")
    assert asked == ["api.example.test"]
    assert dials == []


def test_a_name_that_turns_private_after_the_check_is_not_looked_up_again(
    monkeypatch: pytest.MonkeyPatch, dials: list[list[str]]
) -> None:
    allow = Allow(hosts=frozenset({"api.example.test"}))
    asked = _resolves(monkeypatch, "api.example.test", ["8.8.8.8"], ["127.0.0.1"])
    with EgressProxy(allow) as proxy:
        response = _ask(proxy.address, _connect("api.example.test:443"))
    assert asked == ["api.example.test"]
    assert dials == [["8.8.8.8"]]  # it dials the address it checked, not the second answer
    assert response.startswith(b"HTTP/1.1 502")  # the dial fails, so nothing is tunnelled


def _ask_and_end(address: tuple[str, int], request: bytes) -> bytes:
    """Send a request and end the client's side, so a head cut short reads as end of stream."""
    with socket.create_connection(address, timeout=5) as sock:
        sock.sendall(request)
        sock.shutdown(socket.SHUT_WR)
        return _read_head(sock)


@pytest.mark.parametrize(
    "request_bytes",
    [
        b"CONNECT api.example.test:443 HTTP/2.0\r\n\r\n",
        b"CONNECT api.example.test:443\r\n\r\n",
        b"CONNECT api.example.test:443 HTTP/1.1 extra\r\n\r\n",
        b"CONNECT  api.example.test:443 HTTP/1.1\r\n\r\n",
        b"\r\n",
        b"CONNECT api.example.test:443 HTTP/1.1\r\nHost: api.example.test\r\n",
    ],
)
def test_a_malformed_request_gets_400(request_bytes: bytes) -> None:
    with EgressProxy(ALLOW) as proxy:
        response = _ask_and_end(proxy.address, request_bytes)
    assert response.startswith(b"HTTP/1.1 400")


def test_the_proxy_keeps_serving_after_a_silent_or_junk_client(echo_port: int) -> None:
    allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({echo_port}), local=True)
    with EgressProxy(allow) as proxy:
        with socket.create_connection(proxy.address, timeout=5):
            pass  # connects and leaves without a word
        assert _ask(proxy.address, b"nonsense\r\n\r\n").startswith(b"HTTP/1.1 400")
        assert _ask(proxy.address, _connect(f"localhost:{echo_port}")).startswith(b"HTTP/1.1 200")


@contextlib.contextmanager
def _upstream(handle: Callable[[socket.socket], None]) -> Iterator[int]:
    """A loopback server that gives its one connection to `handle`, on a thread of its own."""
    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(5)

    def serve() -> None:
        conn, _ = server.accept()
        with conn:
            handle(conn)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield int(server.getsockname()[1])
    finally:
        server.close()
        thread.join(timeout=5)


def _read_to_end(sock: socket.socket) -> bytes:
    data = b""
    while chunk := sock.recv(4096):
        data += chunk
    return data


def _reply_after_eof(conn: socket.socket) -> None:
    """Read until the client ends its side, then answer with what it sent."""
    conn.sendall(b"got:" + _read_to_end(conn))


def _say_bye(conn: socket.socket) -> None:
    conn.sendall(b"bye")  # the handler then closes, which ends the upstream's side


def test_bytes_sent_with_the_head_are_relayed() -> None:
    with _upstream(_echo) as port:
        allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({port}), local=True)
        with (
            EgressProxy(allow) as proxy,
            socket.create_connection(proxy.address, timeout=5) as sock,
        ):
            sock.sendall(_connect(f"localhost:{port}") + b"ping")
            reply = b""
            while not reply.endswith(b"ping"):
                chunk = sock.recv(1024)
                assert chunk, reply
                reply += chunk
    assert reply == b"HTTP/1.1 200 Connection Established\r\n\r\nping"


def test_the_client_can_end_its_side_and_still_read_the_reply() -> None:
    with _upstream(_reply_after_eof) as port:
        allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({port}), local=True)
        with (
            EgressProxy(allow) as proxy,
            socket.create_connection(proxy.address, timeout=5) as sock,
        ):
            sock.sendall(_connect(f"localhost:{port}") + b"abc")
            sock.shutdown(socket.SHUT_WR)
            reply = _read_to_end(sock)
    assert reply == b"HTTP/1.1 200 Connection Established\r\n\r\ngot:abc"


def test_when_the_upstream_closes_the_client_reads_its_bytes_then_end_of_stream() -> None:
    with _upstream(_say_bye) as port:
        allow = Allow(hosts=frozenset({"localhost"}), ports=frozenset({port}), local=True)
        with (
            EgressProxy(allow) as proxy,
            socket.create_connection(proxy.address, timeout=5) as sock,
        ):
            sock.sendall(_connect(f"localhost:{port}"))
            reply = _read_to_end(sock)
    assert reply == b"HTTP/1.1 200 Connection Established\r\n\r\nbye"
