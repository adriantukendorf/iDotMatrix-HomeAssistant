# iDotMatrix Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/tukies/iDotMatrix-HomeAssistant)](https://github.com/tukies/iDotMatrix-HomeAssistant/releases)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-yellow.svg)](https://buymeacoffee.com/tukie)

A fully featured, modern Home Assistant integration for **iDotMatrix** pixel art displays. 

Connects directly to your device via Bluetooth (native or proxy) without any cloud dependencies. Unlock the full potential of your display with advanced animations, typography controls, and "Party Mode" features.

---

## Features

- **Instant Bluetooth Connectivity**: Supports native adapters and ESPHome Bluetooth Proxies for rock-solid connections.
- **Advanced Text Engine**: 
    - Full control over Font, Color, Speed, and Animation Mode.
    - **Pixel Fonts**: Bundled fonts include VT323, Press Start 2P, Rain DRM3, and classic BDF bitmap sets.
    - **Typography Controls**: Adjust letter spacing (horizontal/vertical), blur/sharpness, and font size.
- **Fun Text (Party Mode)**: 
    - Animates messages word-by-word with random bright colors.
    - Adjustable delay for perfect timing.
- **Autosize Perfect Fit**: 
    - Automatically scales text to fit the screen bounds, centering it for a clean look.
- **Clock Control**: 
    - Syncs time automatically.
    - Customizable 12h/24h formats, date display, and colors.
- **Designer Card (Layered Templates)**:
    - Build multi-layer faces using text + icon templates.
    - Save/load designs and auto-refresh with a trigger entity (e.g., `sensor.time`).
- **Icons**:
    - Render `mdi:` icons directly.
    - Use `/local/...png` or URL icons for custom sets. SVG requires Cairo (optional).
- **Weather Dashboard**:
    - Animated pixel-art weather display: condition icon, temperature, high/low, humidity and wind.
    - Sources data from any `weather.*` entity, individual sensors (local weather stations!), or a mix.
    - Auto-updates when conditions change.
- **Bitcoin Ticker**:
    - The classic Bitcoin logo with the live USD price below it.
    - Price colored by direction of the last move; optional 24h change row.
    - Auto-updates when the price sensor changes.
- **Device Control**:
    - Turn On/Off, set Brightness, color, and screen size (16x16 / 32x32 / 64x64).

---

## Installation

### Option 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Go to **Integrations** > **Triple Dots** > **Custom Repositories**.
3. Add `https://github.com/tukies/iDotMatrix-HomeAssistant` as an **Integration**.
4. Click **Download**.
5. Restart Home Assistant.

### Option 2: Manual
1. Download the `custom_components/idotmatrix` folder from this repository.
2. Copy it to your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. Go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **iDotMatrix**.
3. The integration will automatically discover nearby devices. Select your device.
    - *Note: Ensure your device is powered on and not connected to the phone app.*

---

## Lovelace Card (Designer)

The integration auto-registers the card in Lovelace storage mode. If you use YAML mode or prefer manual setup:
- URL: `/idotmatrix/idotmatrix-card.js`
- Type: `JavaScript Module`

Add a card to your dashboard:
   ```yaml
   type: custom:idotmatrix-card
   title: iDotMatrix Designer
   ```
Set `Display Mode` on the device page to **Display design from the Card**.

---

## Usage Guide

### Display Mode
Pick what the device shows from the device page:
- **Entity**: `select.<device>_display_mode`
- **Options**: Display Text Field / Display design from the Card
- **Tip**: Entity IDs are per-device, e.g., `text.idm_3fb639_display_text`.

### Text Control
Control the scrolling text on your device using the `Display Text` entity.
- **Entity**: `text.<device>_display_text`
- **Actions**: Type any text to update the display immediately.
- **Settings**: Use the configuration entities (sliders/selects) to adjust:
    - **Font**: Choose from installed pixel-perfect fonts.
    - **Speed**: Scroll speed (1-100).
    - **Color**: Full RGB control via `light.<device>_panel_colour`.
    - **Spacing**: Tweak kerning with "Text Spacing".

### Fun Text (Party Mode)
Want to spice things up? Use the Fun Text entity!
- **Entity**: `text.<device>_fun_text`
- **How it works**:
    1. Enter a phrase like "HAPPY NEW YEAR".
    2. The display shows one word at a time (split on spaces).
    3. Each word gets a **random bright color** from a fixed palette.
    4. The last word remains on screen (no final full‑sentence render).
- **Control**: Adjust the delay between words with the **Fun Text Delay** slider (`number.<device>_fun_text_delay`).

### Autosize (Perfect Fit)
Stop guessing font sizes. Let the integration do the math.
- **Entity**: `switch.<device>_text_perfect_fit_autosize`
- **How it works**:
    - **ON**: The integration iteratively resizes your text (shrinking from max size) until it fits perfectly within the screen capabilities 
    - **OFF**: Standard scrolling or manual font size.

### Designer Card (Layers + Icons)
- Use the Designer card to build a layered face.
- Each layer supports:
  - **Template**: Jinja template for text
  - **Icon Template**: Jinja template that returns an icon string (e.g., `mdi:floor-lamp`)
  - **Icon Size**: Pixel size for the icon
  - **X/Y, font, spacing, blur, color**
- To combine icons and text, use separate layers and offset X/Y.

Examples:
- Icon based on entity state:
  ```
  {{ 'mdi:floor-lamp' if is_state('light.lamp', 'on') else 'mdi:floor-lamp-outline' }}
  ```
- Use an entity icon directly:
  ```
  {{ state_attr('light.lamp', 'icon') }}
  ```
- Custom PNG icon:
  ```
  /local/icons/alert.png
  ```

### Clock & Time
- **Sync Time**: Press `button.<device>_sync_time` to sync the device clock to Home Assistant's time.
- **Formats**: Toggle `select.<device>_clock_format` (12h/24h) and `switch.<device>_clock_show_date`.

### GIF Animations

Display animated GIFs on your device — single files or rotating carousels.

**Single GIF:**
```yaml
action: idotmatrix.display_gif
data:
  path: /config/www/idotmatrix/gifs/Pac-man.gif
```

**Carousel (folder of GIFs):**
```yaml
action: idotmatrix.display_gif
data:
  path: /config/www/idotmatrix/gifs
  rotation_interval: 10
```

- `path`: A single `.gif` file or a folder containing GIF files.
- `rotation_interval`: How many seconds each GIF displays before advancing (1-255, default 5). The device handles rotation natively in hardware.
- When given a folder, up to 12 random GIFs are uploaded as a batch and the device loops through them automatically.
- To stop a running carousel: call `idotmatrix.stop_gif_rotation`.

**Preparing your GIFs:**

The display is 64x64 pixels. Any standard GIF works — the device handles GIF89a, animated GIFs, transparency, and all standard features. For best results, resize your source GIFs to 64x64 before uploading to save transfer time:

```bash
# Requires: gifsicle (apt install gifsicle / brew install gifsicle)
# Resize all GIFs in a folder to 64x64
for gif in *.gif; do
  gifsicle --resize 64x64 -O3 "$gif" -o "optimized/$gif"
done
```

Larger files work fine — they just take longer to transfer over Bluetooth. A 60KB GIF takes roughly 10-15 seconds through a proxy.

**Automation examples:**

Start the GIF carousel on HA boot (with a 1-minute delay for Bluetooth to initialize):
```yaml
automation:
  - alias: "Start GIF Rotation on Boot"
    triggers:
      - trigger: homeassistant
        event: start
    actions:
      - delay: "00:01:00"
      - action: idotmatrix.display_gif
        data:
          path: /config/www/idotmatrix/gifs
          rotation_interval: 60
```

Restart the carousel every morning (in case it stopped overnight):
```yaml
  - alias: "Start GIF Rotation in Morning"
    triggers:
      - trigger: time
        at: "06:05:00"
    actions:
      - action: idotmatrix.display_gif
        data:
          path: /config/www/idotmatrix/gifs
          rotation_interval: 60
```

Watchdog — re-upload a fresh batch every hour to keep things interesting:
```yaml
  - alias: "GIF Rotation Watchdog"
    triggers:
      - trigger: time_pattern
        hours: "/1"
    actions:
      - action: idotmatrix.display_gif
        data:
          path: /config/www/idotmatrix/gifs
          rotation_interval: 60
```

### Weather Dashboard

`idotmatrix.show_weather` renders an animated weather dashboard entirely on the
fly — pixel-art condition icons (rotating sun rays, falling rain, lightning
flashes, twinkling stars), a big color-coded temperature, today's high/low,
humidity and wind — and uploads it as a looping GIF using the reliable
single-upload protocol.

Simplest form — everything from one weather entity (condition, temperature,
humidity, wind, and forecast high/low):

```yaml
action: idotmatrix.show_weather
data:
  weather_entity: weather.openweathermap
```

Mix and match sources. Sensor overrides win over the weather entity, so you can
take the condition/forecast from OpenWeatherMap but show the *actual*
temperature and humidity from a backyard weather station:

```yaml
action: idotmatrix.show_weather
data:
  weather_entity: weather.openweathermap
  temperature_entity: sensor.gw2000b_outdoor_temperature
  humidity_entity: sensor.gw2000b_humidity
```

The condition can also come from a text sensor. OpenWeatherMap description
strings like `broken clouds` or `light rain` are mapped to the right icon
automatically, and clear skies switch to a moon-and-stars icon after sunset:

```yaml
action: idotmatrix.show_weather
data:
  condition_entity: sensor.openweathermap_weather
  temperature_entity: sensor.gw2000b_outdoor_temperature
  humidity_entity: sensor.gw2000b_humidity
```

By default the dashboard **follows the weather**: it re-renders and re-uploads
whenever a source entity changes (debounced, and only when a displayed value
actually changes — a 0.1° wiggle won't touch the device). Forecast high/low is
refreshed every 15 minutes. Stop it with:

```yaml
action: idotmatrix.stop_weather
```

Options:

| Field | Description |
| --- | --- |
| `weather_entity` | Base `weather.*` entity (condition, temp, humidity, wind, forecast high/low). |
| `condition_entity` | Override the condition from a sensor (HA conditions or free text like "light rain"). |
| `temperature_entity` / `humidity_entity` / `wind_entity` | Override individual values, e.g. from a local station. |
| `high_entity` / `low_entity` | Override today's forecast high/low. |
| `pixel_size` | `64` (default, full dashboard) or `32` (compact layout). |
| `follow` | `true` (default) keeps it updated; `false` renders once. |

Starting weather mode stops any running GIF rotation, and calling
`idotmatrix.display_gif` stops weather mode — the two won't fight over the
display.

### Bitcoin Ticker

`idotmatrix.show_bitcoin` renders the classic Bitcoin logo with the
current USD price below it. The price is colored green or red by the direction
of its last move, and an optional second row shows the 24h change percentage.

```yaml
action: idotmatrix.show_bitcoin
data:
  price_entity: sensor.bitcoin_price
```

With a 24h change sensor:

```yaml
action: idotmatrix.show_bitcoin
data:
  price_entity: sensor.bitcoin_price
  change_entity: sensor.bitcoin_24h_change
```

Like weather mode it **follows the price** by default: updates are debounced
and only re-uploaded when the rounded dollar price actually changes. Stop with
`idotmatrix.stop_bitcoin`. The three display modes (GIF rotation, weather,
Bitcoin) are mutually exclusive — starting one stops the others.

| Field | Description |
| --- | --- |
| `price_entity` | Price sensor (default `sensor.bitcoin_price`). |
| `change_entity` | Optional 24h change % sensor. |
| `pixel_size` | `64` (default) or `32` (compact layout). |
| `follow` | `true` (default) keeps it updated; `false` renders once. |

### Bluetooth Proxy

This integration fully supports **ESPHome Bluetooth Proxies** and is the recommended setup for most users.

- If your Home Assistant server is far from the device, use a cheap ESP32 with ESPHome to extend range.
- The integration will automatically find and use the proxy with the best signal.
- **Recommended hardware**: Any ESP32 board running ESPHome with `bluetooth_proxy` enabled. The [M5Stack Atom Lite](https://esphome.github.io/bluetooth-proxies/) is a great compact option.
- GIF uploads use BLE Write Requests (with acknowledgment) for reliable delivery through the proxy. This is slower than a direct Bluetooth connection but rock-solid.

**Direct Bluetooth** is also supported. If your HA server has a Bluetooth adapter and is within range (~10m), the device will connect directly with faster transfer speeds.

---

## Troubleshooting

**"Device unavailable" / "No backend found"**
- Ensure the device is **disconnected** from the mobile app. It can only talk to one controller at a time.
- If using a local adapter on macOS/Linux, ensure BlueZ is up to date.
- Restart the iDotMatrix device (unplug/replug).
- If using an ESPHome proxy, check that the proxy is online and within range of the display.

**GIF not displaying / screen goes blank**
- Power cycle the iDotMatrix device. A failed upload can leave it in a bad state.
- Ensure the GIF file exists at the path specified (paths are relative to the HA container).
- Place GIF files in `/config/www/idotmatrix/gifs/` for easy access.

**GIF uploads are slow**
- This is expected when using a Bluetooth proxy. Each BLE packet must round-trip through WiFi -> proxy -> BLE -> device and back. A 60KB file takes ~10-15 seconds.
- For faster uploads, use a direct Bluetooth adapter on your HA server instead of a proxy.
- Pre-resize GIFs to 64x64 to minimize file size and transfer time.

**Icons not showing**
- For `mdi:` icons, make sure Home Assistant has internet access on first render (the font + metadata are fetched and cached in memory).
- For custom icons, use PNG URLs (`/local/...png` or `https://...png`).
- SVG URLs require Cairo; install it and restart if you need SVG rasterization.

**Designer card changes not showing**
- Hard-refresh the browser after updating `idotmatrix-card.js`.
- If you run `run_ha_dev.sh`, it rewrites `config/configuration.yaml` and uses port 8128.

---

<p align="center">
  Built with love by Tukies, based on great work of @derkalle4 who created python interface to communicate with iDotMatrix.<br>
  GIF upload and BLE proxy support by @scarolan.
</p>
