import shutil

import pytest

from app import __version__
from app.api import Api, detect_engine


def test_app_info_reports_versions():
    info = Api().app_info()
    assert info["version"] == __version__
    assert info["pywebview"]


@pytest.mark.skipif(shutil.which("lualatex") is None, reason="lualatex not installed")
def test_detect_engine_finds_lualatex():
    engine = detect_engine()
    assert engine["path"].lower().endswith(("lualatex", "lualatex.exe"))
    assert "Version" in engine["version"]


def test_detect_engine_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert detect_engine() is None
