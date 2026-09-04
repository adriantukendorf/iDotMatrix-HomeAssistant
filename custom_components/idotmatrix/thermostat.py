"""Thermostat status display for iDotMatrix LED matrix displays.

Renders up to two HVAC zones (a heating thermostat and a cooling
thermostat) as stacked panels. Each panel shows a flame or snowflake icon,
the zone label, a status word (ON / IDLE / OFF / FAN), the current room
temperature at double size and the setpoint beside it.

While a zone is actively calling for heat or cool its icon animates: the
flame flickers and the snowflake pulses. Idle zones keep a dimmed version
of their color so the two rows stay recognisable at a glance; zones that
are switched off go gray.

Reuses the pixel font, text helpers and device-safe GIF encoder from the
weather module. The icon helpers are also used by the power gauge to flag
when a load spike is the furnace or the AC.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .weather import _draw_text, _text_width, frames_to_gif

HEAT_ORANGE = (255, 140, 40)
HEAT_CORE = (255, 220, 90)
COOL_BLUE = (90, 180, 255)
COOL_CORE = (200, 235, 255)
WHITE = (255, 255, 255)
LABEL_COLOR = (140, 140, 150)
DIM_GRAY = (70, 70, 80)
RULE_GRAY = (40, 40, 48)

ACTIVE_ACTIONS = ("heating", "cooling")

# Flame icon (8x8), two frames for flicker. "X" = outer, "o" = hot core.
_FLAME_FRAMES = (
    (
        "....X...",
        "...XX...",
        "...XX...",
        "..XXXX..",
        ".XXXoX..",
        ".XXooXX.",
        ".XXooXX.",
        "..XooX..",
    ),
    (
        "...X....",
        "..XX....",
        "..XXX...",
        "..XXXX..",
        ".XXoXXX.",
        ".XXooXX.",
        ".XXooXX.",
        "..XooX..",
    ),
)

# Snowflake icon (7x7 in an 8x8 cell). "o" = center.
_SNOW_ICON = (
    "...X....",
    ".X.X.X..",
    "..XXX...",
    "XXXoXXX.",
    "..XXX...",
    ".X.X.X..",
    "...X....",
    "........",
)


def _scale_color(color: tuple, k: float) -> tuple:
    return tuple(max(0, min(255, round(c * k))) for c in color)


@dataclass
class ZoneState:
    """One thermostat as read from a Home Assistant climate entity."""

    kind: str                  # "heat" or "cool"
    current: float | None      # room temperature
    target: float | None       # setpoint
    action: str                # heating / cooling / idle / off / fan / unknown

    @property
    def active(self) -> bool:
        return self.action in ACTIVE_ACTIONS

    @property
    def off(self) -> bool:
        return self.action == "off"

    def status(self) -> str:
        if self.active:
            return "ON"
        if self.action == "fan":
            return "FAN"
        if self.off:
            return "OFF"
        if self.action == "unknown":
            return "?"
        return "IDLE"

    def signature(self) -> tuple:
        cur = None if self.current is None else round(self.current)
        tgt = None if self.target is None else round(self.target)
        return (self.kind, cur, tgt, self.action)


@dataclass
class ThermostatData:
    heat: ZoneState | None = None
    cool: ZoneState | None = None
    unit: str = "°F"

    def zones(self) -> list:
        return [z for z in (self.heat, self.cool) if z is not None]

    def signature(self) -> tuple:
        return tuple(z.signature() for z in self.zones())


def _zone_colors(zone: ZoneState) -> tuple:
    """Return (icon color, core color, text color) for the zone's state."""
    base, core = ((HEAT_ORANGE, HEAT_CORE) if zone.kind == "heat"
                  else (COOL_BLUE, COOL_CORE))
    if zone.active:
        return base, core, base
    if zone.off:
        return DIM_GRAY, DIM_GRAY, DIM_GRAY
    dim = _scale_color(base, 0.45)
    return dim, dim, LABEL_COLOR


def _draw_flame(d: ImageDraw.ImageDraw, ox: int, oy: int, color: tuple,
                core: tuple, f: int = 0, n: int = 1,
                animate: bool = False) -> None:
    rows = _FLAME_FRAMES[(f // 2) % 2] if animate else _FLAME_FRAMES[0]
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == "X":
                d.point((ox + c, oy + r), fill=color)
            elif ch == "o":
                d.point((ox + c, oy + r), fill=core)


def _draw_snowflake(d: ImageDraw.ImageDraw, ox: int, oy: int, color: tuple,
                    core: tuple, f: int = 0, n: int = 1,
                    animate: bool = False) -> None:
    if animate and n > 1:
        # Gentle brightness pulse while the AC is running
        k = 0.7 + 0.3 * math.sin(2 * math.pi * f / n)
        color = _scale_color(color, k)
        core = _scale_color(core, k)
    for r, row in enumerate(_SNOW_ICON):
        for c, ch in enumerate(row):
            if ch == "X":
                d.point((ox + c, oy + r), fill=color)
            elif ch == "o":
                d.point((ox + c, oy + r), fill=core)


def draw_zone_icon(d: ImageDraw.ImageDraw, ox: int, oy: int, kind: str,
                   color: tuple, core: tuple, f: int = 0, n: int = 1,
                   animate: bool = False) -> None:
    """Draw the flame (heat) or snowflake (cool) icon at (ox, oy)."""
    if kind == "heat":
        _draw_flame(d, ox, oy, color, core, f, n, animate)
    else:
        _draw_snowflake(d, ox, oy, color, core, f, n, animate)


def _fmt_temp(v: float | None) -> str:
    return "--" if v is None else f"{v:.0f}"


def _draw_zone_panel(d: ImageDraw.ImageDraw, zone: ZoneState, size: int,
                     top: int, f: int, n: int) -> None:
    """Draw one zone in a 64x30 region starting at y=top."""
    icon_c, core_c, text_c = _zone_colors(zone)

    # Row 1: icon, zone label, status word right-aligned
    draw_zone_icon(d, 2, top, zone.kind, icon_c, core_c, f, n, zone.active)
    label = "HEAT" if zone.kind == "heat" else "COOL"
    _draw_text(d, 12, top, label, text_c)
    status = zone.status()
    sw = _text_width(status)
    _draw_text(d, size - sw - 2, top, status, text_c)

    # Row 2: current temperature at scale 2, setpoint at scale 1 on the right
    cur_txt = _fmt_temp(zone.current) + "°"
    cur_color = WHITE if not zone.off else LABEL_COLOR
    _draw_text(d, 2, top + 11, cur_txt, cur_color, scale=2)

    if not zone.off:
        tgt_txt = "▸" + _fmt_temp(zone.target) + "°"
        tw = _text_width(tgt_txt)
        _draw_text(d, size - tw - 2, top + 18, tgt_txt, LABEL_COLOR)


def _layout_large(data: ThermostatData, size: int, f: int = 0,
                  n: int = 1) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    zones = data.zones()
    if not zones:
        msg = "NO DATA"
        _draw_text(d, (size - _text_width(msg)) // 2, size // 2 - 3, msg,
                   LABEL_COLOR)
        return img

    if len(zones) == 1:
        _draw_zone_panel(d, zones[0], size, 18, f, n)
        return img

    _draw_zone_panel(d, zones[0], size, 2, f, n)
    d.line([(2, 31), (size - 3, 31)], fill=RULE_GRAY)
    _draw_zone_panel(d, zones[1], size, 34, f, n)
    return img


def _layout_small(data: ThermostatData, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)

    zones = data.zones()
    if not zones:
        _draw_text(d, 2, size // 2 - 3, "N/A", LABEL_COLOR)
        return img

    step = size // len(zones)
    for i, zone in enumerate(zones):
        icon_c, core_c, _ = _zone_colors(zone)
        y = i * step + (step - 8) // 2
        draw_zone_icon(d, 1, y, zone.kind, icon_c, core_c)
        cur_txt = _fmt_temp(zone.current) + "°"
        cur_color = WHITE if not zone.off else LABEL_COLOR
        _draw_text(d, 11, y, cur_txt, cur_color)
    return img


def render_thermostat_gif(data: ThermostatData, size: int = 64,
                          duration: int = 200) -> bytes:
    if size >= 48:
        n = 16
        frames = [_layout_large(data, size, f, n) for f in range(n)]
    else:
        frame = _layout_small(data, size)
        frames = [frame, frame.copy()]
        duration = 1000
    return frames_to_gif(frames, duration)
