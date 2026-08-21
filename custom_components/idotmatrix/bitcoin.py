"""Animated Bitcoin price ticker for iDotMatrix LED matrix displays.

Renders a looping GIF of a spinning pixel-art Bitcoin coin with the
current USD price below it. The price is colored by the direction of the
last change (green up / red down), with an optional 24h-change row.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

BTC_ORANGE = (247, 147, 26)
BTC_DARK = (185, 100, 10)
BTC_LIGHT = (255, 200, 110)
UP_GREEN = (100, 220, 120)
DOWN_RED = (255, 90, 80)
FLAT_WHITE = (235, 235, 235)
LABEL = (170, 145, 105)


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


# Bitcoin "B" symbol, 11x14 bitmap
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


def _coin_face(size: int = 28) -> Image.Image:
    """Draw the face of the coin (RGBA, transparent outside the circle)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill=BTC_ORANGE + (255,))
    d.ellipse([0, 0, size - 1, size - 1], outline=BTC_DARK + (255,))
    # rim highlight, upper-left
    d.arc([1, 1, size - 2, size - 2], 150, 290, fill=BTC_LIGHT + (255,))
    sym_h = len(_BTC_SYMBOL)
    sym_w = len(_BTC_SYMBOL[0])
    ox = (size - sym_w) // 2
    oy = (size - sym_h) // 2
    for r, row in enumerate(_BTC_SYMBOL):
        for c, ch in enumerate(row):
            if ch == "X":
                d.point((ox + c, oy + r), fill=(255, 255, 255, 255))
    return img


def _paste_coin(canvas: Image.Image, cx: int, cy: int, size: int,
                t: float, face: Image.Image) -> None:
    """Paste the coin mid-spin: width follows cos(angle), back is mirrored."""
    # Ease the rotation so the coin dwells face-on and whips through edge-on
    te = t - 0.8 * math.sin(4 * math.pi * t) / (4 * math.pi)
    wf = math.cos(2 * math.pi * te)
    w = round(size * abs(wf))
    if w < 5:
        # Edge-on: narrow lens shape in rim colors
        w = max(3, w)
        edge = Image.new("RGBA", (w, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(edge)
        d.ellipse([0, 0, w - 1, size - 1], fill=BTC_DARK + (255,),
                  outline=BTC_ORANGE + (255,))
        canvas.paste(edge, (cx - w // 2, cy - size // 2), edge)
        return
    img = face.transpose(Image.FLIP_LEFT_RIGHT) if wf < 0 else face
    scaled = img.resize((w, size), Image.NEAREST)
    canvas.paste(scaled, (cx - w // 2, cy - size // 2), scaled)


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


def _layout_large(data: TickerData, size: int, t: float,
                  face: Image.Image) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    _paste_coin(img, size // 2, 15, 28, t, face)

    price_txt = _fit_price(data.price, size - 2)
    w = _text_width(price_txt)
    _draw_text(d, max(0, (size - w) // 2), 38, price_txt,
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
    _draw_text(d, max(0, (size - w) // 2), 51, txt, col)

    return img


def _layout_small(data: TickerData, size: int, t: float,
                  face: Image.Image) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    _paste_coin(img, size // 2, 8, 14, t, face)

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
                       duration: int = 120) -> bytes:
    """Render the Bitcoin ticker as animated GIF bytes."""
    n = 16
    face = _coin_face(28)
    frames = []
    for f in range(n):
        t = f / n
        if size >= 48:
            frames.append(_layout_large(data, size, t, face))
        else:
            frames.append(_layout_small(data, size, t, face))
    return frames_to_gif(frames, duration)
