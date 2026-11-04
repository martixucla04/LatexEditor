"""Draw the app icon (blue rounded square with a white Λ) and save it as .ico.

Pure Python (no imaging library): shapes are rasterised with 4×4 supersampling
and stored as PNG images inside the .ico (16, 24, 32, 48, 64, 128, 256 px).

Usage:  python scripts/make_icon.py OUT.ico
"""

import math
import struct
import sys
import zlib
from pathlib import Path

ACCENT = (47, 111, 235)
SUPERSAMPLE = 4


def _segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _inside_rounded_square(x, y, radius=0.22):
    cx = min(max(x, radius), 1 - radius)
    cy = min(max(y, radius), 1 - radius)
    return math.hypot(x - cx, y - cy) <= radius


def _in_lambda(x, y):
    width = 0.085  # half stroke width
    apex, left, right = (0.5, 0.22), (0.27, 0.78), (0.73, 0.78)
    return (_segment_distance(x, y, *apex, *left) <= width
            or _segment_distance(x, y, *apex, *right) <= width)


def render(size: int) -> bytes:
    """RGBA pixels, row by row."""
    rows = []
    n = SUPERSAMPLE
    for j in range(size):
        row = bytearray()
        for i in range(size):
            bg = fg = 0
            for sj in range(n):
                for si in range(n):
                    x = (i + (si + 0.5) / n) / size
                    y = (j + (sj + 0.5) / n) / size
                    if _inside_rounded_square(x, y):
                        bg += 1
                        fg += _in_lambda(x, y)
            total = n * n
            alpha = bg / total
            white = fg / bg if bg else 0
            color = [round(c * (1 - white) + 255 * white) for c in ACCENT]
            row += bytes([*color, round(alpha * 255)])
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int) -> bytes:
    raw = render(size)
    stride = size * 4
    scanlines = b"".join(b"\x00" + raw[y * stride:(y + 1) * stride] for y in range(size))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(scanlines, 9)) + chunk(b"IEND", b"")


def write_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    images = [png(s) for s in sizes]
    offset = 6 + 16 * len(images)
    header = struct.pack("<HHH", 0, 1, len(images))
    entries = b""
    for size, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + b"".join(images))


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/icon.ico")
    write_ico(out)
    print(f"Icon written to {out}")
