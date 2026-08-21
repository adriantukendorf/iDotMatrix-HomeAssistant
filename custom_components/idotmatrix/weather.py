"""Animated weather dashboard renderer for iDotMatrix LED matrix displays.

Renders a looping animated GIF sized for the device (64x64 primary, 32x32
compact fallback) from Home Assistant weather entity data. Icons are
hand-drawn pixel art animated per condition (rotating sun rays, falling
rain, lightning flashes, drifting clouds, twinkling stars, ...).

The GIF is encoded with a single shared global palette and no local color
tables, matching the format the device parser is known to handle reliably.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw


@dataclass
class WeatherData:
    """Snapshot of the weather values shown on the display."""

    condition: str
    temperature: float | None = None
    temp_unit: str = "°C"
    humidity: float | None = None
    wind_speed: float | None = None
    high: float | None = None
    low: float | None = None

    def signature(self) -> tuple:
        """Values that affect the rendered output (for change detection)."""

        def r(v):
            return None if v is None else round(v)

        return (
            self.condition,
            r(self.temperature),
            r(self.high),
            r(self.low),
            r(self.humidity),
            r(self.wind_speed),
        )


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

PAL = {
    "sun_core": (255, 205, 0),
    "sun_hi": (255, 240, 130),
    "sun_ray": (255, 160, 0),
    "cloud_lt": (205, 210, 222),
    "cloud_md": (145, 152, 170),
    "cloud_dk": (90, 97, 118),
    "rain": (70, 155, 255),
    "snow": (240, 246, 255),
    "bolt": (255, 232, 70),
    "bolt_dim": (150, 130, 40),
    "moon": (225, 225, 185),
    "star": (255, 255, 255),
    "star_dim": (110, 110, 145),
    "fog": (150, 156, 168),
    "wind": (160, 225, 205),
    "wind_dim": (85, 125, 115),
    "hail": (215, 232, 250),
    "alert": (255, 200, 0),
    "hi": (255, 120, 80),
    "lo": (100, 160, 255),
    "humid": (90, 185, 255),
    "label_dim": (150, 155, 165),
}

# Condition -> (label, label color) for the text row
CONDITION_LABELS = {
    "sunny": ("SUNNY", (255, 200, 0)),
    "clear-night": ("CLEAR", (200, 200, 255)),
    "partlycloudy": ("PTLY CLDY", (220, 220, 230)),
    "cloudy": ("CLOUDY", (170, 175, 190)),
    "rainy": ("RAIN", (80, 160, 255)),
    "pouring": ("POURING", (60, 140, 255)),
    "lightning": ("STORM", (255, 230, 80)),
    "lightning-rainy": ("T-STORM", (255, 230, 80)),
    "snowy": ("SNOW", (235, 240, 255)),
    "snowy-rainy": ("SLEET", (200, 220, 255)),
    "fog": ("FOG", (160, 165, 175)),
    "windy": ("WINDY", (150, 220, 200)),
    "windy-variant": ("WINDY", (150, 220, 200)),
    "hail": ("HAIL", (220, 235, 255)),
    "exceptional": ("ALERT", (255, 90, 60)),
}


def _temp_color(temp: float, unit: str) -> tuple:
    """Color-code the temperature (icy blue -> hot red)."""
    c = temp if "C" in (unit or "°C") else (temp - 32.0) * 5.0 / 9.0
    if c <= 0:
        return (140, 190, 255)
    if c <= 10:
        return (120, 220, 220)
    if c <= 20:
        return (150, 230, 150)
    if c <= 28:
        return (255, 200, 90)
    return (255, 100, 70)


# ---------------------------------------------------------------------------
# Tiny 5x7 pixel font (crisp on LED matrix, no font-file dependencies)
# ---------------------------------------------------------------------------

DROP = "\x10"   # water drop glyph (humidity)
GUST = "\x11"   # wind streaks glyph

_GLYPHS = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11100", "10010", "10001", "10001", "10001", "10010", "11100"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "10001", "11001", "10101", "10011", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "°": ("01100", "10010", "10010", "01100", "00000", "00000", "00000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "?": ("01110", "10001", "00001", "00110", "00100", "00000", "00100"),
    "↑": ("00100", "01110", "10101", "00100", "00100", "00100", "00100"),
    "↓": ("00100", "00100", "00100", "00100", "10101", "01110", "00100"),
    DROP: ("00100", "00100", "01110", "01110", "11111", "11111", "01110"),
    GUST: ("00000", "11100", "00000", "01110", "00000", "00111", "00000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def _prep_font() -> dict:
    """Left-trim glyphs and precompute widths."""
    out = {}
    for ch, rows in _GLYPHS.items():
        cols = [c for row in rows for c, bit in enumerate(row) if bit == "1"]
        if not cols:
            out[ch] = ([[False] * 3] * 7, 3)
            continue
        lo, hi = min(cols), max(cols)
        bits = [[row[c] == "1" for c in range(lo, hi + 1)] for row in rows]
        out[ch] = (bits, hi - lo + 1)
    return out


FONT = _prep_font()


def _text_width(text: str, scale: int = 1) -> int:
    w = 0
    for ch in text:
        _, gw = FONT.get(ch.upper(), FONT["?"])
        w += (gw + 1) * scale
    return w - scale if w else 0


def _draw_text(d: ImageDraw.ImageDraw, x: int, y: int, text: str,
               color: tuple, scale: int = 1) -> int:
    """Draw text with the built-in pixel font. Returns the end x position."""
    for ch in text:
        bits, gw = FONT.get(ch.upper(), FONT["?"])
        for r, row in enumerate(bits):
            for c, on in enumerate(row):
                if not on:
                    continue
                px, py = x + c * scale, y + r * scale
                if scale == 1:
                    d.point((px, py), fill=color)
                else:
                    d.rectangle([px, py, px + scale - 1, py + scale - 1],
                                fill=color)
        x += (gw + 1) * scale
    return x


def _segments_width(segs: list, scale: int = 1) -> int:
    w = 0
    for text, _color in segs:
        w += _text_width(text, scale) + scale
    return w - scale if w else 0


def _draw_segments(d: ImageDraw.ImageDraw, x: int, y: int, segs: list,
                   scale: int = 1) -> None:
    for text, color in segs:
        x = _draw_text(d, x, y, text, color, scale) + scale


# ---------------------------------------------------------------------------
# Icon primitives (drawn on a 32x32 canvas)
# ---------------------------------------------------------------------------

def _sun(d, cx, cy, r, t):
    # Rays rotate 90 degrees per loop (maps onto itself -> seamless).
    rot = t * (math.pi / 2)
    for i in range(8):
        a = rot + i * math.pi / 4
        r1 = r + 3 + (2 if i % 2 == 0 else 0)
        d.line(
            [(cx + (r + 2) * math.cos(a), cy + (r + 2) * math.sin(a)),
             (cx + r1 * math.cos(a), cy + r1 * math.sin(a))],
            fill=PAL["sun_ray"],
        )
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PAL["sun_core"])
    d.ellipse([cx - r + 2, cy - r + 2, cx - r + 4, cy - r + 4],
              fill=PAL["sun_hi"])


def _cloud(d, x, y, w, color):
    h = max(8, int(w * 0.6))
    d.ellipse([x, y + int(h * 0.35), x + int(w * 0.5), y + h], fill=color)
    d.ellipse([x + int(w * 0.18), y, x + int(w * 0.6), y + int(h * 0.8)],
              fill=color)
    d.ellipse([x + int(w * 0.45), y + int(h * 0.2), x + w, y + h], fill=color)


def _moon(d, cx, cy, r):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PAL["moon"])
    off = int(r * 0.55)
    d.ellipse([cx - r + off, cy - r - off, cx + r + off, cy + r - off],
              fill=(0, 0, 0))


def _bolt(d, cx, y, color):
    pts = [(cx - 1, y), (cx + 4, y), (cx + 1, y + 5), (cx + 3, y + 5),
           (cx - 4, y + 12), (cx - 1, y + 6), (cx - 3, y + 6)]
    d.polygon(pts, fill=color)


def _drops(d, box, t, cols, color, ln=3, speed=1):
    x0, y0, x1, y1 = box
    h = y1 - y0
    for i, fx in enumerate(cols):
        ph = (t * speed + i * 0.31) % 1.0
        x = round(x0 + fx * (x1 - x0))
        y = y0 + ph * h
        d.line([(x, y), (x, min(y + ln, y1))], fill=color)


def _flakes(d, box, t, cols, speed=1):
    x0, y0, x1, y1 = box
    h = y1 - y0
    for i, fx in enumerate(cols):
        ph = (t * speed + i * 0.4) % 1.0
        x = round(x0 + fx * (x1 - x0) + math.sin(2 * math.pi * ph + i) * 1.5)
        y = round(y0 + ph * h)
        d.point((x, y), fill=PAL["snow"])
        if i % 2 == 0:  # bigger flake: plus shape
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((x + dx, y + dy), fill=(170, 185, 210))


def _hailstones(d, box, t, cols, speed=2):
    x0, y0, x1, y1 = box
    h = y1 - y0
    for i, fx in enumerate(cols):
        ph = (t * speed + i * 0.37) % 1.0
        x = round(x0 + fx * (x1 - x0))
        y = round(y0 + ph * h)
        d.rectangle([x, y, x + 1, y + 1], fill=PAL["hail"])


# ---------------------------------------------------------------------------
# Condition icons (32x32, frame f of n, t = f/n)
# ---------------------------------------------------------------------------

def _icon_sunny(d, t, f, n):
    _sun(d, 16, 16, 7, t)


def _icon_clear_night(d, t, f, n):
    _moon(d, 16, 16, 8)
    stars = [(5, 6), (27, 8), (25, 26), (6, 26)]
    for i, (sx, sy) in enumerate(stars):
        bright = ((f + i * 3) % n) < n // 2
        d.point((sx, sy), fill=PAL["star"] if bright else PAL["star_dim"])
        if bright:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((sx + dx, sy + dy), fill=PAL["star_dim"])


def _icon_partlycloudy(d, t, f, n):
    _sun(d, 11, 10, 5, t)
    dx = round(math.sin(2 * math.pi * t) * 1.5)
    _cloud(d, 8 + dx, 15, 20, PAL["cloud_lt"])


def _icon_cloudy(d, t, f, n):
    dx = round(math.sin(2 * math.pi * t) * 1.5)
    _cloud(d, 3 - dx, 5, 18, PAL["cloud_md"])
    _cloud(d, 6 + dx, 13, 23, PAL["cloud_lt"])


def _icon_rainy(d, t, f, n):
    _cloud(d, 4, 3, 24, PAL["cloud_lt"])
    _drops(d, (7, 19, 29, 31), t, (0.05, 0.35, 0.65, 0.95), PAL["rain"])


def _icon_pouring(d, t, f, n):
    _cloud(d, 4, 3, 24, PAL["cloud_md"])
    _drops(d, (6, 19, 30, 31), t,
           (0.0, 0.18, 0.36, 0.54, 0.72, 0.9), PAL["rain"], ln=4, speed=2)


def _icon_lightning(d, t, f, n, rain=False):
    flash = f in (3, 4, 10)
    _cloud(d, 4, 3, 24, PAL["cloud_md"] if flash else PAL["cloud_dk"])
    if rain:
        _drops(d, (6, 19, 30, 31), t, (0.05, 0.95), PAL["rain"])
    if flash:
        _bolt(d, 16, 17, PAL["bolt"])
    elif f in (5, 11):
        _bolt(d, 16, 17, PAL["bolt_dim"])


def _icon_lightning_rainy(d, t, f, n):
    _icon_lightning(d, t, f, n, rain=True)


def _icon_snowy(d, t, f, n):
    _cloud(d, 4, 3, 24, PAL["cloud_lt"])
    _flakes(d, (7, 19, 29, 31), t, (0.1, 0.45, 0.8))


def _icon_snowy_rainy(d, t, f, n):
    _cloud(d, 4, 3, 24, PAL["cloud_lt"])
    _drops(d, (7, 19, 29, 31), t, (0.15, 0.85), PAL["rain"])
    _flakes(d, (7, 19, 29, 31), t, (0.5,))


def _icon_fog(d, t, f, n):
    for j in range(4):
        y = 7 + j * 6
        shift = round(math.sin(2 * math.pi * t + j * 1.7) * 2)
        col = PAL["fog"] if j % 2 == 0 else PAL["cloud_dk"]
        d.line([(4 + shift, y), (27 + shift, y)], fill=col, width=2)


def _icon_windy(d, t, f, n):
    for j, (y, ln) in enumerate(((9, 20), (16, 24), (23, 16))):
        x0 = 3 + (j % 2) * 3
        d.line([(x0, y), (x0 + ln, y)], fill=PAL["wind_dim"])
        # curl at the end of the streak
        d.point((x0 + ln, y - 1), fill=PAL["wind_dim"])
        d.point((x0 + ln - 1, y - 2), fill=PAL["wind_dim"])
        # moving gust highlight
        ph = (t + j / 3.0) % 1.0
        gx = x0 + ph * ln
        d.line([(gx, y), (min(gx + 4, x0 + ln), y)], fill=PAL["wind"])


def _icon_hail(d, t, f, n):
    _cloud(d, 4, 3, 24, PAL["cloud_md"])
    _hailstones(d, (6, 19, 29, 30), t, (0.05, 0.35, 0.65, 0.95))


def _icon_exceptional(d, t, f, n):
    blink = (f % n) < n // 2
    d.polygon([(16, 4), (3, 28), (29, 28)],
              fill=(160, 90, 0) if blink else (110, 60, 0),
              outline=PAL["alert"])
    col = (255, 255, 255) if blink else (255, 200, 0)
    d.rectangle([15, 11, 17, 20], fill=col)
    d.rectangle([15, 23, 17, 25], fill=col)


def _icon_unknown(d, t, f, n):
    _draw_text(d, 10, 6, "?", (150, 155, 165), scale=3)


_ICON_PAINTERS = {
    "sunny": _icon_sunny,
    "clear": _icon_sunny,
    "clear-night": _icon_clear_night,
    "partlycloudy": _icon_partlycloudy,
    "cloudy": _icon_cloudy,
    "rainy": _icon_rainy,
    "pouring": _icon_pouring,
    "lightning": _icon_lightning,
    "lightning-rainy": _icon_lightning_rainy,
    "snowy": _icon_snowy,
    "snowy-rainy": _icon_snowy_rainy,
    "fog": _icon_fog,
    "windy": _icon_windy,
    "windy-variant": _icon_windy,
    "hail": _icon_hail,
    "exceptional": _icon_exceptional,
}


def _render_icon(condition: str, f: int, n: int) -> Image.Image:
    img = Image.new("RGB", (32, 32), (0, 0, 0))
    d = ImageDraw.Draw(img)
    cond = (condition or "").lower().replace("_", "-")
    painter = _ICON_PAINTERS.get(cond, _icon_unknown)
    painter(d, f / n, f, n)
    return img


# Keyword fallbacks for condition strings that aren't native HA conditions,
# e.g. OpenWeatherMap description sensors ("broken clouds", "light rain").
# Order matters: first match wins.
_CONDITION_KEYWORDS = (
    ("thunder", "lightning-rainy"),
    ("tornado", "exceptional"),
    ("hurricane", "exceptional"),
    ("hail", "hail"),
    ("sleet", "snowy-rainy"),
    ("freezing rain", "snowy-rainy"),
    ("rain and snow", "snowy-rainy"),
    ("snow", "snowy"),
    ("heavy intensity rain", "pouring"),
    ("very heavy rain", "pouring"),
    ("extreme rain", "pouring"),
    ("torrential", "pouring"),
    ("drizzle", "rainy"),
    ("shower", "rainy"),
    ("rain", "rainy"),
    ("few clouds", "partlycloudy"),
    ("scattered clouds", "partlycloudy"),
    ("partly", "partlycloudy"),
    ("broken clouds", "cloudy"),
    ("overcast", "cloudy"),
    ("cloud", "cloudy"),
    ("mist", "fog"),
    ("fog", "fog"),
    ("haze", "fog"),
    ("smoke", "fog"),
    ("dust", "fog"),
    ("sand", "fog"),
    ("squall", "windy"),
    ("wind", "windy"),
    ("clear", "sunny"),
    ("sun", "sunny"),
)


def normalize_condition(text: str | None, is_night: bool = False) -> str:
    """Map a condition string (HA condition or free text) to an icon key."""
    if not text:
        return "unknown"
    s = str(text).lower().strip().replace("_", "-")
    cond = None
    if s in _ICON_PAINTERS:
        cond = s
    else:
        for kw, c in _CONDITION_KEYWORDS:
            if kw in s:
                cond = c
                break
    if cond is None:
        return s  # unknown: renders the '?' icon with the raw label
    if is_night and cond == "sunny":
        return "clear-night"
    return cond


# ---------------------------------------------------------------------------
# Frame layouts
# ---------------------------------------------------------------------------

def _fmt(v: float | None) -> str:
    return "--" if v is None else str(round(v))


def _layout_large(data: WeatherData, icon: Image.Image, size: int,
                  label: str, label_color: tuple) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    img.paste(icon, (0, 0))
    d = ImageDraw.Draw(img)

    right_x, right_w = 32, size - 32

    # Big temperature, color coded
    if data.temperature is not None:
        tcol = _temp_color(data.temperature, data.temp_unit)
        txt = f"{round(data.temperature)}°"
        scale = 2
        if _text_width(txt, scale) > right_w:
            txt = f"{round(data.temperature)}"  # drop the degree sign
        if _text_width(txt, scale) > right_w + 2:  # may bleed 2px left
            scale = 1
            txt = f"{round(data.temperature)}°"
        w = _text_width(txt, scale)
        x = min(right_x + max(0, (right_w - w) // 2), size - w)
        y = 16 - (7 * scale) // 2
        _draw_text(d, x, y, txt, tcol, scale)

    # Condition label, centered
    if label:
        w = _text_width(label)
        _draw_text(d, max(0, (size - w) // 2), 34, label, label_color)

    # High / low row
    if data.high is not None or data.low is not None:
        segs = []
        if data.high is not None:
            segs.append((f"↑{_fmt(data.high)}", PAL["hi"]))
        if data.low is not None:
            segs.append((f"↓{_fmt(data.low)}", PAL["lo"]))
        w = _segments_width(segs)
        _draw_segments(d, max(0, (size - w) // 2), 44, segs)

    # Bottom row: humidity left, wind right
    if data.humidity is not None:
        _draw_text(d, 2, 55, f"{DROP}{round(data.humidity)}%", PAL["humid"])
    if data.wind_speed is not None:
        txt = f"{GUST}{round(data.wind_speed)}"
        w = _text_width(txt)
        _draw_text(d, size - 2 - w, 55, txt, PAL["label_dim"])

    return img


def _layout_small(data: WeatherData, icon: Image.Image,
                  size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    img.paste(icon.resize((16, 16), Image.NEAREST), (0, 0))
    d = ImageDraw.Draw(img)

    if data.temperature is not None:
        tcol = _temp_color(data.temperature, data.temp_unit)
        txt = f"{round(data.temperature)}°"
        w = _text_width(txt)
        _draw_text(d, 16 + max(0, (16 - w) // 2), 5, txt, tcol)

    if data.high is not None and data.low is not None:
        segs = [(_fmt(data.high), PAL["hi"]), ("/", PAL["label_dim"]),
                (_fmt(data.low), PAL["lo"])]
        w = _segments_width(segs)
        _draw_segments(d, max(0, (size - w) // 2), 17, segs)

    if data.humidity is not None:
        txt = f"{DROP}{round(data.humidity)}%"
        w = _text_width(txt)
        _draw_text(d, max(0, (size - w) // 2), 25, txt, PAL["humid"])

    return img


# ---------------------------------------------------------------------------
# GIF assembly
# ---------------------------------------------------------------------------

def _single_frame_blocks(gif_bytes: bytes) -> tuple:
    """Split a single-frame GIF into (header+GCT, image descriptor, lzw data)."""
    d = gif_bytes
    packed = d[10]
    gct_len = (2 << (packed & 7)) * 3 if packed & 0x80 else 0
    header = d[: 13 + gct_len]
    pos = 13 + gct_len
    while d[pos] == 0x21:  # skip extension blocks
        pos += 2
        while d[pos] != 0:
            pos += 1 + d[pos]
        pos += 1
    if d[pos] != 0x2C:
        raise ValueError("no image descriptor found")
    desc = bytearray(d[pos: pos + 10])
    pos += 10
    if desc[9] & 0x80:  # local color table present (shouldn't happen)
        raise ValueError("unexpected local color table")
    start = pos
    pos += 1  # LZW minimum code size
    while d[pos] != 0:
        pos += 1 + d[pos]
    pos += 1  # block terminator
    desc[9] &= 0x7F
    return header, bytes(desc), d[start:pos]


def _assemble_gif(pframes: list, duration: int) -> bytes:
    """Assemble an animated GIF with a single global palette and no LCTs.

    Pillow's multi-frame writer emits per-frame Local Color Tables, which
    the device parser is suspected to mishandle. Instead we compress each
    frame as a single-frame GIF (all sharing an identical full palette) and
    splice the LZW data into one hand-built animation container.
    """
    delay_cs = max(2, duration // 10)
    out = None
    header0 = None
    for q in pframes:
        buf = io.BytesIO()
        q.save(buf, format="GIF", optimize=False)
        header, desc, lzw = _single_frame_blocks(buf.getvalue())
        if out is None:
            header0 = header
            out = bytearray(header)
            # NETSCAPE looping extension (loop forever)
            out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
        elif header != header0:
            raise ValueError("frame palettes diverged")
        # Graphic Control Extension: disposal=2 (restore to background)
        out += bytes([0x21, 0xF9, 0x04, 0x08,
                      delay_cs & 0xFF, (delay_cs >> 8) & 0xFF, 0x00, 0x00])
        out += desc + lzw
    out += b"\x3b"
    return bytes(out)


def render_weather_gif(data: WeatherData, size: int = 64,
                       duration: int = 150) -> bytes:
    """Render the weather dashboard as animated GIF bytes."""
    cond = (data.condition or "").lower().replace("_", "-")
    n = 16 if cond in ("lightning", "lightning-rainy") else 12

    label, label_color = CONDITION_LABELS.get(
        cond, ((data.condition or "?").upper()[:10], (200, 200, 200)))

    frames = []
    for f in range(n):
        icon = _render_icon(cond, f, n)
        if size >= 48:
            frames.append(_layout_large(data, icon, size, label, label_color))
        else:
            frames.append(_layout_small(data, icon, size))

    # Quantize all frames against one shared palette built from every frame.
    sheet = Image.new("RGB", (size, size * n))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (0, size * i))
    try:
        palette = sheet.quantize(colors=64, method=Image.Quantize.MAXCOVERAGE)
    except Exception:
        palette = sheet.quantize(colors=64)
    full_palette = (palette.getpalette() + [0] * 768)[:768]
    pframes = []
    for fr in frames:
        q = fr.quantize(palette=palette, dither=Image.Dither.NONE)
        q.putpalette(full_palette)
        pframes.append(q)

    try:
        return _assemble_gif(pframes, duration)
    except Exception:
        # Fallback: Pillow's writer (may emit LCTs, but is standard GIF89a)
        buf = io.BytesIO()
        pframes[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=pframes[1:],
            loop=0,
            duration=duration,
            disposal=2,
        )
        return buf.getvalue()
