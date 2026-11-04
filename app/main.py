"""Application entry point: creates the main window and starts pywebview."""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import webview

from .api import Api
from .fsutil import appdata_dir
from .settings import APP_DIR_NAME

# In the packaged .exe (PyInstaller) the web/ folder is unpacked next to the code.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = BASE_DIR / "web"

# Window background shown before the page paints; matches --bg in web/css/app.css.
BACKGROUND = {"light": "#f6f7f9", "dark": "#1e1f22"}


def system_theme():
    """'dark' or 'light' from the Windows app theme setting (light if unknown)."""
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "light"


def window_theme(api) -> str:
    theme = api.get_preferences()["theme"]
    return system_theme() if theme == "system" else theme


def create_window(api):
    window = webview.create_window(
        "LaTeX Editor",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1440,
        height=900,
        min_size=(960, 600),
        background_color=BACKGROUND[window_theme(api)],
    )
    api._attach(window)
    return window


def clear_web_cache(storage: Path) -> None:
    """Drop WebView2's HTTP and compiled-script caches so the UI files are always the
    current ones (pywebview's static server sends Last-Modified, so an updated app could
    otherwise run cached JavaScript). Local storage (pane sizes, filters) is kept."""
    for name in ("Cache", "Code Cache"):
        shutil.rmtree(storage / "EBWebView" / "Default" / name, ignore_errors=True)


def run(debug=False, func=None, args=None, api=None, private=False):
    """Create the window and block until it closes.

    `func(*args)` runs in a background thread once the GUI loop has started
    (used by scripts/ui_check.py and --self-test to drive the window).
    `private` uses a throwaway browser profile (tests), not the user's.
    """
    api = api or Api()
    window = create_window(api)
    if private:
        options = dict(http_server=True, debug=debug, private_mode=True)
    else:
        # Keep the page's localStorage (pane sizes, filters) between sessions.
        storage = appdata_dir() / APP_DIR_NAME / "webview"
        clear_web_cache(storage)
        options = dict(http_server=True, debug=debug, private_mode=False, storage_path=str(storage))
    if func is not None:
        webview.start(func, (window, *(args or ())), **options)
    else:
        webview.start(**options)
    return window


SELF_TEST_PROBE = """
(() => ({
  monaco: typeof window.monaco === "object",
  pdfjs: typeof globalThis.pdfjsLib === "object",
  engine: document.getElementById("engine-line").className,
  engineText: document.getElementById("engine-line").textContent,
  importEnabled: !document.getElementById("btn-import").disabled,
}))()
"""


SPELL_PROBE = """
window.__spellTest = null;
(() => {
  const w = new Worker("js/spell/worker.js");
  w.onmessage = (e) => {
    if (e.data.type === "ready") w.postMessage({ type: "check", id: 1, text: "A pargraph." });
    else { window.__spellTest = e.data.issues ? e.data.issues.map((i) => i.word) : e.data; w.terminate(); }
  };
  w.onerror = (e) => { window.__spellTest = "error: " + e.message; };
  w.postMessage({ type: "init", lang: "en", words: [] });
})();
"""


def _poll(window, script, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = window.evaluate_js(script)
        if value:
            return value
        time.sleep(0.5)
    return None


def self_test(window, api, out_path, zip_path=None):
    """Check the (packaged) app end to end; write a JSON report and quit.

    UI, Monaco, PDF.js and LuaLaTeX detection always; with `zip_path` also an
    import, a real compile, the PDF server and the spell-check worker.
    """
    result = {"loaded": window.events.loaded.wait(60)}
    deadline = time.time() + 60
    while time.time() < deadline:
        probe = window.evaluate_js(SELF_TEST_PROBE) or {}
        result.update(probe)
        if probe.get("monaco") and probe.get("engine") != "engine-line":
            break
        time.sleep(0.5)
    ok = bool(result.get("loaded") and result.get("monaco") and result.get("pdfjs")
              and result.get("engine") == "engine-line ok")

    if zip_path:
        try:
            api.import_zip(zip_path)
            build = api.compile()
            result["build"] = build["status"]
            url = json.dumps(build["pdf_url"])
            # the page must be able to load the PDF from the local PDF server
            result["pdf_http_status"] = window.evaluate_js(
                f"(() => {{ const x = new XMLHttpRequest(); x.open('GET', {url}, false); x.send(); return x.status; }})()")
        except Exception as exc:  # report, don't crash the test
            result["build_error"] = repr(exc)
        window.evaluate_js(SPELL_PROBE)
        result["spell"] = _poll(window, "window.__spellTest", 30)
        ok = ok and result.get("build") == "success" and result.get("pdf_http_status") == 200 \
            and result.get("spell") == ["pargraph"]

    result["ok"] = ok
    Path(out_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    window.destroy()


def main():
    parser = argparse.ArgumentParser(prog="latexeditor")
    parser.add_argument("--debug", action="store_true", help="open the WebView developer tools")
    parser.add_argument("--self-test", metavar="OUT.json", help="start, check the app works, write a report and quit")
    parser.add_argument("--self-test-zip", metavar="PROJECT.zip", help="with --self-test: also import and compile this project")
    args = parser.parse_args()
    if args.self_test:
        import tempfile

        from .settings import Settings

        # Self-tests use a throwaway workspace and settings, never the user's.
        data = Path(tempfile.mkdtemp(prefix="latexeditor-selftest-"))
        settings = Settings(data / "settings.json")
        settings.data["workspace"] = str(data / "workspace")
        api = Api(settings)
        run(func=self_test, args=(api, args.self_test, args.self_test_zip), api=api)
    else:
        run(debug=args.debug)
