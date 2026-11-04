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

from app.api import Api  # noqa: E402
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

# Async: stores its result in window.__editorProbe (evaluate_js does not await promises).
EDITOR_PROBE = """
window.__editorProbe = null;
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ed = monaco.editor.getEditors()[0];
  const model = ed.getModel();
  const tokens = monaco.editor.tokenize("\\\\section{A} $x^2$ % c", "latex")[0].map((t) => t.type);
  // type "\\ref{" at the end and read the suggestion list
  ed.focus();
  ed.setPosition({ lineNumber: 3, column: model.getLineMaxColumn(3) });
  for (const ch of " \\\\ref{") { ed.trigger("keyboard", "type", { text: ch }); await sleep(60); }
  await sleep(1200);
  const suggestions = [...document.querySelectorAll(".suggest-widget .monaco-list-row")]
    .map((r) => r.getAttribute("aria-label").split(",")[0]);
  ed.trigger("keyboard", "hideSuggestWidget", {});
  ed.trigger("keyboard", "undo", {});
  window.__editorProbe = { language: model.getLanguageId(), tokens, suggestions };
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
    window.events.loaded.wait(TIMEOUT_S)
    results["layout"] = wait_for(window, LAYOUT_PROBE, lambda v: v["engineState"] != "engine-line")

    # Import through the API (the native file dialog can't be scripted), then reload
    # so the page lists it under Recent projects and open it from there.
    api.import_zip(str(zip_path))
    window.evaluate_js("location.reload()")
    time.sleep(1)
    wait_for(window, LAYOUT_PROBE, lambda v: v["recent"])
    window.evaluate_js('document.querySelector(".recent-item").click()')
    results["project"] = wait_for(window, PROJECT_PROBE, lambda v: v["tabs"] and v["editorLines"])

    window.evaluate_js('document.getElementById("btn-compile").click()')
    time.sleep(0.5)
    results["build"] = wait_for(window, BUILD_PROBE,
                                lambda v: not v["building"] and v["renderedPages"] and v["pdfText"], timeout=120)
    window.evaluate_js(EDITOR_PROBE)
    results["editor"] = wait_for(window, "window.__editorProbe", lambda v: True, timeout=15)
    time.sleep(0.5)
    api.set_dirty(False)  # the probe typed into the editor; skip the unsaved-changes prompt
    window.destroy()


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
        run(func=check, args=(api, zip_path, results), api=api)

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
            and {"keyword.section.latex", "math.latex", "comment.latex"} <= set(editor.get("tokens", [])),
        "\\ref autocomplete": editor.get("suggestions") == ["sec:intro"],
    }
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
