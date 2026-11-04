"""Launch the real app window, drive it through JavaScript, then close it.

Uses a temporary settings file and workspace (your real recent-projects list is
not touched). Checks that the page loads inside pywebview, the Python API
answers, the layout has sensible sizes, and that a project imported from a
.zip opens from the Recent list with its file tree and main file in a tab.
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
            zf.writestr("check-paper/sec/intro.tex", "Intro")
        api = Api(settings)
        run(func=check, args=(api, zip_path, results), api=api)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    layout, project = results.get("layout", {}), results.get("project", {})
    checks = {
        "engine detected": layout.get("engineState") == "engine-line ok",
        "layout sizes": layout.get("sidebar", 0) > 0 and layout.get("editor", 0) >= 320 and layout.get("pdf", 0) >= 280,
        "tree shows project": project.get("rows") == ["sec", "main.tex"],
        "main file marked": project.get("main") == "main.tex",
        "main file open in editor": project.get("tabs") == ["main.tex"] and project.get("editorLines", 0) >= 5,
    }
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
