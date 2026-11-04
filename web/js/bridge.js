// Promise-based access to the Python API exposed by pywebview (app/api.py).
// When the page is opened in a normal browser there is no backend; calls then
// reject with BackendUnavailable so the UI can still render.

const READY_TIMEOUT_MS = 3000;

export class BackendUnavailable extends Error {
  constructor() {
    super("Backend not connected (page opened outside the app)");
  }
}

let ready = null;

export function backend() {
  ready ??= new Promise((resolve) => {
    if (window.pywebview?.api) {
      resolve(window.pywebview.api);
      return;
    }
    window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
    setTimeout(() => resolve(null), READY_TIMEOUT_MS);
  });
  return ready;
}

export async function call(name, ...args) {
  const api = await backend();
  if (!api) throw new BackendUnavailable();
  return api[name](...args);
}
