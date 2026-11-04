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
const zoomButtons = ["btn-zoom-out", "btn-zoom-in", "btn-fit-width"].map($);

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
}

export function zoom(steps) {
  if (!pdfDoc) return;
  if (steps > 0) viewer.increaseScale({ steps });
  else viewer.decreaseScale({ steps: -steps });
}

export function fitWidth() {
  if (pdfDoc) viewer.currentScaleValue = "page-width";
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
