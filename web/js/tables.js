// "Paste table" dialog: cells copied from Excel (tab-separated text on the clipboard)
// become a LaTeX table. The user picks the environment (tabular, tabularx, longtable),
// each column's type, the vertical and horizontal lines, the header row and the
// caption; Python writes the LaTeX (app/tables.py) and the preview shows it as typed.
// Missing packages (tabularx, longtable, booktabs) can be added to the preamble.

import { call } from "./bridge.js";
import * as editor from "./editor.js";
import { createPlotForm } from "./plotform.js";
import { showError, toast } from "./ui.js";

const OPTIONS_KEY = "latexeditor.tableOptions";
const MODE_KEY = "latexeditor.pasteMode"; // "table" | "plot", the mode used last
const DEFAULTS = { env: "tabular", float: true, caption_position: "top", vlines: "none", hlines: "booktabs",
                   header: true, bold_header: true, escape: true, add_packages: true };

let handlers = { saveAll: async () => true, afterChange: async () => {}, buffers: () => [], refreshProject: async () => {} };

export function initTables(options) {
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
  const { columns, caption, label, ...kept } = options; // these belong to this table only
  try {
    localStorage.setItem(OPTIONS_KEY, JSON.stringify(kept));
  } catch {
    // not remembered
  }
}

const select = (choices, value) => {
  const node = el("select", {}, choices.map(([v, label]) => el("option", { value: v, textContent: label })));
  node.value = value;
  return node;
};

const COLUMN_TYPES = [["l", "Left"], ["c", "Centre"], ["r", "Right"], ["p", "Wrap (p)"], ["X", "Fill (X)"]];

export async function openTableDialog(text) {
  const options = loadOptions();
  const env = select([["tabular", "tabular — normal table"], ["tabularx", "tabularx — full text width"],
                      ["longtable", "longtable — breaks across pages"]], options.env);
  const vlines = select([["none", "None"], ["outer", "Outer border"], ["inner", "Between columns"],
                         ["all", "All"]], options.vlines);
  const hlines = select([["booktabs", "booktabs (top, mid, bottom rules)"], ["frame", "Top, under header, bottom"],
                         ["all", "Every row"], ["header", "Under the header only"], ["none", "None"]], options.hlines);
  const check = (key) => el("input", { type: "checkbox", checked: !!options[key] });
  const header = check("header");
  const bold = check("bold_header");
  const escape = check("escape");
  const float = check("float");
  const addPackages = check("add_packages");
  const caption = el("input", { type: "text", placeholder: "Caption (optional)" });
  const label = el("input", { type: "text", placeholder: "tab:name", spellcheck: false });
  const captionPos = select([["top", "Caption above"], ["bottom", "Caption below"]], options.caption_position);
  const columnsBox = el("div", { className: "table-columns" });
  const setAll = select([["", "Set all…"], ...COLUMN_TYPES], "");
  const preview = el("pre", { className: "table-preview" });
  const packagesNote = el("label", { className: "ref-field checkbox table-packages", hidden: true });
  const info = el("small", { className: "table-info" });

  let columns = null; // column types; null = let Python choose (numbers right, text left/X)
  let columnSelects = [];
  let result = null;

  const current = () => ({
    env: env.value, vlines: vlines.value, hlines: hlines.value, header: header.checked,
    bold_header: bold.checked, escape: escape.checked, float: float.checked,
    caption_position: captionPos.value, caption: caption.value, label: label.value.trim(),
    add_packages: addPackages.checked, columns,
  });

  function renderColumns() {
    const rows = result.rows;
    columnSelects = result.columns.map((type, j) => {
      const s = select(COLUMN_TYPES.filter(([v]) => v !== "X" || env.value === "tabularx"), type === "X" && env.value !== "tabularx" ? "p" : type);
      s.addEventListener("change", () => { columns = columnSelects.map((c) => c.value); update(); });
      return s;
    });
    columnsBox.replaceChildren(...columnSelects.map((s, j) => el("label", { className: "table-column" }, [
      el("span", { textContent: rows[0][j] || `Column ${j + 1}`, title: rows[0][j] || "" }), s,
    ])));
  }

  let timer = null;
  function update() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const options = current();
        result = await call("table_latex", text, options, Object.fromEntries(
          handlers.buffers().map((b) => [b.path, b.text])));
        const typesChanged = !columns || columnSelects.length !== result.columns.length;
        columns = result.columns;
        if (typesChanged || columnSelects.some((s, j) => s.value !== columns[j])) renderColumns();
        preview.textContent = result.latex;
        const rows = result.rows.length;
        info.textContent = `${rows} row${rows === 1 ? "" : "s"} × ${result.columns.length} column${result.columns.length === 1 ? "" : "s"}`;
        packagesNote.hidden = !result.missing.length;
        packagesNote.firstChild.firstChild.textContent =
          `Add \\usepackage{${result.missing.join(",")}} to the preamble`;
        caption.disabled = label.disabled = captionPos.disabled = env.value !== "longtable" && !float.checked;
        captionPos.disabled ||= env.value === "longtable";
        float.disabled = env.value === "longtable";
      } catch (err) {
        preview.textContent = err.message;
      }
    }, 120);
  }

  packagesNote.append(el("span", {}, ["", el("small", { textContent: "Needed by the chosen table; no .tex file of the project loads it yet" })]), addPackages);

  env.addEventListener("change", () => {
    // X columns only exist in tabularx: going there, text columns fill the width; leaving, they wrap.
    if (columns) {
      columns = columns.map((c) => (env.value === "tabularx" ? (c === "l" ? "X" : c) : (c === "X" ? "l" : c)));
    }
    update();
  });
  setAll.addEventListener("change", () => {
    if (!setAll.value) return;
    columns = columnSelects.map(() => (setAll.value === "X" && env.value !== "tabularx" ? "p" : setAll.value));
    setAll.value = "";
    update();
  });
  header.addEventListener("change", () => { columns = null; update(); }); // numeric columns depend on it
  for (const input of [vlines, hlines, bold, escape, float, captionPos, caption, label]) {
    input.addEventListener("input", update);
    input.addEventListener("change", update);
  }
  setAll.querySelectorAll("option").forEach((o) => { if (o.value === "X") o.textContent = "Fill (X, tabularx)"; });

  const field = (title, input, hint) => el("label", { className: "ref-field" }, [
    el("span", {}, [title, hint ? el("small", { textContent: hint }) : ""]), input]);
  const box = (title, input, hint) => el("label", { className: "ref-field checkbox" }, [
    el("span", {}, [title, hint ? el("small", { textContent: hint }) : ""]), input]);

  const asText = el("button", { type: "button", className: "btn", textContent: "Paste as text" });
  const cancel = el("button", { type: "button", className: "btn", textContent: "Cancel" });
  const insert = el("button", { className: "btn primary", textContent: "Insert table" });
  const plot = createPlotForm(text, { field, box });
  const modeButtons = ["table", "plot"].map((m) => el("button", {
    type: "button", className: "mode-btn", textContent: m === "table" ? "Table" : "Plot", value: m,
  }));
  const title = el("span", { textContent: "Paste table" });
  let mode = "table";
  try {
    mode = localStorage.getItem(MODE_KEY) === "plot" ? "plot" : "table";
  } catch {
    // table
  }
  const tableBody = el("div", { className: "table-body" });
  function setMode(next) {
    mode = next;
    for (const b of modeButtons) b.setAttribute("aria-pressed", b.value === mode);
    tableBody.hidden = mode !== "table";
    plot.element.hidden = mode !== "plot";
    title.textContent = mode === "table" ? "Paste table" : "Paste as plot";
    insert.textContent = mode === "table" ? "Insert table" : "Insert plot";
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      // not remembered
    }
  }
  for (const b of modeButtons) b.addEventListener("click", () => setMode(b.value));
  tableBody.append(
    el("div", { className: "table-options" }, [
      el("div", {}, [
        field("Environment", env),
        field("Vertical lines", vlines),
        field("Horizontal lines", hlines, "booktabs needs \\usepackage{booktabs}"),
        box("First row is the header", header, "longtable repeats it on every page"),
        box("Header in bold", bold),
        box("Escape special characters", escape, "& % $ # _ { } ~ ^ \\ written as text"),
      ]),
      el("div", {}, [
        box("Floating table, centred", float, "table environment with caption and label"),
        field("Caption", caption),
        field("Label", label),
        field("Caption position", captionPos),
      ]),
    ]),
    el("div", { className: "table-columns-row" }, [
      el("div", { className: "table-columns-head" }, [el("span", { textContent: "Columns" }), setAll]),
      columnsBox,
    ]),
    packagesNote,
    el("div", { className: "ref-preview-box" }, [el("small", { textContent: "LaTeX" }), preview]),
  );
  const form = el("form", {}, [
    el("h2", {}, [title, " ", info, el("span", { className: "spacer" }), el("span", { className: "mode-switch" }, modeButtons)]),
    tableBody,
    plot.element,
    el("div", { className: "modal-actions" }, [asText, el("span", { className: "spacer" }), cancel, insert]),
  ]);
  const dialog = el("dialog", { className: "modal references tables" }, [form]);
  document.body.append(dialog);
  const close = () => {
    clearTimeout(timer);
    plot.stop();
    if (dialog.open) dialog.close();
    dialog.remove();
    editor.focusEditor();
  };
  cancel.addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  asText.addEventListener("click", () => {
    close();
    editor.insertText(text);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearTimeout(timer);
    insert.disabled = true;
    if (mode === "plot") {
      insertPlot();
      return;
    }
    try {
      const options = current();
      saveOptions(options);
      const final = await call("table_latex", text, options, Object.fromEntries(
        handlers.buffers().map((b) => [b.path, b.text])));
      close();
      editor.insertText(final.latex);
      if (!final.missing.length || !options.add_packages) return;
      if (!(await handlers.saveAll())) throw new Error("Could not save the open files.");
      const added = await call("add_packages", final.missing);
      await handlers.afterChange(added.changed);
      if (added.added.length) {
        toast(`Added \\usepackage{${added.added.join(",")}} to ${added.file}`, "success", 6000);
      }
    } catch (err) {
      showError(err);
      insert.disabled = false;
    }
  });

  async function insertPlot() {
    try {
      const final = await plot.run();
      if (final.csv_path) await call("save_plot_data", final.csv_path, final.csv);
      close();
      editor.insertText(final.latex);
      const buffers = Object.fromEntries(handlers.buffers().map((b) => [b.path, b.text]));
      const missing = await call("missing_packages", ["pgfplots"], buffers);
      let note = final.csv_path ? ` Data saved in ${final.csv_path}.` : "";
      if (missing.length) {
        if (!(await handlers.saveAll())) throw new Error("Could not save the open files.");
        const added = await call("add_packages", missing);
        await handlers.afterChange(added.changed);
        if (added.added.length) note += ` Added \\usepackage{pgfplots} to ${added.file}.`;
      }
      if (note) toast(`Plot inserted.${note}`, "success", 6000);
      if (final.csv_path) await handlers.refreshProject();
    } catch (err) {
      showError(err);
      insert.disabled = false;
    }
  }

  setMode(mode);
  dialog.showModal();
  update();
  (mode === "table" ? env : modeButtons[1]).focus();
}
