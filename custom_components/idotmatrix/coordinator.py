"""DataUpdateCoordinator for iDotMatrix."""
from __future__ import annotations

import logging
import asyncio
import re
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .client.connectionManager import ConnectionManager
from .client.modules.text import Text
from .client.modules.image import Image as IDMImage
from .client.modules.clock import Clock


from homeassistant.helpers import template
from homeassistant.util import dt as dt_util

import os
import tempfile
from PIL import Image, ImageDraw, ImageFont

from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "idotmatrix_settings_"

# Regex to extract entity IDs from Jinja templates
ENTITY_REGEX = re.compile(r"states\(['\"]([a-z_]+\.[a-z0-9_]+)['\"]\)")


class IDotMatrixCoordinator(DataUpdateCoordinator):
    """Class to manage fetching iDotMatrix data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry.entry_id}")
        self._entity_unsubs: list = []  # Entity state change unsubscribe callbacks
        
        # Shared settings for Text entity
        self.text_settings = {
            "current_text": "",   # The actual text content
            "font": "Rain-DRM3.otf",
            "animation_mode": 1,  # Marquee
            "speed": 80,
            "color_mode": 1,      # Single Color
            "color": [255, 0, 0], # Red default
            "spacing": 1,         # Horizontal Spacing (pixels)
            "spacing_y": 1,       # Vertical Spacing (pixels)
            "proportional": True, # Use proportional font rendering
            "blur": 5,            # Text Blur/Antialiasing (0=Sharp, 5=Smooth)
            "font_size": 10,      # Font Size (pixels)
            "multiline": False,   # Wrap text as image
            "screen_size": 32,    # 32x32 or 16x16
            "brightness": 128,    # 0-255 (mapped to 5-100)
            "clock_style": 0,     # Default style index
            "clock_date": True,   # Show date
            "clock_format": "24h",# 12h or 24h
            "fun_text_delay": 0.4,# Fun Text delay in seconds
            "autosize": False,    # Auto-scale font to fit screen
            "mode": "basic",      # basic | advanced
            "layers": [],         # List of layers for advanced mode
        }
        
    async def async_set_face_config(self, face_config: dict) -> None:
        """Update face configuration from service and set up entity tracking."""
        layers = face_config.get("layers", [])
        self.text_settings["mode"] = "advanced"
        self.text_settings["layers"] = layers
        
        # Cancel previous entity listeners
        for unsub in self._entity_unsubs:
            unsub()
        self._entity_unsubs = []
        
        # Extract entity IDs from layers
        entities_to_track = set()
        for layer in layers:
            # Direct entity reference
            if entity := layer.get("entity"):
                entities_to_track.add(entity)
            
            # Entity IDs in templates (e.g., {{ states('sensor.temp') }})
            if content := layer.get("content"):
                matches = ENTITY_REGEX.findall(content)
                entities_to_track.update(matches)
            if tpl := layer.get("template"):
                matches = ENTITY_REGEX.findall(tpl)
                entities_to_track.update(matches)
        
        # Set up state change listeners
        if entities_to_track:
            _LOGGER.info(f"[iDotMatrix] Tracking entities for auto-update: {entities_to_track}")
            unsub = async_track_state_change_event(
                self.hass,
                list(entities_to_track),
                self._on_entity_state_change
            )
            self._entity_unsubs.append(unsub)
        
        # Trigger initial update
        await self.async_update_device()

    @callback
    def _on_entity_state_change(self, event: Event) -> None:
        """Handle entity state change by re-rendering face."""
        entity_id = event.data.get("entity_id")
        _LOGGER.debug(f"[iDotMatrix] Entity {entity_id} changed, re-rendering face")
        # Schedule async update
        self.hass.async_create_task(self.async_update_device())


    async def _render_face(self, layers: list, screen_size: int) -> Image.Image:
        """Render the advanced display face."""
        # Create base canvas
        canvas = Image.new("RGB", (screen_size, screen_size), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        
        # Load Fonts Cache (simple dict for now)
        # We can reuse the font loading logic or abstract it
        
        for layer in layers:
            # check conditions
            if (cond_tpl := layer.get("condition_template")):
                try:
                    tpl = template.Template(cond_tpl, self.hass)
                    if not tpl.async_render(parse_result=False):
                        continue
                except Exception as e:
                    _LOGGER.warning(f"Error evaluating condition '{cond_tpl}': {e}")
                    continue

            l_type = layer.get("type", "text")
            x = layer.get("x", 0)
            y = layer.get("y", 0)
            
            if l_type == "text":
                content = ""
                
                # Priority: content (already resolved) > entity > template
                if layer.get("content"):
                    # Content already resolved by frontend
                    content = layer.get("content", "")
                elif entity_id := layer.get("entity"):
                    # Get state from entity
                    if state := self.hass.states.get(entity_id):
                        content = state.state
                    else:
                        content = "N/A"
                elif layer.get("is_template", False) or layer.get("template"):
                    # Render Jinja template
                    tpl_str = layer.get("template") or ""
                    try:
                        tpl = template.Template(tpl_str, self.hass)
                        content = tpl.async_render(parse_result=False)
                    except Exception as e:
                        content = "ERR"
                        _LOGGER.warning(f"Error evaluating text template: {e}")
                
                # Skip empty content
                if not content:
                    continue
                
                # Render Text using LAYER settings only (not global text_settings)
                color = tuple(layer.get("color", [255, 255, 255]))
                font_name = layer.get("font", "Rain-DRM3.otf")
                font_size = int(layer.get("font_size", 10))
                spacing_x = int(layer.get("spacing_x", 1))
                spacing_y = int(layer.get("spacing_y", 1))
                
                # Resolve font path
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
                        
                try:
                    font = ImageFont.truetype(font_path, font_size)
                except:
                    font = ImageFont.load_default()
                
                # Character-by-character rendering with custom spacing
                current_x = x
                for char in str(content):
                    draw.text((current_x, y), char, font=font, fill=color)
                    # Get character width
                    try:
                        bbox = font.getbbox(char)
                        char_width = bbox[2] - bbox[0] if bbox else font.getlength(char)
                    except:
                        char_width = font_size // 2
                    current_x += int(char_width) + spacing_x

            elif l_type == "image":
                 image_path = layer.get("image_path")
                 if not image_path: continue
                 
                 # Resolve path (Check 'www' or absolute)
                 if not os.path.isabs(image_path):
                     # Default to config/www/idotmatrix/
                     base_www = self.hass.config.path("www", "idotmatrix")
                     potential = os.path.join(base_www, image_path)
                     if os.path.exists(potential):
                         image_path = potential
                     else:
                         # Try locally in integration (bundled icons?)
                         local = os.path.join(os.path.dirname(__file__), "images", image_path)
                         if os.path.exists(local):
                             image_path = local
                             
                 if os.path.exists(image_path):
                     try:
                         with Image.open(image_path) as img:
                             img = img.convert("RGBA")
                             # Resize if size provided
                             w = layer.get("width")
                             h = layer.get("height")
                             if w and h:
                                 img = img.resize((int(w), int(h)))
                             
                             canvas.paste(img, (x, y), img)
                     except Exception as e:
                         _LOGGER.error(f"Failed to load image layer {image_path}: {e}")

        return canvas

    async def async_load_settings(self) -> None:
        """Load settings from storage."""
        if (data := await self._store.async_load()):
            _LOGGER.debug(f"Loaded persist settings: {data}")
            self.text_settings.update(data)

    async def async_save_settings(self) -> None:
        """Save settings to storage."""
        await self._store.async_save(self.text_settings)

    async def _async_update_data(self):
        """Fetch data from the device."""
        return {"connected": True}

    async def async_update_device(self) -> None:
        """Send current configuration to the device."""
        text = self.text_settings.get("current_text", "")
        settings = self.text_settings
        
        if settings.get("mode") == "advanced":
             # Advanced Rendering
             screen_size = int(settings.get("screen_size", 32))
             image = await self._render_face(settings.get("layers", []), screen_size)
             
             # Save image in executor to avoid blocking
             with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
             
             await self.hass.async_add_executor_job(image.save, tmp_path)
             
             try:
                await IDMImage().setMode(1)
                await IDMImage().uploadProcessed(tmp_path, pixel_size=screen_size)
             finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
             
        elif text:
            # Render Text (Basic Mode)
            if settings.get("multiline", False):
                await self._set_multiline_text(text, settings)
            else:
                # Standard Scroller
                await Text().setMode(
                    text=text,
                    font_size=int(settings.get("font_size", 10)), 
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
        else:
            # Render Clock (Default fallback)
            # Use self.text_settings for clock config
            # Retrieve color and format
            c = settings.get("color", [255, 0, 0])
            h24 = settings.get("clock_format", "24h") == "24h"
            
            style = settings.get("clock_style", 0)
            show_date = settings.get("clock_date", True)
            
                
            await Clock().setMode(
                style=style,
                visibleDate=show_date,
                hour24=h24,
                r=c[0],
                g=c[1],
                b=c[2]
            )
            
        # Notify listeners to update UI states
        self.async_set_updated_data(self.data)
        
        # Save persistence
        await self.async_save_settings()

    async def _set_multiline_text(self, text: str, settings: dict) -> None:
        """Generate an image from text and upload it."""
        screen_size = int(settings.get("screen_size", 32))
        font_name = settings.get("font")
        color = tuple(settings.get("color", (255, 0, 0)))
        spacing = int(settings.get("spacing", 1))
        spacing_y = int(settings.get("spacing_y", 1))
        blur = int(settings.get("blur", 5))
        
        # Resolve font path
        # Note: __file__ here is coordinator.py, so we need to adjust path logic
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
                
        # Determine font size and max scanning range if autosize is on
        initial_font_size = int(settings.get("font_size", 10))
        target_font_size = initial_font_size
        
        if settings.get("autosize", False):
            # Start from user's size or 32, whichever is reasonable, and shrink until fit
            # Or always start large? Let's start from current size and shrink, 
            # OR start from 32 (max) to find biggest possible fit? "Perfectly" usually means "Maximize".
            # Let's try to Maximize: Start at 32 (or screen_size) down to 6.
            start_size = screen_size
            end_size = 6
        else:
            # Single pass
            start_size = initial_font_size
            end_size = initial_font_size

        font_path_to_use = font_path

        # Iterative resizing loop
        for s in range(start_size, end_size - 1, -1):
            target_font_size = s
            try:
                if font_path_to_use.lower().endswith(".bdf"):
                     font = ImageFont.load(font_path_to_use)
                     # BDF fonts are fixed size, autosize won't work well unless we pick different files.
                     # For now, skip autosize on BDF or just use it as is.
                else:
                     font = ImageFont.truetype(font_path_to_use, s)
            except:
                font = ImageFont.load_default()

            # Pixel-based Word Wrapping (Simulated for check)
            words = text.split(' ')
            lines = []
            current_line = []
            
            def get_word_width(word):
                if not word: return 0
                w = 0
                for i, char in enumerate(word):
                    bbox = font.getbbox(char)
                    char_w = (bbox[2] - bbox[0]) if bbox else font.getlength(char)
                    w += char_w + spacing
                return w - spacing
            
            # Recalculate space width for this font size
            try:
                space_bbox = font.getbbox(" ")
                space_w = (space_bbox[2] - space_bbox[0]) if space_bbox else font.getlength(" ")
            except:
                space_w = 4
            space_width = space_w + spacing
            if space_width < 1: space_width = 1
            
            current_line_width = 0
            
            for word in words:
                word_width = get_word_width(word)
                if current_line_width + word_width <= screen_size:
                    current_line.append(word)
                    current_line_width += word_width + space_width
                else:
                    if current_line:
                        lines.append(current_line)
                        current_line = []
                        current_line_width = 0
                    current_line.append(word)
                    current_line_width = word_width + space_width
            if current_line:
                lines.append(current_line)
            
            # Check Height
            ascent, descent = font.getmetrics()
            line_height = ascent + descent + spacing_y
            total_height = len(lines) * line_height
            
            # If autosize is OFF, we accept the first pass (initial_font_size)
            if not settings.get("autosize", False):
                break
                
            # If autosize is ON, check if it fits
            if total_height <= screen_size and all(get_word_width(w) <= screen_size for w in words):
                 # Fits!
                 break
        
        # Draw lines using chosen target_font_size
        text_layer = Image.new("RGBA", (screen_size, screen_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)
        
        y = (screen_size - total_height) // 2 if settings.get("autosize", False) else 0 # Center vertically if autosizing
        if y < 0: y = 0
        
        for line_words in lines:
            if y >= screen_size: break
            # Center Horizontally?
            # Standard wrapper is left aligned. Perfect fit usually implies Center/Center.
            # Let's calculate line width for centering
            line_w = 0
            for i, w in enumerate(line_words):
                 line_w += get_word_width(w)
                 if i < len(line_words) - 1: line_w += space_width
            
            x = (screen_size - line_w) // 2 if settings.get("autosize", False) else 0
            if x < 0: x = 0
            
            for i, word in enumerate(line_words):
                for char in word:
                    if x >= screen_size: break
                    draw.text((x, y), char, font=font, fill=(255, 255, 255, 255))
                    bbox = font.getbbox(char)
                    char_w = (bbox[2] - bbox[0]) if bbox else font.getlength(char)
                    x += char_w + spacing
                if i < len(line_words) - 1:
                     x += space_width
            y += line_height
            
        if blur < 5:
             r, g, b, a = text_layer.split()
             gain = 1.0 + ((5 - blur) * 2.0) 
             def apply_contrast(p):
                 v = (p - 128) * gain + 128
                 return max(0, min(255, int(v)))
             a = a.point(apply_contrast)
             text_layer.putalpha(a)
             
        final_image = Image.new("RGB", (screen_size, screen_size), (0, 0, 0))
        r, g, b, a = text_layer.split()
        colored_text = Image.new("RGB", (screen_size, screen_size), color)
        final_image.paste(colored_text, mask=a)
        
        image = final_image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image.save(tmp.name)
            tmp_path = tmp.name
        try:
            await IDMImage().setMode(1)
            await IDMImage().uploadProcessed(tmp_path, pixel_size=screen_size)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
