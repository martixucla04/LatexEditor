import zipfile
from pathlib import Path

import pytest

from app.errors import UserError
from app.workspace import export_zip, import_zip

DOC = r"\documentclass{article}\begin{document}Hi\end{document}"


def test_import_flat_zip(make_zip, tmp_path):
    z = make_zip({"main.tex": DOC, "img/fig.png": b"\x89PNG"})
    root = import_zip(z, tmp_path / "ws")
    assert root.name == "paper"
    assert (root / "main.tex").read_text() == DOC
    assert (root / "img" / "fig.png").read_bytes() == b"\x89PNG"


def test_import_unwraps_single_top_folder(make_zip, tmp_path):
    z = make_zip({"thesis/main.tex": DOC, "thesis/ch/one.tex": "x"})
    root = import_zip(z, tmp_path / "ws")
    assert (root / "main.tex").exists()
    assert (root / "ch" / "one.tex").exists()


def test_import_keeps_top_folder_when_files_at_root(make_zip, tmp_path):
    z = make_zip({"main.tex": DOC, "ch/one.tex": "x"})
    root = import_zip(z, tmp_path / "ws")
    assert (root / "ch" / "one.tex").exists()


def test_import_skips_junk(make_zip, tmp_path):
    z = make_zip({"p/main.tex": DOC, "__MACOSX/p/._main.tex": "junk", "p/.DS_Store": "junk", "p/._x": "j"})
    root = import_zip(z, tmp_path / "ws")
    assert sorted(p.name for p in root.rglob("*")) == ["main.tex"]


def test_import_unique_folder_names(make_zip, tmp_path):
    z = make_zip({"main.tex": DOC})
    first = import_zip(z, tmp_path / "ws")
    second = import_zip(z, tmp_path / "ws")
    assert first.name == "paper" and second.name == "paper (2)"


@pytest.mark.parametrize("bad", ["../evil.tex", "/abs.tex", "a/../../evil.tex", "con.tex", "a:b.tex"])
def test_import_rejects_unsafe_paths(make_zip, tmp_path, bad):
    z = make_zip({"main.tex": DOC, bad: "x"})
    with pytest.raises(UserError):
        import_zip(z, tmp_path / "ws")
    assert not (tmp_path / "evil.tex").exists()
    # rejected before anything is written: no project or staging folder left behind
    ws = tmp_path / "ws"
    assert not ws.exists() or list(ws.iterdir()) == []


def test_import_rejects_empty_and_invalid(make_zip, tmp_path):
    with pytest.raises(UserError):
        import_zip(make_zip({"__MACOSX/x": "j"}), tmp_path / "ws")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(UserError):
        import_zip(bad, tmp_path / "ws")


def test_export_excludes_app_files(make_project, tmp_path):
    root = make_project({
        "main.tex": DOC, "fig/a.png": b"png", ".latexeditor.json": "{}", ".build/main.pdf": b"%PDF",
    })
    dest = tmp_path / "out.zip"
    assert export_zip(root, dest) == 2
    with zipfile.ZipFile(dest) as zf:
        assert sorted(zf.namelist()) == ["fig/a.png", "main.tex"]


def test_export_with_pdf(make_project, tmp_path):
    root = make_project({"main.tex": DOC, ".build/main.pdf": b"%PDF"})
    dest = tmp_path / "out.zip"
    export_zip(root, dest, root / ".build" / "main.pdf")
    with zipfile.ZipFile(dest) as zf:
        assert sorted(zf.namelist()) == ["main.pdf", "main.tex"]


def test_export_roundtrip(make_zip, tmp_path):
    files = {"main.tex": DOC, "sec/intro.tex": "Intro àé", "refs.bib": "@book{x,}"}
    root = import_zip(make_zip(files), tmp_path / "ws")
    dest = tmp_path / "again.zip"
    export_zip(root, dest)
    with zipfile.ZipFile(dest) as zf:
        assert {n: zf.read(n).decode() for n in zf.namelist()} == files


def test_check_link_folder_accepts_latex_folder(tmp_path):
    from app.workspace import check_link_folder

    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "intro.tex").write_text("x", encoding="utf-8")
    assert check_link_folder(tmp_path) == tmp_path.resolve()


def test_check_link_folder_rejects_bad_folders(tmp_path, monkeypatch):
    import app.workspace as ws

    with pytest.raises(UserError, match="not found"):
        ws.check_link_folder(tmp_path / "missing")
    with pytest.raises(UserError, match="whole drive"):
        ws.check_link_folder(Path(tmp_path.anchor))
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(UserError, match="No .tex file"):
        ws.check_link_folder(tmp_path)
    (tmp_path / "main.tex").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ws, "MAX_FILES", 1)
    with pytest.raises(UserError, match="more than 1 files"):
        ws.check_link_folder(tmp_path)
