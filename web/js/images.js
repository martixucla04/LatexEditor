// "Paste image" dialog: a screenshot pasted into a .tex file becomes a PNG in the project
// and a figure block in the document's style. The image can be cropped (drag on the
// preview), trimmed (empty border cut off) and have a plain background made white or
// transparent (flood fill from the edges, so lines inside the drawing are kept).
// Python picks free names and writes the file (app/images.py).

import { call } from "./bridge.js";
import * as editor from "./editor.js";
import { showError, toast } from "./ui.js";

const OPTIONS_KEY = "latexeditor.imageOptions";
const DEFAULTS = { width: 0.8, background: "none", tolerance: 15, folder: null };
const PREVIEW_W = 420;
const PREVIEW_H = 280;

let handlers = { saveAll: async () => true, afterChange: async () => {}, refreshProject: async () => {}, buffers: () => [] };

export function initImages(options) {
  handlers = { ...handlers, ...options };
}

const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

function loadOptions() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(OPTIONS_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

function saveOptions(options) {
  try {
    localStorage.setItem(OPTIONS_KEY, JSON.stringify(options));
  } catch {
    // not remembered
  }
}

// --- image operations on canvases ------------------------------------------------

function canvasOf(width, height) {
  return Object.assign(document.createElement("canvas"), { width, height });
}

function cropCanvas(source, x, y, w, h) {
  const out = canvasOf(w, h);
  out.getContext("2d").drawImage(source, x, y, w, h, 0, 0, w, h);
  return out;
}

const distance = (d, i, c) => Math.max(Math.abs(d[i] - c[0]), Math.abs(d[i + 1] - c[1]), Math.abs(d[i + 2] - c[2]));

// The most common colour along the border (transparent pixels count as white).
function edgeColour(data, w, h) {
  const counts = new Map();
  const add = (x, y) => {
    const i = (y * w + x) * 4;
    const key = data[i + 3] < 128 ? 0xffffff : (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
    counts.set(key, (counts.get(key) || 0) + 1);
  };
  for (let x = 0; x < w; x++) { add(x, 0); add(x, h - 1); }
  for (let y = 0; y < h; y++) { add(0, y); add(w - 1, y); }
  const key = [...counts].sort((a, b) => b[1] - a[1])[0][0];
  return [(key >> 16) & 255, (key >> 8) & 255, key & 255];
}

// Bounding box of the pixels that differ from the border colour: the image without its empty margin.
function trimBox(canvas, tolerance) {
  const { width: w, height: h } = canvas;
  const { data } = canvas.getContext("2d").getImageData(0, 0, w, h);
  const colour = edgeColour(data, w, h);
  const limit = tolerance * 2.55;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (data[i + 3] >= 128 && distance(data, i, colour) > limit) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  if (x1 < 0) return null; // only background
  const pad = 2;
  x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad);
  x1 = Math.min(w - 1, x1 + pad); y1 = Math.min(h - 1, y1 + pad);
  return { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
}

// Background reached from the edges through pixels near the border colour -> white or transparent.
function removeBackground(source, mode, tolerance) {
  const { width: w, height: h } = source;
  const out = cropCanvas(source, 0, 0, w, h);
  if (mode === "none") return out;
  const ctx = out.getContext("2d");
  const image = ctx.getImageData(0, 0, w, h);
  const data = image.data;
  const colour = edgeColour(data, w, h);
  const limit = tolerance * 2.55;
  const seen = new Uint8Array(w * h);
  const stack = [];
  const push = (x, y) => {
    const p = y * w + x;
    if (seen[p]) return;
    seen[p] = 1;
    const i = p * 4;
    if (data[i + 3] < 128 || distance(data, i, colour) <= limit) stack.push(p);
  };
  for (let x = 0; x < w; x++) { push(x, 0); push(x, h - 1); }
  for (let y = 0; y < h; y++) { push(0, y); push(w - 1, y); }
  while (stack.length) {
    const p = stack.pop();
    const i = p * 4;
    if (mode === "white") {
      data[i] = data[i + 1] = data[i + 2] = data[i + 3] = 255;
    } else {
      data[i + 3] = 0;
    }
    const x = p % w, y = (p - x) / w;
    if (x > 0) push(x - 1, y);
    if (x < w - 1) push(x + 1, y);
    if (y > 0) push(x, y - 1);
    if (y < h - 1) push(x, y + 1);
  }
  ctx.putImageData(image, 0, 0);
  return out;
}

const pngBase64 = (canvas) => new Promise((resolve, reject) => {
  canvas.toBlob((blob) => {
    if (!blob) return reject(new Error("Could not encode the image."));
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  }, "image/png");
});

// --- LaTeX ------------------------------------------------------------------------

export function figureLatex({ path, width, caption, source, label }) {
  const w = Number(width) >= 0.999 ? "\\textwidth" : `${Number(width).toFixed(2).replace(/0$/, "")}\\textwidth`;
  const full = source.trim() ? `${caption.trim()} (Font: ${source.trim()})` : caption.trim();
  return [
    "\\begin{figure}[ht]",
    "    \\centering",
    `    \\includegraphics[width=${w}]{${path}}`,
    `    \\caption{${full}}`,
    ...(label.trim() ? [`    \\label{${label.trim()}}`] : []),
    "\\end{figure}",
    "",
  ].join("\n");
}

// --- dialog -------------------------------------------------------------------------

export async function openImageDialog(file) {
  let original;
  try {
    const bitmap = await createImageBitmap(file);
    original = canvasOf(bitmap.width, bitmap.height);
    original.getContext("2d").drawImage(bitmap, 0, 0);
  } catch {
    showError(new Error("The clipboard image could not be read."));
    return;
  }
  const options = loadOptions();
  // Figures before the cursor come last, so Python's "last \includegraphics" is the nearest one above.
  const where = editor.textAroundCursor();
  let folders;
  try {
    folders = await call("image_folders", where.after + "\n" + where.before);
  } catch (err) {
    showError(err);
    return;
  }

  let work = original; // after crop and trim
  let shown = null; // after the background step: what is saved
  let scale = 1;

  const preview = el("canvas", { className: "image-preview", width: PREVIEW_W, height: PREVIEW_H });
  const sizeNote = el("small", { className: "image-size" });
  const resetCrop = el("button", { type: "button", className: "btn", textContent: "Reset" });
  const trim = el("button", { type: "button", className: "btn", textContent: "Trim margins" });
  const background = el("select", {}, [
    el("option", { value: "none", textContent: "Keep background" }),
    el("option", { value: "white", textContent: "Make background white" }),
    el("option", { value: "transparent", textContent: "Make background transparent" }),
  ]);
  background.value = options.background;
  const tolerance = el("input", { type: "range", min: 0, max: 60, step: 1, value: options.tolerance });
  const caption = el("input", { type: "text", placeholder: "Caption" });
  const label = el("input", { type: "text", spellcheck: false });
  const width = el("input", { type: "range", min: 0.3, max: 1, step: 0.05, value: options.width });
  const widthValue = el("span", { className: "image-width-value" });
  const pageBox = el("div", { className: "image-page" }, [el("div", { className: "image-page-figure" })]);
  const folderList = el("datalist", { id: "image-folders" },
    folders.folders.map((f) => el("option", { value: f })));
  // the current file's figures decide; without any, the folder used last time
  const hasFigure = /\\includegraphics/.test(where.before + where.after);
  const remembered = options.folder && folders.folders.includes(options.folder) ? options.folder : null;
  const folder = el("input", { type: "text", spellcheck: false, value: hasFigure ? folders.default : remembered ?? folders.default });
  folder.setAttribute("list", "image-folders");
  const fileName = el("input", { type: "text", spellcheck: false });
  const source = el("input", { type: "text", placeholder: "e.g. \\cite{ltc6811} or Analog Devices" });
  const code = el("pre", { className: "table-preview" });
  let labelEdited = false;
  let fileEdited = false;
  label.addEventListener("input", () => { labelEdited = true; updateCode(); });
  fileName.addEventListener("input", () => { fileEdited = true; updateCode(); });

  function render() {
    shown = removeBackground(work, background.value, Number(tolerance.value));
    scale = Math.min(PREVIEW_W / shown.width, PREVIEW_H / shown.height, 1);
    const ctx = preview.getContext("2d");
    ctx.clearRect(0, 0, PREVIEW_W, PREVIEW_H);
    const w = shown.width * scale, h = shown.height * scale;
    preview.dataset.ox = (PREVIEW_W - w) / 2;
    preview.dataset.oy = (PREVIEW_H - h) / 2;
    ctx.drawImage(shown, Number(preview.dataset.ox), Number(preview.dataset.oy), w, h);
    sizeNote.textContent = `${shown.width} × ${shown.height} px · drag on the image to crop`;
    resetCrop.disabled = work === original;
  }

  // Crop by dragging a rectangle on the preview.
  let drag = null;
  const toImage = (e) => {
    const r = preview.getBoundingClientRect();
    const px = (e.clientX - r.left) * (PREVIEW_W / r.width) - Number(preview.dataset.ox);
    const py = (e.clientY - r.top) * (PREVIEW_H / r.height) - Number(preview.dataset.oy);
    return { x: Math.max(0, Math.min(work.width, px / scale)), y: Math.max(0, Math.min(work.height, py / scale)) };
  };
  preview.addEventListener("pointerdown", (e) => {
    drag = { start: toImage(e), end: toImage(e) };
    preview.setPointerCapture(e.pointerId);
  });
  preview.addEventListener("pointermove", (e) => {
    if (!drag) return;
    drag.end = toImage(e);
    render();
    const ctx = preview.getContext("2d");
    const x = Math.min(drag.start.x, drag.end.x) * scale + Number(preview.dataset.ox);
    const y = Math.min(drag.start.y, drag.end.y) * scale + Number(preview.dataset.oy);
    ctx.strokeStyle = "#2f81f7";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(x, y, Math.abs(drag.end.x - drag.start.x) * scale, Math.abs(drag.end.y - drag.start.y) * scale);
  });
  preview.addEventListener("pointerup", () => {
    if (!drag) return;
    const x = Math.round(Math.min(drag.start.x, drag.end.x)), y = Math.round(Math.min(drag.start.y, drag.end.y));
    const w = Math.round(Math.abs(drag.end.x - drag.start.x)), h = Math.round(Math.abs(drag.end.y - drag.start.y));
    drag = null;
    if (w >= 8 && h >= 8) work = cropCanvas(work, x, y, w, h);
    render();
  });
  resetCrop.addEventListener("click", () => { work = original; render(); });
  trim.addEventListener("click", () => {
    const box = trimBox(work, Number(tolerance.value));
    if (box && (box.w < work.width || box.h < work.height)) {
      work = cropCanvas(work, box.x, box.y, box.w, box.h);
      render();
    } else {
      toast("No empty margin to trim.", "info");
    }
  });
  background.addEventListener("change", render);
  tolerance.addEventListener("input", render);

  function updateWidth() {
    widthValue.textContent = `${Number(width.value).toFixed(2)} × text width`;
    pageBox.firstChild.style.width = `${Number(width.value) * 100}%`;
    updateCode();
  }
  width.addEventListener("input", updateWidth);

  const pathOf = () => [folder.value.trim().replace(/\/+$/, ""), fileName.value.trim() || "figura.png"].filter(Boolean).join("/");
  function updateCode() {
    code.textContent = figureLatex({
      path: pathOf(), width: width.value, caption: caption.value, source: source.value, label: label.value,
    });
  }
  source.addEventListener("input", updateCode);

  let namesTimer = null;
  function updateNames() {
    clearTimeout(namesTimer);
    namesTimer = setTimeout(async () => {
      try {
        const names = await call("figure_names", folder.value.trim().replace(/\/+$/, ""), caption.value);
        if (!labelEdited) label.value = names.label;
        if (!fileEdited) fileName.value = names.file;
        updateCode();
      } catch {
        // an invalid folder name: shown when saving
      }
    }, 200);
  }
  caption.addEventListener("input", () => { updateCode(); updateNames(); });
  folder.addEventListener("change", updateNames);

  const field = (title, input, hint) => el("label", { className: "ref-field" }, [
    el("span", {}, [title, hint ? el("small", { textContent: hint }) : ""]), input]);

  const saveOnly = el("button", { type: "button", className: "btn", textContent: "Save image only" });
  const cancel = el("button", { type: "button", className: "btn", textContent: "Cancel" });
  const insert = el("button", { className: "btn primary", textContent: "Insert figure" });
  const form = el("form", {}, [
    el("h2", { textContent: "Paste image" }),
    el("div", { className: "image-layout" }, [
      el("div", { className: "image-edit" }, [
        preview,
        el("div", { className: "image-tools" }, [sizeNote, el("span", { className: "spacer" }), trim, resetCrop]),
        el("div", { className: "image-tools" }, [background, el("label", { className: "image-tolerance" }, ["Tolerance", tolerance])]),
      ]),
      el("div", { className: "image-fields" }, [
        field("Caption", caption),
        field("Source", source, "optional, added as (Font: …)"),
        field("Label", label),
        field("Width", el("div", { className: "image-width" }, [width, widthValue, pageBox])),
        field("Folder", el("div", {}, [folder, folderList])),
        field("File name", fileName),
      ]),
    ]),
    el("div", { className: "ref-preview-box" }, [el("small", { textContent: "LaTeX" }), code]),
    el("div", { className: "modal-actions" }, [saveOnly, el("span", { className: "spacer" }), cancel, insert]),
  ]);
  const dialog = el("dialog", { className: "modal references tables images" }, [form]);
  document.body.append(dialog);
  const close = () => {
    clearTimeout(namesTimer);
    if (dialog.open) dialog.close();
    dialog.remove();
    editor.focusEditor();
  };
  cancel.addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });

  async function save() {
    saveOptions({ width: Number(width.value), background: background.value,
                  tolerance: Number(tolerance.value), folder: folder.value.trim() });
    return call("save_image", folder.value.trim().replace(/\/+$/, ""), fileName.value.trim() || "figura.png",
                await pngBase64(shown));
  }

  saveOnly.addEventListener("click", async () => {
    saveOnly.disabled = insert.disabled = true;
    try {
      const path = await save();
      close();
      await handlers.refreshProject();
      toast(`Saved ${path}`, "success");
    } catch (err) {
      showError(err);
      saveOnly.disabled = insert.disabled = false;
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    saveOnly.disabled = insert.disabled = true;
    try {
      const path = await save();
      close();
      editor.insertText(figureLatex({
        path, width: width.value, caption: caption.value, source: source.value, label: label.value,
      }));
      await handlers.refreshProject();
      const buffers = Object.fromEntries(handlers.buffers().map((b) => [b.path, b.text]));
      const missing = await call("missing_packages", ["graphicx"], buffers);
      let note = "";
      if (missing.length) {
        if (!(await handlers.saveAll())) throw new Error("Could not save the open files.");
        const added = await call("add_packages", missing);
        await handlers.afterChange(added.changed);
        if (added.added.length) note = ` and added \\usepackage{graphicx} to ${added.file}`;
      }
      toast(`Saved ${path}${note}`, "success");
    } catch (err) {
      showError(err);
      saveOnly.disabled = insert.disabled = false;
    }
  });

  render();
  updateWidth();
  updateNames();
  dialog.showModal();
  caption.focus();
}
