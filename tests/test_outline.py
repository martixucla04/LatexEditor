import shutil

import pytest

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


def test_count_words_skips_latex():
    from app.outline import count_words

    assert count_words("Hola món, l'art de la col·lecció té 3,65 V i 50\\% \\textbf{negreta}.") == 12
    assert count_words("$x^2 + y$ i \\[ a = b \\] \\begin{equation} E = mc^2 \\end{equation} fi") == 2
    assert count_words("Vegeu~\\ref{fig:a} i \\cite[p.~3]{smith} \\label{x}\\includegraphics[width=2cm]{a/b.png}") == 2
    assert count_words("\\begin{tabular}{lll} a & b \\\\ c & d \\end{tabular}") == 4
    assert count_words("\\footnote{Una nota} \\href{http://x.org/a}{web} \\url{http://y.org}") == 3


def test_word_counts_per_heading_follow_inputs(make_project):
    root = make_project({
        "main.tex": "\\documentclass{report}\n\\input{estil}\n\\begin{document}\nAbstract text here.\n"
                    "\\chapter{Intro}\nOne two three.\n\\input{ch/s}\n\\chapter{End}\nFour five.\n"
                    "\\end{document}\nIgnored after the end.\n",
        "estil.tex": "\\newcommand{\\x}{preamble words do not count}\n",
        "ch/s.tex": "\\section{Sub part}\nSix seven eight nine.\n",
    })
    totals = {}
    items = outline(Project(root), totals=totals)
    words = {i["title"]: i["words"] for i in items}
    assert words == {"Intro": 1 + 3 + (2 + 4), "Sub part": 2 + 4, "End": 1 + 2}
    assert totals["words"] == 3 + 10 + 3  # the abstract before the first chapter counts in the total


def test_clean_title():
    assert clean_title("A~\\emph{b}\\label{sec:x} $x^2$") == "A b x^2"
    assert clean_title("  ") == "(untitled)"


@pytest.mark.latex
@pytest.mark.skipif(shutil.which("lualatex") is None, reason="lualatex not installed")
def test_headings_get_their_pdf_page_and_position(make_project, settings):
    from app.api import Api
    from app.builder import Builder

    # running heads repeat section titles at the top of later pages; \\chapter starts a page
    root = make_project({
        "main.tex": "\\documentclass{report}\n\\pagestyle{headings}\n\\begin{document}\n"
                    "\\chapter{One}\nText.\n\\section{Alpha}\n\\input{more}\n\\chapter{Two}\nEnd.\n\\end{document}\n",
        "more.tex": "\\clearpage\nPage two.\n\\section{Beta}\nText.\n\\clearpage\nPage three.\n",
    })
    assert Builder(root, "main.tex").run().status == "success"
    api = Api(settings)
    api.open_project(str(root))
    at = {i["title"]: (i["pdf"]["page"], i["pdf"]["y"]) for i in api.outline()["items"]}
    assert [p for p, _ in at.values()] == [1, 1, 2, 4]  # Two: on its own page, not the one before
    assert at["One"][1] < at["Alpha"][1]
    assert all(y > 50 for _, y in at.values())  # never the running head
