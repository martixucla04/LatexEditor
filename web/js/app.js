// App bootstrap: layout, panels, keyboard shortcuts and the status bar.

import { call, BackendUnavailable } from "./bridge.js";
import { initLayout, toggleSidebar, togglePanel } from "./layout.js";

const $ = (id) => document.getElementById(id);

export function setStatus(text, kind = "") {
  const el = $("status-message");
  el.textContent = text;
  el.className = kind;
}

function initPanelTabs() {
  const tabs = document.querySelectorAll(".panel-tab");
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      for (const t of tabs) {
        const active = t === tab;
        t.classList.toggle("active", active);
        t.setAttribute("aria-selected", active);
        document.querySelector(`[data-panel-body="${t.dataset.panel}"]`).hidden = !active;
      }
    });
  }
}

function initShortcuts() {
  const bindings = {
    b: toggleSidebar,
    j: togglePanel,
    s: () => {}, // save + compile arrive in phases 2-3; keep the browser default from firing
  };
  window.addEventListener("keydown", (event) => {
    if (!event.ctrlKey || event.altKey || event.shiftKey) return;
    const action = bindings[event.key.toLowerCase()];
    if (!action) return;
    event.preventDefault();
    action();
  });
}

async function showAppInfo() {
  const line = $("engine-line");
  const engine = $("status-engine");
  try {
    const info = await call("app_info");
    if (info.engine) {
      line.textContent = `LuaLaTeX ready: ${info.engine.version}`;
      line.className = "engine-line ok";
      engine.textContent = info.engine.version.split(" (")[0];
      engine.title = info.engine.path;
    } else {
      line.textContent = "LuaLaTeX was not found. Install MiKTeX or TeX Live and make sure lualatex is on the PATH.";
      line.className = "engine-line missing";
      engine.textContent = "LuaLaTeX not found";
      engine.className = "warning";
    }
    setStatus("Ready");
  } catch (err) {
    line.textContent = err instanceof BackendUnavailable ? err.message : `Could not query the backend: ${err}`;
    line.className = "engine-line missing";
    setStatus(err.message, "warning");
  }
}

initLayout();
initPanelTabs();
initShortcuts();
showAppInfo();
