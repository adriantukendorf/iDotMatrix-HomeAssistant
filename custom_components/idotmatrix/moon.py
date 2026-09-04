"""Moon phase display for iDotMatrix LED matrix displays.

Renders the moon as a large disc with the lit portion shaped by the real
terminator curve for the current lunar age, so a crescent is a crescent
and a gibbous moon bulges the right way. The disc is drawn 4x
supersampled and downscaled for a smooth edge, with a few darker maria
for texture. Stars twinkle around it.

The phase name is stacked on two lines at the top; the illuminated
fraction and the days until the next full or new moon run along the
bottom. In the southern hemisphere the lit side is mirrored.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

SYNODIC_MONTH = 29.530588853
# Reference new moon: 2000-01-06 18:14 UTC
_REF_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

MOON_LIT = (235, 232, 215)
MOON_MARIA = (190, 188, 175)
MOON_DARK = (28, 28, 40)
LABEL_COLOR = (140, 140, 150)
PCT_COLOR = (220, 220, 200)
NEXT_COLOR = (150, 170, 220)
STAR_COLOR = (200, 210, 240)
STAR_DIM = (35, 40, 65)

# (upper age bound in days, line 1, line 2)
_PHASES = (
    (1.85, "NEW", "MOON"),
    (5.53, "WAXING", "CRESCENT"),
    (9.22, "FIRST", "QUARTER"),
    (12.91, "WAXING", "GIBBOUS"),
    (16.61, "FULL", "MOON"),
    (20.30, "WANING", "GIBBOUS"),
    (23.99, "LAST", "QUARTER"),
    (27.68, "WANING", "CRESCENT"),
    (99.0, "NEW", "MOON"),
)

# Maria (dark patches) as (x, y, r) in unit-disc coordinates
_MARIA = (
    (-0.35, -0.30, 0.22),
    (0.10, -0.42, 0.16),
    (-0.15, 0.10, 0.20),
    (0.30, 0.05, 0.14),
    (-0.45, 0.35, 0.12),
    (0.15, 0.45, 0.10),
)


def moon_age(when: datetime) -> float:
    """Days since the last new moon (0 <= age < 29.53)."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = (when - _REF_NEW_MOON).total_seconds() / 86400.0
    return days % SYNODIC_MONTH


def phase_name(age: float) -> tuple:
    for bound, l1, l2 in _PHASES:
        if age < bound:
            return l1, l2
    return "NEW", "MOON"


@dataclass
class MoonData:
    age: float                 # days since new moon
    south: bool = False        # southern hemisphere: mirror the lit side

    @property
    def angle(self) -> float:
        return 2 * math.pi * self.age / SYNODIC_MONTH

    @property
    def illumination(self) -> float:
        return (1 - math.cos(self.angle)) / 2

    @property
    def waxing(self) -> bool:
        return self.age < SYNODIC_MONTH / 2

    def next_txt(self) -> str:
        if self.waxing:
            days = SYNODIC_MONTH / 2 - self.age
            label = "FULL"
        else:
            days = SYNODIC_MONTH - self.age
            label = "NEW"
        d = max(0, round(days))
        return f"{label} {d}D" if d else f"{label} NOW"

    def pct_txt(self) -> str:
        return f"{round(self.illumination * 100)}%"

    def signature(self) -> tuple:
        return (phase_name(self.age), self.pct_txt(), self.next_txt(),
                round(self.age * 2), self.south)


def _lit(x: float, y: float, r: float, angle: float, south: bool) -> bool:
    """Is unit-disc point (x, y) on the lit side for this phase angle?"""
    if x * x + y * y > r * r:
        return False
    if south:
        x = -x
    half = math.sqrt(max(0.0, r * r - y * y))
    xt = half * math.cos(angle)
    if angle <= math.pi:          # waxing: right side lit
        return x >= xt
    return x <= -xt               # waning: left side lit


def _render_disc(data: MoonData, r: int, ss: int = 4) -> Image.Image:
    """Render the moon disc (diameter 2r+1) supersampled and downscaled."""
    size = (2 * r + 1) * ss
    big = Image.new("RGB", (size, size), (0, 0, 0))
    px = big.load()
    R = r * ss
    c = size / 2.0
    for yy in range(size):
        for xx in range(size):
            x, y = xx + 0.5 - c, yy + 0.5 - c
            if x * x + y * y > R * R:
                continue
            if _lit(x, y, R, data.angle, data.south):
                color = MOON_LIT
                ux, uy = x / R, y / R
                for mx, my, mr in _MARIA:
                    if (ux - mx) ** 2 + (uy - my) ** 2 <= mr * mr:
                        color = MOON_MARIA
                        break
            else:
                color = MOON_DARK
            px[xx, yy] = color
    return big.resize((2 * r + 1, 2 * r + 1), Image.LANCZOS)


def _draw_stars(d: ImageDraw.ImageDraw, stars: tuple, f: int, n: int) -> None:
    for i, (x, y) in enumerate(stars):
        k = 0.5 + 0.5 * math.sin(2 * math.pi * (f / n + i * 0.19))
        c = tuple(round(STAR_DIM[j] + (STAR_COLOR[j] - STAR_DIM[j]) * k)
                  for j in range(3))
        d.point((x, y), fill=c)


_STARS_LARGE = ((5, 22), (58, 20), (8, 44), (57, 47), (3, 33), (61, 36),
                (12, 52), (52, 18))


def _layout_large(data: MoonData, disc: Image.Image, size: int,
                  f: int = 0, n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    l1, l2 = phase_name(data.age)
    _draw_text(d, (size - _text_width(l1)) // 2, 1, l1, LABEL_COLOR)
    _draw_text(d, (size - _text_width(l2)) // 2, 9, l2, LABEL_COLOR)

    _draw_stars(d, _STARS_LARGE, f, n)

    r = disc.width // 2
    img.paste(disc, (size // 2 - r, 34 - r))

    pct = data.pct_txt()
    _draw_text(d, 2, 55, pct, PCT_COLOR)
    nxt = data.next_txt()
    if _text_width(pct) + 3 + _text_width(nxt) > size - 4:
        nxt = nxt.replace(" ", "")     # "100%" + "NEW 15D" would collide
    _draw_text(d, size - _text_width(nxt) - 2, 55, nxt, NEXT_COLOR)
    return img


def _layout_small(data: MoonData, disc: Image.Image, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    r = disc.width // 2
    img.paste(disc, (size // 2 - r, 12 - r))
    pct = data.pct_txt()
    _draw_text(d, (size - _text_width(pct)) // 2, 24, pct, PCT_COLOR)
    return img


def render_moon_gif(data: MoonData, size: int = 64,
                    duration: int = 250) -> bytes:
    if size >= 48:
        disc = _render_disc(data, 16)
        n = 16
        frames = [_layout_large(data, disc, size, f, n) for f in range(n)]
    else:
        disc = _render_disc(data, 10)
        frame = _layout_small(data, disc, size)
        frames = [frame, frame.copy()]
        duration = 1000
    return frames_to_gif(frames, duration)
