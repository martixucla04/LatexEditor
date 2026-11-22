import shutil

import pytest

from app.project import Project
from app.report import _log_excerpt, error_report


def test_no_problems_gives_no_report(make_project):
    root = make_project({"main.tex": "\\documentclass{article}\n"})
    assert error_report(Project(root), [{"severity": "info", "message": "Overfull \\hbox"}]) == ""


def test_log_excerpt_takes_each_error_once():
    log = "\n".join(["(./main.tex", "./main.tex:5: Undefined control sequence.", "l.5 \\foo", "", "x", "y",
                     "z", "w", "v", "u"])
    assert _log_excerpt(log).splitlines()[:3] == ["./main.tex:5: Undefined control sequence.", "l.5 \\foo", ""]
    assert _log_excerpt("no errors here") == ""


@pytest.mark.latex
@pytest.mark.skipif(shutil.which("lualatex") is None, reason="lualatex not installed")
def test_report_of_a_real_build(make_project, settings):
    from app.api import Api
    from app.builder import Builder

    root = make_project({
        "main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{ch}\n\\end{document}\n",
        "ch.tex": "One.\nTwo \\foo{x} three.\nSee \\ref{fig:none}.\nFour.\n",
    })
    result = Builder(root, "main.tex").run()
    api = Api(settings)
    api.open_project(str(root))
    text = api.error_report([p.to_dict() if hasattr(p, "to_dict") else p for p in result.problems])

    assert text.startswith("I'm compiling a LaTeX document with ")
    assert "main file: main.tex" in text
    assert "## Error 1: Undefined control sequence." in text
    assert "Where: ch.tex, line 2" in text
    assert "> 2 | Two \\foo{x} three." in text  # the source line, marked
    assert "  1 | One." in text and "  4 | Four." in text
    assert "## Warnings" in text and "fig:none" in text
    assert "## From the LaTeX log" in text and "ch.tex:2: Undefined control sequence." in text
