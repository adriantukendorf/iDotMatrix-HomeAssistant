"""CO2 gauge for iDotMatrix LED matrix displays.

Renders a large PPM reading with a horizontal color-coded bar gauge.
Colors shift green -> yellow -> orange -> red based on thresholds.
A lung icon breathes gently in the corner.

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

_LUNG_BITMAP = (
    "..XX..XX..",
    ".XXXX.XXX.",
    ".XXXX.XXX.",
    "XXXXX.XXXX",
    "XXXXX.XXXX",
    "XXXXX.XXXX",
    ".XXXX.XXX.",
    ".XXXX.XXX.",
    "..XXX.XX..",
    "...XX.X...",
    "....X.X...",
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


def _draw_lung(d: ImageDraw.ImageDraw, ox: int, oy: int,
               color: tuple, scale: float = 1.0) -> None:
    bw = len(_LUNG_BITMAP[0])
    bh = len(_LUNG_BITMAP)
    center_x = ox + bw / 2
    center_y = oy + bh / 2
    for r, row in enumerate(_LUNG_BITMAP):
        for c, ch in enumerate(row):
            if ch == "X":
                if scale != 1.0:
                    cx = round(center_x + (ox + c - center_x) * scale)
                    cy = round(center_y + (oy + r - center_y) * scale)
                else:
                    cx, cy = ox + c, oy + r
                if 0 <= cx < 64 and 0 <= cy < 64:
                    d.point((cx, cy), fill=color)


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

    # Needle marker for current value
    needle_x = x + 1 + round(fill_frac * (w - 2))
    if x < needle_x < x + w - 1:
        d.line([(needle_x, y - 1), (needle_x, y + h)], fill=(255, 255, 255))


def _layout_large(data: CO2Data, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    color = _ppm_color(data.ppm)

    # Row 1 (y=2): Lung icon on left + "CO2" label at scale=1
    breath = 1.0 + 0.08 * math.sin(2 * math.pi * f / n)
    _draw_lung(d, 2, 2, color, scale=breath)

    _draw_text(d, 15, 4, "CO2", LABEL_COLOR)

    # Status label top-right (e.g. "GOOD", "POOR")
    label = _ppm_label(data.ppm)
    lw = _text_width(label)
    _draw_text(d, size - lw - 2, 4, label, color)

    # Row 2 (y=16): Big PPM number at scale=2, centered
    ppm_txt = f"{data.ppm:.0f}"
    w2 = _text_width(ppm_txt, scale=2)
    _draw_text(d, (size - w2) // 2, 16, ppm_txt, color, scale=2)

    # Row 3 (y=32): "ppm" label centered at scale=1
    pw = _text_width("ppm")
    _draw_text(d, (size - pw) // 2, 33, "ppm", LABEL_COLOR)

    # Row 4 (y=43): Horizontal bar gauge, full width with margin
    _draw_hbar(d, 2, 43, size - 4, 7, data.ppm)

    # Row 5 (y=53): Tick labels under the bar
    _draw_text(d, 2, 53, "0", DIM_GRAY)
    tw6 = _text_width("600")
    _draw_text(d, round(0.3 * (size - 4)) - tw6 // 2, 53, "600", DIM_GRAY)
    tw1k = _text_width("1K")
    _draw_text(d, round(0.5 * (size - 4)) - tw1k // 2, 53, "1K", DIM_GRAY)
    tw15 = _text_width("1.5K")
    _draw_text(d, round(0.75 * (size - 4)) - tw15 // 2, 53, "1.5K", DIM_GRAY)
    tw2 = _text_width("2K")
    _draw_text(d, size - tw2 - 3, 53, "2K", DIM_GRAY)

    # Haze particles when CO2 is high
    if data.ppm >= 1000:
        t = f / n
        for i in range(5):
            phase = t + i * 0.2
            px = round(size * (0.15 + 0.7 * ((phase * 1.3 + i * 0.37) % 1.0)))
            py = round(38 + 3 * math.sin(2 * math.pi * phase))
            if 0 <= px < size and 0 <= py < size:
                d.point((px, py), fill=(80, 65, 50))

    return img


def _layout_small(data: CO2Data, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    color = _ppm_color(data.ppm)

    _draw_text(d, 1, 1, "CO2", LABEL_COLOR)

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
