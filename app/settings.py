"""App settings and the recent-projects list (%APPDATA%\\LatexEditor\\settings.json)."""

import json
import time
from pathlib import Path

from .fsutil import appdata_dir, atomic_write_bytes, documents_dir

APP_DIR_NAME = "LatexEditor"
MAX_RECENT = 10


def default_settings_path() -> Path:
    return appdata_dir() / APP_DIR_NAME / "settings.json"


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or default_settings_path()
        self.data = {"workspace": str(documents_dir() / APP_DIR_NAME), "recent": []}
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
