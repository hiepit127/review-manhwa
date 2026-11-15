"""Đóng cổng Gradio còn bị giữ sau lần chạy trước."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time


def _port_free(port: int) -> bool:
    import socket

    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _listeners(port: int) -> list[tuple[int, int | None]]:
    """Tiến trình và file descriptor đang listen trên cổng."""
    lsof = shutil.which("lsof")
    if lsof:
        result = subprocess.run(
            [lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "pf"],
            capture_output=True,
            text=True,
        )
        found: list[tuple[int, int | None]] = []
        pid = None
        for line in result.stdout.splitlines():
            if line.startswith("p") and line[1:].isdigit():
                pid = int(line[1:])
            elif line.startswith("f") and line[1:].isdigit() and pid is not None:
                found.append((pid, int(line[1:])))
        if found:
            return found
    return _listeners_from_proc(port)


def _listeners_from_proc(port: int) -> list[tuple[int, int | None]]:
    inodes = set()
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        if not os.path.isfile(name):
            continue
        with open(name, encoding="utf-8") as handle:
            next(handle, None)
            for line in handle:
                parts = line.split()
                if len(parts) < 10 or parts[3] != "0A":
                    continue
                if int(parts[1].rsplit(":", 1)[-1], 16) == port:
                    inodes.add(parts[9])
    if not inodes or not os.path.isdir("/proc"):
        return []
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        folder = f"/proc/{pid}/fd"
        if not os.path.isdir(folder):
            continue
        for fd_name in os.listdir(folder):
            if not fd_name.isdigit():
                continue
            try:
                target = os.readlink(os.path.join(folder, fd_name))
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in inodes:
                found.append((pid, int(fd_name)))
    return found


def _stop_gradio() -> None:
    try:
        import gradio as gr
        from gradio.blocks import Blocks
    except Exception:
        return
    for block in list(Blocks.get_instances()):
        node = getattr(block, "node_process", None)
        if node is not None and node.poll() is None:
            node.terminate()
            try:
                node.wait(timeout=2)
            except Exception:
                node.kill()
        try:
            if getattr(block, "is_running", False):
                block.close(verbose=False)
        except Exception:
            pass
    try:
        gr.close_all(verbose=False)
    except Exception:
        pass


def _release(pid: int, fd: int | None) -> None:
    if pid == os.getpid():
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass
        return
    if pid <= 1:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def close_ports(start: int = 7860, count: int = 10) -> list[int]:
    """Đóng các cổng listen trong khoảng [start, start + count)."""
    _stop_gradio()
    time.sleep(0.2)
    freed = []
    last = start + count - 1
    for port in range(start, start + count):
        if _port_free(port):
            continue
        for pid, fd in _listeners(port):
            _release(pid, fd)
        time.sleep(0.1)
        if _port_free(port):
            freed.append(port)
            print(f"Đã đóng cổng {port}.")
        else:
            print(f"Không đóng được cổng {port}.")
    if not freed:
        print(f"Không có tiến trình nào đang giữ cổng {start}–{last}.")
    return freed
