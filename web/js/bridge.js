// Promise-based access to the Python API exposed by pywebview (app/api.py).
// With "?dev" in the URL the page talks to scripts/dev_server.py over HTTP
// instead. When the page is opened in a normal browser there is no backend;
// calls then reject with BackendUnavailable so the UI can still render.

const READY_TIMEOUT_MS = 3000;

export class BackendUnavailable extends Error {
  constructor() {
    super("Backend not connected (page opened outside the app)");
  }
}

// Same calling convention as window.pywebview.api, over fetch.
const httpApi = new Proxy({}, {
  // "then" must stay undefined, or resolving a promise with this proxy treats it as a thenable.
  get: (_, name) => (name === "then" ? undefined : async (...args) => {
    const response = await fetch(`/api/${name}`, { method: "POST", body: JSON.stringify({ args }) });
    const payload = await response.json();
    if (payload.error) {
      const error = new Error(payload.error.message);
      error.name = payload.error.name;
      throw error;
    }
    return payload.value;
  }),
});

let ready = null;

export function backend() {
  ready ??= new Promise((resolve) => {
    if (new URLSearchParams(location.search).has("dev")) {
      resolve(httpApi);
      return;
    }
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
