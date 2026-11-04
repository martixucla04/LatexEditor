"""App settings and the recent-projects list (%APPDATA%\\LatexEditor\\settings.json)."""

import json
import time
from pathlib import Path

from .fsutil import appdata_dir, atomic_write_bytes, documents_dir

APP_DIR_NAME = "LatexEditor"
MAX_RECENT = 10

THEMES = ("system", "light", "dark")
FONT_SIZES = range(10, 25)
DEFAULT_PREFERENCES = {"theme": "system", "font_size": 14, "word_wrap": True, "reopen_last": True}


def default_settings_path() -> Path:
    return appdata_dir() / APP_DIR_NAME / "settings.json"


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or default_settings_path()
        self.data = {"workspace": str(documents_dir() / APP_DIR_NAME), "recent": [], **DEFAULT_PREFERENCES}
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # first run or unreadable file: keep defaults

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.path, json.dumps(self.data, indent=2).encode("utf-8"))

    @property
    def workspace(self) -> Path:
        path = Path(self.data["workspace"])
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- preferences (Settings dialog) -------------------------------------------

    def preferences(self) -> dict:
        return {
            "theme": self.data["theme"] if self.data.get("theme") in THEMES else "system",
            "font_size": self.data["font_size"] if self.data.get("font_size") in FONT_SIZES else 14,
            "word_wrap": bool(self.data.get("word_wrap", True)),
            "reopen_last": bool(self.data.get("reopen_last", True)),
            "workspace": self.data["workspace"],
        }

    def update_preferences(self, changes: dict) -> dict:
        """Apply known, valid keys from `changes`; returns the resulting preferences."""
        if changes.get("theme") in THEMES:
            self.data["theme"] = changes["theme"]
        if changes.get("font_size") in FONT_SIZES:
            self.data["font_size"] = int(changes["font_size"])
        for flag in ("word_wrap", "reopen_last"):
            if isinstance(changes.get(flag), bool):
                self.data[flag] = changes[flag]
        if changes.get("workspace"):
            path = Path(changes["workspace"])
            path.mkdir(parents=True, exist_ok=True)  # raises if the location is not writable
            self.data["workspace"] = str(path)
        self.save()
        return self.preferences()

    def recent(self) -> list[dict]:
        return [dict(item, exists=Path(item["path"]).is_dir()) for item in self.data["recent"]]

    def add_recent(self, root: Path, name: str) -> None:
        key = str(root)
        items = [i for i in self.data["recent"] if i["path"].lower() != key.lower()]
        items.insert(0, {"path": key, "name": name, "opened": time.time()})
        self.data["recent"] = items[:MAX_RECENT]
        self.save()

    def remove_recent(self, path: str) -> None:
        self.data["recent"] = [i for i in self.data["recent"] if i["path"].lower() != path.lower()]
        self.save()
