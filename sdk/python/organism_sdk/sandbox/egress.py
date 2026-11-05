"""An allowlist CONNECT proxy for a sandboxed child (v1.12 W5, network groundwork).

The work executor's profile names the hosts its CLI may reach. The jail enforces that list when the
profile sets `enforce_network` (WORK_AGENT.md, section 10). The child then runs in its own network
namespace, which has no route out, and the only way out is this proxy. The proxy is the part that
decides: it opens a tunnel only to a host on its allowlist, on a port the allowlist permits, and
relays the bytes without reading them. Anything else gets a 403.

The jail starts this proxy on a Unix socket in an owner-only directory. A bridge in the child
(`egress_bridge.py`) carries the child's connections to that socket. The proxy accepts any client
that can reach the socket, so the directory's owner-only mode is part of the control.
"""

from __future__ import annotations

import contextlib
import ipaddress
import os
import socket
import socketserver
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from io import BufferedIOBase
from pathlib import Path
from typing import Any, Self, cast

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
    server: Any  # a _TcpServer or a _UnixServer, each with an `allow`

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


class _TcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], allow: Allow) -> None:
        self.allow = allow
        super().__init__(address, _Handler)


if sys.platform != "win32":  # Unix sockets exist on Linux and macOS, not on Windows

    class _UnixServer(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

        def __init__(self, path: str, allow: Allow) -> None:
            self.allow = allow
            super().__init__(path, _Handler)

    def _unix_server(path: Path, allow: Allow) -> socketserver.BaseServer:
        server = _UnixServer(str(path), allow)
        # owner-only: the directory is owner-only too, this is the socket's own mode
        os.chmod(path, 0o600)
        return server


class EgressProxy:
    """A CONNECT proxy that tunnels only to its allowlist. Use it as a context manager.

    It listens on loopback at `port` (0 takes any free port, which `address` then reports). Given
    `socket_path`, it listens on that Unix socket instead, owner-only. The work executor's child
    reaches the proxy that way, because the child's own network namespace has no route to loopback.
    """

    def __init__(self, allow: Allow, *, port: int = 0, socket_path: Path | None = None) -> None:
        if socket_path is None:
            self._server: socketserver.BaseServer = _TcpServer(("127.0.0.1", port), allow)
        elif sys.platform == "win32":
            raise RuntimeError("the egress proxy cannot listen on a Unix socket on Windows")
        else:
            self._server = _unix_server(socket_path, allow)
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        """The loopback address of a TCP proxy."""
        host, port = cast(tuple[str, int], self._server.server_address)
        return host, port

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
