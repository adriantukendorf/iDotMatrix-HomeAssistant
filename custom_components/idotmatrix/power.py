"""Power usage gauge for iDotMatrix LED matrix displays.

Renders the whole-house active power draw as a large watts reading with a
horizontal color-coded bar gauge scaled 0-5000 W. Colors shift
green -> yellow -> orange -> red as load climbs from baseline (~500-1200 W)
through large appliances (~2 kW), furnace (~3-3.5 kW) and AC (~4-4.5 kW).
A lightning bolt icon in the corner changes color with the load level, and
a bright spark travels along the filled bar to suggest current flow.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

GOOD_GREEN = (80, 200, 80)
NORM_GREEN = (140, 210, 80)
OK_YELLOW = (220, 200, 40)
WARN_ORANGE = (240, 150, 30)
BAD_RED = (240, 60, 50)
MAX_RED = (200, 30, 30)
DIM_GRAY = (50, 50, 50)
LABEL_COLOR = (140, 140, 150)

MAX_WATTS = 5000

_THRESHOLDS = (
    (500, GOOD_GREEN, "LOW"),
    (1300, NORM_GREEN, "NORM"),
    (2500, OK_YELLOW, "MED"),
    (3800, WARN_ORANGE, "HIGH"),
    (5000, BAD_RED, "PEAK"),
    (999999, MAX_RED, "MAX"),
)

# Lightning bolt icon (8x8) from LaMetric icon set (#95)
_BOLT_ICON = (
    "....XXX.",
    "...XXX..",
    "..XXX...",
    ".XXX....",
    "...XXX..",
    "...XX...",
    "..XX....",
    "..X.....",
)


def _watts_color(watts: float) -> tuple:
    for threshold, color, _ in _THRESHOLDS:
        if watts < threshold:
            return color
    return MAX_RED


def _watts_label(watts: float) -> str:
    for threshold, _, label in _THRESHOLDS:
        if watts < threshold:
            return label
    return "MAX"


@dataclass
class PowerData:
    watts: float

    def signature(self) -> tuple:
        # Round to 25 W so sensor jitter doesn't trigger BLE re-uploads
        return (round(self.watts / 25),)


def _draw_icon(d: ImageDraw.ImageDraw, ox: int, oy: int,
               color: tuple) -> None:
    for r, row in enumerate(_BOLT_ICON):
        for c, ch in enumerate(row):
            if ch == "X":
                d.point((ox + c, oy + r), fill=color)


def _draw_hbar(d: ImageDraw.ImageDraw, x: int, y: int,
               w: int, h: int, watts: float,
               f: int = 0, n: int = 1) -> None:
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=DIM_GRAY)

    fill_frac = min(1.0, max(0.0, watts / MAX_WATTS))
    fill_w = max(0, round(fill_frac * (w - 2)))

    for col in range(fill_w):
        xx = x + 1 + col
        col_frac = col / max(1, w - 2)
        if col_frac < 0.26:
            c = GOOD_GREEN
        elif col_frac < 0.5:
            c = OK_YELLOW
        elif col_frac < 0.76:
            c = WARN_ORANGE
        else:
            c = BAD_RED
        d.line([(xx, y + 1), (xx, y + h - 2)], fill=c)

    # Spark traveling along the filled portion (current flow)
    if fill_w > 3 and n > 1:
        spark = round((f / n) * (fill_w - 1))
        sx = x + 1 + spark
        d.line([(sx, y + 1), (sx, y + h - 2)], fill=(255, 255, 255))

    needle_x = x + 1 + round(fill_frac * (w - 2))
    if x < needle_x < x + w - 1:
        d.line([(needle_x, y - 1), (needle_x, y + h)], fill=(255, 255, 255))


def _layout_large(data: PowerData, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    color = _watts_color(data.watts)

    # Row 1 (y=2): lightning bolt icon on left + status label right
    _draw_icon(d, 2, 2, color)

    label = _watts_label(data.watts)
    lw = _text_width(label)
    _draw_text(d, size - lw - 2, 3, label, color)

    # Row 2 (y=19): Big watts number at scale=2, centered
    watts_txt = f"{data.watts:.0f}"
    w2 = _text_width(watts_txt, scale=2)
    _draw_text(d, (size - w2) // 2, 19, watts_txt, color, scale=2)

    # Row 3 (y=36): "WATTS" label centered at scale=1
    pw = _text_width("WATTS")
    _draw_text(d, (size - pw) // 2, 36, "WATTS", LABEL_COLOR)

    # Row 4 (y=50): Horizontal bar gauge, full width with margin
    _draw_hbar(d, 2, 50, size - 4, 7, data.watts, f, n)

    return img


def _layout_small(data: PowerData, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    color = _watts_color(data.watts)

    _draw_icon(d, 1, 1, color)

    watts_txt = f"{data.watts:.0f}"
    scale = 2 if _text_width(watts_txt, scale=2) <= size - 2 else 1
    w = _text_width(watts_txt, scale=scale)
    _draw_text(d, (size - w) // 2, 10, watts_txt, color, scale=scale)

    label = _watts_label(data.watts)
    lw = _text_width(label)
    _draw_text(d, (size - lw) // 2, 24, label, color)

    return img


def render_power_gif(data: PowerData, size: int = 64,
                     duration: int = 200) -> bytes:
    if size >= 48:
        n = 16
        frames = [_layout_large(data, size, f, n) for f in range(n)]
    else:
        frame = _layout_small(data, size)
        frames = [frame, frame.copy()]
        duration = 1000
    return frames_to_gif(frames, duration)
