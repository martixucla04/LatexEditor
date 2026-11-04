import zipfile
from pathlib import Path

import pytest

from app.settings import Settings


@pytest.fixture
def settings(tmp_path):
    s = Settings(tmp_path / "settings.json")
    s.data["workspace"] = str(tmp_path / "workspace")
    return s


@pytest.fixture
def make_zip(tmp_path):
    """make_zip({"name/in/zip": "text" | bytes}, name="x.zip") -> Path"""

    def _make(files: dict, name: str = "paper.zip") -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as zf:
            for arcname, content in files.items():
                zf.writestr(arcname, content)
        return path

    return _make


@pytest.fixture
def make_project(tmp_path):
    """make_project({"rel/path": "text" | bytes}) -> Path of a project folder"""

    def _make(files: dict, name: str = "proj") -> Path:
        root = tmp_path / name
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        root.mkdir(exist_ok=True)
        return root

    return _make
