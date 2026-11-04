// App preferences: theme, editor font size, word wrap and the workspace folder
// (stored by Python in %APPDATA%\LatexEditor\settings.json). Opened from the
// gear button; changes apply as soon as they are saved.

import { call } from "./bridge.js";
import * as editor from "./editor.js";
import { showError, toast } from "./ui.js";

let prefs = { theme: "system", font_size: 14, word_wrap: true, workspace: "" };
let onWorkspaceChange = () => {};

export function applyPreferences(p) {
  prefs = { ...prefs, ...p };
  const root = document.documentElement;
  if (prefs.theme === "system") delete root.dataset.theme;
  else root.dataset.theme = prefs.theme;
  editor.setEditorOptions({ fontSize: prefs.font_size, wordWrap: prefs.word_wrap });
  editor.refreshTheme();
  onWorkspaceChange(prefs.workspace);
}

export async function loadPreferences(handlers = {}) {
  onWorkspaceChange = handlers.onWorkspaceChange || onWorkspaceChange;
  applyPreferences(await call("get_preferences"));
}

const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

function row(label, control, hint = "") {
  return el("label", { className: "setting-row" }, [
    el("span", { className: "setting-label" }, [label, hint ? el("small", { textContent: hint }) : ""]),
    control,
  ]);
}

export function openSettings() {
  const theme = el("select", {}, [
    el("option", { value: "system", textContent: "Same as Windows" }),
    el("option", { value: "light", textContent: "Light" }),
    el("option", { value: "dark", textContent: "Dark" }),
  ]);
  theme.value = prefs.theme;
  const fontSize = el("select");
  for (let size = 10; size <= 24; size++) fontSize.append(el("option", { value: String(size), textContent: `${size} px` }));
  fontSize.value = String(prefs.font_size);
  const wrap = el("input", { type: "checkbox", checked: prefs.word_wrap });
  const workspace = el("code", { className: "setting-path", textContent: prefs.workspace });
  const change = el("button", { type: "button", className: "btn", textContent: "Change…" });

  // Preview theme and font while the dialog is open; Cancel restores.
  const original = { ...prefs };
  const preview = () => applyPreferences({ theme: theme.value, font_size: Number(fontSize.value), word_wrap: wrap.checked });
  theme.addEventListener("change", preview);
  fontSize.addEventListener("change", preview);
  wrap.addEventListener("change", preview);

  change.addEventListener("click", async () => {
    try {
      const result = await call("choose_workspace_dialog");
      if (result) {
        workspace.textContent = result.workspace;
        original.workspace = result.workspace;
        applyPreferences({ workspace: result.workspace });
      }
    } catch (err) {
      showError(err);
    }
  });

  const cancel = el("button", { type: "button", className: "btn", textContent: "Cancel" });
  const save = el("button", { className: "btn primary", textContent: "Save" });
  const form = el("form", {}, [
    el("h2", { textContent: "Settings" }),
    row("Theme", theme),
    row("Editor font size", fontSize),
    row("Wrap long lines", wrap),
    el("div", { className: "setting-row setting-workspace" }, [
      el("span", { className: "setting-label" }, ["Projects folder", el("small", { textContent: "Where imported .zip projects are unpacked" })]),
      el("div", { className: "setting-path-row" }, [workspace, change]),
    ]),
    el("div", { className: "modal-actions" }, [cancel, save]),
  ]);
  const dialog = el("dialog", { className: "modal settings" }, [form]);
  document.body.append(dialog);

  const close = () => {
    if (dialog.open) dialog.close();
    dialog.remove();
  };
  cancel.addEventListener("click", () => {
    applyPreferences(original);
    close();
  });
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    applyPreferences(original);
    close();
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      applyPreferences(await call("set_preferences", {
        theme: theme.value, font_size: Number(fontSize.value), word_wrap: wrap.checked,
      }));
      toast("Settings saved", "success", 2000);
      close();
    } catch (err) {
      showError(err);
    }
  });
  dialog.showModal();
  theme.focus();
}
