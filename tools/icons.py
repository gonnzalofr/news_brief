"""Draws the brief's icon: a sun rising over a line of text, on the page's teal.

One set of shapes, written as brief/static/favicon.svg and rendered here, with no
dependencies, to the PNG fallbacks, favicon.ico and the apple-touch-icon. Run it after
changing a shape or a colour:

    python3 tools/icons.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "brief" / "static"

# The page's accent (render.CSS, --accent-h 183: hsl(183 42% 32%)), and a warm paper white.
TILE, TILE_DARK, SUN = "#2f7074", "#3b8589", "#f7e7c6"
LINE_ALPHA = 0.6  # the line of text under the horizon, lighter than the sun

# On a 32 by 32 grid: the tile's corner, the sun (a half disc on the horizon), the horizon, a line.
CORNER = 7
SUN_C, SUN_R = (16, 16), 8
HORIZON = (5, 18, 27, 20.5, 1.25)  # x0, y0, x1, y1, corner
LINE = (9, 23, 23, 25, 1)


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def svg() -> str:
    hx0, hy0, hx1, hy1, hr = HORIZON
    lx0, ly0, lx1, ly1, lr = LINE
    (cx, cy), r = SUN_C, SUN_R
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f"<style>.t{{fill:{TILE}}}.s{{fill:{SUN}}}@media (prefers-color-scheme:dark){{.t{{fill:{TILE_DARK}}}}}</style>\n"
        f'<rect class="t" width="32" height="32" rx="{CORNER}"/>\n'
        f'<path class="s" d="M{cx - r} {cy}a{r} {r} 0 0 1 {2 * r} 0z"/>\n'
        f'<rect class="s" x="{hx0}" y="{hy0}" width="{hx1 - hx0}" height="{hy1 - hy0}" rx="{hr}"/>\n'
        f'<rect class="s" x="{lx0}" y="{ly0}" width="{lx1 - lx0}" height="{ly1 - ly0}" rx="{lr}" opacity="{LINE_ALPHA}"/>\n'
        "</svg>\n"
    )


def _in_rrect(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    dx = max(x0 + r - x, 0, x - (x1 - r))
    dy = max(y0 + r - y, 0, y - (y1 - r))
    return dx * dx + dy * dy <= r * r


def _sample(x: float, y: float, rounded: bool) -> tuple[float, float, float, float]:
    """The colour at a point of the 32 grid, as RGBA in 0-1."""
    if rounded and not _in_rrect(x, y, 0, 0, 32, 32, CORNER):
        return (0, 0, 0, 0)
    tile, sun = _hex(TILE), _hex(SUN)
    (cx, cy), r = SUN_C, SUN_R
    if (y <= cy and (x - cx) ** 2 + (y - cy) ** 2 <= r * r) or _in_rrect(x, y, *HORIZON):
        c = sun
    elif _in_rrect(x, y, *LINE):
        c = tuple(t + (s - t) * LINE_ALPHA for t, s in zip(tile, sun))
    else:
        c = tile
    return (c[0] / 255, c[1] / 255, c[2] / 255, 1)


def render(size: int, rounded: bool = True, inset: float = 0.0, ss: int = 6) -> bytes:
    """A size x size RGBA PNG. `inset` (in grid units) shrinks the drawing, for a full-bleed square."""
    span = 32 + 2 * inset
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + 0.5) / ss) / size * span - inset
                    y = (py + (sy + 0.5) / ss) / size * span - inset
                    if inset and not (0 <= x <= 32 and 0 <= y <= 32):
                        c = (*(v / 255 for v in _hex(TILE)), 1)
                    else:
                        c = _sample(x, y, rounded)
                    acc[0] += c[0] * c[3]
                    acc[1] += c[1] * c[3]
                    acc[2] += c[2] * c[3]
                    acc[3] += c[3]
            a = acc[3]
            rgb = [round(v / a * 255) if a else 0 for v in acc[:3]]
            row += bytes(rgb + [round(a / (ss * ss) * 255)])
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def ico(pngs: dict[int, bytes]) -> bytes:
    """A .ico holding PNG images, which every current browser reads."""
    out = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    body = b""
    for size, data in sorted(pngs.items()):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(body))
        body += data
    return out + body


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "favicon.svg").write_text(svg(), encoding="utf-8")
    small = {n: render(n) for n in (16, 32, 48)}
    (OUT / "favicon.ico").write_bytes(ico(small))
    (OUT / "favicon-32.png").write_bytes(small[32])
    (OUT / "icon-192.png").write_bytes(render(192))
    # iOS rounds the corners itself and shows transparency as black: a full square, a little inset.
    (OUT / "apple-touch-icon.png").write_bytes(render(180, rounded=False, inset=2.5))
    for p in sorted(OUT.iterdir()):
        print(p.relative_to(OUT.parent.parent), p.stat().st_size)


if __name__ == "__main__":
    main()
