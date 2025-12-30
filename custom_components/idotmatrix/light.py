"""Light platform for iDotMatrix Panel Colour."""
from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .entity import IDotMatrixEntity
from .client.modules.common import Common

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDotMatrix light platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IDotMatrixLight(coordinator, entry),
    ])

class IDotMatrixLight(IDotMatrixEntity, LightEntity):
    """Representation of the Panel Colour Light."""

    _attr_icon = "mdi:palette"
    _attr_name = "Panel Colour"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_entity_category = EntityCategory.CONFIG
    
    @property
    def unique_id(self) -> str:
        return f"{self._mac}_panel_color"

    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        # We track state locally to allow toggling, 
        # but realistically the device is always 'on' unless screenOff called.
        return self.coordinator.text_settings.get("is_on", True)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return self.coordinator.text_settings.get("brightness", 128)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value [int, int, int]."""
        return tuple(self.coordinator.text_settings.get("color", (255, 0, 0)))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        
        # 1. On
        if not self.is_on:
             await Common().screenOn()
             self.coordinator.text_settings["is_on"] = True
        
        # 2. Brightness
        if ATTR_BRIGHTNESS in kwargs:
            bright = kwargs[ATTR_BRIGHTNESS]
            self.coordinator.text_settings["brightness"] = bright
            # Map 0-255 to 5-100
            val = max(5, int((bright / 255) * 100))
            await Common().setBrightness(val)
            
        # 3. Color
        if ATTR_RGB_COLOR in kwargs:
            rgb = kwargs[ATTR_RGB_COLOR]
            self.coordinator.text_settings["color"] = list(rgb)
            
            # Send color update immediately to Clock
            # We assume user wants to see the color change now.
            # Ideally we would only update if in Clock mode, but we default to updating Clock.
            s = self.coordinator.text_settings
            style = s.get("clock_style", 0)
            show_date = s.get("clock_date", True)
            h24 = s.get("clock_format", "24h") == "24h"
            
            from .client.modules.clock import Clock
            await Clock().setMode(style, show_date, h24, rgb[0], rgb[1], rgb[2])
            
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await Common().screenOff()
        self.coordinator.text_settings["is_on"] = False
        self.async_write_ha_state()
