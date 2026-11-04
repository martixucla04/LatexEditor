"""Serve the web UI to a normal browser with the real Python API behind it.

Open http://127.0.0.1:8765/index.html?dev and the page talks to app.api.Api
over HTTP (POST /api/<method>) instead of the pywebview bridge. Native file
dialogs are replaced by a queue: POST /dev/dialog {"result": [...]} sets what
the next dialog returns. Settings and the workspace live in a temp folder so
your real recent-projects list is untouched.

Usage:  .venv\\Scripts\\python scripts/dev_server.py [--port 8765] [--data DIR]
"""

import argparse
import json
import sys
import tempfile
import traceback
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api import Api  # noqa: E402
from app.settings import Settings  # noqa: E402


class _Event:
    def __iadd__(self, handler):
        return self


class _Events:
    closing = _Event()
    loaded = _Event()


class DevWindow:
    """Stands in for the pywebview window: dialogs answer from a queue."""

    def __init__(self):
        self.title = "LaTeX Editor"
        self.events = _Events()
        self.dialog_results = []

    def create_file_dialog(self, *args, **kwargs):
        return self.dialog_results.pop(0) if self.dialog_results else None

    def evaluate_js(self, script):
        pass  # no push channel to the browser in dev mode


def make_handler(api, window):
    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, fmt, *args):
            if self.path.startswith(("/api/", "/dev/")):
                sys.stderr.write(f"{self.command} {self.path}\n")

        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/dev/dialog":
                window.dialog_results.append(data.get("result"))
                return self._json(200, {"queued": len(window.dialog_results)})
            if not self.path.startswith("/api/"):
                return self._json(404, {"error": {"name": "NotFound", "message": self.path}})
            name = self.path[len("/api/"):]
            method = getattr(api, name, None)
            if name.startswith("_") or not callable(method):
                return self._json(404, {"error": {"name": "NotFound", "message": name}})
            try:
                return self._json(200, {"value": method(*data.get("args", []))})
            except Exception as exc:  # mirror pywebview: reject the JS promise
                traceback.print_exc()
                return self._json(200, {"error": {"name": type(exc).__name__, "message": str(exc)}})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", help="folder for settings + workspace (default: a new temp folder)")
    args = parser.parse_args()

    data = Path(args.data or tempfile.mkdtemp(prefix="latexeditor-dev-"))
    settings = Settings(data / "settings.json")
    settings.data["workspace"] = str(data / "workspace")
    api = Api(settings)
    window = DevWindow()
    api._attach(window)

    handler = partial(make_handler(api, window), directory=str(ROOT / "web"))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Dev server on http://127.0.0.1:{args.port}/index.html?dev  (data: {data})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
