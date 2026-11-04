import shutil

import pytest

from app import __version__
from app.api import Api, detect_engine

DOC = r"\documentclass{article}\begin{document}Hi\end{document}"


def test_app_info_reports_versions(settings):
    info = Api(settings).app_info()
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


def test_import_opens_project_and_records_recent(settings, make_zip):
    api = Api(settings)
    info = api.import_zip(str(make_zip({"main.tex": DOC})))
    assert info["name"] == "paper"
    assert info["main_file"] == "main.tex"
    assert [r["name"] for r in api.recent_projects()] == ["paper"]
    assert api.read_file("main.tex")["text"] == DOC

    # reopening moves it to the top without duplicating
    api.open_project(info["root"])
    assert len(api.recent_projects()) == 1
    assert api.remove_recent(info["root"]) == []


def test_closing_guard(settings, monkeypatch):
    import app.api as api_module

    api = Api(settings)
    assert api._on_closing() is True
    api.set_dirty(True)
    monkeypatch.setattr(api_module, "ask_yes_no", lambda *a: False)
    assert api._on_closing() is False
    monkeypatch.setattr(api_module, "ask_yes_no", lambda *a: True)
    assert api._on_closing() is True
