from __future__ import annotations

import math
import os
import struct
import zlib

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
    "src-tauri",
    "icons",
)


def rounded_rect_alpha(x: float, y: float, size: int, radius: float) -> float:
    x0, y0 = radius, radius
    x1, y1 = size - radius, size - radius
    if x0 <= x <= x1 or y0 <= y <= y1:
        return 1.0
    cx = x0 if x < x0 else x1
    cy = y0 if y < y0 else y1
    return 1.0 if math.hypot(x - cx, y - cy) <= radius else 0.0


def draw_icon(size: int) -> bytes:
    top = (0x2F, 0x6F, 0xED)
    bottom = (0x7A, 0x5A, 0xF5)
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            t = y / max(1, size - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            alpha = rounded_rect_alpha(x + 0.5, y + 0.5, size, size * 0.22)
            cross = False
            stroke = max(2, size // 10)
            cx = size // 2
            cy = size // 2
            if abs(y - cy) <= stroke or abs(x - cx) <= stroke:
                cross = True
            if cross:
                r = g = b = 0xFF
            row += bytes((r, g, b, int(255 * alpha)))
        rows.append(bytes(row))
    return b"".join(rows)


def write_png(path: str, size: int) -> None:
    raw = draw_icon(size)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    stride = size * 4
    filtered = bytearray()
    for y in range(size):
        filtered.append(0)
        filtered.extend(raw[y * stride : (y + 1) * stride])
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(filtered), 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)


def write_ico(path: str, png_path: str) -> None:
    with open(png_path, "rb") as f:
        png = f.read()
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    with open(path, "wb") as f:
        f.write(header + entry + png)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, size in (
        ("32x32.png", 32),
        ("128x128.png", 128),
        ("128x128@2x.png", 256),
        ("icon.png", 512),
    ):
        write_png(os.path.join(OUT_DIR, name), size)
    write_ico(
        os.path.join(OUT_DIR, "icon.ico"),
        os.path.join(OUT_DIR, "128x128@2x.png"),
    )
    print(f"icons written to {OUT_DIR}")


if __name__ == "__main__":
    main()
