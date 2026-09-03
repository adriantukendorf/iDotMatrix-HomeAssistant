"""One-shot messages for iDotMatrix LED matrix displays.

Any automation can push a line of text to the panel with
``idotmatrix.show_message``. Five visual styles are available:

* ``card``       - calm notification: icon on top, word-wrapped text
                   below, long text paged every few seconds.
* ``alert``      - the card with a pulsing border and blinking icon.
* ``marquee``    - classic ticker: icon pinned left, text scrolls by.
* ``party``      - homage to the original "Fun Text": one word at a
                   time, each in a random color, confetti everywhere.
* ``typewriter`` - text appears a character at a time behind a
                   blinking block cursor, phosphor green by default.

Two fonts: the house 5x7 pixel font (``pixel``) or Press Start 2P
(``arcade``), the 8x8 arcade font shipped in the fonts folder, rendered
without antialiasing so it stays crisp on the LEDs.

Every style renders to a GIF through the same device-safe encoder as the
other display modes.
"""
from __future__ import annotations

import colorsys
import math
import os
import random
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .power import _BOLT_ICON
from .thermostat import (COOL_BLUE, COOL_CORE, HEAT_CORE, HEAT_ORANGE,
                         _FLAME_FRAMES, _SNOW_ICON)
from .weather import _draw_text, _text_width, frames_to_gif

STYLES = ("card", "alert", "marquee", "party", "typewriter")
FONTS = ("pixel", "arcade")

WHITE = (235, 235, 235)
PHOSPHOR = (120, 255, 120)
DIM = (60, 60, 70)

_ARCADE_PATH = os.path.join(os.path.dirname(__file__), "fonts",
                            "PressStart2P.ttf")

# Fun Text palette, kept verbatim as a nod to the original
PARTY_PALETTE = (
    (255, 0, 0), (0, 255, 0), (0, 120, 255), (160, 0, 255),
    (255, 255, 255), (255, 120, 0), (255, 0, 170), (0, 255, 220),
)

# ---------------------------------------------------------------------------
# Icons: 8x8, "X" = primary color, "o" = secondary, drawn at 2x on 64px
# ---------------------------------------------------------------------------

ICONS = {
    "info": (((60, 140, 255), (255, 255, 255)), (
        ".XXXXXX.", "XXXooXXX", "XXXXXXXX", "XXXooXXX",
        "XXXooXXX", "XXXooXXX", "XXXooXXX", ".XXXXXX.")),
    "alert": (((255, 200, 40), (30, 30, 30)), (
        "...XX...", "...XX...", "..XooX..", "..XooX..",
        ".XXooXX.", ".XXXXXX.", "XXXooXXX", "XXXXXXXX")),
    "check": (((80, 220, 80), (80, 220, 80)), (
        "........", "......XX", ".....XX.", "....XX..",
        "XX.XX...", ".XXX....", "..X.....", "........")),
    "cross": (((240, 60, 50), (240, 60, 50)), (
        "XX....XX", ".XX..XX.", "..XXXX..", "...XX...",
        "..XXXX..", ".XX..XX.", "XX....XX", "........")),
    "bell": (((255, 200, 60), (200, 120, 40)), (
        "...XX...", "..XXXX..", ".XXXXXX.", ".XXXXXX.",
        ".XXXXXX.", "XXXXXXXX", "........", "...oo...")),
    "heart": (((255, 70, 90), (255, 70, 90)), (
        ".XX..XX.", "XXXXXXXX", "XXXXXXXX", "XXXXXXXX",
        ".XXXXXX.", "..XXXX..", "...XX...", "........")),
    "star": (((255, 215, 60), (255, 215, 60)), (
        "...XX...", "...XX...", "XXXXXXXX", ".XXXXXX.",
        "..XXXX..", ".XX..XX.", "XX....XX", "........")),
    "mail": (((230, 230, 230), (150, 150, 160)), (
        "XXXXXXXX", "Xo....oX", "X.o..o.X", "X..oo..X",
        "X.o..o.X", "Xo....oX", "XXXXXXXX", "........")),
    "door": (((160, 100, 50), (255, 215, 60)), (
        ".XXXXXX.", ".XXXXXX.", ".XXXXXX.", ".XXXXoX.",
        ".XXXXoX.", ".XXXXXX.", ".XXXXXX.", ".XXXXXX.")),
    "package": (((200, 150, 90), (120, 80, 40)), (
        "XXXoXXXX", "XXXoXXXX", "oooooooo", "XXXoXXXX",
        "XXXoXXXX", "XXXoXXXX", "XXXoXXXX", "XXXXXXXX")),
    "drop": (((80, 160, 255), (80, 160, 255)), (
        "...X....", "...X....", "..XXX...", ".XXXXX..",
        ".XXXXX..", "XXXXXXX.", "XXXXXXX.", ".XXXXX..")),
    "flame": ((HEAT_ORANGE, HEAT_CORE), _FLAME_FRAMES[0]),
    "snowflake": ((COOL_BLUE, COOL_CORE), _SNOW_ICON),
    "sun": (((255, 215, 60), (255, 140, 40)), (
        "X..XX..X", ".X.XX.X.", "..XXXX..", "XXXooXXX",
        "XXXooXXX", "..XXXX..", ".X.XX.X.", "X..XX..X")),
    "moon": (((220, 225, 240), (220, 225, 240)), (
        "...XXXX.", "..XX....", ".XX.....", ".XX.....",
        ".XX.....", ".XX.....", "..XX....", "...XXXX.")),
    "bolt": (((255, 220, 60), (255, 220, 60)), _BOLT_ICON),
    "dog": (((170, 110, 60), (30, 30, 30)), (
        "XX....XX", "XXXXXXXX", "XoXXXXoX", "XXXXXXXX",
        "XXXooXXX", ".XXooXX.", "..XXXX..", "........")),
    "car": (((230, 60, 60), (40, 40, 50)), (
        "........", "..XXXX..", ".XooooX.", "XXXXXXXX",
        "XXXXXXXX", "XoXXXXoX", ".o....o.", "........")),
    "timer": (((230, 230, 230), (255, 200, 60)), (
        "XXXXXXXX", ".XooooX.", "..XooX..", "...XX...",
        "...XX...", "..X..X..", ".XooooX.", "XXXXXXXX")),
    "phone": (((80, 220, 120), (80, 220, 120)), (
        ".XX..XX.", "XXXXXXXX", "XXXXXXXX", "XX.XX.XX",
        "XX....XX", "XX....XX", "........", "........")),
    "home": (((230, 230, 230), (255, 200, 80)), (
        "...XX...", "..XXXX..", ".XXXXXX.", "XXXXXXXX",
        ".XXXXXX.", ".XXooXX.", ".XXooXX.", ".XXooXX.")),
    "gift": (((230, 60, 60), (255, 215, 60)), (
        ".oo..oo.", "XXXooXXX", "oooooooo", "XXXooXXX",
        "XXXooXXX", "XXXooXXX", "XXXooXXX", "........")),
    "coffee": (((180, 120, 60), (200, 200, 210)), (
        "..o.o...", ".o.o....", "........", "XXXXXX..",
        "XXXXXXX.", "XXXXXXX.", "XXXXXX..", ".XXXX...")),
    "music": (((230, 90, 230), (230, 90, 230)), (
        "...XXXXX", "...XXXXX", "...X...X", "...X...X",
        ".XXX.XXX", "XXXX.XXX", ".XX...X.", "........")),
}


def icon_names() -> list:
    return sorted(ICONS)


def draw_icon(d: ImageDraw.ImageDraw, name: str, ox: int, oy: int,
              scale: int = 2, colors: tuple | None = None) -> None:
    spec = ICONS.get(name)
    if not spec:
        return
    (primary, secondary), rows = spec
    if colors:
        primary, secondary = colors
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            color = primary if ch == "X" else secondary
            x, y = ox + c * scale, oy + r * scale
            if scale == 1:
                d.point((x, y), fill=color)
            else:
                d.rectangle([x, y, x + scale - 1, y + scale - 1], fill=color)


def icon_color(name: str | None) -> tuple | None:
    spec = ICONS.get(name or "")
    return spec[0][0] if spec else None


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def _arcade_font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_ARCADE_PATH, px)


class _Font:
    """Uniform interface over the 5x7 pixel font and Press Start 2P."""

    def __init__(self, kind: str):
        self.kind = "arcade" if kind == "arcade" else "pixel"

    def height(self, scale: int) -> int:
        return (8 if self.kind == "arcade" else 7) * scale

    def gap(self, scale: int) -> int:
        return scale + (1 if self.kind == "arcade" else 0)

    def width(self, text: str, scale: int) -> int:
        if self.kind == "arcade":
            return 8 * scale * len(text)
        return _text_width(text, scale)

    def draw(self, img: Image.Image, x: int, y: int, text: str,
             color, scale: int) -> None:
        """Draw text. ``color`` is an RGB tuple or a callable(index)."""
        if not text:
            return
        d = ImageDraw.Draw(img)
        if self.kind == "pixel":
            if callable(color):
                for i, ch in enumerate(text):
                    _draw_text(d, x, y, ch, color(i), scale)
                    x += (_text_width(ch, scale) + scale)
            else:
                _draw_text(d, x, y, text, color, scale)
            return

        font = _arcade_font(8 * scale)
        cw = 8 * scale
        for i, ch in enumerate(text):
            if ch == " ":
                continue
            c = color(i) if callable(color) else color
            mask = Image.new("L", (cw, cw), 0)
            ImageDraw.Draw(mask).text((0, 0), ch, font=font, fill=255)
            mask = mask.point(lambda v: 255 if v > 128 else 0)
            img.paste(Image.new("RGB", (cw, cw), c), (x + i * cw, y), mask)


def _wrap(font: _Font, text: str, max_w: int, scale: int) -> list:
    """Greedy word wrap honouring explicit newlines."""
    lines = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for word in words:
            # Break words that are wider than the line on their own
            while font.width(word, scale) > max_w:
                room = max(1, len(word) - 1)
                while room > 1 and font.width(word[:room], scale) > max_w:
                    room -= 1
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(word[:room])
                word = word[room:]
            trial = f"{cur} {word}" if cur else word
            if font.width(trial, scale) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _rainbow(f: int, n: int, per_char: float = 0.07):
    def color(i: int) -> tuple:
        h = (i * per_char + f / max(1, n)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.85, 1.0)
        return (round(r * 255), round(g * 255), round(b * 255))
    return color


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

@dataclass
class MessageSpec:
    text: str
    style: str = "card"
    icon: str | None = None
    color: tuple | None = None      # None = style default
    rainbow: bool = False
    font: str = "pixel"

    def text_color(self, f: int = 0, n: int = 1):
        if self.rainbow:
            return _rainbow(f, n)
        if self.color:
            return tuple(self.color)
        return PHOSPHOR if self.style == "typewriter" else WHITE

    def accent(self) -> tuple:
        return icon_color(self.icon) or (self.color and tuple(self.color)) \
            or (240, 60, 50)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

@dataclass
class _Block:
    scale: int
    pages: list                      # list of list-of-lines
    line_h: int
    gap: int


def _fit_text(font: _Font, text: str, max_w: int, area_h: int,
              scales=(2, 1)) -> _Block:
    """Pick the biggest scale whose wrapped text fits; else paginate."""
    for scale in scales:
        lines = _wrap(font, text, max_w, scale)
        lh, gap = font.height(scale), font.gap(scale)
        if len(lines) * lh + (len(lines) - 1) * gap <= area_h:
            return _Block(scale, [lines], lh, gap)
    scale = scales[-1]
    lines = _wrap(font, text, max_w, scale)
    lh, gap = font.height(scale), font.gap(scale)
    per_page = max(1, (area_h + gap) // (lh + gap))
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)]
    return _Block(scale, pages, lh, gap)


def _draw_lines(img: Image.Image, font: _Font, lines: list, block: _Block,
                x0: int, width: int, y0: int, area_h: int, color,
                reveal: int | None = None) -> tuple:
    """Draw centred lines; returns (x, y) just after the last drawn char."""
    total = len(lines) * block.line_h + (len(lines) - 1) * block.gap
    y = y0 + max(0, (area_h - total) // 2)
    shown = 0
    end = (x0, y)
    for line in lines:
        x = x0 + (width - font.width(line, block.scale)) // 2
        if reveal is None:
            font.draw(img, x, y, line, color, block.scale)
            end = (x + font.width(line, block.scale), y)
        else:
            take = max(0, min(len(line), reveal - shown))
            part = line[:take]
            font.draw(img, x, y, part, color, block.scale)
            end = (x + font.width(part, block.scale) +
                   (block.scale if part else 0), y)
            shown += len(line) + 1     # +1 for the implicit newline
            if shown > reveal:
                break
        y += block.line_h + block.gap
    return end


def _icon_area(spec: MessageSpec, size: int, inset: int) -> tuple:
    """Return (icon_y, text_y0, text_h) for a top-icon layout."""
    if spec.icon and spec.icon in ICONS:
        icon_y = inset
        text_y0 = inset + 16 + 3
    else:
        icon_y = None
        text_y0 = inset
    return icon_y, text_y0, size - inset - text_y0


# ---------------------------------------------------------------------------
# Styles (each returns (frames, tick_ms))
# ---------------------------------------------------------------------------

def _style_card(spec: MessageSpec, size: int, font: _Font,
                bordered: bool = False) -> tuple:
    inset = 4 if bordered else 2
    icon_y, ty, th = _icon_area(spec, size, inset)
    block = _fit_text(font, spec.text, size - 2 * inset, th)
    animated = spec.rainbow or bordered
    n = 8 if animated else 1
    per_page = 12 if len(block.pages) > 1 else 1   # ~3 s per page at 250 ms
    tick = 250
    frames = []
    for page in block.pages:
        for k in range(per_page if not animated else max(per_page, n)):
            f = k % n
            img = Image.new("RGB", (size, size), (0, 0, 0))
            d = ImageDraw.Draw(img)
            if bordered:
                accent = spec.accent()
                bright = f < n // 2
                c = accent if bright else tuple(v // 3 for v in accent)
                d.rectangle([0, 0, size - 1, size - 1], outline=c)
                d.rectangle([1, 1, size - 2, size - 2], outline=c)
            if icon_y is not None and not (bordered and f >= n - 2):
                draw_icon(d, spec.icon, (size - 16) // 2, icon_y, 2)
            _draw_lines(img, font, page, block, inset, size - 2 * inset,
                        ty, th, spec.text_color(f, n))
            if len(block.pages) > 1:
                # page dots along the bottom edge
                pi = block.pages.index(page)
                total = len(block.pages)
                x = (size - (total * 3 - 1)) // 2
                for j in range(total):
                    d.point((x + j * 3, size - 1),
                            fill=WHITE if j == pi else DIM)
            frames.append(img)
    if len(frames) == 1:
        frames.append(frames[0].copy())
        tick = 1000
    return frames, tick


def _style_marquee(spec: MessageSpec, size: int, font: _Font) -> tuple:
    text = " ".join(spec.text.split())
    has_icon = bool(spec.icon and spec.icon in ICONS)
    left = 22 if has_icon else 2
    region_w = size - left - 2
    scale = 2 if font.width(text, 2) <= 480 else 1
    lh = font.height(scale)
    tw = font.width(text, scale)
    step = 3 if scale == 2 else 2
    n = math.ceil((region_w + tw) / step) + 1
    y = (size - lh) // 2
    frames = []
    for f in range(n):
        img = Image.new("RGB", (size, size), (0, 0, 0))
        x = left + region_w - f * step
        # Draw into a strip and paste so the text clips at the region edge
        strip = Image.new("RGB", (region_w, lh), (0, 0, 0))
        font.draw(strip, x - left, 0, text, spec.text_color(f, n), scale)
        img.paste(strip, (left, y))
        d = ImageDraw.Draw(img)
        if has_icon:
            draw_icon(d, spec.icon, 2, (size - 16) // 2, 2)
            d.line([(20, 8), (20, size - 9)], fill=DIM)
        frames.append(img)
    return frames, 100


def _style_party(spec: MessageSpec, size: int, font: _Font) -> tuple:
    words = spec.text.split() or ["!"]
    rng = random.Random(len(spec.text) * 7 + sum(map(ord, spec.text)))
    scales = (3, 2, 1) if font.kind == "pixel" else (2, 1)
    frames = []
    reps = 2   # two confetti variations per word -> 450 ms per word

    def confetti(d):
        for _ in range(28):
            x, y = rng.randrange(size), rng.randrange(size)
            d.point((x, y), fill=rng.choice(PARTY_PALETTE))

    if spec.icon and spec.icon in ICONS:
        for _ in range(reps):
            img = Image.new("RGB", (size, size), (0, 0, 0))
            d = ImageDraw.Draw(img)
            confetti(d)
            draw_icon(d, spec.icon, (size - 24) // 2, (size - 24) // 2, 3)
            frames.append(img)

    for i, word in enumerate(words):
        color = (spec.color and tuple(spec.color)) or \
            PARTY_PALETTE[rng.randrange(len(PARTY_PALETTE))]
        scale = next((s for s in scales
                      if font.width(word, s) <= size - 4), scales[-1])
        if font.width(word, scale) > size - 4:
            word = _wrap(font, word, size - 4, scale)[0]
        for _ in range(reps):
            img = Image.new("RGB", (size, size), (0, 0, 0))
            d = ImageDraw.Draw(img)
            confetti(d)
            x = (size - font.width(word, scale)) // 2
            y = (size - font.height(scale)) // 2
            col = _rainbow(i, len(words), 0.12) if spec.rainbow else color
            font.draw(img, x, y, word, col, scale)
            frames.append(img)
    return frames, 225


def _style_typewriter(spec: MessageSpec, size: int, font: _Font) -> tuple:
    inset = 2
    icon_y, ty, th = _icon_area(spec, size, inset)
    block = _fit_text(font, spec.text, size - 2 * inset, th)
    if len(block.pages) > 1:
        return _style_card(spec, size, font)
    lines = block.pages[0]
    total_chars = sum(len(l) for l in lines) + max(0, len(lines) - 1)
    hold = 16
    n = total_chars + hold + 1
    color = spec.text_color()
    frames = []
    for f in range(n):
        reveal = min(total_chars, f)
        img = Image.new("RGB", (size, size), (0, 0, 0))
        d = ImageDraw.Draw(img)
        if icon_y is not None:
            draw_icon(d, spec.icon, (size - 16) // 2, icon_y, 2)
        cx, cy = _draw_lines(img, font, lines, block, inset,
                             size - 2 * inset, ty, th,
                             spec.text_color(f, n) if spec.rainbow else color,
                             reveal=reveal)
        if (f // 3) % 2 == 0:
            cw = max(3, (5 if font.kind == "pixel" else 7) * block.scale)
            cur = color(0) if callable(color) else color
            if cx + cw < size:
                d.rectangle([cx, cy, cx + cw - 1, cy + block.line_h - 1],
                            fill=cur)
        frames.append(img)
    return frames, 120


def _style_small(spec: MessageSpec, size: int, font: _Font) -> tuple:
    """Compact card for 32x32: 8x8 icon on top, scale-1 text."""
    inset = 1
    has_icon = bool(spec.icon and spec.icon in ICONS)
    ty = inset + (10 if has_icon else 0)
    th = size - inset - ty
    block = _fit_text(font, spec.text, size - 2 * inset, th, scales=(1,))
    frames = []
    for page in block.pages:
        img = Image.new("RGB", (size, size), (0, 0, 0))
        d = ImageDraw.Draw(img)
        if has_icon:
            draw_icon(d, spec.icon, (size - 8) // 2, inset, 1)
        _draw_lines(img, font, page, block, inset, size - 2 * inset, ty, th,
                    spec.text_color())
        for _ in range(12 if len(block.pages) > 1 else 1):
            frames.append(img)
    if len(frames) == 1:
        frames.append(frames[0].copy())
        return frames, 1000
    return frames, 250


def render_message_gif(spec: MessageSpec, size: int = 64) -> bytes:
    font = _Font(spec.font)
    if size < 48:
        if spec.style == "marquee":
            frames, tick = _style_marquee(spec, size, font)
        else:
            frames, tick = _style_small(spec, size, font)
    elif spec.style == "alert":
        frames, tick = _style_card(spec, size, font, bordered=True)
    elif spec.style == "marquee":
        frames, tick = _style_marquee(spec, size, font)
    elif spec.style == "party":
        frames, tick = _style_party(spec, size, font)
    elif spec.style == "typewriter":
        frames, tick = _style_typewriter(spec, size, font)
    else:
        frames, tick = _style_card(spec, size, font)
    return frames_to_gif(frames, tick)
