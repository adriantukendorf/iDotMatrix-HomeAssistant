"""Sunrise / sunset arc for iDotMatrix LED matrix displays.

Draws a horizon line with an arc across the sky. During the day the sun
travels the arc from sunrise (left) to sunset (right); the part of the
path already travelled glows warm and the rest is a dim dotted trail.
At night the moon takes the same arc from sunset to the next sunrise on a
cool blue trail with a couple of twinkling stars.

Sunrise and sunset times sit under the two ends of the horizon, the
daylight length runs along the top, and a countdown to the next event
("SET 4H12M" / "RISE 9H05M") along the bottom.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

HORIZON = (70, 70, 80)
TRAIL_DIM = (48, 48, 58)
DAY_TRAIL = (210, 150, 70)
NIGHT_TRAIL = (80, 95, 160)
RISE_COLOR = (255, 170, 80)
SET_COLOR = (200, 120, 200)
LABEL_COLOR = (140, 140, 150)
MOON_COLOR = (220, 225, 240)
STAR_COLOR = (200, 210, 240)

SUN_LOW = (255, 120, 60)      # near the horizon
SUN_HIGH = (255, 225, 90)     # high in the sky
SUN_HI = (255, 250, 220)      # highlight dot


@dataclass
class SunData:
    is_day: bool
    progress: float           # 0..1 along the current arc
    rise_txt: str             # e.g. "6:22"
    set_txt: str              # e.g. "19:14"
    countdown_txt: str        # e.g. "SET 4H12M"
    daylight_txt: str         # e.g. "DAY 12H52M"

    def signature(self) -> tuple:
        # The sun moves ~1 px per 15 min on the 64 px arc; quantise so
        # that only visible movement or a text change triggers an upload.
        return (self.is_day, round(self.progress * 54), self.rise_txt,
                self.set_txt, self.countdown_txt, self.daylight_txt)


def _lerp(a: tuple, b: tuple, k: float) -> tuple:
    k = max(0.0, min(1.0, k))
    return tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _arc_point(cx: int, cy: int, rx: int, ry: int, p: float) -> tuple:
    """Point on the sky arc for progress p (0 = left horizon, 1 = right)."""
    a = math.pi * (1.0 - p)
    return cx + rx * math.cos(a), cy - ry * math.sin(a)


def _draw_trail(d: ImageDraw.ImageDraw, cx: int, cy: int, rx: int, ry: int,
                progress: float, color: tuple) -> None:
    # Remaining path: dotted
    steps = 60
    for i in range(0, steps + 1, 2):
        p = i / steps
        if p > progress:
            x, y = _arc_point(cx, cy, rx, ry, p)
            d.point((round(x), round(y)), fill=TRAIL_DIM)
    # Travelled path: solid
    prev = None
    for i in range(steps + 1):
        p = min(progress, i / steps)
        x, y = _arc_point(cx, cy, rx, ry, p)
        pt = (round(x), round(y))
        if prev is not None:
            d.line([prev, pt], fill=color)
        prev = pt
        if p >= progress:
            break


def _draw_sun(d: ImageDraw.ImageDraw, cx: float, cy: float, r: int,
              progress: float, t: float) -> None:
    # Warm near the horizon, bright yellow overhead
    height = math.sin(math.pi * progress)
    color = _lerp(SUN_LOW, SUN_HIGH, height)
    ray = _lerp(SUN_LOW, SUN_HIGH, height * 0.8)
    rot = t * (math.pi / 2)
    for i in range(8):
        a = rot + i * math.pi / 4
        r0 = r + 2
        r1 = r + 3 + (1 if i % 2 == 0 else 0)
        d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                (cx + r1 * math.cos(a), cy + r1 * math.sin(a))], fill=ray)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    d.point((round(cx - 1), round(cy - 1)), fill=SUN_HI)


def _draw_moon(d: ImageDraw.ImageDraw, cx: float, cy: float, r: int) -> None:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MOON_COLOR)
    off = max(1, round(r * 0.7))
    d.ellipse([cx - r + off, cy - r - off, cx + r + off, cy + r - off],
              fill=(0, 0, 0))


def _draw_stars(d: ImageDraw.ImageDraw, size: int, f: int, n: int) -> None:
    stars = ((8, 14), (54, 12), (26, 20), (44, 26), (14, 30))
    for i, (x, y) in enumerate(stars):
        k = 0.5 + 0.5 * math.sin(2 * math.pi * (f / n + i * 0.23))
        c = _lerp((40, 45, 70), STAR_COLOR, k)
        d.point((x, y), fill=c)


def _layout_large(data: SunData, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    t = f / n

    cx, cy, rx, ry = size // 2, 43, 27, 26

    # Top: daylight length
    dw = _text_width(data.daylight_txt)
    _draw_text(d, (size - dw) // 2, 2, data.daylight_txt, LABEL_COLOR)

    if not data.is_day:
        _draw_stars(d, size, f, n)

    # Sky arc and horizon
    _draw_trail(d, cx, cy, rx, ry, data.progress,
                DAY_TRAIL if data.is_day else NIGHT_TRAIL)
    d.line([(2, cy), (size - 3, cy)], fill=HORIZON)

    # Sun or moon at the current position
    sx, sy = _arc_point(cx, cy, rx, ry, data.progress)
    if data.is_day:
        _draw_sun(d, sx, sy, 3, data.progress, t)
    else:
        _draw_moon(d, sx, sy, 3)

    # Sunrise (left) and sunset (right) times under the horizon ends
    _draw_text(d, 2, cy + 4, data.rise_txt, RISE_COLOR)
    sw = _text_width(data.set_txt)
    _draw_text(d, size - sw - 2, cy + 4, data.set_txt, SET_COLOR)

    # Bottom: countdown to the next event
    cw = _text_width(data.countdown_txt)
    _draw_text(d, (size - cw) // 2, 56, data.countdown_txt, LABEL_COLOR)

    return img


def _layout_small(data: SunData, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    cx, cy, rx, ry = size // 2, 20, 13, 13
    _draw_trail(d, cx, cy, rx, ry, data.progress,
                DAY_TRAIL if data.is_day else NIGHT_TRAIL)
    d.line([(1, cy), (size - 2, cy)], fill=HORIZON)

    sx, sy = _arc_point(cx, cy, rx, ry, data.progress)
    if data.is_day:
        _draw_sun(d, sx, sy, 2, data.progress, 0.0)
    else:
        _draw_moon(d, sx, sy, 2)

    # Next event time centred below
    txt = data.set_txt if data.is_day else data.rise_txt
    color = SET_COLOR if data.is_day else RISE_COLOR
    tw = _text_width(txt)
    _draw_text(d, (size - tw) // 2, 24, txt, color)
    return img


def render_sun_gif(data: SunData, size: int = 64,
                   duration: int = 200) -> bytes:
    if size >= 48:
        n = 16
        frames = [_layout_large(data, size, f, n) for f in range(n)]
    else:
        frame = _layout_small(data, size)
        frames = [frame, frame.copy()]
        duration = 1000
    return frames_to_gif(frames, duration)
