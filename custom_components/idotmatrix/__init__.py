"""The iDotMatrix integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_MAC
from .client.connectionManager import ConnectionManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TEXT, Platform.SELECT, Platform.BUTTON, Platform.NUMBER, Platform.SWITCH, Platform.LIGHT]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up iDotMatrix from a config entry."""
    
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize connection manager (singleton currently, might need adaptation per entry if multiple devices supported properly)
    # For now, we store the address in the manager? Or pass it to entities?
    # The client library assumes Singleton ConnectionManager. 
    # We might need to refactor the client library eventually to support multiple instances.
    # For now, we will assume one device per integration instance or update the singleton.
    
    hass.data[DOMAIN][entry.entry_id] = entry.data
    
    # Initialize the Singleton ConnectionManager with the device address
    manager = ConnectionManager()
    manager.set_hass(hass)
    manager.address = entry.data[CONF_MAC]

    from .coordinator import IDotMatrixCoordinator
    coordinator = IDotMatrixCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator instance
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
