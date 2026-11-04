// Resizable panes: file tree | editor + problems panel | PDF.
// Sizes and visibility are remembered per machine in localStorage.
// The PDF pane is stored as a share of the window width so it scales with it.

const STORAGE_KEY = "latexeditor.layout";
const DEFAULT_PDF_RATIO = 0.45;
const MIN_EDITOR_W = 320;
const MIN_EDITOR_H = 120;
const KEY_STEP = 16;

const workbench = document.getElementById("workbench");
const column = document.getElementById("editor-column");
const root = document.documentElement;

const state = {
  sidebar: 240,
  pdfRatio: DEFAULT_PDF_RATIO,
  panel: 180,
  sidebarVisible: true,
  panelVisible: true,
};

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    for (const key of Object.keys(state)) {
      if (typeof saved[key] === typeof state[key]) state[key] = saved[key];
    }
  } catch {
    // storage unavailable or corrupt: keep defaults
  }
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore: layout simply is not remembered
  }
}

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

// Pixel sizes for the current window, keeping every pane within bounds.
function measure() {
  const width = workbench.clientWidth;
  const sidebar = clamp(state.sidebar, 160, Math.max(160, Math.min(480, width / 3)));
  const pdfMax = Math.max(280, width - (state.sidebarVisible ? sidebar : 0) - MIN_EDITOR_W - 10);
  const pdf = clamp(Math.round(width * state.pdfRatio), 280, pdfMax);
  const tabsH = document.getElementById("tabs").offsetHeight;
  const panel = clamp(state.panel, 80, Math.max(80, column.clientHeight - tabsH - MIN_EDITOR_H));
  return { width, sidebar, pdf, panel };
}

function apply() {
  const size = measure();
  root.style.setProperty("--sidebar-w", `${size.sidebar}px`);
  root.style.setProperty("--pdf-w", `${size.pdf}px`);
  root.style.setProperty("--panel-h", `${size.panel}px`);
  workbench.classList.toggle("sidebar-hidden", !state.sidebarVisible);
  column.classList.toggle("panel-hidden", !state.panelVisible);
  document.getElementById("btn-toggle-sidebar").setAttribute("aria-pressed", state.sidebarVisible);
  document.getElementById("btn-toggle-panel").setAttribute("aria-pressed", state.panelVisible);
}

// Each resizable pane: how to read its current pixel size and how to store a new one.
const panes = {
  sidebar: { get: () => measure().sidebar, set: (px) => { state.sidebar = px; } },
  pdf: { get: () => measure().pdf, set: (px) => { state.pdfRatio = px / workbench.clientWidth; } },
  panel: { get: () => measure().panel, set: (px) => { state.panel = px; } },
};

function resize(pane, px) {
  panes[pane].set(px);
  apply();
  // Store the clamped value so the saved layout matches what is on screen.
  panes[pane].set(panes[pane].get());
}

// Attach drag + keyboard resizing to a splitter.
//   axis: "x" | "y", sign: +1 grows with the pointer, -1 shrinks
function makeSplitter(el, pane, axis, sign) {
  const bodyClass = axis === "x" ? "resizing-col" : "resizing-row";
  el.tabIndex = 0;

  el.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const start = axis === "x" ? event.clientX : event.clientY;
    const startSize = panes[pane].get();
    el.setPointerCapture(event.pointerId);
    el.classList.add("dragging");
    document.body.classList.add(bodyClass);

    const move = (e) => {
      const pos = axis === "x" ? e.clientX : e.clientY;
      resize(pane, startSize + sign * (pos - start));
    };
    const end = () => {
      el.removeEventListener("pointermove", move);
      el.classList.remove("dragging");
      document.body.classList.remove(bodyClass);
      save();
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", end, { once: true });
    el.addEventListener("pointercancel", end, { once: true });
  });

  el.addEventListener("keydown", (event) => {
    const keys = axis === "x" ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
    const dir = keys.indexOf(event.key);
    if (dir === -1) return;
    event.preventDefault();
    resize(pane, panes[pane].get() + (dir === 0 ? -1 : 1) * sign * KEY_STEP);
    save();
  });
}

export function toggleSidebar() {
  state.sidebarVisible = !state.sidebarVisible;
  apply();
  save();
}

export function togglePanel() {
  state.panelVisible = !state.panelVisible;
  apply();
  save();
}

export function initLayout() {
  load();
  makeSplitter(document.getElementById("split-sidebar"), "sidebar", "x", 1);
  makeSplitter(document.getElementById("split-pdf"), "pdf", "x", -1);
  makeSplitter(document.getElementById("split-panel"), "panel", "y", -1);

  // Double-click the PDF splitter to go back to the default split.
  document.getElementById("split-pdf").addEventListener("dblclick", () => {
    state.pdfRatio = DEFAULT_PDF_RATIO;
    apply();
    save();
  });

  document.getElementById("btn-toggle-sidebar").addEventListener("click", toggleSidebar);
  document.getElementById("btn-toggle-panel").addEventListener("click", togglePanel);
  window.addEventListener("resize", apply);
  apply();
}
