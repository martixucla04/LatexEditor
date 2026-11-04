"""Launch the real app window, drive it through JavaScript, then close it.

Uses a temporary settings file and workspace (your real recent-projects list is
not touched). Checks that the page loads inside pywebview, the Python API
answers, the layout has sensible sizes, that a project imported from a .zip
opens from the Recent list with its file tree and main file in a tab, and that
Compile runs LuaLaTeX and shows the PDF.
Prints the findings as JSON and exits non-zero if a check fails.

Usage:  .venv\\Scripts\\python scripts/ui_check.py
"""

import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.api  # noqa: E402
from app.api import Api  # noqa: E402

# The probes type into the editor; never stop at the "unsaved changes, quit?" box.
app.api.ask_yes_no = lambda *args: True
from app.main import run  # noqa: E402
from app.settings import Settings  # noqa: E402

TIMEOUT_S = 30

LAYOUT_PROBE = """
(() => {
  const r = (id) => document.getElementById(id).getBoundingClientRect();
  const line = document.getElementById("engine-line");
  return {
    engineState: line.className,
    engineText: line.textContent,
    sidebar: Math.round(r("sidebar").width),
    editor: Math.round(r("editor-column").width),
    pdf: Math.round(r("pdf-pane").width),
    panel: Math.round(r("panel").height),
    recent: [...document.querySelectorAll(".recent-item strong")].map((e) => e.textContent),
  };
})()
"""

PROJECT_PROBE = """
(() => ({
  title: document.title,
  rows: [...document.querySelectorAll(".tree-row")].map((r) => r.dataset.path),
  main: document.querySelector(".main-badge")?.closest(".tree-row")?.dataset.path,
  tabs: [...document.querySelectorAll(".tab")].map((t) => t.title),
  editorLines: document.querySelectorAll("#editor .view-line").length,
}))()
"""

BUILD_PROBE = """
(() => ({
  building: document.getElementById("btn-compile").classList.contains("building"),
  status: document.getElementById("status-message").textContent,
  pages: document.getElementById("page-indicator").textContent,
  renderedPages: document.querySelectorAll("#pdf-pages .page[data-loaded]").length,
  pdfText: document.querySelector("#pdf-pages .textLayer")?.textContent || "",
  problemBadge: document.getElementById("problem-count").textContent,
  problemsEmpty: document.getElementById("problems-empty").textContent,
}))()
"""

# SyncTeX round trip: cursor on main.tex line 3 -> "Find in PDF" highlight -> double-click it -> back to line 3.
SYNCTEX_PROBE = """
window.__syncProbe = null;
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ed = monaco.editor.getEditors()[0];
  ed.setPosition({ lineNumber: 3, column: 2 });
  document.getElementById("btn-sync").click();
  let flash = null;
  for (let i = 0; i < 100 && !(flash = document.querySelector(".synctex-flash")); i++) await sleep(50);
  if (!flash) { window.__syncProbe = { flash: false }; return; }
  await sleep(600); // smooth scroll
  const r = flash.getBoundingClientRect();
  ed.setPosition({ lineNumber: 1, column: 1 });
  const x = r.left + Math.min(20, r.width / 2), y = r.top + r.height / 2;
  document.elementFromPoint(x, y).dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: x, clientY: y }));
  await sleep(1500);
  window.__syncProbe = { flash: true, file: document.querySelector(".tab.active")?.title, line: ed.getPosition().lineNumber };
})();
"""

# Spelling: a typo in prose gets a marker (a typo inside \\cite does not), and Ctrl+. offers fixes.
SPELL_PROBE = """
window.__spellProbe = null;
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ed = monaco.editor.getEditors()[0];
  const model = ed.getModel();
  for (let i = 0; i < 40 && !document.getElementById("status-spell").textContent.includes("English"); i++) await sleep(250);
  model.pushEditOperations([], [{ range: new monaco.Range(3, 1, 3, 1), text: "A pargraph \\\\cite{smth}.\\n" }], () => null);
  await sleep(1500);
  const markers = monaco.editor.getModelMarkers({ owner: "spelling", resource: model.uri }).map((m) => m.message);
  ed.focus();
  ed.setPosition({ lineNumber: 3, column: 5 });
  await sleep(3000); // suggestions are prefetched while the cursor rests on the word
  ed.trigger("keyboard", "editor.action.quickFix", {});
  let rows = [];
  for (let i = 0; i < 40 && !rows.length; i++) {
    await sleep(150);
    rows = [...document.querySelectorAll(".action-widget .monaco-list-row")].map((r) => r.textContent.trim());
  }
  ed.trigger("keyboard", "hideCodeActionWidget", {});
  model.pushEditOperations([], [{ range: new monaco.Range(3, 1, 4, 1), text: "" }], () => null);
  window.__spellProbe = { status: document.getElementById("status-spell").textContent, markers, rows };
})();
"""

# Async: stores its result in window.__editorProbe (evaluate_js does not await promises).
EDITOR_PROBE = """
window.__editorProbe = null;
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ed = monaco.editor.getEditors()[0];
  const model = ed.getModel();
  const tokens = monaco.editor.tokenize("\\\\section{A} $x^2$ % c", "latex")[0].map((t) => t.type);
  // Lines that once crashed the tokenizer (optional groups in the \\cite rule)
  let tokenizerError = null;
  try {
    monaco.editor.tokenize("\\\\cite{a} \\\\parencite[p.~2]{b} \\\\textcite[see][]{c}\\n\\\\begin{align}x&=1\\\\end{align}", "latex");
    monaco.editor.tokenize("@article{k, title={A {B} C}, year=2020}", "bibtex");
  } catch (e) {
    tokenizerError = String(e);
  }
  // Project search: Ctrl+Shift+F, type, wait for results
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "F", code: "KeyF", ctrlKey: true, shiftKey: true, bubbles: true }));
  const search = document.getElementById("search-input");
  search.value = "intro";
  search.dispatchEvent(new Event("input"));
  await sleep(1500);
  const searchSummary = document.getElementById("search-summary").textContent;
  document.querySelector('.sidebar-tab[data-view="files"]').click();
  // type "\\ref{" at the end and read the suggestion list
  ed.focus();
  ed.setPosition({ lineNumber: 3, column: model.getLineMaxColumn(3) });
  for (const ch of " \\\\ref{") { ed.trigger("keyboard", "type", { text: ch }); await sleep(60); }
  await sleep(1200);
  const suggestions = [...document.querySelectorAll(".suggest-widget .monaco-list-row")]
    .map((r) => r.getAttribute("aria-label").split(",")[0]);
  ed.trigger("keyboard", "hideSuggestWidget", {});
  ed.trigger("keyboard", "undo", {});
  // Formatting toolbar: Bold wraps the selected word, a second click unwraps it.
  ed.focus();
  ed.setSelection(new monaco.Selection(3, 1, 3, 6)); // "Hello"
  document.querySelector('.format-btn[data-action="bold"]').click();
  const bold = model.getLineContent(3);
  document.querySelector('.format-btn[data-action="bold"]').click();
  const unbold = model.getLineContent(3);
  // Monaco's right-click menu must get the theme colours (it was unreadable in dark mode).
  const menuBg = getComputedStyle(document.getElementById("editor")).getPropertyValue("--vscode-menu-background").trim();
  // Recent projects menu in the toolbar lists the open project.
  document.getElementById("btn-recent").click();
  await sleep(500);
  const recentMenu = [...document.querySelectorAll(".context-menu .recent-menu-item span")].map((s) => s.textContent);
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  window.__editorProbe = { language: model.getLanguageId(), tokens, tokenizerError, searchSummary, suggestions, bold, unbold, menuBg, recentMenu };
})();
"""

DOC = "\\documentclass{article}\n\\begin{document}\nHello\n\\input{sec/intro}\n\\end{document}\n"


def wait_for(window, script, ready, timeout=TIMEOUT_S):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = window.evaluate_js(script)
        if value and ready(value):
            return value
        time.sleep(0.25)
    return value


def check(window, api, zip_path, results):
    try:
        _check(window, api, zip_path, results)
    except Exception as exc:  # record and still close the window, so the script never hangs
        results["error"] = repr(exc)
    finally:
        window.destroy()


def _check(window, api, zip_path, results):
    window.events.loaded.wait(TIMEOUT_S)
    results["layout"] = wait_for(window, LAYOUT_PROBE, lambda v: v["engineState"] != "engine-line")

    # Import through the API (the native file dialog can't be scripted), then reload
    # so the page lists it under Recent projects and open it from there.
    api.import_zip(str(zip_path))
    window.evaluate_js("location.reload()")
    time.sleep(1)
    results["after_reload"] = wait_for(window, LAYOUT_PROBE, lambda v: v["recent"])
    window.evaluate_js('document.querySelector(".recent-item").click()')
    results["project"] = wait_for(window, PROJECT_PROBE, lambda v: v["tabs"] and v["editorLines"] >= 5)

    window.evaluate_js('document.getElementById("btn-compile").click()')
    time.sleep(0.5)
    results["build"] = wait_for(window, BUILD_PROBE,
                                lambda v: not v["building"] and v["renderedPages"] and v["pdfText"], timeout=120)
    window.evaluate_js(SYNCTEX_PROBE)
    results["synctex"] = wait_for(window, "window.__syncProbe", lambda v: True, timeout=20)
    window.evaluate_js(SPELL_PROBE)
    results["spell"] = wait_for(window, "window.__spellProbe", lambda v: True, timeout=30)
    window.evaluate_js(EDITOR_PROBE)
    results["editor"] = wait_for(window, "window.__editorProbe", lambda v: True, timeout=15)


def main():
    results = {}
    with tempfile.TemporaryDirectory(prefix="latexeditor-uicheck-") as tmp:
        tmp = Path(tmp)
        settings = Settings(tmp / "settings.json")
        settings.data["workspace"] = str(tmp / "workspace")
        zip_path = tmp / "check-paper.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("check-paper/main.tex", DOC)
            zf.writestr("check-paper/sec/intro.tex", "Intro\\label{sec:intro}")
        api = Api(settings)
        run(func=check, args=(api, zip_path, results), api=api, private=True)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    layout, project, build = results.get("layout", {}), results.get("project", {}), results.get("build", {})
    editor = results.get("editor") or {}
    checks = {
        "engine detected": layout.get("engineState") == "engine-line ok",
        "layout sizes": layout.get("sidebar", 0) > 0 and layout.get("editor", 0) >= 320 and layout.get("pdf", 0) >= 280,
        "tree shows project": project.get("rows") == ["sec", "main.tex"],
        "main file marked": project.get("main") == "main.tex",
        "main file open in editor": project.get("tabs") == ["main.tex"] and project.get("editorLines", 0) >= 5,
        "compiles": build.get("status", "").startswith("Compiled in"),
        "PDF shown": build.get("pages") == "1 / 1" and "Hello" in build.get("pdfText", "") and "Intro" in build.get("pdfText", ""),
        "no problems reported": build.get("problemBadge") == "0" and build.get("problemsEmpty") == "No problems in the last build.",
        "LaTeX highlighting": editor.get("language") == "latex"
            and {"keyword.section.latex", "math.latex", "comment.latex"} <= set(editor.get("tokens", []))
            and editor.get("tokenizerError") is None,
        # \input{sec/intro} in main.tex; "Intro" and sec:intro in sec/intro.tex (case-insensitive)
        "project search": editor.get("searchSummary") == "3 results in 2 files",
        "\\ref autocomplete": editor.get("suggestions") == ["sec:intro"],
        "formatting toolbar": editor.get("bold", "").startswith("\\textbf{Hello}") and editor.get("unbold", "").startswith("Hello"),
        "editor menu has theme colours": bool(editor.get("menuBg")),
        "recent projects menu": editor.get("recentMenu") == ["check-paper"],
        "SyncTeX source -> PDF -> source": results.get("synctex") == {"flash": True, "file": "main.tex", "line": 3},
        "spell check marks prose typos only": (results.get("spell") or {}).get("markers")
            == ["“pargraph” is not in the English (US) dictionary"],
        "spelling quick fixes": any("paragraph" in r for r in (results.get("spell") or {}).get("rows", []))
            and any("project dictionary" in r for r in (results.get("spell") or {}).get("rows", [])),
    }
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
