"""Custom clock faces for iDotMatrix LED matrix displays.

A "facelift" for the factory clock styles. Two designs:

- "pixel": big HH:MM in the house pixel font with a blinking colon,
  weekday up top in an accent color, date below in muted gray, and a
  thin accent rule under the time.
- "analog": a minimal dial — accent-colored 2x4 rectangles at 12/3/6/9,
  white two-pixel diagonal ticks at the other hours, smooth anti-aliased
  hour/minute hands, a pulsing center dot, and a small day-of-month in
  the corner as a date window.

Both render as 2-frame GIFs (500ms per frame) so the blink/pulse
animates on the device itself; Home Assistant re-uploads once a minute
when the time changes.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

TIME_COLOR = (255, 255, 255)
LABEL_COLOR = (140, 140, 150)
DEFAULT_ACCENT = (100, 180, 255)

_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


@dataclass
class ClockFaceData:
    hour: int          # 0-23
    minute: int
    weekday: int       # 0=Monday .. 6=Sunday
    month: int         # 1-12
    day: int
    hour24: bool = True
    show_date: bool = True

    def signature(self) -> tuple:
        return (self.hour, self.minute, self.day)


def _time_parts(data: ClockFaceData) -> tuple[str, str]:
    """Return (time_text, suffix) where suffix is '', 'AM' or 'PM'."""
    if data.hour24:
        return f"{data.hour:02d}:{data.minute:02d}", ""
    suffix = "AM" if data.hour < 12 else "PM"
    h = data.hour % 12 or 12
    return f"{h}:{data.minute:02d}", suffix


def _draw_time(d: ImageDraw.ImageDraw, size: int, y: int,
               data: ClockFaceData, colon_on: bool, scale: int) -> None:
    time_txt, _ = _time_parts(data)
    w = _text_width(time_txt, scale=scale)
    x = (size - w) // 2
    for ch in time_txt:
        if ch == ":" and not colon_on:
            x += (_text_width(":") + 1) * scale
            continue
        x = _draw_text(d, x, y, ch, TIME_COLOR, scale=scale)


def _layout_large(data: ClockFaceData, accent: tuple,
                  colon_on: bool, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    # Row 1 (y=8): weekday centered in accent, flanked by dim ticks
    wd = _WEEKDAYS[data.weekday]
    ww = _text_width(wd)
    wx = (size - ww) // 2
    _draw_text(d, wx, 8, wd, accent)
    d.line([(4, 11), (wx - 4, 11)], fill=(45, 45, 50))
    d.line([(wx + ww + 3, 11), (size - 5, 11)], fill=(45, 45, 50))

    # Row 2 (y=24): big HH:MM, blinking colon
    _draw_time(d, size, 24, data, colon_on, scale=2)

    _, suffix = _time_parts(data)

    # Accent rule under the time
    d.line([(10, 42), (size - 11, 42)], fill=accent)

    # Row 3 (y=48): date centered in gray (+ AM/PM in 12h mode)
    if data.show_date:
        date_txt = f"{_MONTHS[data.month - 1]} {data.day}"
        if suffix:
            date_txt += f" {suffix}"
        dw = _text_width(date_txt)
        _draw_text(d, (size - dw) // 2, 48, date_txt, LABEL_COLOR)
    elif suffix:
        sw = _text_width(suffix)
        _draw_text(d, (size - sw) // 2, 48, suffix, LABEL_COLOR)

    return img


def _layout_small(data: ClockFaceData, accent: tuple,
                  colon_on: bool, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    _draw_time(d, size, 5, data, colon_on, scale=1)

    if data.show_date:
        date_txt = f"{_MONTHS[data.month - 1]} {data.day}"
        dw = _text_width(date_txt)
        _draw_text(d, (size - dw) // 2, 18, date_txt, LABEL_COLOR)

    return img


def render_clockface_gif(data: ClockFaceData, size: int = 64,
                         accent: tuple = DEFAULT_ACCENT) -> bytes:
    layout = _layout_large if size >= 48 else _layout_small
    frames = [layout(data, accent, True, size),
              layout(data, accent, False, size)]
    return frames_to_gif(frames, 500)


# ----------------------------------------------------------------------
# Analog face
# ----------------------------------------------------------------------

ANALOG_ACCENT = (100, 210, 110)


def _hand_point(cx: float, cy: float, angle_deg: float,
                length: float) -> tuple[float, float]:
    """Point at `length` from center, angle measured clockwise from 12."""
    a = math.radians(angle_deg)
    return (cx + length * math.sin(a), cy - length * math.cos(a))


def _draw_ticks(d: ImageDraw.ImageDraw, size: int, accent: tuple) -> None:
    """Hard-coded crisp tick marks (the supersampled versions smear)."""
    m = 2                       # margin to the panel edge
    c0 = size // 2 - 1          # the two center columns/rows
    c1 = size // 2

    # Cardinal points: 2x4 rectangles in the accent color
    d.rectangle([c0, m, c1, m + 3], fill=accent)                    # 12
    d.rectangle([c0, size - m - 4, c1, size - m - 1], fill=accent)  # 6
    d.rectangle([size - m - 4, c0, size - m - 1, c1], fill=accent)  # 3
    d.rectangle([m, c0, m + 3, c1], fill=accent)                    # 9

    # Other hours: white two-pixel diagonal marks, angled toward center
    cx = cy = (size - 1) / 2
    radius = size // 2 - 3
    for h in range(12):
        if h % 3 == 0:
            continue
        a = math.radians(h * 30)
        sin_a, cos_a = math.sin(a), math.cos(a)
        ox = round(cx + radius * sin_a)
        oy = round(cy - radius * cos_a)
        ix = ox + (-1 if sin_a > 0 else 1)
        iy = oy + (1 if cos_a > 0 else -1)
        d.point((ox, oy), fill=TIME_COLOR)
        d.point((ix, iy), fill=TIME_COLOR)


def _layout_analog(data: ClockFaceData, accent: tuple,
                   pulse_on: bool, size: int) -> Image.Image:
    # Hands are drawn 4x oversized and downscaled so the angled lines
    # come out smooth instead of stair-stepped; the LED matrix renders
    # the resulting grays as a soft glow. Ticks, center dot and date are
    # drawn crisp afterwards.
    ss = 4
    big = size * ss
    img = Image.new("RGB", (big, big), (0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = cy = (big - 1) / 2
    radius = (size // 2 - 3) * ss

    # Hands: hour short and thick, minute long and thin, both white
    hour_angle = (data.hour % 12) * 30 + data.minute * 0.5
    minute_angle = data.minute * 6
    d.line([(cx, cy), _hand_point(cx, cy, hour_angle, radius * 0.52)],
           fill=TIME_COLOR, width=2 * ss)
    d.line([(cx, cy), _hand_point(cx, cy, minute_angle, radius * 0.82)],
           fill=TIME_COLOR, width=ss)

    img = img.resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(img)

    _draw_ticks(d, size, accent)

    # Center dot pulses once a second
    dim = tuple(int(v * 0.45) for v in accent)
    c = (size - 1) // 2
    d.rectangle([c, c, c + 1, c + 1],
                fill=accent if pulse_on else dim)

    # Small day-of-month in the bottom-right corner, clear of the dial
    if data.show_date and size >= 48:
        day_txt = str(data.day)
        dw = _text_width(day_txt)
        _draw_text(d, size - dw - 2, size - 9, day_txt, LABEL_COLOR)

    return img


def render_analog_gif(data: ClockFaceData, size: int = 64,
                      accent: tuple = ANALOG_ACCENT) -> bytes:
    frames = [_layout_analog(data, accent, True, size),
              _layout_analog(data, accent, False, size)]
    return frames_to_gif(frames, 500)
