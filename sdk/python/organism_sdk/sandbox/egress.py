"""An allowlist CONNECT proxy for a sandboxed child (v1.12 W5, network groundwork).

The work executor's profile names the hosts its CLI may reach, but the jail does not enforce that
list (WORK_AGENT.md, section 10). Enforcing it takes two parts. The child runs in its own network
namespace, which has no network of its own. And a route carries the child's connections to this
proxy. The proxy is the part that decides: it opens a tunnel only to a host on its allowlist, on a
port the allowlist permits, and relays the bytes without reading them. Anything else gets a 403.

The route is not built. Until a bridge carries the child's connection here, the child cannot reach
this proxy, and the work executor does not start it. The proxy listens on loopback and accepts any
client that connects, so the bridge must let only the one child in.
"""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import socketserver
import threading
from collections.abc import Callable
from dataclasses import dataclass
from io import BufferedIOBase
from typing import Self, cast

MAX_HEAD_BYTES = 8192
UPSTREAM_TIMEOUT_S = 10.0
CHUNK = 65536
DEFAULT_PORTS = frozenset({443})


@dataclass(frozen=True)
class Allow:
    """The hosts a tunnel may reach, and the ports it may use. Host names are lower case.

    `local` lets a host resolve to loopback or private addresses. It is off, so a name on the list
    cannot reach the machine or its network through the proxy. Only tests turn it on.
    """

    hosts: frozenset[str]
    ports: frozenset[int] = DEFAULT_PORTS
    local: bool = False

    def __post_init__(self) -> None:
        for host in self.hosts:
            if not host or host != host.lower() or any(c in host for c in ":/ []"):
                raise ValueError(f"not a host name: {host!r}")
        for port in self.ports:
            if not 1 <= port <= 65535:
                raise ValueError(f"not a port: {port}")


def decide(target: str, allow: Allow) -> str | None:
    """Why a CONNECT to `target` ("host:port") must be refused, or None when it may tunnel.

    The host is compared lower case, with a trailing dot ignored. The reason is for a log. It is
    never sent back to the client, because it may echo the target.
    """
    host, separator, port_text = target.rpartition(":")
    if not separator or not host:
        return "target is not host:port"
    if not (port_text.isascii() and port_text.isdigit()):
        return "port is not a number"
    port = int(port_text)
    if not 1 <= port <= 65535:
        return "port is out of range"
    name = host.lower().removesuffix(".")
    if name not in allow.hosts:
        return "host is not on the allowlist"
    if port not in allow.ports:
        return "port is not allowed"
    return None


def _is_local(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    if mapped is not None and _is_local(mapped):
        return True
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _addresses(host: str, port: int, allow: Allow) -> list[str]:
    """The addresses to connect to, or [] when the host resolves to one the proxy must not reach.

    The proxy connects to the addresses checked here, not to the name again, so a name cannot
    resolve differently the second time. Raises OSError when the name does not resolve.
    """
    found = [str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    if allow.local:
        return found
    for text in found:
        if _is_local(ipaddress.ip_address(text.split("%", 1)[0])):
            return []
    return found


def _dial(addresses: list[str], port: int) -> socket.socket | None:
    """A connection to the first checked address that accepts one, or None when none does."""
    for address in addresses:
        try:
            return socket.create_connection((address, port), timeout=UPSTREAM_TIMEOUT_S)
        except OSError:
            continue
    return None


def _read_head(rfile: BufferedIOBase) -> bytes | None:
    """The request head, through its blank line, or None when it is missing or too long."""
    head = b""
    while True:
        line = rfile.readline(MAX_HEAD_BYTES + 1)
        if not line:
            return None
        head += line
        if len(head) > MAX_HEAD_BYTES:
            return None
        if line in (b"\r\n", b"\n"):
            return head


def _pump(read: Callable[[int], bytes], sink: socket.socket) -> None:
    """Copy until the source ends, then tell the sink no more is coming."""
    with contextlib.suppress(OSError):
        while data := read(CHUNK):
            sink.sendall(data)
    with contextlib.suppress(OSError):
        sink.shutdown(socket.SHUT_WR)


class _Handler(socketserver.StreamRequestHandler):
    server: _Server

    def handle(self) -> None:
        head = _read_head(self.rfile)
        if head is None:
            self._status(400, "Bad Request")
            return
        parts = head.split(b"\r\n", 1)[0].split(b" ")
        if len(parts) != 3 or not parts[2].startswith(b"HTTP/1."):
            self._status(400, "Bad Request")
            return
        method, target = parts[0], parts[1].decode("latin-1")
        if method != b"CONNECT":
            self._status(405, "Method Not Allowed")
            return
        if decide(target, self.server.allow) is not None:
            self._status(403, "Forbidden")
            return
        host, _, port = target.rpartition(":")
        try:
            addresses = _addresses(host, int(port), self.server.allow)
        except OSError:
            self._status(502, "Bad Gateway")
            return
        if not addresses:
            self._status(403, "Forbidden")
            return
        upstream = _dial(addresses, int(port))
        if upstream is None:
            self._status(502, "Bad Gateway")
            return
        with upstream:
            upstream.settimeout(None)  # the timeout is for connecting, not for an idle tunnel
            self.connection.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            # Read the client through rfile: bytes it sent after the head may already be buffered.
            back = threading.Thread(
                target=_pump, args=(upstream.recv, self.connection), daemon=True
            )
            back.start()
            _pump(self.rfile.read1, upstream)
            back.join()

    def _status(self, code: int, text: str) -> None:
        with contextlib.suppress(OSError):
            self.connection.sendall(
                f"HTTP/1.1 {code} {text}\r\nContent-Length: 0\r\n\r\n".encode("ascii")
            )


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], allow: Allow) -> None:
        self.allow = allow
        super().__init__(address, _Handler)


class EgressProxy:
    """A CONNECT proxy on loopback that tunnels only to its allowlist. Use it as a context manager.

    `port` 0 takes any free port, which `address` then reports.
    """

    def __init__(self, allow: Allow, *, port: int = 0) -> None:
        self._server = _Server(("127.0.0.1", port), allow)
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return cast(str, host), port

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:  # shutdown waits for the serve loop, so only a started one
            self._server.shutdown()
            self._thread.join(timeout=5)
        self._server.server_close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
