#!/bin/sh
# Đóng cổng giao diện. Không tham số: 7860–7869. Có tham số: đúng các cổng đó.
cd "$(dirname "$0")/.."
exec python3 scripts/close_port.py "$@"
