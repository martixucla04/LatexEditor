// "Add reference" dialog: choose what you are citing (book, part of a book,
// standard, catalogue, periodical, journal/newspaper article, official
// publication, web page); the form, the formatting rules and a live preview
// come from Python (app/reftypes.py). On Add: \cite{key} goes at the cursor,
// open files are saved, and Python adds the entry to the bibliography
// (a .bib @misc entry or a \bibitem, see app/references.py).

import { call } from "./bridge.js";
import * as editor from "./editor.js";
import { showError, toast } from "./ui.js";

const LAST_TYPE_KEY = "latexeditor.referenceType";
const CITE_KEY = "latexeditor.referenceCite";

let handlers = { saveAll: async () => true, afterChange: async () => {} };

export function initReferences(options) {
  handlers = { ...handlers, ...options };
}

const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// LaTeX source of the entry -> how it reads in the PDF (for the preview only).
function readable(latex) {
  return latex
    .replace(/\\url\{([^}]*)\}/g, "$1")
    .replace(/\\textbackslash\{\}/g, "\\")
    .replace(/\\textasciitilde\{\}/g, "~")
    .replace(/\\textasciicircum\{\}/g, "^")
    .replace(/\\([&%$#_{}])/g, "$1");
}

function loadLastType(types) {
  try {
    const saved = localStorage.getItem(LAST_TYPE_KEY);
    if (types.some((t) => t.id === saved)) return saved;
  } catch {
    // default below
  }
  return "web";
}

function rememberType(id) {
  try {
    localStorage.setItem(LAST_TYPE_KEY, id);
  } catch {
    // not remembered
  }
}

function loadCite() {
  try {
    return localStorage.getItem(CITE_KEY) !== "no";
  } catch {
    return true;
  }
}

function rememberCite(cite) {
  try {
    localStorage.setItem(CITE_KEY, cite ? "yes" : "no");
  } catch {
    // not remembered
  }
}

export async function openReferenceDialog() {
  let types;
  try {
    types = await call("reference_types");
  } catch (err) {
    showError(err);
    return;
  }

  const kind = el("select", { className: "ref-kind" },
    types.map((t) => el("option", { value: t.id, textContent: t.label })));
  kind.value = loadLastType(types);
  const fieldsBox = el("div", { className: "ref-fields" });
  const key = el("input", { type: "text", spellcheck: false, placeholder: "automatic" });
  const preview = el("p", { className: "ref-preview" });
  const keyNote = el("small", { className: "ref-key-note" });
  // Unticked: the reference is only listed in the bibliography (BibTeX/biblatex get \nocite).
  const cite = el("input", { type: "checkbox", checked: loadCite(), className: "ref-cite" });
  cite.addEventListener("change", () => { rememberCite(cite.checked); updatePreview(); });
  let inputs = {}; // field id -> input
  let keyEdited = false;
  key.addEventListener("input", () => { keyEdited = true; updatePreview(); });

  const values = () => {
    const out = {};
    for (const [id, input] of Object.entries(inputs)) out[id] = input.type === "checkbox" ? input.checked : input.value;
    if (keyEdited) out.key = key.value.trim();
    return out;
  };

  // Build the form for the chosen type, keeping values typed into fields that both types share.
  function renderFields() {
    const type = types.find((t) => t.id === kind.value);
    const previous = values();
    inputs = {};
    fieldsBox.replaceChildren();
    for (const f of type.fields) {
      const input = el("input", {
        type: f.type === "checkbox" ? "checkbox" : f.type || "text",
        placeholder: f.placeholder || "",
        required: !!f.required && f.type !== "checkbox",
        spellcheck: f.type !== "url",
      });
      if (f.type === "checkbox") input.checked = !!previous[f.id];
      else input.value = previous[f.id] ?? f.default ?? "";
      input.addEventListener("input", updatePreview);
      input.addEventListener("change", updatePreview);
      inputs[f.id] = input;
      fieldsBox.append(el("label", { className: `ref-field${f.type === "checkbox" ? " checkbox" : ""}` }, [
        el("span", {}, [f.label + (f.required ? " *" : ""), f.hint ? el("small", { textContent: f.hint }) : ""]),
        input,
      ]));
    }
    updatePreview();
  }

  let timer = null;
  function updatePreview() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const type = types.find((t) => t.id === kind.value);
      const missing = type.fields.filter((f) => f.required && f.type !== "checkbox" && !inputs[f.id].value.trim());
      if (missing.length) {
        preview.textContent = `Fill in: ${missing.map((f) => f.label).join(", ")}.`;
        preview.classList.add("empty");
        keyNote.textContent = "";
        return;
      }
      try {
        const result = await call("preview_reference", kind.value, values());
        preview.replaceChildren(...readable(result.text).split(" \\newline ").flatMap((line, i) =>
          (i ? [el("br"), line] : [line])));
        preview.classList.remove("empty");
        if (!keyEdited) key.value = result.key;
        const shownKey = keyEdited ? key.value.trim() : result.key;
        keyNote.textContent = cite.checked
          ? `Cited as \\cite{${shownKey}} at the cursor`
          : `Listed in the bibliography only, not cited in the text (key ${shownKey})`;
      } catch (err) {
        preview.textContent = err.message;
        preview.classList.add("empty");
      }
    }, 200);
  }

  kind.addEventListener("change", () => {
    rememberType(kind.value);
    renderFields();
  });

  const cancel = el("button", { type: "button", className: "btn", textContent: "Cancel" });
  const add = el("button", { className: "btn primary", textContent: "Add reference" });
  const form = el("form", {}, [
    el("h2", { textContent: "Add reference" }),
    el("label", { className: "ref-field ref-kind-row" }, [el("span", { textContent: "What are you citing?" }), kind]),
    fieldsBox,
    el("label", { className: "ref-field" }, [el("span", { textContent: "Citation key" }), key]),
    el("label", { className: "ref-field checkbox" }, [
      el("span", {}, ["Cite it at the cursor", el("small", { textContent: "Untick to only list it in the bibliography" })]),
      cite,
    ]),
    el("div", { className: "ref-preview-box" }, [el("small", { textContent: "Preview" }), preview, keyNote]),
    el("div", { className: "modal-actions" }, [cancel, add]),
  ]);
  const dialog = el("dialog", { className: "modal references" }, [form]);
  document.body.append(dialog);
  const close = () => {
    if (dialog.open) dialog.close();
    dialog.remove();
  };
  cancel.addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    add.disabled = true;
    try {
      const fields = values();
      const { key: citeKey } = await call("preview_reference", kind.value, fields);
      const wantCite = cite.checked;
      // \cite first (so it is saved with the rest), then the entry on disk.
      const cited = wantCite && editor.insertCitation(citeKey);
      if (!(await handlers.saveAll())) throw new Error("Could not save the open files.");
      let result;
      try {
        result = await call("add_reference", kind.value, { ...fields, key: citeKey, cite: wantCite });
      } catch (err) {
        if (cited) editor.undoLastEdit();
        throw err;
      }
      await handlers.afterChange(result.changed);
      close();
      toast(`Reference added as [${result.key}] in ${result.file}`
        + (result.url_package_added ? " (and \\usepackage{url} in the preamble)" : "")
        + (!wantCite
          ? `, listed without citing it${result.nocite_file ? ` (\\nocite in ${result.nocite_file})` : ""}`
          : cited ? "" : ". Open a .tex file to insert \\cite automatically next time."), "success", 7000);
    } catch (err) {
      showError(err);
      add.disabled = false;
    }
  });

  renderFields();
  dialog.showModal();
  kind.focus();
}
