"""Bitcoin price ticker for iDotMatrix LED matrix displays.

Renders the classic Bitcoin logo (orange circle, tilted white B — bundled
as images/bitcoin_logo.png) with the current USD price below it. The
price is colored by the direction of the last change (green up / red
down), with an optional 24h-change row.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

BTC_ORANGE = (247, 147, 26)
UP_GREEN = (100, 220, 120)
DOWN_RED = (255, 90, 80)
FLAT_WHITE = (235, 235, 235)
LABEL = (170, 145, 105)

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "images",
                          "bitcoin_logo.png")

# Fallback if the bundled logo asset is missing: 11x14 Bitcoin "B" bitmap
_BTC_SYMBOL = (
    "..X..X.....",
    "..X..X.....",
    ".XXXXXXX...",
    ".XX....XX..",
    ".XX.....XX.",
    ".XX....XX..",
    ".XXXXXXX...",
    ".XX....XX..",
    ".XX.....XX.",
    ".XX.....XX.",
    ".XX....XX..",
    ".XXXXXXX...",
    "..X..X.....",
    "..X..X.....",
)


def _fallback_logo(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill=BTC_ORANGE + (255,))
    ox = (size - len(_BTC_SYMBOL[0])) // 2
    oy = (size - len(_BTC_SYMBOL)) // 2
    for r, row in enumerate(_BTC_SYMBOL):
        for c, ch in enumerate(row):
            if ch == "X":
                d.point((ox + c, oy + r), fill=(255, 255, 255, 255))
    return img


@lru_cache(maxsize=4)
def _logo(size: int) -> Image.Image:
    """The classic Bitcoin logo at the given pixel size (RGBA)."""
    try:
        master = Image.open(_LOGO_PATH).convert("RGBA")
        return master.resize((size, size), Image.LANCZOS)
    except Exception:
        return _fallback_logo(size)


@dataclass
class TickerData:
    """Snapshot of the ticker values shown on the display."""

    price: float
    direction: int = 0  # +1 last change up, -1 down, 0 flat/unknown
    change_pct: float | None = None

    def signature(self) -> tuple:
        return (
            round(self.price),
            self.direction,
            None if self.change_pct is None else round(self.change_pct, 1),
        )


def _price_color(direction: int) -> tuple:
    if direction > 0:
        return UP_GREEN
    if direction < 0:
        return DOWN_RED
    return FLAT_WHITE


def _fit_price(price: float, max_width: int) -> str:
    """Format the price to fit, degrading gracefully."""
    for txt in (
        f"${price:,.0f}",
        f"{price:,.0f}",
        f"{price / 1000:.1f}K",
        f"{price / 1000:.0f}K",
    ):
        if _text_width(txt) <= max_width:
            return txt
    return f"{price / 1_000_000:.1f}M"


# Sparkle glints on the coin: (x, y, start frame). Each lasts 3 frames,
# so most of the loop nothing is flashing.
_SPARKLES = ((20, 6, 4), (46, 28, 14))

# Ember particles drifting up behind the coin: (x, phase offset)
_EMBERS = ((5, 0.0), (58, 0.17), (13, 0.36), (51, 0.55), (31, 0.74), (61, 0.9))
_EMBER_COLORS = ((95, 62, 18), (70, 45, 14))


def _draw_sparkle(d: ImageDraw.ImageDraw, x: int, y: int, phase: int) -> None:
    """A small four-pointed glint: appear, flash, fade."""
    if phase == 1:  # peak: bright 5px cross with dim tips
        d.point((x, y), fill=(255, 255, 255))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d.point((x + dx, y + dy), fill=(255, 245, 200))
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            d.point((x + dx, y + dy), fill=(210, 170, 90))
    else:  # appear / fade: single warm pixel
        d.point((x, y), fill=(255, 230, 160) if phase == 0 else (200, 165, 90))


def _draw_embers(d: ImageDraw.ImageDraw, size: int, t: float) -> None:
    """Dim warm particles rising slowly in the background."""
    for i, (x, ph) in enumerate(_EMBERS):
        rise = (ph + t) % 1.0
        yy = round((1.0 - rise) * (size - 1))
        xx = x + round(math.sin(2 * math.pi * (t + ph)))
        d.point((xx, yy), fill=_EMBER_COLORS[i % 2])


def _layout_large(data: TickerData, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background embers first, so the coin and text draw over them
    _draw_embers(d, size, f / n)

    logo = _logo(40)
    img.paste(logo, ((size - 40) // 2, 0), logo)

    d = ImageDraw.Draw(img)
    for sx, sy, start in _SPARKLES:
        phase = f - start
        if 0 <= phase <= 2:
            _draw_sparkle(d, sx, sy, phase)
    price_txt = _fit_price(data.price, size - 2)
    w = _text_width(price_txt)
    _draw_text(d, max(0, (size - w) // 2), 43, price_txt,
               _price_color(data.direction))

    if data.change_pct is not None:
        if data.change_pct > 0:
            txt, col = f"↑{abs(data.change_pct):.1f}%", UP_GREEN
        elif data.change_pct < 0:
            txt, col = f"↓{abs(data.change_pct):.1f}%", DOWN_RED
        else:
            txt, col = "-0.0%", FLAT_WHITE
    else:
        txt, col = "BTC/USD", LABEL
    w = _text_width(txt)
    _draw_text(d, max(0, (size - w) // 2), 54, txt, col)

    return img


def _layout_small(data: TickerData, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))

    logo = _logo(15)
    img.paste(logo, ((size - 15) // 2, 0), logo)

    d = ImageDraw.Draw(img)
    price_txt = _fit_price(data.price, size - 2)
    w = _text_width(price_txt)
    _draw_text(d, max(0, (size - w) // 2), 17, price_txt,
               _price_color(data.direction))

    if data.change_pct is not None:
        arrow = "↑" if data.change_pct > 0 else "↓"
        col = UP_GREEN if data.change_pct > 0 else DOWN_RED
        txt = f"{arrow}{abs(data.change_pct):.1f}%"
        w = _text_width(txt)
        _draw_text(d, max(0, (size - w) // 2), 25, txt, col)

    return img


def render_bitcoin_gif(data: TickerData, size: int = 64,
                       duration: int = 160) -> bytes:
    """Render the Bitcoin ticker as animated GIF bytes.

    The logo and price are static; subtle background embers drift upward
    and occasional sparkle glints flash on the coin.
    """
    if size >= 48:
        n = 20
        frames = [_layout_large(data, size, f, n) for f in range(n)]
    else:
        # Compact layout stays static; two identical frames keep the file
        # structurally an animation, the GIF shape the device handles.
        frame = _layout_small(data, size)
        frames = [frame, frame.copy()]
        duration = 1000
    return frames_to_gif(frames, duration)
