/**
 * Communal Grid Card for Home Assistant
 * Displays VPP program matches for your smart home devices.
 *
 * Auto-registered by the Communal Grid integration -- no manual YAML needed.
 * Just install the integration, then pick "Communal Grid" from the card picker.
 *
 * Version: 1.0.0
 */

class CommunalGridCard extends HTMLElement {
  // --- Lovelace card boilerplate -----------------------------------------------

  static getConfigElement() {
    return document.createElement("communal-grid-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = config;
  }

  getCardSize() {
    return 4;
  }

  // --- Core HA lifecycle -------------------------------------------------------

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  // --- Render -----------------------------------------------------------------

  _render() {
    if (!this.shadowRoot || !this._hass) return;

    const entity = this._hass.states["sensor.communal_grid_vpp_matches"];
    const state = entity ? entity.state : undefined;
    const attrs = entity ? entity.attributes : {};
    const vpps = (attrs && attrs.matching_vpps) ? attrs.matching_vpps : null;

    const isLoading = !entity || state === "unavailable" || state === "unknown";
    const count = isLoading ? 0 : Number(state);

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--primary-font-family, sans-serif);
        }

        /* -- Header -- */
        .header {
          background: #FFD400;
          color: #1a1a1a;
          border-radius: 16px 16px 0 0;
          padding: 20px 20px 16px;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
        }
        .header ha-icon {
          --mdc-icon-size: 32px;
          color: #1a1a1a;
          margin-bottom: 8px;
        }
        .header .label {
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          opacity: 0.8;
          margin-bottom: 6px;
        }
        .header .count {
          font-size: 24px;
          font-weight: bold;
          line-height: 1.2;
        }
        .header .subtitle {
          font-size: 13px;
          opacity: 0.7;
          margin-top: 4px;
        }

        /* -- Body -- */
        .body {
          background: var(--card-background-color, #1c1c1e);
          border-radius: 0 0 16px 16px;
          padding: 4px 16px 16px;
          color: var(--primary-text-color, #fff);
        }

        .loading {
          padding: 24px;
          text-align: center;
          opacity: 0.6;
          font-size: 14px;
        }

        .empty {
          padding: 24px 16px;
          text-align: center;
          opacity: 0.6;
          font-size: 14px;
          line-height: 1.6;
        }

        /* -- VPP entry -- */
        .divider {
          border: none;
          border-top: 1px solid rgba(255,255,255,0.12);
          margin: 12px 0;
        }

        .vpp-name {
          font-size: 16px;
          font-weight: 700;
          margin: 0 0 4px;
        }

        .vpp-meta {
          font-size: 13px;
          opacity: 0.7;
          margin-bottom: 6px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .vpp-meta .dot {
          opacity: 0.4;
        }

        .reward {
          font-size: 13px;
          margin-bottom: 8px;
          display: flex;
          gap: 6px;
          align-items: flex-start;
        }

        /* -- Device groups -- */
        details {
          font-size: 13px;
          margin: 4px 0;
          border: 1px solid rgba(255,255,255,0.1);
          border-radius: 8px;
          overflow: hidden;
        }

        summary {
          padding: 8px 12px;
          cursor: pointer;
          font-weight: 600;
          display: flex;
          justify-content: space-between;
          align-items: center;
          list-style: none;
          user-select: none;
        }

        summary::-webkit-details-marker { display: none; }

        summary::after {
          content: "\\203A";
          font-size: 18px;
          opacity: 0.5;
          transition: transform 0.2s;
        }

        details[open] summary::after {
          transform: rotate(90deg);
        }

        .device-list {
          padding: 4px 12px 10px;
          opacity: 0.8;
          line-height: 2;
          border-top: 1px solid rgba(255,255,255,0.08);
        }

        .device-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
        }

        .device-item::before {
          content: "\\00B7";
          opacity: 0.5;
        }

        /* -- Actions -- */
        .actions {
          display: flex;
          gap: 12px;
          margin-top: 10px;
          align-items: center;
        }

        .btn-enroll {
          display: inline-block;
          background: #FFD400;
          color: #1a1a1a;
          font-weight: 700;
          font-size: 13px;
          padding: 6px 14px;
          border-radius: 20px;
          text-decoration: none;
          transition: opacity 0.15s;
        }

        .btn-enroll:hover { opacity: 0.85; }

        .btn-learn {
          display: inline-block;
          color: #FFD400;
          font-size: 13px;
          text-decoration: none;
          opacity: 0.8;
          transition: opacity 0.15s;
        }

        .btn-learn:hover { opacity: 1; }
      </style>

      <!-- Header -->
      <div class="header">
        <ha-icon icon="mdi:leaf-circle-outline"></ha-icon>
        <div class="label">Available VPP Programs</div>
        <div class="count">${this._headerCount(isLoading, count)}</div>
        ${!isLoading && count > 0
          ? `<div class="subtitle">Enroll in 1 or more to start earning ASAP</div>`
          : ""}
      </div>

      <!-- Body -->
      <div class="body">
        ${isLoading
          ? `<div class="loading">Discovering devices...</div>`
          : count === 0
          ? `<div class="empty">No VPP programs match your current utility and devices.<br>Add more smart devices or check back as new programs launch.</div>`
          : vpps
          ? vpps.map(v => this._renderVpp(v)).join("")
          : `<div class="loading">Loading program details...</div>`
        }
      </div>
    `;
  }

  _headerCount(isLoading, count) {
    if (isLoading) return "Discovering devices...";
    if (count === 0) return "No eligible programs found";
    return `${count} eligible program${count !== 1 ? "s" : ""} found`;
  }

  _renderVpp(vpp) {
    const deviceCount = vpp.matching_device_count || 0;
    const powerW = vpp.total_matching_power_w || 0;
    const kwhYr = vpp.total_matching_annual_kwh || 0;

    // Group devices by manufacturer+model
    const groups = {};
    (vpp.matching_devices || []).forEach(d => {
      const key = `${d.manufacturer || ""} ${d.model || "Unknown"}`.trim();
      if (!groups[key]) groups[key] = { devices: [], power: 0, kwh: 0 };
      groups[key].devices.push(d.name || "Unknown device");
      groups[key].power += d.current_power_w || 0;
      groups[key].kwh += d.estimated_annual_kwh || 0;
    });

    const groupKeys = Object.keys(groups).sort();

    return `
      <hr class="divider">
      <div class="vpp-name">&#9889; ${this._esc(vpp.name)}</div>
      <div class="vpp-meta">
        <span>${deviceCount} qualifying device${deviceCount !== 1 ? "s" : ""}</span>
        ${powerW > 0 ? `<span class="dot">&middot;</span><span><strong>${Math.round(powerW)}W</strong> now</span>` : ""}
        ${kwhYr > 0 ? `<span class="dot">&middot;</span><span>~${Math.round(kwhYr)} kWh/yr</span>` : ""}
      </div>
      ${vpp.reward && vpp.reward.description
        ? `<div class="reward">&#128176; <span>${this._esc(vpp.reward.description)}</span></div>`
        : ""}
      ${groupKeys.map(key => {
        const g = groups[key];
        const metaParts = [];
        if (g.power > 0) metaParts.push(`&#9889; ${Math.round(g.power)}W`);
        if (g.kwh > 0) metaParts.push(`~${Math.round(g.kwh)} kWh/yr`);
        return `
          <details>
            <summary>
              <span>${this._esc(key)}${metaParts.length ? " &middot;" + metaParts.join(" &middot;") : ""}</span>
            </summary>
            <div class="device-list">
              ${g.devices.map(name => `<div class="device-item">${this._esc(name)}</div>`).join("")}
            </div>
          </details>`;
      }).join("")}
      <div class="actions">
        ${vpp.enrollment_url
          ? `<a class="btn-enroll" href="${this._esc(vpp.enrollment_url)}" target="_blank" rel="noopener">Enroll</a>`
          : ""}
        ${vpp.learn_more
          ? `<a class="btn-learn" href="${this._esc(vpp.learn_more)}" target="_blank" rel="noopener">Learn more</a>`
          : ""}
      </div>
    `;
  }

  _esc(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}

// --- Simple editor (shows in the card picker visual editor) -------------------

class CommunalGridCardEditor extends HTMLElement {
  setConfig() {}

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        p { font-family: sans-serif; font-size: 14px; padding: 8px 0; color: var(--primary-text-color); }
      </style>
      <p>This card automatically displays your Communal Grid VPP program matches. No configuration needed.</p>
    `;
  }
}

// --- Register both elements ---------------------------------------------------

customElements.define("communal-grid-card", CommunalGridCard);
customElements.define("communal-grid-card-editor", CommunalGridCardEditor);

// --- Register with HA's card picker -------------------------------------------

window.customCards = window.customCards || [];
window.customCards.push({
  type: "communal-grid-card",
  name: "Communal Grid",
  description: "Shows VPP programs available for your smart home devices",
  preview: false,
  documentationURL: "https://github.com/Civilian-Power/communal-grid-ha",
});
