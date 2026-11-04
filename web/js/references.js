// "Add web reference" dialog: author, consultation date, page title, medium and
// URL in the house format
//   Autor (Pàgina consultada <data>). Títol, [En línia]. Adreça URL: <url>
// On Add: \cite{key} goes at the cursor, open files are saved, and Python adds the
// \bibitem to the document's thebibliography (app/references.py).

import { call } from "./bridge.js";
import * as editor from "./editor.js";
import { showError, toast } from "./ui.js";

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

const today = () => new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD in local time

export function openReferenceDialog() {
  const field = (label, input, hint = "") =>
    el("label", { className: "ref-field" }, [el("span", {}, [label, hint ? el("small", { textContent: hint }) : ""]), input]);
  const author = el("input", { type: "text", required: true, placeholder: "SIEMENS" });
  const consulted = el("input", { type: "date", required: true, value: today() });
  const title = el("input", { type: "text", required: true, placeholder: "SIEMENS. Productos y soluciones" });
  const medium = el("input", { type: "text", required: true, value: "En línia" });
  const url = el("input", { type: "url", required: true, placeholder: "https://…", spellcheck: false });
  const key = el("input", { type: "text", spellcheck: false, placeholder: "automatic" });
  const preview = el("p", { className: "ref-preview" });
  const keyNote = el("small", { className: "ref-key-note" });
  let keyEdited = false;
  key.addEventListener("input", () => { keyEdited = true; });

  const fields = () => ({
    author: author.value, consulted: consulted.value, title: title.value, medium: medium.value,
    url: url.value, key: keyEdited ? key.value.trim() : "",
  });

  let timer = null;
  const updatePreview = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!author.value.trim() || !title.value.trim() || !url.value.trim()) {
        preview.textContent = "Fill in the author, title and URL to see the reference.";
        preview.classList.add("empty");
        return;
      }
      try {
        const result = await call("preview_web_reference", fields());
        preview.textContent = readable(result.text);
        preview.classList.remove("empty");
        if (!keyEdited) key.value = result.key;
        keyNote.textContent = `Cited as \\cite{${keyEdited ? key.value.trim() : result.key}}`;
      } catch (err) {
        preview.textContent = err.message;
        preview.classList.add("empty");
      }
    }, 200);
  };
  for (const input of [author, consulted, title, medium, url, key]) input.addEventListener("input", updatePreview);

  const cancel = el("button", { type: "button", className: "btn", textContent: "Cancel" });
  const add = el("button", { className: "btn primary", textContent: "Add reference" });
  const form = el("form", {}, [
    el("h2", { textContent: "Add web reference" }),
    field("Author", author, "Organisation, or the person for a personal page"),
    field("Date consulted", consulted),
    field("Page title", title),
    field("Medium", medium),
    field("URL", url),
    field("Citation key", key),
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
      const { key: citeKey } = await call("preview_web_reference", fields());
      // \cite first (so it is saved with the rest), then the \bibitem on disk.
      const cited = editor.insertCitation(citeKey);
      if (!(await handlers.saveAll())) throw new Error("Could not save the open files.");
      let result;
      try {
        result = await call("add_web_reference", { ...fields(), key: citeKey });
      } catch (err) {
        if (cited) editor.undoLastEdit();
        throw err;
      }
      await handlers.afterChange(result.changed);
      close();
      toast(`Reference added as [${result.key}] in ${result.file}`
        + (result.url_package_added ? " (and \\usepackage{url} in the preamble)" : "")
        + (cited ? "" : ". Open a .tex file to insert \\cite automatically next time."), "success", 7000);
    } catch (err) {
      showError(err);
      add.disabled = false;
    }
  });

  dialog.showModal();
  updatePreview();
  author.focus();
}
