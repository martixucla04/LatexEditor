"""Localhost HTTP server that hands the latest compiled PDF to PDF.js.

Passing a multi-megabyte PDF through the pywebview bridge would mean base64 and
JSON on every compile; a tiny server streams the bytes instead. It only binds
to 127.0.0.1 and only answers URLs carrying a random per-session token. The PDF
is served from an in-memory snapshot, so a build that is rewriting the file
never hands out a half-written PDF.
"""

import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class PdfServer:
    def __init__(self):
        self._token = secrets.token_urlsafe(16)
        self._data: bytes | None = None
        self._version = 0
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True, name="pdf-server").start()

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def publish(self, pdf: Path) -> str:
        """Snapshot `pdf` and return a fresh URL for it."""
        data = Path(pdf).read_bytes()
        with self._lock:
            self._data = data
            self._version += 1
            return f"http://127.0.0.1:{self.port}/{self._token}/{self._version}.pdf"

    def clear(self) -> None:
        with self._lock:
            self._data = None

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                parts = self.path.strip("/").split("/")
                with server._lock:
                    data = server._data
                if len(parts) != 2 or not secrets.compare_digest(parts[0], server._token) or data is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

        return Handler
