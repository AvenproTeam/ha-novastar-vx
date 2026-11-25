/*
 * NovaStar screen map card for Home Assistant.
 * Shows every cabinet (receiving card) where it physically sits on the screen,
 * coloured green / yellow / red, so technicians can find a failing cabinet fast.
 *
 *   type: custom:novastar-screen-card
 *   entry_id: <optional, defaults to the first controller>
 *   title: <optional>
 *   view: front | back          # default front; "back" mirrors the map for work behind the screen
 *   labels: true | false        # default true
 */
const LEVEL_LABEL = { ok: "OK", warning: "Check", error: "Fault" };
const REASON = {
  offline: "Not answering (offline, no power or data cable)",
  over_temperature: "Over the temperature alarm",
  high_temperature: "Close to the temperature alarm",
  module_flag: "Module status flag set",
};

class NovaStarScreenCard extends HTMLElement {
  static getStubConfig() {
    return { view: "front", labels: true };
  }

  setConfig(config) {
    this._config = { view: "front", labels: true, ...config };
    this._view = this._config.view === "back" ? "back" : "front";
    this._selected = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || !this._unsub) this._subscribe();
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub.then((unsub) => unsub()).catch(() => {});
      this._unsub = null;
    }
  }

  getCardSize() {
    return 8;
  }

  _subscribe() {
    if (!this._hass || this._unsub) return;
    const msg = { type: "novastar_vx/subscribe_map" };
    if (this._config && this._config.entry_id) msg.entry_id = this._config.entry_id;
    this._unsub = this._hass.connection.subscribeMessage((data) => {
      this._data = data;
      this._error = null;
      this._render();
    }, msg);
    this._unsub.catch((err) => {
      this._error = (err && err.message) || "Could not load the screen map";
      this._unsub = null;
      this._render();
    });
  }

  _esc(text) {
    return String(text ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  }

  _layout(data) {
    // Use the real positions when the controller gave them; otherwise one row per output.
    if (data.geometry) {
      return { width: data.width, height: data.height, cards: data.cards, outputs: data.outputs };
    }
    const size = 100;
    const cols = Math.max(...data.outputs.map((o) => o.cards), 1);
    const cards = data.cards.map((c) => ({ ...c, rect: [(c.index - 1) * size, (c.output - 1) * size, size, size] }));
    const outputs = data.outputs.map((o, i) => ({ ...o, rect: [0, i * size, o.cards * size, size] }));
    return { width: cols * size, height: data.outputs.length * size, cards, outputs };
  }

  _mirror(rect, width) {
    const [x, y, w, h] = rect;
    return this._view === "back" ? [width - x - w, y, w, h] : [x, y, w, h];
  }

  _position(card, layout) {
    if (!card.rect) return "";
    const [x, y, w, h] = this._mirror(card.rect, layout.width);
    const col = Math.round(x / w) + 1;
    const row = Math.round(y / h) + 1;
    const side = this._view === "back" ? "seen from the back" : "seen from the front";
    return `Column ${col} from the left, row ${row} from the top (${side})`;
  }

  _svg(layout) {
    const W = layout.width;
    const H = layout.height;
    const unit = Math.min(...layout.cards.filter((c) => c.rect).map((c) => Math.min(c.rect[2], c.rect[3])), W);
    const font = Math.max(unit * 0.22, 8);
    let out = "";
    for (const card of layout.cards) {
      if (!card.rect) continue;
      const [x, y, w, h] = this._mirror(card.rect, W);
      const sel = this._selected === card.id ? " selected" : "";
      out += `<g class="cab ${card.level}${sel}" data-id="${this._esc(card.id)}">
        <rect x="${x + unit * 0.03}" y="${y + unit * 0.03}" width="${w - unit * 0.06}" height="${h - unit * 0.06}" rx="${unit * 0.06}"/>`;
      if (this._config.labels) {
        out += `<text x="${x + w / 2}" y="${y + h / 2}" font-size="${font}">${this._esc(card.id)}</text>`;
        if (card.temperature != null) {
          out += `<text class="sub" x="${x + w / 2}" y="${y + h / 2 + font * 1.1}" font-size="${font * 0.75}">${card.temperature}°</text>`;
        }
      }
      out += "</g>";
    }
    for (const o of layout.outputs) {
      if (!o.rect) continue;
      const [x, y, w, h] = this._mirror(o.rect, W);
      const cls = o.on_backup ? "out backup" : "out";
      out += `<rect class="${cls}" x="${x}" y="${y}" width="${w}" height="${h}"/>`;
    }
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${out}</svg>`;
  }

  _details(layout) {
    const card = layout.cards.find((c) => c.id === this._selected);
    if (!card) return `<div class="hint">Tap a cabinet for details.</div>`;
    const reasons = [...card.problems, ...card.warnings].map((r) => `<li>${this._esc(REASON[r] || r)}</li>`).join("");
    const t = card.temperature != null ? `${card.temperature} °C` : "–";
    const v = card.voltage != null ? `${card.voltage} V` : "–";
    return `<div class="details ${card.level}">
      <div class="dhead"><b>${this._esc(card.id)}</b><span class="badge ${card.level}">${LEVEL_LABEL[card.level]}</span></div>
      <div>Output ${card.output}, card ${card.index} in the chain</div>
      <div>${this._esc(this._position(card, layout))}</div>
      <div>Temperature ${t} · Voltage ${v}</div>
      ${reasons ? `<ul>${reasons}</ul>` : ""}
    </div>`;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const title = this._config.title || (this._data && this._data.title) || "LED screen";
    let body;
    if (this._error) {
      body = `<div class="msg">${this._esc(this._error)}</div>`;
    } else if (!this._data) {
      body = `<div class="msg">Loading…</div>`;
    } else {
      const d = this._data;
      const layout = this._layout(d);
      const count = (lvl) => d.cards.filter((c) => c.level === lvl).length;
      const backup = d.outputs.filter((o) => o.on_backup);
      body = `
        <div class="chips">
          <span class="chip ok">${count("ok")} OK</span>
          <span class="chip warning">${count("warning")} check</span>
          <span class="chip error">${count("error")} fault</span>
          ${backup.map((o) => `<span class="chip backup">Output ${o.output} on backup (via ${o.backup_output})</span>`).join("")}
          ${d.online ? "" : `<span class="chip error">Controller not answering</span>`}
        </div>
        <div class="map ${d.online ? "" : "stale"}">${this._svg(layout)}</div>
        ${d.geometry ? "" : `<div class="hint">The controller did not report cabinet positions, so cabinets are shown in chain order, one row per output.</div>`}
        ${this._details(layout)}`;
    }
    this.shadowRoot.innerHTML = `
      <style>
        :host { --ok: var(--success-color, #43a047); --warn: var(--warning-color, #ffa000); --err: var(--error-color, #db4437); }
        ha-card { padding: 12px 16px 16px; }
        .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .title { font-size: 1.2em; font-weight: 500; }
        button { background: none; border: 1px solid var(--divider-color, #ccc); border-radius: 16px; padding: 4px 12px;
                 color: var(--primary-text-color); cursor: pointer; font: inherit; font-size: 0.85em; }
        .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
        .chip { border-radius: 12px; padding: 2px 10px; font-size: 0.85em; color: #fff; }
        .chip.ok { background: var(--ok); } .chip.warning { background: var(--warn); } .chip.error { background: var(--err); }
        .chip.backup { background: #8e24aa; }
        .map svg { width: 100%; height: auto; display: block; background: var(--secondary-background-color, #222); border-radius: 6px; }
        .map.stale { opacity: 0.45; }
        .cab { cursor: pointer; }
        .cab rect { stroke: rgba(0,0,0,0.35); stroke-width: 1; }
        .cab.ok rect { fill: var(--ok); } .cab.warning rect { fill: var(--warn); } .cab.error rect { fill: var(--err); }
        .cab.error rect { animation: blink 1.2s ease-in-out infinite; }
        .cab.selected rect { stroke: var(--primary-text-color, #fff); stroke-width: 6; }
        .cab text { fill: #fff; text-anchor: middle; dominant-baseline: middle; pointer-events: none; font-family: inherit; font-weight: 600; }
        .cab text.sub { font-weight: 400; opacity: 0.9; }
        .out { fill: none; stroke: var(--primary-text-color, #fff); stroke-opacity: 0.55; stroke-width: 4; stroke-dasharray: 18 10; pointer-events: none; }
        .out.backup { stroke: #8e24aa; stroke-opacity: 1; stroke-width: 10; }
        @keyframes blink { 50% { opacity: 0.45; } }
        .msg, .hint { color: var(--secondary-text-color); padding: 8px 0; font-size: 0.9em; }
        .details { margin-top: 10px; padding: 10px 12px; border-radius: 8px; border-left: 6px solid var(--ok);
                   background: var(--secondary-background-color, rgba(127,127,127,0.1)); line-height: 1.5; }
        .details.warning { border-color: var(--warn); } .details.error { border-color: var(--err); }
        .details ul { margin: 4px 0 0; padding-left: 20px; }
        .dhead { display: flex; justify-content: space-between; align-items: center; }
        .badge { border-radius: 10px; padding: 0 8px; color: #fff; font-size: 0.8em; }
        .badge.ok { background: var(--ok); } .badge.warning { background: var(--warn); } .badge.error { background: var(--err); }
      </style>
      <ha-card>
        <div class="head">
          <span class="title">${this._esc(title)}</span>
          <button id="view" title="Mirror the map for work from behind the screen">${this._view === "back" ? "Back view" : "Front view"}</button>
        </div>
        ${body}
      </ha-card>`;
    this.shadowRoot.getElementById("view").addEventListener("click", () => {
      this._view = this._view === "back" ? "front" : "back";
      this._render();
    });
    this.shadowRoot.querySelectorAll(".cab").forEach((el) =>
      el.addEventListener("click", () => {
        this._selected = this._selected === el.dataset.id ? null : el.dataset.id;
        this._render();
      }),
    );
  }
}

if (!customElements.get("novastar-screen-card")) {
  customElements.define("novastar-screen-card", NovaStarScreenCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "novastar-screen-card",
    name: "NovaStar screen map",
    description: "Live map of every LED cabinet, coloured by status.",
    preview: false,
    documentationURL: "https://github.com/AvenproTeam/ha-novastar-vx",
  });
}
