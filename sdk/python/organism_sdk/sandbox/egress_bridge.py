"""Run one command with a bridge to the host's egress proxy, inside the jail's network namespace.

The jail runs this file as the first part of its argv:

    python -I egress_bridge.py --listen HOST:PORT --upstream SOCKET -- COMMAND [ARG ...]

It binds HOST:PORT, where the jail has already brought loopback up, and carries each connection to
the proxy's Unix socket at SOCKET. Then it runs COMMAND and exits with COMMAND's status. The bind
happens before COMMAND starts, so a first connection cannot race it. If the bind fails, nothing
runs: this exits without starting COMMAND, and the jail reports the failure.

Standard library only, and no import from organism_sdk, because it runs in the jail. The design is
in docs/v1.12/WORK_AGENT.md, section 10.
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import subprocess
import sys
import threading
from collections.abc import Sequence

CHUNK = 65536
UNREACHABLE = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n"


def _relay(source: socket.socket, sink: socket.socket) -> None:
    """Copy until the source ends, then tell the sink no more is coming."""
    with contextlib.suppress(OSError):
        while data := source.recv(CHUNK):
            sink.sendall(data)
    with contextlib.suppress(OSError):
        sink.shutdown(socket.SHUT_WR)


def _serve(client: socket.socket, upstream: str) -> None:
    """Carry one client connection to the proxy's Unix socket, in both directions."""
    if sys.platform == "win32":  # the bridge runs in the Linux jail, which has Unix sockets
        raise RuntimeError("the egress bridge needs Unix sockets, which only Linux has")
    with client:
        proxy = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        with proxy:
            try:
                proxy.connect(upstream)
            except OSError:
                with contextlib.suppress(OSError):
                    client.sendall(UNREACHABLE)
                return
            back = threading.Thread(target=_relay, args=(proxy, client), daemon=True)
            back.start()
            _relay(client, proxy)
            back.join()


def _accept(server: socket.socket, upstream: str) -> None:
    while True:
        client, _ = server.accept()
        threading.Thread(target=_serve, args=(client, upstream), daemon=True).start()


def main(argv: Sequence[str]) -> int:
    items = list(argv)
    if "--" not in items:
        sys.stderr.write("egress bridge: the command follows `--`\n")
        return 2
    separator = items.index("--")
    parser = argparse.ArgumentParser(prog="egress_bridge")
    parser.add_argument("--listen", required=True, help="HOST:PORT the command connects to")
    parser.add_argument("--upstream", required=True, help="the proxy's Unix socket")
    args = parser.parse_args(items[:separator])
    command = items[separator + 1 :]
    if not command:
        sys.stderr.write("egress bridge: no command after `--`\n")
        return 2
    host, _, port = args.listen.rpartition(":")
    try:
        server = socket.create_server((host, int(port)))
    except OSError as error:
        sys.stderr.write(f"egress bridge: cannot start: {error}\n")
        return 111
    threading.Thread(target=_accept, args=(server, args.upstream), daemon=True).start()
    try:
        completed = subprocess.run(command, check=False)
    except OSError as error:
        sys.stderr.write(f"egress bridge: cannot run the command: {error}\n")
        return 127
    status = completed.returncode
    return status if status >= 0 else 128 - status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
