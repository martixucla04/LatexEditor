// Document outline in the sidebar: parts, chapters, sections and subsections in
// reading order (app/outline.py follows \input / \include from the main file).
// Click a heading to jump to it; the heading the cursor is under is highlighted.

import { call } from "./bridge.js";

const viewEl = document.getElementById("outline-view");
const listEl = document.getElementById("outline-list");

let handlers = { onOpen() {}, buffers: () => [] };
let items = [];
let timer = null;
let runId = 0;
let cursor = { file: null, line: 0 };

export function initOutline(options) {
  handlers = { ...handlers, ...options };
  document.querySelector('.sidebar-tab[data-view="outline"]').addEventListener("click", () => refreshOutline(0));
}

// Re-read the headings after `delay` ms; skipped while the Outline view is hidden
// (showing it refreshes it).
export function refreshOutline(delay = 0) {
  clearTimeout(timer);
  if (viewEl.hidden) return;
  timer = setTimeout(load, delay);
}

export function clearOutline() {
  runId++;
  clearTimeout(timer);
  items = [];
  render("No project open.");
}

async function load() {
  const id = ++runId;
  try {
    // unsaved edits count: send the text of modified files
    const overrides = Object.fromEntries(handlers.buffers().map((b) => [b.path, b.text]));
    const result = await call("outline", overrides);
    if (id !== runId) return;
    items = result;
    render();
  } catch (err) {
    if (id !== runId) return;
    items = [];
    render(err.message);
  }
}

// The heading the cursor is under: the last one before it in the same file.
export function setOutlineCursor(file, line) {
  cursor = { file, line };
  highlight();
}

function highlight() {
  let active = -1;
  items.forEach((item, i) => {
    if (item.file === cursor.file && item.line <= cursor.line) active = i;
  });
  listEl.querySelectorAll(".outline-item").forEach((el, i) => el.classList.toggle("active", i === active));
}

function render(message = "No sections found. Headings appear here once the main file (or a file it \\input-s) has \\chapter, \\section…") {
  listEl.replaceChildren();
  if (!items.length) {
    const p = document.createElement("p");
    p.className = "empty-state";
    p.textContent = message;
    listEl.append(p);
    return;
  }
  const top = Math.min(...items.map((i) => i.level));
  for (const item of items) {
    const button = document.createElement("button");
    button.className = `outline-item level-${item.level}`;
    button.style.paddingLeft = `${10 + (item.level - top) * 14}px`;
    button.textContent = item.title;
    button.title = `${item.title}\n${item.file}:${item.line}`;
    button.addEventListener("click", () => handlers.onOpen(item.file, item.line));
    listEl.append(button);
  }
  highlight();
}
