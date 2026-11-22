import shutil

import pytest

from app.project import Project

DOC = "\\documentclass{article}\n\\begin{document}\n\\section{One}\\label{s}\nSee~\\ref{s}.\n\\end{document}\n"


def test_engine_from_choice_magic_comment_or_default(make_project):
    root = make_project({"main.tex": DOC})
    project = Project(root)
    assert project.engine == "lualatex"
    (root / "main.tex").write_text("% !TeX program = XeLaTeX\n" + DOC, encoding="utf-8")
    assert project.engine == "xelatex"
    (root / "main.tex").write_text("% !TEX TS-program = pdflatex\n" + DOC, encoding="utf-8")
    assert project.engine == "pdflatex"
    project.set_engine("lualatex")  # an explicit choice wins over the comment
    assert Project(root).engine == "lualatex"
    assert Project(root).info()["engine"] == "lualatex"
    with pytest.raises(Exception, match="Unknown compiler"):
        project.set_engine("tectonic")


@pytest.mark.latex
@pytest.mark.parametrize("engine", ["pdflatex", "xelatex"])
def test_build_with_another_engine(make_project, engine):
    from app.builder import Builder

    if shutil.which(engine) is None:
        pytest.skip(f"{engine} not installed")
    root = make_project({"main.tex": DOC}, name=engine)
    result = Builder(root, "main.tex", engine=engine).run()
    assert result.status == "success", result.log[-2000:]
    assert [s.tool for s in result.steps] == [engine, engine]  # second run settles \ref
    assert f"This is {'XeTeX' if engine == 'xelatex' else 'pdfTeX'}" in result.log

    # nothing changed: up to date; switching the engine rebuilds
    assert Builder(root, "main.tex", engine=engine).run().steps == []
    assert [s.tool for s in Builder(root, "main.tex", engine="lualatex").run().steps][0] == "lualatex"
