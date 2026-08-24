"""The iDotMatrix integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
import os
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import CONF_RESOURCE_TYPE_WS, CONF_URL
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_MAC
from .client.connectionManager import ConnectionManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TEXT, Platform.SELECT, Platform.BUTTON, Platform.NUMBER, Platform.SWITCH, Platform.LIGHT]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_CARD_URL_PATH = "/idotmatrix"
_CARD_FILENAME = "idotmatrix-card.js"
_CARD_RESOURCE_URL = f"{_CARD_URL_PATH}/{_CARD_FILENAME}"

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the iDotMatrix component."""
    return True


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register the Lovelace card resource in storage mode."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("_static_path_registered"):
        www_path = os.path.join(os.path.dirname(__file__), "www")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_URL_PATH, www_path, not hass.config.debug)]
        )
        domain_data["_static_path_registered"] = True

    lovelace_data = hass.data.get("lovelace")
    if not lovelace_data:
        # Lovelace not loaded
        return

    # Handle both old dict-style and new LovelaceData object
    if hasattr(lovelace_data, "resources"):
        resources = lovelace_data.resources
    elif isinstance(lovelace_data, dict):
        resources = lovelace_data.get("resources")
    else:
        return

    if not resources or not hasattr(resources, "async_create_item"):
        # Likely YAML mode
        return

    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    # Get version from manifest (use executor to avoid blocking)
    def _read_manifest_version():
        try:
            import json
            manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
                return manifest.get("version", "0.0.0")
        except Exception:
            return "0.0.0"

    version = await hass.async_add_executor_job(_read_manifest_version)

    # Append version to URL for cache busting
    card_url = f"{_CARD_RESOURCE_URL}?v={version}"

    existing = resources.async_items() or []
    for item in existing:
        if item.get(CONF_URL).startswith(_CARD_RESOURCE_URL):
            # If URL matches (ignoring version query param) but full URL is different, update it
            if item.get(CONF_URL) != card_url:
                await resources.async_update_item(item["id"], {CONF_RESOURCE_TYPE_WS: "module", CONF_URL: card_url})
                _LOGGER.info("Updated Lovelace resource to: %s", card_url)
            return

    await resources.async_create_item(
        {CONF_RESOURCE_TYPE_WS: "module", CONF_URL: card_url}
    )
    _LOGGER.info("Registered Lovelace resource: %s", card_url)


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

    async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Automatically register the Lovelace card resource (storage mode only).
    async def _on_homeassistant_started(event):
        """Handle Home Assistant started event."""
        await _async_register_lovelace_resource(hass)

    if hass.is_running:
        await _async_register_lovelace_resource(hass)
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_homeassistant_started)

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

    # Register list_fonts service for dynamic font discovery
    async def async_list_fonts(call):
        """List all available fonts in the fonts directory."""
        import os
        
        base_path = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(base_path, "fonts")
        
        def list_fonts_sync():
            if not os.path.exists(fonts_dir):
                return []
            
            result = []
            for filename in sorted(os.listdir(fonts_dir)):
                if filename.lower().endswith(('.otf', '.ttf', '.bdf')):
                    # Create display name from filename
                    name = filename.rsplit('.', 1)[0]
                    # Convert to readable format (e.g., "Rain-DRM3" -> "Rain DRM3")
                    display_name = name.replace('-', ' ').replace('_', ' ')
                    result.append({
                        "filename": filename,
                        "name": display_name
                    })
            return result

        fonts = await hass.async_add_executor_job(list_fonts_sync)
        
        return {"fonts": fonts}

    hass.services.async_register(
        DOMAIN, 
        "list_fonts", 
        async_list_fonts,
        supports_response="only"
    )

    # Initialize Design Storage
    from .storage import DesignStorage
    storage = DesignStorage(hass)
    await storage.async_load()
    hass.data[DOMAIN]["storage"] = storage

    # Register WebSocket commands
    from homeassistant.components import websocket_api
    
    @websocket_api.websocket_command({
        "type": "idotmatrix/list_designs",
    })
    @websocket_api.async_response
    async def websocket_list_designs(hass, connection, msg):
        """List all designs."""
        designs = storage.get_designs()
        connection.send_result(msg["id"], {"designs": designs})



    @websocket_api.websocket_command({
        "type": "idotmatrix/save_design",
        "name": str,
        "layers": list,
    })
    @websocket_api.async_response
    async def websocket_save_design(hass, connection, msg):
        """Save a design."""
        storage.save_design(msg["name"], msg["layers"])
        connection.send_result(msg["id"])

    @websocket_api.websocket_command({
        "type": "idotmatrix/delete_design",
        "name": str,
    })
    @websocket_api.async_response
    async def websocket_delete_design(hass, connection, msg):
        """Delete a design."""
        if storage.delete_design(msg["name"]):
            connection.send_result(msg["id"])
        else:
            connection.send_error(msg["id"], "design_not_found", "Design not found")

    websocket_api.async_register_command(hass, websocket_list_designs)

    websocket_api.async_register_command(hass, websocket_save_design)
    websocket_api.async_register_command(hass, websocket_delete_design)


    async def async_set_saved_design(call):
        """Set a saved design by name."""
        design_name = call.data.get("name")
        design = storage.get_design(design_name)
        
        if not design:
            _LOGGER.error(f"Design '{design_name}' not found")
            return

        face_config = {"layers": design["layers"]}
        
        # Apply to all coordinators (similar logic to set_face)
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_set_face_config(face_config)

    hass.services.async_register(DOMAIN, "set_saved_design", async_set_saved_design)

    # Register display_gif service
    async def async_display_gif(call):
        """Handle the display_gif service call."""
        path = call.data.get("path")
        rotation_interval = call.data.get("rotation_interval", 5)

        if not path:
            _LOGGER.error("display_gif service requires 'path' parameter")
            return

        # Apply to all coordinators
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_display_gif(
                    path=path,
                    rotation_interval=rotation_interval,
                )

    hass.services.async_register(DOMAIN, "display_gif", async_display_gif)

    # Register stop_gif_rotation service
    async def async_stop_gif_rotation(call):
        """Handle the stop_gif_rotation service call."""
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_stop_gif_rotation()

    hass.services.async_register(DOMAIN, "stop_gif_rotation", async_stop_gif_rotation)

    # Register show_weather service
    async def async_show_weather(call):
        """Handle the show_weather service call."""
        cfg = {
            "weather_entity": call.data.get("weather_entity", "weather.openweathermap"),
            "condition_entity": call.data.get("condition_entity"),
            "temperature_entity": call.data.get("temperature_entity"),
            "humidity_entity": call.data.get("humidity_entity"),
            "wind_entity": call.data.get("wind_entity"),
            "high_entity": call.data.get("high_entity"),
            "low_entity": call.data.get("low_entity"),
            "pixel_size": call.data.get("pixel_size"),
        }
        follow = call.data.get("follow", True)

        if not any(
            cfg.get(k) for k in ("weather_entity", "condition_entity", "temperature_entity")
        ):
            _LOGGER.error(
                "show_weather requires at least one of: weather_entity, "
                "condition_entity, temperature_entity"
            )
            return

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                if follow:
                    await coordinator.async_start_weather_mode(cfg)
                else:
                    await coordinator.async_show_weather(cfg, force=True)

    hass.services.async_register(DOMAIN, "show_weather", async_show_weather)

    # Register stop_weather service
    async def async_stop_weather(call):
        """Handle the stop_weather service call."""
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_stop_weather_mode()

    hass.services.async_register(DOMAIN, "stop_weather", async_stop_weather)

    # Register show_bitcoin service
    async def async_show_bitcoin(call):
        """Handle the show_bitcoin service call."""
        cfg = {
            "price_entity": call.data.get("price_entity", "sensor.bitcoin_price"),
            "change_entity": call.data.get("change_entity"),
            "pixel_size": call.data.get("pixel_size"),
        }
        follow = call.data.get("follow", True)

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                if follow:
                    await coordinator.async_start_bitcoin_mode(cfg)
                else:
                    await coordinator.async_show_bitcoin(cfg, force=True)

    hass.services.async_register(DOMAIN, "show_bitcoin", async_show_bitcoin)

    # Register stop_bitcoin service
    async def async_stop_bitcoin(call):
        """Handle the stop_bitcoin service call."""
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_stop_bitcoin_mode()

    hass.services.async_register(DOMAIN, "stop_bitcoin", async_stop_bitcoin)

    # Register show_co2 service
    async def async_show_co2(call):
        """Handle the show_co2 service call."""
        cfg = {
            "co2_entity": call.data.get("co2_entity", "sensor.aranet4_19d46_carbon_dioxide"),
            "pixel_size": call.data.get("pixel_size"),
        }
        follow = call.data.get("follow", True)

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                if follow:
                    await coordinator.async_start_co2_mode(cfg)
                else:
                    await coordinator.async_show_co2(cfg, force=True)

    hass.services.async_register(DOMAIN, "show_co2", async_show_co2)

    # Register stop_co2 service
    async def async_stop_co2(call):
        """Handle the stop_co2 service call."""
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_stop_co2_mode()

    hass.services.async_register(DOMAIN, "stop_co2", async_stop_co2)

    # Register show_power service
    async def async_show_power(call):
        """Handle the show_power service call."""
        cfg = {
            "power_entity": call.data.get(
                "power_entity",
                "sensor.shellypro3em_0cb815fd2f44_total_active_power",
            ),
            "pixel_size": call.data.get("pixel_size"),
        }
        follow = call.data.get("follow", True)

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                if follow:
                    await coordinator.async_start_power_mode(cfg)
                else:
                    await coordinator.async_show_power(cfg, force=True)

    hass.services.async_register(DOMAIN, "show_power", async_show_power)

    # Register stop_power service
    async def async_stop_power(call):
        """Handle the stop_power service call."""
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, IDotMatrixCoordinator):
                await coordinator.async_stop_power_mode()

    hass.services.async_register(DOMAIN, "stop_power", async_stop_power)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        if hasattr(coordinator, "_clear_face_tracking"):
            coordinator._clear_face_tracking()
        if hasattr(coordinator, "async_stop_gif_rotation"):
            await coordinator.async_stop_gif_rotation()
        if hasattr(coordinator, "async_stop_weather_mode"):
            await coordinator.async_stop_weather_mode()
        if hasattr(coordinator, "async_stop_bitcoin_mode"):
            await coordinator.async_stop_bitcoin_mode()
        if hasattr(coordinator, "async_stop_co2_mode"):
            await coordinator.async_stop_co2_mode()
        if hasattr(coordinator, "async_stop_power_mode"):
            await coordinator.async_stop_power_mode()
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
