"""Text platform for iDotMatrix."""
from __future__ import annotations

import os
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageFont

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IDotMatrixEntity
from .client.modules.image import Image as IDMImage
from .client.modules.text import Text

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iDotMatrix text."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IDotMatrixText(coordinator, entry),
    ])

class IDotMatrixText(IDotMatrixEntity, TextEntity):
    """Representation of the Text input."""

    _attr_icon = "mdi:form-textbox"
    _attr_name = "Display Text"
    _attr_native_value = None
    
    @property
    def unique_id(self) -> str:
        return f"{self._mac}_display_text"

    @property
    def native_value(self) -> str | None:
        """Return the value reported by the text entity."""
        return self._attr_native_value

    async def async_set_value(self, value: str) -> None:
        """Change the text value."""
        if value:
            settings = self.coordinator.text_settings
            
            if settings.get("multiline", False):
                await self._set_multiline_text(value, settings)
            else:
                await Text().setMode(
                    text=value,
                    font_size=16, 
                    font_path=settings.get("font"),
                    text_mode=settings.get("animation_mode", 1),
                    speed=settings.get("speed", 80),
                    text_color_mode=settings.get("color_mode", 1),
                    text_color=tuple(settings.get("color", (255, 0, 0))),
                    text_bg_mode=0,
                    text_bg_color=(0, 0, 0),
                    spacing=settings.get("spacing", 1),
                    proportional=settings.get("proportional", True)
                )
            self._attr_native_value = value
            self.async_write_ha_state()

    async def _set_multiline_text(self, text: str, settings: dict) -> None:
        """Generate an image from text and upload it."""
        screen_size = settings.get("screen_size", 32)
        font_name = settings.get("font")
        color = tuple(settings.get("color", (255, 0, 0)))
        
        # Resolve font path - duplicate logic from text.py module
        base_path = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(base_path, "fonts")
        font_path = os.path.join(fonts_dir, "Rain-DRM3.otf")
        
        if font_name:
            if not os.path.isabs(font_name):
                 potential = os.path.join(fonts_dir, font_name)
                 if os.path.exists(potential):
                     font_path = potential
            elif os.path.exists(font_name):
                font_path = font_name
                
        # Create image
        image = Image.new("RGB", (screen_size, screen_size), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Load font - size 10 usually fits well on 32x32 for multiline
        # Adjust size based on screen?
        font_size = 10 if screen_size == 32 else 8
        try:
            font = ImageFont.truetype(font_path, font_size)
        except:
            font = ImageFont.load_default()

        # Wrap text logic
        # Approx chars per line?
        avg_char_width = 4
        wrapper = textwrap.TextWrapper(width=max(1, screen_size // avg_char_width))
        lines = wrapper.wrap(text)
        
        # Draw lines
        y = 0
        line_height = font_size + 1
        for line in lines:
            if y >= screen_size: break
            draw.text((0, y), line, font=font, fill=color)
            y += line_height
            
        # Save to temp file and upload
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image.save(tmp.name)
            tmp_path = tmp.name
            
        try:
            # Upload processed
            await IDMImage().uploadProcessed(tmp_path, pixel_size=screen_size)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
