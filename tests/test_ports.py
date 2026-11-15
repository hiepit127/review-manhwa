from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
import time

from src.ports import _port_free, close_ports


def test_close_listening_socket_in_this_process():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert close_ports(port, count=1) == [port]
        assert _port_free(port)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def test_close_port_stops_another_process():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    code = textwrap.dedent(
        """
        import socket, sys, time
        sock = socket.socket()
        sock.bind(("127.0.0.1", int(sys.argv[1])))
        sock.listen(1)
        time.sleep(30)
        """
    )
    proc = subprocess.Popen([sys.executable, "-c", code, str(port)])
    try:
        for _ in range(50):
            if not _port_free(port):
                break
            time.sleep(0.05)
        assert close_ports(port, count=1) == [port]
        proc.wait(timeout=3)
        assert _port_free(port)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
