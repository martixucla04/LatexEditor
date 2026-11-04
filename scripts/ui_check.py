"""Launch the real app window, inspect the UI through JavaScript, then close it.

Checks that the page loads inside pywebview, the Python API answers, and the
three-pane layout has sensible sizes. Prints the findings as JSON and exits
non-zero if a check fails.

Usage:  .venv\\Scripts\\python scripts/ui_check.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import run  # noqa: E402

TIMEOUT_S = 30

PROBE = """
(() => {
  const r = (id) => document.getElementById(id).getBoundingClientRect();
  const line = document.getElementById("engine-line");
  return {
    engineState: line.className,
    engineText: line.textContent,
    statusEngine: document.getElementById("status-engine").textContent,
    window: [window.innerWidth, window.innerHeight],
    sidebar: Math.round(r("sidebar").width),
    editor: Math.round(r("editor-column").width),
    pdf: Math.round(r("pdf-pane").width),
    panel: Math.round(r("panel").height),
  };
})()
"""

results = {}


def check(window):
    window.events.loaded.wait(TIMEOUT_S)
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        info = window.evaluate_js(PROBE)
        if info and info["engineState"] != "engine-line":  # app_info has answered
            results.update(info)
            break
        time.sleep(0.25)
    window.destroy()


def main():
    run(func=check)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    ok = (
        results.get("engineState") == "engine-line ok"
        and results["sidebar"] > 0 and results["editor"] >= 320 and results["pdf"] >= 280
    )
    print("UI check:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
