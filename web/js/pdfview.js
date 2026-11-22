// PDF preview built on PDF.js: continuous scrolling pages with a text layer,
// zoom controls, a page indicator, and the reading position kept across
// recompiles (same zoom, same scroll offset).

import * as pdfjsLib from "../vendor/pdfjs/build/pdf.min.mjs";

globalThis.pdfjsLib = pdfjsLib; // pdf_viewer.mjs looks the library up globally
const { EventBus, PDFLinkService, PDFViewer } = await import("../vendor/pdfjs/web/pdf_viewer.mjs");

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL("../vendor/pdfjs/build/pdf.worker.min.mjs", import.meta.url).href;
const VENDOR = new URL("../vendor/pdfjs/", import.meta.url).href;

const $ = (id) => document.getElementById(id);
const container = $("pdf-container");
const emptyState = $("pdf-empty");
const pageIndicator = $("page-indicator");
const zoomValue = $("zoom-value");
// enabled only while a PDF is shown
const zoomButtons = ["btn-zoom-out", "btn-zoom-in", "btn-fit-width", "btn-download-pdf"].map($);

const eventBus = new EventBus();
const linkService = new PDFLinkService({ eventBus, externalLinkTarget: 2 /* open in a new window */ });
const viewer = new PDFViewer({ container, viewer: $("pdf-pages"), eventBus, linkService });
linkService.setViewer(viewer);

let pdfDoc = null;
let shownTask = null; // loading task of the PDF on screen (destroying it frees the document)
let loadingTask = null; // a newer PDF still loading, if any

function updateIndicators() {
  pageIndicator.textContent = pdfDoc ? `${viewer.currentPageNumber} / ${pdfDoc.numPages}` : "– / –";
  zoomValue.textContent = pdfDoc ? `${Math.round(viewer.currentScale * 100)}%` : "100%";
  for (const button of zoomButtons) button.disabled = !pdfDoc;
}

eventBus.on("pagechanging", updateIndicators);
eventBus.on("scalechanging", updateIndicators);

const pagesInit = () => new Promise((resolve) => eventBus.on("pagesinit", resolve, { once: true }));

// Load the PDF at `url`, keeping zoom and scroll position from the previous one.
export async function showPdf(url) {
  const previous = pdfDoc
    ? { scale: viewer.currentScaleValue, top: container.scrollTop, left: container.scrollLeft }
    : null;

  loadingTask?.destroy();
  const task = pdfjsLib.getDocument({
    url,
    cMapUrl: `${VENDOR}cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${VENDOR}standard_fonts/`,
    wasmUrl: `${VENDOR}wasm/`,
    iccUrl: `${VENDOR}iccs/`,
    disableRange: true,
    isEvalSupported: false,
  });
  loadingTask = task;

  let doc;
  try {
    doc = await task.promise;
  } catch (err) {
    if (task !== loadingTask) return; // superseded by a newer PDF
    loadingTask = null;
    throw err;
  }
  if (task !== loadingTask) return; // superseded (that call destroyed this task)
  loadingTask = null;

  const oldTask = shownTask;
  shownTask = task;
  pdfDoc = doc;
  const ready = pagesInit();
  viewer.setDocument(doc);
  linkService.setDocument(doc);
  emptyState.hidden = true;
  await ready;
  viewer.currentScaleValue = previous?.scale ?? "page-width";
  if (previous) {
    container.scrollTop = previous.top;
    container.scrollLeft = previous.left;
  }
  oldTask?.destroy();
  updateIndicators();
  notifyView();
}

export function clearPdf() {
  loadingTask?.destroy();
  loadingTask = null;
  viewer.setDocument(null);
  linkService.setDocument(null);
  shownTask?.destroy();
  shownTask = null;
  pdfDoc = null;
  emptyState.hidden = false;
  updateIndicators();
  notifyView();
}

export function zoom(steps) {
  if (!pdfDoc) return;
  if (steps > 0) viewer.increaseScale({ steps });
  else viewer.decreaseScale({ steps: -steps });
}

export function fitWidth() {
  if (pdfDoc) viewer.currentScaleValue = "page-width";
}

// ---------------------------------------------------------------------------
// SyncTeX: points and boxes in PDF coordinates (points, top-left origin)
// ---------------------------------------------------------------------------

let inverseHandler = null;

// fn(page, x, y) is called when the user double-clicks a spot in the PDF.
export function onInverseSearch(fn) {
  inverseHandler = fn;
}

container.addEventListener("dblclick", (e) => {
  const pageDiv = e.target.closest(".page");
  if (!pageDiv || !inverseHandler || !pdfDoc) return;
  const pageNumber = Number(pageDiv.dataset.pageNumber);
  const { viewport } = viewer.getPageView(pageNumber - 1);
  const rect = pageDiv.getBoundingClientRect();
  const [px, py] = viewport.convertToPdfPoint(e.clientX - rect.left - pageDiv.clientLeft, e.clientY - rect.top - pageDiv.clientTop);
  const [x0, , , y1] = viewport.viewBox;
  window.getSelection()?.removeAllRanges(); // the double-click also selected a word
  inverseHandler(pageNumber, px - x0, y1 - py);
});

let flashTimer = null;

// Scroll to and briefly highlight source boxes [{page, x, y, w, h}] from synctex.
export function highlightBoxes(boxes) {
  if (!pdfDoc || !boxes.length) return false;
  for (const el of container.querySelectorAll(".synctex-flash")) el.remove();
  clearTimeout(flashTimer);

  const page = boxes[0].page;
  const containerRect = container.getBoundingClientRect();
  let firstTop = null;
  for (const box of boxes.filter((b) => b.page === page)) {
    const pageView = viewer.getPageView(page - 1);
    if (!pageView) continue;
    const { viewport, div } = pageView;
    const [x0, , , y1] = viewport.viewBox;
    // PDF.js 6 only converts points, so map two opposite corners.
    const [ax, ay] = viewport.convertToViewportPoint(x0 + box.x, y1 - box.y - box.h);
    const [bx, by] = viewport.convertToViewportPoint(x0 + box.x + box.w, y1 - box.y);
    const pageRect = div.getBoundingClientRect();
    const left = pageRect.left - containerRect.left + container.scrollLeft + div.clientLeft + Math.min(ax, bx);
    const top = pageRect.top - containerRect.top + container.scrollTop + div.clientTop + Math.min(ay, by);
    const flash = document.createElement("div");
    flash.className = "synctex-flash";
    Object.assign(flash.style, {
      left: `${left - 2}px`,
      top: `${top - 2}px`,
      width: `${Math.max(Math.abs(bx - ax), 6) + 4}px`,
      height: `${Math.max(Math.abs(by - ay), 6) + 4}px`,
    });
    container.append(flash);
    firstTop ??= top;
  }
  if (firstTop !== null) container.scrollTo({ top: Math.max(0, firstTop - container.clientHeight / 3), behavior: "smooth" });
  flashTimer = setTimeout(() => {
    for (const el of container.querySelectorAll(".synctex-flash")) el.remove();
  }, 2500);
  return firstTop !== null;
}

// ---------------------------------------------------------------------------
// Reading position, for the outline: which point of the PDF is in view
// ---------------------------------------------------------------------------

const viewListeners = [];
let viewFrame = 0;

// fn() is called (at most once per frame) when the visible part of the PDF changes.
export function onViewChange(fn) {
  viewListeners.push(fn);
}

function notifyView() {
  if (viewFrame) return;
  viewFrame = requestAnimationFrame(() => {
    viewFrame = 0;
    for (const fn of viewListeners) fn();
  });
}

container.addEventListener("scroll", notifyView, { passive: true });
eventBus.on("scalechanging", notifyView);

// {pages, height}: the shown PDF's page count and its first page's height in PDF points.
export function pdfPages() {
  if (!pdfDoc) return null;
  const view = viewer.getPageView(0)?.viewport?.viewBox;
  return { pages: pdfDoc.numPages, height: view ? view[3] - view[1] : 842 };
}

// {page, y} (PDF points from the page top) of the point a quarter down the visible area
// (the bottom of it once scrolled to the end, where the last headings never reach the top).
export function viewPosition() {
  if (!pdfDoc) return null;
  const box = container.getBoundingClientRect();
  const atEnd = container.scrollTop + container.clientHeight >= container.scrollHeight - 2;
  const ref = box.top + (atEnd ? container.clientHeight - 1 : container.clientHeight / 4);
  for (let i = 0; i < pdfDoc.numPages; i++) {
    const pageView = viewer.getPageView(i);
    if (!pageView) continue;
    const rect = pageView.div.getBoundingClientRect();
    if (rect.bottom < ref) continue;
    if (rect.top > ref) return { page: i + 1, y: 0 }; // in the gap above this page
    const [, py] = pageView.viewport.convertToPdfPoint(0, ref - rect.top - pageView.div.clientTop);
    return { page: i + 1, y: pageView.viewport.viewBox[3] - py };
  }
  return { page: pdfDoc.numPages, y: Infinity };
}

// Scroll so that point `y` (PDF points from the top) of `page` is near the top of the view.
export function scrollToPdfPoint(page, y) {
  const pageView = pdfDoc && viewer.getPageView(page - 1);
  if (!pageView) return;
  const { viewport, div } = pageView;
  const [x0, , , y1] = viewport.viewBox;
  const [, vy] = viewport.convertToViewportPoint(x0, y1 - y);
  const top = div.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop + div.clientTop + vy;
  container.scrollTo({ top: Math.max(0, top - 12), behavior: "smooth" });
}

$("btn-zoom-in").addEventListener("click", () => zoom(1));
$("btn-zoom-out").addEventListener("click", () => zoom(-1));
$("btn-fit-width").addEventListener("click", fitWidth);

// Ctrl + mouse wheel zooms the PDF (not the whole page).
container.addEventListener("wheel", (e) => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  zoom(e.deltaY < 0 ? 1 : -1);
}, { passive: false });

// Keep "fit width" fitting when the pane is resized.
new ResizeObserver(() => {
  if (pdfDoc && viewer.currentScaleValue === "page-width") viewer.currentScaleValue = "page-width";
}).observe(container);

updateIndicators();
