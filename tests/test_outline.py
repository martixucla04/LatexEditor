from app.outline import clean_title, outline
from app.project import Project

MAIN = (
    "\\documentclass{report}\n"
    "\\begin{document}\n"
    "\\chapter*{\\TituloResumen}\n"
    "% \\chapter{Commented out}\n"
    "\\chapter{Introducció}\n"
    "  \\input{chapters/intro}\n"
    "\\chapter[Short]{Estat de l'art \\textbf{actual}}\n"
    "\\include{chapters/missing}\n"
    "\\end{document}\n"
)
INTRO = "\\section{Formula Student}\ntext \\% not a comment\n\\subsection{Resum}\n\\input{chapters/intro}\n"


def test_outline_follows_input_in_reading_order(make_project):
    root = make_project({"main.tex": MAIN, "chapters/intro.tex": INTRO})
    items = [(i["level"], i["title"], i["file"], i["line"]) for i in outline(Project(root))]
    assert items == [
        (1, "\\TituloResumen", "main.tex", 3),  # a title that is only a macro shows its name
        (1, "Introducció", "main.tex", 5),
        (2, "Formula Student", "chapters/intro.tex", 1),
        (3, "Resum", "chapters/intro.tex", 3),  # the file \input-ing itself is read once
        (1, "Estat de l'art actual", "main.tex", 7),
    ]


def test_outline_uses_unsaved_text(make_project):
    root = make_project({"main.tex": MAIN, "chapters/intro.tex": INTRO})
    items = outline(Project(root), {"chapters/intro.tex": "\n\\section{New section}\n"})
    assert [(i["title"], i["line"]) for i in items if i["file"] == "chapters/intro.tex"] == [("New section", 2)]


def test_clean_title():
    assert clean_title("A~\\emph{b}\\label{sec:x} $x^2$") == "A b x^2"
    assert clean_title("  ") == "(untitled)"
