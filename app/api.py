"""Python functions exposed to the web UI as window.pywebview.api.*

pywebview exposes every public method and walks public attributes, so internal
state is kept in underscore-prefixed attributes.
"""

import platform
import shutil
import subprocess
from importlib.metadata import version

from . import __version__


def detect_engine():
    """Return the LuaLaTeX path and version banner, or None if it is not installed."""
    path = shutil.which("lualatex")
    if path is None:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    banner = out.splitlines()[0].strip() if out else "version unknown"
    return {"path": path, "version": banner.removeprefix("This is ").strip()}


class Api:
    def __init__(self):
        self._window = None
        self._engine = None

    def attach(self, window):
        """Called by main.py once the window exists (not exposed: underscore state only)."""
        self._window = window

    def app_info(self):
        if self._engine is None:
            self._engine = detect_engine() or False
        return {
            "version": __version__,
            "python": platform.python_version(),
            "pywebview": version("pywebview"),
            "engine": self._engine or None,
        }
