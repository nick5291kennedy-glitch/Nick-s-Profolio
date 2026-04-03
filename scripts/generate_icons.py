#!/usr/bin/env python3
from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "icons"


def chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack("!I", len(data))
        + tag
        + data
        + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def color_for_pixel(size: int, x: int, y: int) -> tuple[int, int, int]:
    base_r = 10
    base_g = 74
    base_b = 102
    accent_r = 9
    accent_g = 138
    accent_b = 91
    paper = (239, 244, 248)

    dx = x - size / 2
    dy = y - size / 2
    radius = size * 0.42
    distance = (dx * dx + dy * dy) ** 0.5

    if distance > radius:
        mix = min(1.0, (x + y) / (size * 1.8))
        return tuple(int(paper[index] * (1 - mix * 0.08)) for index in range(3))

    vertical = y / max(1, size - 1)
    horizontal = x / max(1, size - 1)
    blend = min(1.0, max(0.0, 0.55 * vertical + 0.45 * (1 - horizontal)))
    r = int(base_r * (1 - blend) + accent_r * blend + 15)
    g = int(base_g * (1 - blend) + accent_g * blend + 18)
    b = int(base_b * (1 - blend) + accent_b * blend + 24)

    band = abs(dx + dy * 0.7)
    if band < size * 0.07:
        r = min(255, r + 80)
        g = min(255, g + 85)
        b = min(255, b + 70)

    return (r, g, b)


def create_png(size: int, destination: Path) -> None:
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            r, g, b = color_for_pixel(size, x, y)
            row.extend((r, g, b, 255))
        rows.append(bytes(row))

    raw = b"".join(rows)
    ihdr = struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    destination.write_bytes(png)


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    create_png(180, ICONS_DIR / "icon-180.png")
    create_png(192, ICONS_DIR / "icon-192.png")
    create_png(512, ICONS_DIR / "icon-512.png")
    create_png(512, ICONS_DIR / "icon-maskable-512.png")


if __name__ == "__main__":
    main()
