"""Phase 0 smoke test: LuaLaTeX + pywebview + vendored JS libraries.

Compiles a tiny document with lualatex, opens web/smoke.html in a pywebview
window, and waits for the page to report whether Monaco, typo.js and PDF.js
loaded and rendered. The window closes itself when the report arrives.

Usage:  .venv\\Scripts\\python scripts/smoke_test.py [--keep-open]
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 60

SAMPLE = r"""\documentclass{article}
\usepackage{fontspec}
\begin{document}
\section{Smoke test}
Hello from Lua\LaTeX{}: àèéíòóú ç l·l.
\[ E = mc^2 \]
\end{document}
"""


def compile_sample(workdir: Path) -> Path:
    tex = workdir / "sample.tex"
    tex.write_text(SAMPLE, encoding="utf-8")
    cmd = ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "-synctex=1", tex.name]
    result = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    pdf = workdir / "sample.pdf"
    if result.returncode != 0 or not pdf.exists():
        print(result.stdout[-2000:])
        raise SystemExit("lualatex failed")
    return pdf


class Api:
    def __init__(self, source: str, pdf: Path, keep_open: bool):
        self._source = source
        self._pdf = pdf
        self._keep_open = keep_open
        self.result = None
        self.done = threading.Event()

    def get_source(self):
        return self._source

    def get_pdf(self):
        return base64.b64encode(self._pdf.read_bytes()).decode()

    def report(self, report):
        self.result = report
        self.done.set()
        if not self._keep_open:
            threading.Timer(1.0, lambda: webview.windows[0].destroy()).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-open", action="store_true", help="leave the window open after the test")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="latexeditor-smoke-") as tmp:
        print("Compiling sample with lualatex ...")
        pdf = compile_sample(Path(tmp))
        print(f"  ok ({pdf.stat().st_size} bytes)")

        api = Api(SAMPLE, pdf, args.keep_open)
        window = webview.create_window("LaTeX Editor - smoke test", str(ROOT / "web" / "smoke.html"),
                                       js_api=api, width=1200, height=800)

        def watchdog():
            if not api.done.wait(TIMEOUT_S):
                print(f"Timed out after {TIMEOUT_S}s waiting for the page report")
                window.destroy()

        print("Opening pywebview window ...")
        webview.start(watchdog, http_server=True)

    if api.result is None:
        sys.exit(1)
    print(json.dumps(api.result, indent=2, ensure_ascii=False))
    sys.exit(0 if all(v["ok"] for v in api.result.values()) else 1)


if __name__ == "__main__":
    main()
