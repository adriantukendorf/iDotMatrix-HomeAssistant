"""CO2 gauge for iDotMatrix LED matrix displays.

Renders a large PPM reading with a horizontal color-coded bar gauge.
Colors shift green -> yellow -> orange -> red based on thresholds.
A CO2 molecule icon (from LaMetric icon set) in the corner changes color
with the severity level.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

GOOD_GREEN = (80, 200, 80)
OK_YELLOW = (220, 200, 40)
WARN_ORANGE = (240, 150, 30)
BAD_RED = (240, 60, 50)
DIM_GRAY = (50, 50, 50)
LABEL_COLOR = (140, 140, 150)

_THRESHOLDS = (
    (600, GOOD_GREEN, "GOOD"),
    (800, (140, 210, 80), "OK"),
    (1000, OK_YELLOW, "FAIR"),
    (1200, WARN_ORANGE, "POOR"),
    (1500, BAD_RED, "BAD"),
    (9999, (200, 30, 30), "CRIT"),
)

# CO2 molecule icon (8x8) from LaMetric icon set (#8458/8459/8460)
_CO2_ICON = (
    "XXX.X...",
    "X..X.X..",
    "X..X.X..",
    "X..X.X..",
    "XXX.X.XX",
    ".......X",
    "......X.",
    "......XX",
)


def _ppm_color(ppm: float) -> tuple:
    for threshold, color, _ in _THRESHOLDS:
        if ppm < threshold:
            return color
    return BAD_RED


def _ppm_label(ppm: float) -> str:
    for threshold, _, label in _THRESHOLDS:
        if ppm < threshold:
            return label
    return "CRIT"


@dataclass
class CO2Data:
    ppm: float

    def signature(self) -> tuple:
        return (round(self.ppm),)


def _draw_icon(d: ImageDraw.ImageDraw, ox: int, oy: int,
               color: tuple) -> None:
    for r, row in enumerate(_CO2_ICON):
        for c, ch in enumerate(row):
            if ch == "X":
                d.point((ox + c, oy + r), fill=color)


def _draw_hbar(d: ImageDraw.ImageDraw, x: int, y: int,
               w: int, h: int, ppm: float) -> None:
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=DIM_GRAY)

    fill_frac = min(1.0, max(0.0, ppm / 2000))
    fill_w = max(0, round(fill_frac * (w - 2)))

    for col in range(fill_w):
        xx = x + 1 + col
        col_frac = col / max(1, w - 2)
        if col_frac < 0.3:
            c = GOOD_GREEN
        elif col_frac < 0.5:
            c = OK_YELLOW
        elif col_frac < 0.75:
            c = WARN_ORANGE
        else:
            c = BAD_RED
        d.line([(xx, y + 1), (xx, y + h - 2)], fill=c)

    needle_x = x + 1 + round(fill_frac * (w - 2))
    if x < needle_x < x + w - 1:
        d.line([(needle_x, y - 1), (needle_x, y + h)], fill=(255, 255, 255))


def _layout_large(data: CO2Data, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    color = _ppm_color(data.ppm)

    # Row 1 (y=2): CO2 molecule icon on left + status label right
    _draw_icon(d, 2, 2, color)

    label = _ppm_label(data.ppm)
    lw = _text_width(label)
    _draw_text(d, size - lw - 2, 3, label, color)

    # Row 2 (y=22): Big PPM number at scale=2, centered
    ppm_txt = f"{data.ppm:.0f}"
    w2 = _text_width(ppm_txt, scale=2)
    _draw_text(d, (size - w2) // 2, 22, ppm_txt, color, scale=2)

    # Row 3 (y=38): "ppm" label centered at scale=1
    pw = _text_width("ppm")
    _draw_text(d, (size - pw) // 2, 39, "ppm", LABEL_COLOR)

    # Row 4 (y=50): Horizontal bar gauge, full width with margin
    _draw_hbar(d, 2, 50, size - 4, 7, data.ppm)

    # Haze particles when CO2 is high
    if data.ppm >= 1000:
        t = f / n
        for i in range(5):
            phase = t + i * 0.2
            px = round(size * (0.15 + 0.7 * ((phase * 1.3 + i * 0.37) % 1.0)))
            py = round(45 + 3 * math.sin(2 * math.pi * phase))
            if 0 <= px < size and 0 <= py < size:
                d.point((px, py), fill=(80, 65, 50))

    return img


def _layout_small(data: CO2Data, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    color = _ppm_color(data.ppm)

    _draw_icon(d, 1, 1, color)

    ppm_txt = f"{data.ppm:.0f}"
    w = _text_width(ppm_txt, scale=2)
    _draw_text(d, (size - w) // 2, 10, ppm_txt, color, scale=2)

    label = _ppm_label(data.ppm)
    lw = _text_width(label)
    _draw_text(d, (size - lw) // 2, 26, label, color)

    return img


def render_co2_gif(data: CO2Data, size: int = 64,
                   duration: int = 200) -> bytes:
    if size >= 48:
        n = 16
        frames = [_layout_large(data, size, f, n) for f in range(n)]
    else:
        frame = _layout_small(data, size)
        frames = [frame, frame.copy()]
        duration = 1000
    return frames_to_gif(frames, duration)
