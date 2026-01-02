import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@3.3.3/lit-element.js?module";

console.info(
  "%c iDotMatrix Card %c v0.2.0 ",
  "color: white; background: #333; font-weight: bold;",
  "color: white; background: #03a9f4; font-weight: bold;"
);

class IDotMatrixCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _layers: { type: Array, state: true },
      _previews: { type: Object, state: true }, // Stores rendered template values by layer ID
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      ha-card {
        padding: 16px;
      }
      .card-header {
        font-size: 18px;
        font-weight: bold;
        margin-bottom: 16px;
        color: var(--primary-text-color);
      }
      .container {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .canvas-container {
        background: #000;
        width: 320px;
        height: 320px;
        margin: 0 auto;
        position: relative;
        border: 4px solid #333;
        border-radius: 8px;
        image-rendering: pixelated;
      }
      canvas {
        width: 100%;
        height: 100%;
      }
      .layer-item {
        display: flex;
        align-items: center;
        gap: 8px;
        background: var(--secondary-background-color);
        padding: 12px;
        border-radius: 8px;
      }
      .layer-item span {
        min-width: 24px;
        font-weight: bold;
      }
      .layer-controls {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        flex: 1;
      }
      ha-textfield {
        flex: 1;
        min-width: 150px;
      }
      .coord-input {
        width: 60px;
      }
      mwc-button {
        --mdc-theme-primary: var(--primary-color);
      }
      .actions {
        display: flex;
        gap: 8px;
        margin-top: 16px;
      }
      .actions mwc-button {
        flex: 1;
      }
      .template-hint {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 4px;
      }
    `;
  }

  constructor() {
    super();
    this._layers = [];
    this._previews = {};
    this._templateSubs = {}; // WebSocket unsubscribe functions
    this._debouncers = {};   // Debounce timers
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    this.config = config;

    // Initialize layers from config or defaults
    this._layers = config.layers || [
      {
        id: "default",
        type: "text",
        template: "{{ now().strftime('%H:%M') }}",
        x: 0,
        y: 8,
        color: [0, 255, 0],
        font_size: 10,
      },
    ];
  }

  // Graphical card editor using HA's form schema with template selector
  static getConfigForm() {
    return {
      schema: [
        {
          name: "title",
          selector: { text: {} },
        },
        {
          name: "template",
          selector: { template: {} },  // HA's Jinja editor with autocomplete
        },
        {
          name: "",
          type: "grid",
          schema: [
            {
              name: "x",
              selector: { number: { min: 0, max: 32, mode: "box" } },
            },
            {
              name: "y",
              selector: { number: { min: 0, max: 32, mode: "box" } },
            },
          ],
        },
      ],
      computeLabel: (schema) => {
        const labels = {
          title: "Card Title",
          template: "Template (Jinja2)",
          x: "X Position",
          y: "Y Position",
        };
        return labels[schema.name] || schema.name;
      },
    };
  }

  static getStubConfig() {
    return {
      title: "iDotMatrix",
      template: "{{ now().strftime('%H:%M') }}",
      x: 0,
      y: 8,
    };
  }

  render() {
    if (!this.hass || !this.config) {
      return html``;
    }

    return html`
      <ha-card>
        <div class="card-header">
          ${this.config.title || "iDotMatrix Designer"}
        </div>
        <div class="container">
          <div class="canvas-container">
            <canvas id="preview" width="32" height="32"></canvas>
          </div>

          <div class="layers-list">
            ${this._layers.map(
      (layer, index) => html`
                <div class="layer-item">
                  <span>${index + 1}.</span>
                  <div class="layer-controls">
                    <ha-textfield
                      label="Template"
                      .value=${layer.template || ""}
                      @input=${(e) => this._updateLayer(index, "template", e.target.value)}
                    ></ha-textfield>
                    <ha-textfield
                      class="coord-input"
                      label="X"
                      type="number"
                      .value=${String(layer.x)}
                      @input=${(e) => this._updateLayer(index, "x", parseInt(e.target.value) || 0)}
                    ></ha-textfield>
                    <ha-textfield
                      class="coord-input"
                      label="Y"
                      type="number"
                      .value=${String(layer.y)}
                      @input=${(e) => this._updateLayer(index, "y", parseInt(e.target.value) || 0)}
                    ></ha-textfield>
                    <ha-textfield
                      class="coord-input"
                      label="Sp.X"
                      type="number"
                      .value=${String(layer.spacing_x ?? 1)}
                      @input=${(e) => this._updateLayer(index, "spacing_x", parseInt(e.target.value) || 0)}
                    ></ha-textfield>
                    <ha-textfield
                      class="coord-input"
                      label="Sp.Y"
                      type="number"
                      .value=${String(layer.spacing_y ?? 1)}
                      @input=${(e) => this._updateLayer(index, "spacing_y", parseInt(e.target.value) || 0)}
                    ></ha-textfield>
                    <input
                      type="color"
                      .value=${this._rgbToHex(layer.color)}
                      @input=${(e) => this._updateLayer(index, "color", this._hexToRgb(e.target.value))}
                    />
                    <mwc-button dense @click=${() => this._removeLayer(index)}>
                      <ha-icon icon="mdi:delete"></ha-icon>
                    </mwc-button>
                  </div>
                </div>
              `
    )}
          </div>

          <p class="template-hint">
            Use Jinja2 templates: {{ states('sensor.time') }}, {{ now().strftime('%H:%M') }}
          </p>

          <div class="actions">
            <mwc-button raised @click=${this._addLayer}>
              <ha-icon icon="mdi:plus"></ha-icon>
              Add Layer
            </mwc-button>
            <mwc-button raised @click=${this._saveToDevice}>
              <ha-icon icon="mdi:content-save"></ha-icon>
              Save to Device
            </mwc-button>
          </div>
          
          <div class="actions">
            <mwc-button @click=${this._saveDesign}>
              <ha-icon icon="mdi:folder-download"></ha-icon>
              Save Design
            </mwc-button>
            <mwc-button @click=${this._loadDesign}>
              <ha-icon icon="mdi:folder-upload"></ha-icon>
              Load Design
            </mwc-button>
          </div>
        </div>
      </ha-card>
    `;
  }


  updated(changedProperties) {
    super.updated(changedProperties);

    // Subscribe to templates when hass becomes available
    if (changedProperties.has("hass") && this.hass) {
      this._subscribeAllLayers();
    }

    // Redraw canvas when previews or layers change
    if (changedProperties.has("_previews") || changedProperties.has("_layers")) {
      this._drawCanvas();
    }
  }

  firstUpdated() {
    this._subscribeAllLayers();
    this._drawCanvas();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubscribeAll();
  }

  _subscribeAllLayers() {
    this._layers.forEach((layer) => {
      if (layer.template) {
        this._subscribeTemplate(layer);
      }
    });
  }

  _unsubscribeAll() {
    Object.values(this._templateSubs).forEach((unsub) => {
      if (typeof unsub === "function") unsub();
    });
    this._templateSubs = {};
  }

  async _subscribeTemplate(layer) {
    // Unsubscribe existing
    if (this._templateSubs[layer.id]) {
      this._templateSubs[layer.id]();
      delete this._templateSubs[layer.id];
    }

    if (!this.hass?.connection || !layer.template) {
      return;
    }

    try {
      const unsub = await this.hass.connection.subscribeMessage(
        (msg) => {
          // Update preview for this layer
          this._previews = {
            ...this._previews,
            [layer.id]: msg.result || String(msg),
          };
        },
        {
          type: "render_template",
          template: layer.template,
          variables: {},
        }
      );
      this._templateSubs[layer.id] = unsub;
    } catch (e) {
      console.error("[iDotMatrix] Template subscription error:", e);
      this._previews = {
        ...this._previews,
        [layer.id]: "ERR",
      };
    }
  }

  async _drawCanvas() {
    const canvas = this.shadowRoot?.getElementById("preview");
    if (!canvas || !this.hass) return;

    const ctx = canvas.getContext("2d");

    // Clear canvas first
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, 32, 32);

    // Prepare layers with resolved template values
    const layersWithContent = this._layers.map((layer) => ({
      ...layer,
      content: this._previews[layer.id] || "",
      is_template: false, // Already resolved
    }));

    try {
      // Call backend to render using Python/PIL
      const response = await this.hass.callService(
        "idotmatrix",
        "render_preview",
        {
          face: { layers: layersWithContent },
          screen_size: 32,
        },
        undefined,
        true,  // returnResponse
      );

      if (response?.image) {
        // Load and draw the base64 image
        const img = new Image();
        img.onload = () => {
          ctx.drawImage(img, 0, 0, 32, 32);
        };
        img.src = response.image;
      }
    } catch (e) {
      console.error("[iDotMatrix] Preview render error:", e);
      // Fallback: draw placeholder
      ctx.fillStyle = "#ff0000";
      ctx.font = "8px monospace";
      ctx.fillText("ERR", 4, 16);
    }
  }

  _updateLayer(index, prop, value) {
    const newLayers = [...this._layers];
    const layer = { ...newLayers[index] };
    layer[prop] = value;

    // Always treat as template
    layer.is_template = true;

    newLayers[index] = layer;
    this._layers = newLayers;

    // Debounce template subscription
    if (prop === "template") {
      if (this._debouncers[layer.id]) {
        clearTimeout(this._debouncers[layer.id]);
      }
      this._debouncers[layer.id] = setTimeout(() => {
        this._subscribeTemplate(layer);
      }, 500);
    }
  }

  _addLayer() {
    const newId = Date.now().toString();
    this._layers = [
      ...this._layers,
      {
        id: newId,
        type: "text",
        template: "",
        x: 0,
        y: 0,
        spacing_x: 1,
        spacing_y: 1,
        color: [255, 255, 255],
        font_size: 10,
        is_template: true,
      },
    ];
  }

  _removeLayer(index) {
    const layer = this._layers[index];
    // Unsubscribe
    if (this._templateSubs[layer.id]) {
      this._templateSubs[layer.id]();
      delete this._templateSubs[layer.id];
    }

    const newLayers = [...this._layers];
    newLayers.splice(index, 1);
    this._layers = newLayers;
  }

  _saveToDevice() {
    if (!this.hass) return;

    this.hass.callService("idotmatrix", "set_face", {
      face: {
        layers: this._layers.map((l) => ({
          ...l,
          is_template: true,
        })),
      },
    });

    // Show toast notification
    const event = new CustomEvent("hass-notification", {
      detail: { message: "Configuration sent to iDotMatrix!" },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  _saveDesign() {
    const designName = prompt("Enter design name:", "My Design");
    if (!designName) return;

    // Get existing designs
    const designs = JSON.parse(localStorage.getItem("idotmatrix_designs") || "{}");

    // Save current layers
    designs[designName] = {
      name: designName,
      layers: this._layers,
      savedAt: new Date().toISOString(),
    };

    localStorage.setItem("idotmatrix_designs", JSON.stringify(designs));

    const event = new CustomEvent("hass-notification", {
      detail: { message: `Design "${designName}" saved!` },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  _loadDesign() {
    const designs = JSON.parse(localStorage.getItem("idotmatrix_designs") || "{}");
    const designNames = Object.keys(designs);

    if (designNames.length === 0) {
      alert("No saved designs found.");
      return;
    }

    const designName = prompt(
      `Available designs:\n${designNames.join("\n")}\n\nEnter design name to load:`
    );

    if (!designName || !designs[designName]) {
      alert("Design not found.");
      return;
    }

    // Unsubscribe old layers
    this._unsubscribeAll();

    // Load layers
    this._layers = designs[designName].layers;

    // Re-subscribe
    this._subscribeAllLayers();

    const event = new CustomEvent("hass-notification", {
      detail: { message: `Design "${designName}" loaded!` },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  _rgbToHex(rgb) {
    return (
      "#" +
      rgb
        .map((x) => {
          const hex = x.toString(16);
          return hex.length === 1 ? "0" + hex : hex;
        })
        .join("")
    );
  }

  _hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result
      ? [
        parseInt(result[1], 16),
        parseInt(result[2], 16),
        parseInt(result[3], 16),
      ]
      : [255, 255, 255];
  }

  getCardSize() {
    return 6;
  }
}

customElements.define("idotmatrix-card", IDotMatrixCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "idotmatrix-card",
  name: "iDotMatrix Card",
  description: "A display designer card for iDotMatrix LED displays",
  preview: true,
  documentationURL: "https://github.com/dopheideb/iDotMatrix-HomeAssistant",
});
