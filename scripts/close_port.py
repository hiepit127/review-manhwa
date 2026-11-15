#!/usr/bin/env python3
"""Đóng cổng Gradio còn bị giữ. Mặc định đóng 7860–7869."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ports import close_ports


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        for item in args:
            close_ports(int(item), count=1)
        return
    close_ports()


if __name__ == "__main__":
    main()
