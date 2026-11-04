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


def test_dropped_files_are_forwarded_to_the_page(settings):
    class FakeWindow:
        scripts = []

        def evaluate_js(self, script):
            self.scripts.append(script)

    api = Api(settings)
    api._window = FakeWindow()
    api._on_drop({"dataTransfer": {"files": [
        {"name": "paper.zip", "pywebviewFullPath": "C:\\Users\\me\\Tesi Martí\\paper.zip"},
        {"name": "x.png"},  # no full path: ignored
    ]}})
    api._on_drop({"dataTransfer": {}})  # nothing dropped: no call
    assert FakeWindow.scripts == [
        'window.onFilesDropped && window.onFilesDropped(["C:\\\\Users\\\\me\\\\Tesi Mart\\u00ed\\\\paper.zip"], [])'
    ]


def test_closing_guard(settings, monkeypatch):
    import app.api as api_module

    api = Api(settings)
    assert api._on_closing() is True
    api.set_dirty(True)
    monkeypatch.setattr(api_module, "ask_yes_no", lambda *a: False)
    assert api._on_closing() is False
    monkeypatch.setattr(api_module, "ask_yes_no", lambda *a: True)
    assert api._on_closing() is True


def test_link_folder_edits_in_place_and_is_marked_linked(settings, tmp_path, make_zip):
    folder = tmp_path / "elsewhere" / "thesis"
    folder.mkdir(parents=True)
    (folder / "main.tex").write_text(DOC, encoding="utf-8")
    api = Api(settings)

    info = api.link_folder(str(folder))
    assert info["root"] == str(folder.resolve())
    assert info["main_file"] == "main.tex"
    api.save_file("main.tex", DOC + "\n% edited")
    assert (folder / "main.tex").read_text(encoding="utf-8").endswith("% edited")  # no copy

    api.import_zip(str(make_zip({"main.tex": DOC})))
    linked = {r["name"]: r["linked"] for r in api.recent_projects()}
    assert linked == {"paper": False, "thesis": True}


def test_link_folder_without_tex_is_refused(settings, tmp_path):
    from app.errors import UserError

    (tmp_path / "photos").mkdir()
    with pytest.raises(UserError, match="No .tex file"):
        Api(settings).link_folder(str(tmp_path / "photos"))
