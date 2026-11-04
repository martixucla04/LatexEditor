import json

import pytest

from app.errors import UserError
from app.project import Project

DOC = "\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n"


def test_detects_single_documentclass(make_project):
    root = make_project({"paper.tex": DOC, "sec/intro.tex": "Intro"})
    p = Project(root)
    assert p.main_file == "paper.tex"
    # choice is persisted in the project config
    assert json.loads((root / ".latexeditor.json").read_text())["main_file"] == "paper.tex"


def test_prefers_root_main_tex(make_project):
    p = Project(make_project({"main.tex": DOC, "other/standalone.tex": DOC}))
    assert p.main_file == "main.tex"


def test_magic_root_comment(make_project):
    root = make_project({"thesis.tex": DOC, "draft.tex": DOC, "ch/one.tex": "% !TEX root = ../thesis.tex\nText"})
    assert Project(root).main_file == "thesis.tex"


def test_ambiguous_main_lists_candidates(make_project):
    p = Project(make_project({"a.tex": DOC, "b.tex": DOC, "sub/c.tex": DOC}))
    assert p.main_file is None
    info = p.info()
    assert info["main_file"] is None
    assert info["main_candidates"] == ["a.tex", "b.tex", "sub/c.tex"]
    p.set_main_file("b.tex")
    assert p.info()["main_file"] == "b.tex"


def test_commented_documentclass_is_ignored(make_project):
    p = Project(make_project({"main2.tex": "% \\documentclass{x}\n", "real.tex": DOC}))
    assert p.main_file == "real.tex"


def test_tree_hides_app_files_and_sorts(make_project):
    root = make_project({"main.tex": DOC, "B.tex": "", "a/x.tex": "", ".build/main.pdf": b"", "Z/y.tex": ""})
    tree = Project(root).tree()
    assert [n["name"] for n in tree] == ["a", "Z", "B.tex", "main.tex"]
    assert tree[0]["children"] == [{"name": "x.tex", "path": "a/x.tex", "type": "file"}]


def test_read_text_encodings(make_project):
    root = make_project({
        "main.tex": DOC,
        "utf8.tex": "Català àéí",
        "bom.tex": b"\xef\xbb\xbfBOM text",
        "latin.tex": "Catal\xe0".encode("cp1252"),
    })
    p = Project(root)
    assert p.read_file("utf8.tex") | {"size": 0} == {"kind": "text", "text": "Català àéí", "encoding": "utf-8", "size": 0}
    assert p.read_file("bom.tex")["encoding"] == "utf-8-sig"
    latin = p.read_file("latin.tex")
    assert (latin["text"], latin["encoding"]) == ("Català", "cp1252")
    # saving keeps the original encoding
    p.write_file("latin.tex", "Català 2", latin["encoding"])
    assert (root / "latin.tex").read_bytes() == "Català 2".encode("cp1252")
    # characters cp1252 cannot encode fall back to UTF-8
    assert p.write_file("latin.tex", "Ω", "cp1252") == "utf-8"


def test_read_image_and_binary(make_project):
    p = Project(make_project({"main.tex": DOC, "f.png": b"\x89PNG", "data.bin": b"\x00\x01"}))
    assert p.read_file("f.png")["url"].startswith("data:image/png;base64,")
    assert p.read_file("data.bin")["kind"] == "binary"


@pytest.mark.parametrize("bad", ["../outside.tex", "a/../../x", ".build/main.pdf", ".latexeditor.json"])
def test_paths_outside_project_are_refused(make_project, bad):
    p = Project(make_project({"main.tex": DOC}))
    with pytest.raises(UserError):
        p.read_file(bad)


def test_create_rename_delete(make_project, monkeypatch):
    # don't fill the real Recycle Bin from tests
    monkeypatch.setattr("app.project.move_to_trash", lambda path: path.unlink())
    root = make_project({"main.tex": DOC})
    p = Project(root)
    assert p.create_folder("", "chapters") == "chapters"
    assert p.create_file("chapters", "one.tex") == "chapters/one.tex"
    with pytest.raises(UserError):
        p.create_file("chapters", "one.tex")
    with pytest.raises(UserError):
        p.create_file("", "bad:name.tex")
    assert p.rename("chapters", "parts") == "parts"
    assert (root / "parts" / "one.tex").exists()
    p.delete("parts/one.tex")
    assert not (root / "parts" / "one.tex").exists()


def test_rename_main_file_updates_config(make_project):
    p = Project(make_project({"main.tex": DOC}))
    p.rename("main.tex", "thesis.tex")
    assert p.main_file == "thesis.tex"


@pytest.mark.parametrize("preamble, expected", [
    ("", "en"),
    ("\\usepackage[catalan]{babel}\n", "ca"),
    ("\\usepackage[english,spanish]{babel}\n", "es"),  # babel: the last language is the main one
    ("\\usepackage[spanish,main=catalan]{babel}\n", "ca"),
    ("\\usepackage{polyglossia}\n\\setdefaultlanguage{catalan}\n\\setotherlanguage{english}\n", "ca"),
    ("% \\usepackage[catalan]{babel}\n", "en"),
    ("\\usepackage[british]{babel}\n", "en-GB"),
    ("\\setdefaultlanguage[variant=british]{english}\n", "en-GB"),
])
def test_spell_language_detection(make_project, preamble, expected):
    p = Project(make_project({"main.tex": "\\documentclass{article}\n" + preamble + "\\begin{document}\n\\end{document}\n"}))
    assert p.spell_settings() == {"language": expected, "words": []}


def test_spell_settings_persist(make_project):
    root = make_project({"main.tex": DOC})
    p = Project(root)
    p.set_spell_language("ca")
    p.add_spell_word("Kirchhoff")
    p.add_spell_word("FEniCS")
    assert Project(root).spell_settings() == {"language": "ca", "words": ["FEniCS", "Kirchhoff"]}
    with pytest.raises(UserError):
        p.set_spell_language("fr")
    with pytest.raises(UserError):
        p.add_spell_word("two words")


def test_add_files_avoids_overwrite(make_project, tmp_path):
    src = tmp_path / "fig.png"
    src.write_bytes(b"png")
    p = Project(make_project({"main.tex": DOC, "fig.png": b"old"}))
    assert p.add_files("", [str(src)]) == ["fig (2).png"]
