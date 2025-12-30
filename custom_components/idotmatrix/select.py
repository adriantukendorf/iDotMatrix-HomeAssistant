"""Select platform for iDotMatrix."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IDotMatrixEntity
from .client.modules.clock import Clock
from .client.modules.effect import Effect

CLOCK_STYLES = [
    "Default", "Christmas", "Racing", "Inverted Full Screen",
    "Animated Hourglass", "Frame 1", "Frame 2", "Frame 3"
]

# Mapping names to IDs for internal use if needed, but the library mostly takes indices
# Clock().setMode(style_idx, ...)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDotMatrix select."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IDotMatrixClockFace(coordinator, entry),
    ])

class IDotMatrixClockFace(IDotMatrixEntity, SelectEntity):
    """Representation of the Clock Face selector."""

    _attr_icon = "mdi:clock-digital"
    _attr_options = CLOCK_STYLES
    _attr_name = "Clock Face"
    _attr_current_option = None
    _attr_unique_id = "clock_face"

    @property
    def unique_id(self) -> str:
        return f"{self._mac}_clock_face"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Map option string to index
        if option in CLOCK_STYLES:
            idx = CLOCK_STYLES.index(option)
            # Defaults: show_date=True, show_24hr=True, color=White
            # Future: make these configurable
            await Clock().setMode(idx, True, True, 255, 255, 255)
            self._attr_current_option = option
            self.async_write_ha_state()
