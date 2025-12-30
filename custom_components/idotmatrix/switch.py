"""Switch platform for iDotMatrix."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .entity import IDotMatrixEntity

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDotMatrix switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IDotMatrixTextProportional(coordinator, entry),
        IDotMatrixMultiline(coordinator, entry),
    ])

class IDotMatrixTextProportional(IDotMatrixEntity, SwitchEntity):
    """Switch to toggle proportional text rendering."""

    _attr_icon = "mdi:format-text-variant"
    _attr_name = "Proportional Spacing"
    _attr_entity_category = EntityCategory.CONFIG
    
    @property
    def unique_id(self) -> str:
        return f"{self._mac}_text_proportional"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self.coordinator.text_settings.get("proportional", True)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        self.coordinator.text_settings["proportional"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        self.coordinator.text_settings["proportional"] = False
        self.async_write_ha_state()

class IDotMatrixMultiline(IDotMatrixEntity, SwitchEntity):
    """Switch to toggle multiline text (static image)."""

    _attr_icon = "mdi:wrap"
    _attr_name = "Multiline Text"
    _attr_entity_category = EntityCategory.CONFIG
    
    @property
    def unique_id(self) -> str:
        return f"{self._mac}_text_multiline"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self.coordinator.text_settings.get("multiline", False)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        self.coordinator.text_settings["multiline"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        self.coordinator.text_settings["multiline"] = False
        self.async_write_ha_state()
