"""Select platform for iDotMatrix."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import EntityCategory
from .const import DOMAIN, ANIMATION_MODES, COLOR_MODES
from .entity import IDotMatrixEntity
from .client.modules.clock import Clock
from .client.modules.effect import Effect
import os

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
        IDotMatrixFont(coordinator, entry),
        IDotMatrixTextAnimation(coordinator, entry),
        IDotMatrixTextColorMode(coordinator, entry),
        IDotMatrixScreenSize(coordinator, entry),
    ])

class IDotMatrixClockFace(IDotMatrixEntity, SelectEntity):
    """Representation of the Clock Face selector."""

    _attr_icon = "mdi:clock-digital"
# ... (rest of file)

class IDotMatrixScreenSize(IDotMatrixEntity, SelectEntity):
    """Selector for Screen Size."""
    _attr_icon = "mdi:monitor-screenshot"
    _attr_name = "Screen Size"
    _attr_options = ["32x32", "16x16"]
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        size = self.coordinator.text_settings.get("screen_size", 32)
        self._attr_current_option = "32x32" if size == 32 else "16x16"

    @property
    def unique_id(self) -> str:
        return f"{self._mac}_screen_size"

    async def async_select_option(self, option: str) -> None:
        """Select screen size."""
        self.coordinator.text_settings["screen_size"] = 32 if option == "32x32" else 16
        self._attr_current_option = option
        self.async_write_ha_state()
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



class IDotMatrixFont(IDotMatrixEntity, SelectEntity):
    """Selector for Text Font."""
    _attr_icon = "mdi:format-font"
    _attr_name = "Text Font"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_options = self._get_fonts()
        # Set default option to first available or saved
        current = self.coordinator.text_settings.get("font", "Rain-DRM3.otf")
        if current in self._attr_options:
            self._attr_current_option = current
        elif self._attr_options:
            self._attr_current_option = self._attr_options[0]

    @property
    def unique_id(self) -> str:
        return f"{self._mac}_text_font"

    def _get_fonts(self) -> list[str]:
        """Scan fonts directory."""
        # Locate fonts dir relative to this file
        # select.py -> custom_components/idotmatrix/select.py
        # fonts -> custom_components/idotmatrix/fonts/
        base_path = os.path.dirname(os.path.abspath(__file__))
        fonts_path = os.path.join(base_path, "fonts")
        options = []
        if os.path.isdir(fonts_path):
            for file in os.listdir(fonts_path):
                if file.endswith((".otf", ".ttf")):
                    options.append(file)
        return sorted(options) if options else ["Rain-DRM3.otf"]

    async def async_select_option(self, option: str) -> None:
        """Select font."""
        self.coordinator.text_settings["font"] = option
        self._attr_current_option = option
        self.async_write_ha_state()

class IDotMatrixTextAnimation(IDotMatrixEntity, SelectEntity):
    """Selector for Text Animation Mode."""
    _attr_icon = "mdi:animation"
    _attr_name = "Text Animation"
    _attr_options = list(ANIMATION_MODES.keys())
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        current_val = self.coordinator.text_settings.get("animation_mode", 1)
        # Find key for value
        for key, val in ANIMATION_MODES.items():
            if val == current_val:
                self._attr_current_option = key
                break

    @property
    def unique_id(self) -> str:
        return f"{self._mac}_text_animation"

    async def async_select_option(self, option: str) -> None:
        """Select animation."""
        self.coordinator.text_settings["animation_mode"] = ANIMATION_MODES[option]
        self._attr_current_option = option
        self.async_write_ha_state()

class IDotMatrixTextColorMode(IDotMatrixEntity, SelectEntity):
    """Selector for Text Color Mode."""
    _attr_icon = "mdi:palette"
    _attr_name = "Text Color Mode"
    _attr_options = list(COLOR_MODES.keys())
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        current_val = self.coordinator.text_settings.get("color_mode", 1)
        for key, val in COLOR_MODES.items():
            if val == current_val:
                self._attr_current_option = key
                break

    @property
    def unique_id(self) -> str:
        return f"{self._mac}_text_color_mode"

    async def async_select_option(self, option: str) -> None:
        """Select color mode."""
        self.coordinator.text_settings["color_mode"] = COLOR_MODES[option]
        self._attr_current_option = option
        self.async_write_ha_state()
