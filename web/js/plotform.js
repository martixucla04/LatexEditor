// The Plot mode of the paste-table dialog: the pasted cells as a pgfplots chart.
// Python writes the LaTeX (app/plots.py); the dialog shows a quick SVG drawing of
// the data (approximate: the real look is in the PDF) and the code.

import { call } from "./bridge.js";

const OPTIONS_KEY = "latexeditor.plotOptions";
const DEFAULTS = { type: "markers", grid: true, width: 0.8, height: 0.6 };
const COLOURS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"];
const SVG_NS = "http://www.w3.org/2000/svg";

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

function saveOptions({ type, grid, width, height }) {
  try {
    localStorage.setItem(OPTIONS_KEY, JSON.stringify({ type, grid, width, height }));
  } catch {
    // not remembered
  }
}

const svg = (tag, attrs = {}) => {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};

// A rough drawing of the chart: axes, grid, one colour per series.
function drawPreview(box, preview, type, grid) {
  const W = 360, H = 220, L = 40, R = 10, T = 10, B = 26;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "plot-preview" });
  const ys = preview.series.flat().filter((v) => v !== null);
  if (!preview.x.length || !ys.length) {
    box.replaceChildren(root);
    return;
  }
  let [x0, x1] = [Math.min(...preview.x), Math.max(...preview.x)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  if (type === "bar") { y0 = Math.min(0, y0); x0 -= 0.5; x1 += 0.5; }
  if (x0 === x1) { x0 -= 1; x1 += 1; }
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const px = (x) => L + ((x - x0) / (x1 - x0)) * (W - L - R);
  const py = (y) => H - B - ((y - y0) / (y1 - y0)) * (H - T - B);
  const tick = (v) => (Math.abs(v) >= 1000 || (Math.abs(v) < 0.01 && v !== 0) ? v.toExponential(1) : +v.toFixed(2));
  for (let i = 0; i <= 4; i++) {
    const yv = y0 + ((y1 - y0) * i) / 4, xv = x0 + ((x1 - x0) * i) / 4;
    if (grid) {
      root.append(svg("line", { x1: L, x2: W - R, y1: py(yv), y2: py(yv), class: "grid" }));
      root.append(svg("line", { x1: px(xv), x2: px(xv), y1: T, y2: H - B, class: "grid" }));
    }
    root.append(Object.assign(svg("text", { x: L - 4, y: py(yv) + 3, "text-anchor": "end" }), { textContent: tick(yv) }));
    if (!preview.labels.length) {
      root.append(Object.assign(svg("text", { x: px(xv), y: H - B + 12, "text-anchor": "middle" }), { textContent: tick(xv) }));
    }
  }
  preview.labels.forEach((label, i) => {
    root.append(Object.assign(svg("text", { x: px(i + 1), y: H - B + 12, "text-anchor": "middle" }), { textContent: label.slice(0, 10) }));
  });
  root.append(svg("rect", { x: L, y: T, width: W - L - R, height: H - T - B, class: "frame" }));
  const n = preview.series.length;
  preview.series.forEach((series, s) => {
    const colour = COLOURS[s % COLOURS.length];
    if (type === "bar") {
      const slot = ((W - L - R) / (x1 - x0)) * 0.7, bw = slot / n;
      series.forEach((v, i) => {
        if (v === null) return;
        const x = px(preview.x[i]) - slot / 2 + s * bw;
        root.append(svg("rect", { x, y: Math.min(py(v), py(0)), width: Math.max(1, bw - 1), height: Math.abs(py(0) - py(v)), fill: colour }));
      });
      return;
    }
    if (type !== "scatter") {
      let d = "";
      series.forEach((v, i) => { d += v === null ? " " : `${d && !d.endsWith(" ") ? "L" : "M"}${px(preview.x[i])},${py(v)}`; });
      root.append(svg("path", { d, stroke: colour, fill: "none", "stroke-width": 1.6 }));
    }
    if (type !== "line") {
      series.forEach((v, i) => {
        if (v !== null) root.append(svg("circle", { cx: px(preview.x[i]), cy: py(v), r: 2.6, fill: colour }));
      });
    }
  });
  box.replaceChildren(root);
}

// The form's element, and run(): the final {latex, csv_path, csv} for Insert.
export function createPlotForm(text, { field, box }) {
  const options = loadOptions();
  const type = el("select", {}, [
    el("option", { value: "markers", textContent: "Line with markers" }),
    el("option", { value: "line", textContent: "Line" }),
    el("option", { value: "scatter", textContent: "Scatter (markers only)" }),
    el("option", { value: "bar", textContent: "Bar" }),
  ]);
  type.value = options.type;
  const xSelect = el("select");
  const ysBox = el("div", { className: "plot-ys" });
  const xlabel = el("input", { type: "text" });
  const ylabel = el("input", { type: "text" });
  const legend = el("input", { type: "checkbox" });
  const grid = el("input", { type: "checkbox", checked: options.grid });
  const comma = el("input", { type: "checkbox" });
  const width = el("input", { type: "range", min: 0.4, max: 1, step: 0.05, value: options.width });
  const height = el("select", {}, [["0.45", "Wide"], ["0.6", "Normal"], ["0.75", "Tall"]].map(([v, t]) =>
    el("option", { value: v, textContent: t })));
  height.value = String(options.height);
  const caption = el("input", { type: "text", placeholder: "Caption" });
  const label = el("input", { type: "text", spellcheck: false });
  const notes = el("p", { className: "plot-notes" });
  const drawing = el("div", { className: "plot-drawing" });
  const code = el("pre", { className: "table-preview" });

  let result = null;
  let first = true; // labels, legend and comma start from what Python suggests
  let labelEdited = false;
  label.addEventListener("input", () => { labelEdited = true; update(); });

  const current = () => ({
    type: type.value, x: Number(xSelect.value || 0),
    ys: [...ysBox.querySelectorAll("input:checked")].map((c) => Number(c.value)),
    xlabel: xlabel.value, ylabel: ylabel.value, legend: legend.checked, grid: grid.checked,
    comma: comma.checked, width: Number(width.value), height: Number(height.value),
    caption: caption.value, label: label.value.trim(),
  });

  function renderColumns() {
    xSelect.replaceChildren(...result.columns.map((c, j) => el("option", { value: j, textContent: c.name })));
    xSelect.value = String(result.x);
    ysBox.replaceChildren(...result.columns.map((c, j) => el("label", { className: "plot-y" }, [
      el("input", { type: "checkbox", value: j, checked: result.ys.includes(j), disabled: !c.numeric || j === result.x }),
      c.name,
    ])));
  }

  let timer = null;
  function update() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const opts = first ? { type: type.value, grid: grid.checked, width: Number(width.value),
                               height: Number(height.value), caption: caption.value, label: label.value.trim() }
          : current();
        result = await call("plot_latex", text, opts);
        if (first) {
          first = false;
          renderColumns();
          const cols = result.columns;
          xlabel.value = cols[result.x]?.name ?? "";
          ylabel.value = result.ys.length === 1 ? cols[result.ys[0]].name : "";
          legend.checked = result.ys.length > 1;
          comma.checked = result.comma;
        }
        code.textContent = result.latex || "";
        notes.textContent = result.warnings.join(" ");
        notes.hidden = !result.warnings.length;
        if (result.preview) drawPreview(drawing, result.preview, type.value, grid.checked);
        else drawing.replaceChildren();
      } catch (err) {
        code.textContent = err.message;
      }
    }, 120);
  }

  let namesTimer = null;
  caption.addEventListener("input", () => {
    update();
    clearTimeout(namesTimer);
    namesTimer = setTimeout(async () => {
      if (labelEdited) return;
      try {
        label.value = (await call("figure_names", "", caption.value)).label;
        update();
      } catch {
        // keep the label
      }
    }, 200);
  });
  xSelect.addEventListener("change", () => {
    const x = Number(xSelect.value);
    ysBox.querySelectorAll("input").forEach((c) => {
      const j = Number(c.value);
      c.disabled = !result.columns[j].numeric || j === x;
      if (j === x) c.checked = false;
    });
    xlabel.value = result.columns[x].name;
    update();
  });
  ysBox.addEventListener("change", () => {
    const chosen = [...ysBox.querySelectorAll("input:checked")];
    if (chosen.length === 1) ylabel.value = result.columns[Number(chosen[0].value)].name;
    legend.checked = chosen.length > 1;
    update();
  });
  for (const input of [type, xlabel, ylabel, legend, grid, comma, width, height]) {
    input.addEventListener("input", update);
    input.addEventListener("change", update);
  }

  const element = el("div", { className: "plot-form" }, [
    el("div", { className: "table-options" }, [
      el("div", {}, [
        field("Type", type),
        field("X axis", xSelect),
        field("Y series", ysBox, "numeric columns"),
        field("X label", xlabel),
        field("Y label", ylabel),
      ]),
      el("div", {}, [
        drawing,
        notes,
        field("Width", width, "of the text width"),
        field("Height", height),
        box("Legend", legend),
        box("Grid", grid),
        box("Decimal comma on the axes", comma, "3,65 instead of 3.65"),
        field("Caption", caption),
        field("Label", label),
      ]),
    ]),
    el("div", { className: "ref-preview-box" }, [el("small", { textContent: "LaTeX (needs \\usepackage{pgfplots})" }), code]),
  ]);

  async function run() {
    clearTimeout(timer);
    const opts = current();
    saveOptions(opts);
    const final = await call("plot_latex", text, opts);
    if (!final.latex) throw new Error(final.warnings.join(" ") || "Nothing to plot.");
    return final;
  }

  update();
  return { element, run, stop: () => { clearTimeout(timer); clearTimeout(namesTimer); } };
}
