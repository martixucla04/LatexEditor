// Promise-based access to the Python API exposed by pywebview (app/api.py).
// With "?dev" in the URL the page talks to scripts/dev_server.py over HTTP
// instead. When the page is opened in a normal browser there is no backend;
// calls then reject with BackendUnavailable so the UI can still render.

const READY_TIMEOUT_MS = 3000; // ordinary browser only
const FUNCTION_TIMEOUT_MS = 15000;

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

const isDev = new URLSearchParams(location.search).has("dev");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ready = null;

// Resolves once a backend exists (null when the page runs in an ordinary browser).
export function backend() {
  ready ??= new Promise((resolve) => {
    if (isDev) {
      resolve(httpApi);
      return;
    }
    if (window.pywebview?.api) {
      resolve(window.pywebview.api);
      return;
    }
    window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
    // Inside the app (WebView2) the bridge always arrives, just later on a slow first
    // start; only a page opened in an ordinary browser gives up waiting.
    if (!window.chrome?.webview) setTimeout(() => resolve(null), READY_TIMEOUT_MS);
  });
  return ready;
}

export async function call(name, ...args) {
  if (!(await backend())) throw new BackendUnavailable();
  if (isDev) return httpApi[name](...args);
  // pywebview fills window.pywebview.api in after creating it (and recreates it on a
  // reload), so always use the live object and wait briefly for the function to appear.
  const deadline = Date.now() + FUNCTION_TIMEOUT_MS;
  while (typeof window.pywebview?.api?.[name] !== "function") {
    if (Date.now() > deadline) throw new Error(`The app backend did not provide "${name}"`);
    await sleep(50);
  }
  return window.pywebview.api[name](...args);
}
