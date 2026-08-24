"""Custom clock face for iDotMatrix LED matrix displays.

A "facelift" for the factory clock styles: big HH:MM in the house pixel
font with a blinking colon, weekday up top in an accent color, date below
in muted gray, and a thin accent rule under the time. Rendered as a
2-frame GIF (colon on / colon off, 500ms each) so the blink animates on
the device itself; Home Assistant re-uploads once a minute when the time
changes.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module.
"""
from __future__ import annotations

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

    # Row 1 (y=4): weekday centered in accent, flanked by dim ticks
    wd = _WEEKDAYS[data.weekday]
    ww = _text_width(wd)
    wx = (size - ww) // 2
    _draw_text(d, wx, 4, wd, accent)
    d.line([(4, 7), (wx - 4, 7)], fill=(45, 45, 50))
    d.line([(wx + ww + 3, 7), (size - 5, 7)], fill=(45, 45, 50))

    # Row 2 (y=20): big HH:MM, blinking colon
    _draw_time(d, size, 20, data, colon_on, scale=2)

    _, suffix = _time_parts(data)

    # Accent rule under the time
    d.line([(10, 38), (size - 11, 38)], fill=accent)

    # Row 3 (y=44): date centered in gray (+ AM/PM in 12h mode)
    if data.show_date:
        date_txt = f"{_MONTHS[data.month - 1]} {data.day}"
        if suffix:
            date_txt += f" {suffix}"
        dw = _text_width(date_txt)
        _draw_text(d, (size - dw) // 2, 44, date_txt, LABEL_COLOR)
    elif suffix:
        sw = _text_width(suffix)
        _draw_text(d, (size - sw) // 2, 44, suffix, LABEL_COLOR)

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
