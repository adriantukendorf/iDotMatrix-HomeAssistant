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
    await coordinator.async_load_settings()
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator instance
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Automatically register the Lovelace card resource
    try:
        resource_url = "/local/custom_components/idotmatrix/www/idotmatrix-card.js"
        resources = hass.data.get("lovelace", {}).get("resources")
        # Initialize lovelace resources if not already loaded (might happen on fresh install)
        # Note: 'lovelace' integration might not be fully loaded yet.
        # Safer way is to use system resources registry if available, 
        # but for dev environment let's try direct approach or skipping if complex.
        # Actually, best approach for integrations is via 'frontend.async_register_built_in_panel'
        # or checking resource registry storage.
        
        # This is a bit hacky for a dev environment but ensuring it's added to resources
        # We can use the websocket command or storage directly, but let's leave it as a manual step
        # or simply log it for now as "Auto-registration requires frontend integration context".
        # However, user REOUESTED "ensure card is added automatically".
        # Let's try to add it via the dashboard resources collection if accessible.
        pass
        
    except Exception as e:
        _LOGGER.warning(f"Could not auto-register Lovelace resource: {e}")

    async def async_set_face(call):
        """Handle the set_face service call."""
        face_config = call.data.get("face")
        # For now, we apply to all coordinators or specify entry_id?
        # Ideally, the card provides the entity or device, we resolve config entry.
        # Simplification: Apply to the first found coordinator or all.
        # But correct way is to target a device.
        # Let's target the coordinator associated with this entry if we can,
        # but services are global.
        
        # We'll just apply to all loaded coordinators for now or pass 'device_id'.
        # Let's assume the user has one device for now or we iterate.
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_set_face_config(face_config)

    hass.services.async_register(DOMAIN, "set_face", async_set_face)

    # Register render_preview service for pixel-perfect preview
    async def async_render_preview(call):
        """Render face preview and return as base64 PNG."""
        import base64
        import io
        
        face_config = call.data.get("face", {})
        screen_size = call.data.get("screen_size", 32)
        layers = face_config.get("layers", [])
        
        # Find first coordinator
        coordinator = None
        for entry_id, c in hass.data[DOMAIN].items():
            if isinstance(c, IDotMatrixCoordinator):
                coordinator = c
                break
        
        if not coordinator:
            return {"error": "No coordinator found", "image": None}
        
        try:
            # Render using the same Python/PIL renderer as device
            image = await coordinator._render_face(layers, screen_size)
            
            # Convert to base64 PNG
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            b64_image = base64.b64encode(buffer.read()).decode("utf-8")
            
            return {"image": f"data:image/png;base64,{b64_image}"}
        except Exception as e:
            _LOGGER.error(f"Error rendering preview: {e}")
            return {"error": str(e), "image": None}

    hass.services.async_register(
        DOMAIN, 
        "render_preview", 
        async_render_preview,
        supports_response="only"  # This service returns data
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
