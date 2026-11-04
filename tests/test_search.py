import pytest

from app.errors import UserError
from app.project import Project
from app.search import replace, search

MAIN = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\\sectionmark{x}\nThe Panel and the panel.\n\\input{ch/one}\n\\end{document}\n"
ONE = "A panel here (panels too).\r\nTermodinàmica panel.\r\n"


@pytest.fixture
def project(make_project):
    return Project(make_project({
        "main.tex": MAIN, "ch/one.tex": ONE.encode("utf-8"), "refs.bib": "@book{panel1, title={Panel}}\n",
        "notes.txt": "panel", "fig.png": b"\x89PNG\x00panel",
    }))


def matches(result):
    return [(f["file"], m["line"], m["column"]) for f in result["files"] for m in f["matches"]]


def test_literal_case_insensitive_by_default(project):
    result = search(project, "panel")
    assert result["total"] == 7
    assert {f["file"] for f in result["files"]} == {"main.tex", "ch/one.tex", "refs.bib"}  # .txt/.png excluded


def test_case_and_whole_word(project):
    assert matches(search(project, "panel", case=True, word=True, include="*.tex")) == [
        ("ch/one.tex", 1, 3), ("ch/one.tex", 2, 15), ("main.tex", 4, 19)]


def test_backslash_commands_whole_word(project):
    # "\section" as a whole word must not match "\sectionmark"
    assert matches(search(project, "\\section", word=True)) == [("main.tex", 3, 1)]
    assert len(search(project, "\\section")["files"][0]["matches"]) == 2


def test_regex_and_preview(project):
    result = search(project, r"\\(begin|end)\{document\}", regex=True)
    assert [m["line"] for m in result["files"][0]["matches"]] == [2, 6]
    m = search(project, "Termodinàmica")["files"][0]["matches"][0]
    assert m["preview"].startswith("Termodinàmica") and (m["offset"], m["length"]) == (0, 13)


def test_invalid_regex(project):
    with pytest.raises(UserError):
        search(project, "(unclosed", regex=True)


def test_replace_literal_keeps_line_endings(project):
    result = replace(project, "panel", "plate", case=True, word=True)
    # refs.bib only has "panel1" and "Panel": not whole-word, case-sensitive matches
    assert result == {"files": ["ch/one.tex", "main.tex"], "count": 3}
    assert (project.root / "ch" / "one.tex").read_bytes() == "A plate here (panels too).\r\nTermodinàmica plate.\r\n".encode()
    assert "The Panel and the plate." in (project.root / "main.tex").read_text()


def test_replace_regex_groups_and_file_filter(project):
    result = replace(project, r"\\(section)\{(\w+)\}", r"\\$1*{$2}", regex=True, files=["main.tex"])
    assert result == {"files": ["main.tex"], "count": 1}
    assert "\\section*{Intro}\\sectionmark{x}" in (project.root / "main.tex").read_text()


def test_replace_text_with_backslashes_literally(project):
    replace(project, "\\input{ch/one}", "\\include{ch/one}")
    assert "\\include{ch/one}" in (project.root / "main.tex").read_text()


def test_replace_keeps_cp1252_encoding(make_project):
    root = make_project({"main.tex": "\\documentclass{article}\n", "old.tex": "Mecànica".encode("cp1252")})
    replace(Project(root), "Mecànica", "Termodinàmica")
    assert (root / "old.tex").read_bytes() == "Termodinàmica".encode("cp1252")
