"""Application entry point: creates the main window and starts pywebview."""

import argparse
from pathlib import Path

import webview

from .api import Api

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

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


def create_window(api):
    window = webview.create_window(
        "LaTeX Editor",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1440,
        height=900,
        min_size=(960, 600),
        background_color=BACKGROUND[system_theme()],
    )
    api._attach(window)
    return window


def run(debug=False, func=None, args=None, api=None):
    """Create the window and block until it closes.

    `func(*args)` runs in a background thread once the GUI loop has started
    (used by scripts/ui_check.py to drive the window, with its own `api`).
    """
    api = api or Api()
    window = create_window(api)
    if func is not None:
        webview.start(func, (window, *(args or ())), http_server=True, debug=debug)
    else:
        webview.start(http_server=True, debug=debug)
    return window


def main():
    parser = argparse.ArgumentParser(prog="latexeditor")
    parser.add_argument("--debug", action="store_true", help="open the WebView developer tools")
    args = parser.parse_args()
    run(debug=args.debug)
