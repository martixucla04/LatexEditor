// Small UI building blocks: toasts, modal dialogs and context menus.

const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// ---------------------------------------------------------------------------
// Toasts
// ---------------------------------------------------------------------------

const toastHost = el("div", { className: "toasts", role: "status" });
document.body.append(toastHost);

export function toast(message, kind = "info", timeout = 4000) {
  const node = el("div", { className: `toast ${kind}`, textContent: message });
  node.addEventListener("click", () => node.remove());
  toastHost.append(node);
  if (timeout) setTimeout(() => node.remove(), timeout);
}

export function showError(err) {
  console.error(err);
  toast(err?.message || String(err), "error", 8000);
}

// ---------------------------------------------------------------------------
// Dialogs (one at a time, built on <dialog>)
// ---------------------------------------------------------------------------

function openDialog({ title, body, okLabel = "OK", danger = false, cancelLabel = "Cancel" }) {
  const dialog = el("dialog", { className: "modal" });
  const ok = el("button", { className: `btn ${danger ? "danger" : "primary"}`, value: "ok", textContent: okLabel });
  const cancel = el("button", { className: "btn", value: "cancel", textContent: cancelLabel, type: "button" });
  const form = el("form", { method: "dialog" }, [
    el("h2", { textContent: title }),
    ...body,
    el("div", { className: "modal-actions" }, [cancel, ok]),
  ]);
  dialog.append(form);
  document.body.append(dialog);
  cancel.addEventListener("click", () => dialog.close("cancel"));

  const done = new Promise((resolve) => {
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "ok");
      dialog.remove();
    });
  });
  dialog.showModal();
  return { dialog, form, ok, done };
}

export async function promptDialog({ title, label, value = "", okLabel = "OK", selectStem = false }) {
  const input = el("input", { type: "text", value, spellcheck: false, required: true });
  const { done } = openDialog({ title, okLabel, body: [el("label", {}, [label, input])] });
  input.focus();
  const dot = value.lastIndexOf(".");
  if (selectStem && dot > 0) input.setSelectionRange(0, dot);
  else input.select();
  return (await done) ? input.value.trim() || null : null;
}

export async function confirmDialog({ title, message, okLabel = "OK", danger = false }) {
  const { ok, done } = openDialog({ title, okLabel, danger, body: [el("p", { textContent: message })] });
  ok.focus();
  return done;
}

// options: [{ value, label, detail? }]; resolves to the chosen value or null.
export async function chooseDialog({ title, message, options, okLabel = "Choose" }) {
  const list = el("div", { className: "choices" });
  options.forEach((opt, i) => {
    const radio = el("input", { type: "radio", name: "choice", value: String(i), checked: i === 0 });
    list.append(el("label", { className: "choice" }, [
      radio,
      el("span", {}, [opt.label, opt.detail ? el("small", { textContent: opt.detail }) : ""]),
    ]));
  });
  const body = message ? [el("p", { textContent: message }), list] : [list];
  const { form, ok, done } = openDialog({ title, okLabel, body });
  ok.focus();
  if (!(await done)) return null;
  const checked = form.querySelector("input[name=choice]:checked");
  return checked ? options[Number(checked.value)].value : null;
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------

let openMenu = null;

export function closeContextMenu() {
  openMenu?.remove();
  openMenu = null;
}

// items: [{ label, action, danger?, disabled?, shortcut? } | "-"]
export function contextMenu(x, y, items) {
  closeContextMenu();
  const menu = el("div", { className: "context-menu", role: "menu" });
  for (const item of items) {
    if (item === "-") {
      menu.append(el("div", { className: "separator" }));
      continue;
    }
    const button = el("button", {
      className: item.danger ? "danger" : "",
      disabled: !!item.disabled,
      role: "menuitem",
    }, [el("span", { textContent: item.label }), el("kbd", { textContent: item.shortcut || "" })]);
    button.addEventListener("click", () => {
      closeContextMenu();
      item.action();
    });
    menu.append(button);
  }
  document.body.append(menu);
  const { innerWidth, innerHeight } = window;
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.min(x, innerWidth - rect.width - 4)}px`;
  menu.style.top = `${Math.min(y, innerHeight - rect.height - 4)}px`;
  menu.querySelector("button:not(:disabled)")?.focus();
  openMenu = menu;
}

window.addEventListener("pointerdown", (e) => {
  if (openMenu && !openMenu.contains(e.target)) closeContextMenu();
}, true);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeContextMenu();
});
window.addEventListener("blur", closeContextMenu);
