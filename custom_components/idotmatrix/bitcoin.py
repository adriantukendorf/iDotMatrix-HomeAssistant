"""Bitcoin price ticker for iDotMatrix LED matrix displays.

Renders the classic Bitcoin logo (orange circle, tilted white B — bundled
as images/bitcoin_logo.png) with the current USD price below it. The
price is colored by the direction of the last change (green up / red
down), with an optional 24h-change row.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

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


def _layout_large(data: TickerData, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))

    logo = _logo(40)
    img.paste(logo, ((size - 40) // 2, 0), logo)

    d = ImageDraw.Draw(img)
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
                       duration: int = 1000) -> bytes:
    """Render the Bitcoin ticker as (static) animated GIF bytes.

    The display is static; two identical frames keep the file structurally
    an animation, matching the GIF shape the device is known to handle.
    """
    if size >= 48:
        frame = _layout_large(data, size)
    else:
        frame = _layout_small(data, size)
    return frames_to_gif([frame, frame.copy()], duration)
