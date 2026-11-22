// Document outline, in a hidable column to the right of the PDF: parts, chapters,
// sections and subsections in reading order (app/outline.py follows \input /
// \include from the main file). Two highlights: the heading the editor cursor is
// under ("Code") and the heading of the part of the PDF in view ("PDF", from the
// SyncTeX positions of the last build). Clicking a heading moves both there.

import { call } from "./bridge.js";
import { onViewChange, scrollToPdfPoint, viewPosition } from "./pdfview.js";

const VISIBLE_KEY = "latexeditor.outlineVisible";

const viewEl = document.getElementById("outline-view");
const listEl = document.getElementById("outline-list");
const toggleBtn = document.getElementById("btn-outline");

let handlers = { onOpen() {}, buffers: () => [] };
let items = [];
let timer = null;
let runId = 0;
let cursor = { file: null, line: 0 };
let pinned = null; // heading clicked last: stays the "PDF" one until the user scrolls the PDF

function setVisible(visible) {
  viewEl.hidden = !visible;
  toggleBtn.setAttribute("aria-pressed", visible);
  try {
    localStorage.setItem(VISIBLE_KEY, visible ? "yes" : "no");
  } catch {
    // not remembered
  }
  if (visible) refreshOutline(0);
}

export function initOutline(options) {
  handlers = { ...handlers, ...options };
  let visible = true;
  try {
    visible = localStorage.getItem(VISIBLE_KEY) !== "no";
  } catch {
    // shown
  }
  viewEl.hidden = !visible;
  toggleBtn.setAttribute("aria-pressed", visible);
  toggleBtn.addEventListener("click", () => setVisible(viewEl.hidden));
  onViewChange(highlightPdf);
  const unpin = () => {
    pinned = null;
  };
  for (const type of ["wheel", "pointerdown", "keydown"]) {
    document.getElementById("pdf-container").addEventListener(type, unpin, { passive: true });
  }
}

// Re-read the headings after `delay` ms; skipped while the outline is hidden
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
  highlightCode();
}

function mark(className, index) {
  listEl.querySelectorAll(".outline-item").forEach((el, i) => {
    const on = i === index;
    if (on && !el.classList.contains(className)) el.scrollIntoView({ block: "nearest" });
    el.classList.toggle(className, on);
  });
}

function highlightCode() {
  let active = -1;
  items.forEach((item, i) => {
    if (item.file === cursor.file && item.line <= cursor.line) active = i;
  });
  mark("at-cursor", active);
}

// The last heading at or above the part of the PDF in view.
function highlightPdf() {
  if (viewEl.hidden) return;
  const view = viewPosition();
  let active = -1;
  if (pinned !== null && view) {
    active = items.findIndex((i) => i.file === pinned.file && i.line === pinned.line); // survives a refresh
  } else if (view) {
    items.forEach((item, i) => {
      const at = item.pdf;
      if (at && (at.page < view.page || (at.page === view.page && at.y <= view.y))) active = i;
    });
  }
  mark("in-pdf", active);
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
    button.style.paddingLeft = `${8 + (item.level - top) * 12}px`;
    button.textContent = item.title;
    button.title = `${item.title}\n${item.file}:${item.line}${item.pdf ? `\nPDF page ${item.pdf.page}` : "\nNot in the PDF yet (compile)"}`;
    button.addEventListener("click", () => {
      handlers.onOpen(item.file, item.line);
      if (item.pdf) {
        pinned = item;
        scrollToPdfPoint(item.pdf.page, item.pdf.y);
        highlightPdf();
      }
    });
    listEl.append(button);
  }
  highlightCode();
  highlightPdf();
}
