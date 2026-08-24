"""CO2 gauge for iDotMatrix LED matrix displays.

Renders a vertical bar gauge with the current CO2 PPM reading. The bar
and text color shift from green (good) through yellow (moderate) to red
(poor) based on concentration thresholds. A lung icon and subtle
breathing animation give it life.

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
DIM_GRAY = (60, 60, 60)
LABEL_COLOR = (170, 170, 170)

_THRESHOLDS = (
    (600, GOOD_GREEN, "GOOD"),
    (800, (140, 210, 80), "OK"),
    (1000, OK_YELLOW, "FAIR"),
    (1200, WARN_ORANGE, "POOR"),
    (1500, BAD_RED, "BAD"),
    (9999, (200, 30, 30), "!!!!"),
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
    return "!!!!"


@dataclass
class CO2Data:
    ppm: float

    def signature(self) -> tuple:
        return (round(self.ppm),)


def _draw_lung(d: ImageDraw.ImageDraw, ox: int, oy: int,
               color: tuple, scale: float = 1.0) -> None:
    for r, row in enumerate(_LUNG_BITMAP):
        for c, ch in enumerate(row):
            if ch == "X":
                cx = ox + c
                cy = oy + r
                if scale != 1.0:
                    center_x = ox + len(row) / 2
                    center_y = oy + len(_LUNG_BITMAP) / 2
                    cx = round(center_x + (cx - center_x) * scale)
                    cy = round(center_y + (cy - center_y) * scale)
                if 0 <= cx < 64 and 0 <= cy < 64:
                    d.point((cx, cy), fill=color)


def _draw_bar(d: ImageDraw.ImageDraw, x: int, y: int,
              w: int, h: int, ppm: float) -> None:
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=DIM_GRAY)

    fill_frac = min(1.0, max(0.0, ppm / 2000))
    fill_h = max(0, round(fill_frac * (h - 2)))

    for row in range(fill_h):
        yy = y + h - 2 - row
        row_frac = row / max(1, h - 2)
        if row_frac < 0.3:
            c = GOOD_GREEN
        elif row_frac < 0.5:
            c = OK_YELLOW
        elif row_frac < 0.75:
            c = WARN_ORANGE
        else:
            c = BAD_RED
        d.line([(x + 1, yy), (x + w - 2, yy)], fill=c)

    for tick_ppm in (600, 1000, 1500):
        tick_frac = tick_ppm / 2000
        tick_y = y + h - 2 - round(tick_frac * (h - 2))
        if y < tick_y < y + h - 1:
            d.point((x, tick_y), fill=LABEL_COLOR)
            d.point((x + w - 1, tick_y), fill=LABEL_COLOR)


def _layout_large(data: CO2Data, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    color = _ppm_color(data.ppm)

    # Breathing animation: subtle lung scale pulse
    breath = 1.0 + 0.06 * math.sin(2 * math.pi * f / n)
    _draw_lung(d, 3, 2, color, scale=breath)

    # "CO2" label
    _draw_text(d, 17, 2, "CO2", LABEL_COLOR)

    # PPM reading
    ppm_txt = f"{data.ppm:.0f}"
    w = _text_width(ppm_txt)
    _draw_text(d, max(17, (size + 17 - w) // 2), 12, ppm_txt, color)

    # "ppm" unit
    _draw_text(d, max(17, (size + 17 - _text_width("ppm")) // 2), 22, "ppm",
               LABEL_COLOR)

    # Status label
    label = _ppm_label(data.ppm)
    lw = _text_width(label)
    _draw_text(d, max(17, (size + 17 - lw) // 2), 32, label, color)

    # Vertical bar gauge on the right side
    _draw_bar(d, size - 10, 2, 8, size - 4, data.ppm)

    # Particle effects when CO2 is high
    if data.ppm >= 1000:
        t = f / n
        for i in range(3):
            px = 20 + round(20 * math.sin(2 * math.pi * (t + i * 0.33)))
            py = 44 + round(8 * math.cos(2 * math.pi * (t + i * 0.25)))
            if 0 <= px < size and 0 <= py < size:
                d.point((px, py), fill=(100, 80, 60))

    return img


def _layout_small(data: CO2Data, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    color = _ppm_color(data.ppm)

    _draw_text(d, 1, 2, "CO2", LABEL_COLOR)

    ppm_txt = f"{data.ppm:.0f}"
    w = _text_width(ppm_txt)
    _draw_text(d, (size - w) // 2, 12, ppm_txt, color)

    label = _ppm_label(data.ppm)
    lw = _text_width(label)
    _draw_text(d, (size - lw) // 2, 22, label, color)

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
