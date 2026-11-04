from datetime import date

import pytest

from app.errors import UserError
from app.project import Project
from app.references import add_web_reference, catalan_date, format_web_reference, suggest_key

DOC = "\\documentclass{article}\n\\begin{document}\nText \\cite{x}.\n\\end{document}\n"


@pytest.mark.parametrize("d, expected", [
    (date(2000, 2, 11), "l’11 de febrer de 2000"),
    (date(2024, 4, 1), "l’1 d’abril de 2024"),
    (date(2024, 8, 2), "el 2 d’agost de 2024"),
    (date(2024, 10, 21), "el 21 d’octubre de 2024"),
    (date(2024, 3, 15), "el 15 de març de 2024"),
])
def test_catalan_date(d, expected):
    assert catalan_date(d) == expected


def test_examples_match_the_house_format():
    assert format_web_reference("SIEMENS", "2000-02-11", "SIEMENS. Productos y soluciones", "En línia",
                                "http://www.siemens.es/html/prodsolu/prodserv.html") == (
        "SIEMENS (Pàgina consultada l’11 de febrer de 2000). SIEMENS. Productos y soluciones, [En línia]. "
        "Adreça URL: \\url{http://www.siemens.es/html/prodsolu/prodserv.html}")
    assert format_web_reference("Equip Mediterrani", "2000-02-11", "Proyecto Despertaferro", "",
                                "http://www.racingservices.net/cochesolar/") == (
        "Equip Mediterrani (Pàgina consultada l’11 de febrer de 2000). Proyecto Despertaferro, [En línia]. "
        "Adreça URL: \\url{http://www.racingservices.net/cochesolar/}")


def test_special_characters_are_escaped_but_not_the_url():
    text = format_web_reference("R&D_Lab", "2024-05-02", "50% of #1", "En línia", "https://x.org/a_b?c=1&d=2#e")
    assert text.startswith("R\\&D\\_Lab (Pàgina consultada el 2 de maig de 2024). 50\\% of \\#1,")
    assert text.endswith("\\url{https://x.org/a_b?c=1&d=2#e}")


def test_required_fields():
    with pytest.raises(UserError):
        format_web_reference("", "2024-01-01", "T", "", "http://x")
    with pytest.raises(UserError):
        format_web_reference("A", "not-a-date", "T", "", "http://x")


def test_suggest_key():
    assert suggest_key("SIEMENS", "2000-02-11") == "siemens2000"
    assert suggest_key("Equip Mediterrani", "2000-02-11") == "equipmediterrani2000"
    assert suggest_key("Generalitat de Catalunya · Àrea", "2024-01-01").startswith("generalitatdecatalunya")


FIELDS = {"author": "SIEMENS", "consulted": "2000-02-11", "title": "SIEMENS. Productos y soluciones",
          "medium": "En línia", "url": "http://www.siemens.es/html/prodsolu/prodserv.html"}


def test_creates_bibliography_and_url_package(make_project):
    root = make_project({"main.tex": DOC})
    result = add_web_reference(Project(root), FIELDS)
    text = (root / "main.tex").read_text(encoding="utf-8")
    assert result["key"] == "siemens2000" and result["url_package_added"]
    assert text.startswith("\\documentclass{article}\n\\usepackage{url}\n")
    assert "\\begin{thebibliography}{99}\n\n\\bibitem{siemens2000} SIEMENS (Pàgina consultada" in text
    assert text.rstrip().endswith("\\end{thebibliography}\n\n\\end{document}")
    assert text.splitlines()[result["line"] - 1].startswith("\\bibitem{siemens2000}")


def test_appends_to_existing_bibliography_with_unique_keys(make_project):
    root = make_project({
        "main.tex": "\\documentclass{article}\n\\usepackage{hyperref}\n\\begin{document}\n\\input{refs}\n\\end{document}\n",
        "refs.tex": "\\begin{thebibliography}{9}\n  \\bibitem{siemens2000} Old.\n\\end{thebibliography}\n",
    })
    result = add_web_reference(Project(root), FIELDS)
    assert (result["key"], result["file"], result["changed"], result["url_package_added"]) == (
        "siemens2000b", "refs.tex", ["refs.tex"], False)
    refs = (root / "refs.tex").read_text(encoding="utf-8")
    assert refs.index("\\bibitem{siemens2000} Old.") < refs.index("  \\bibitem{siemens2000b} SIEMENS")
    assert "\\usepackage{url}" not in (root / "main.tex").read_text(encoding="utf-8")


@pytest.mark.latex
@pytest.mark.skipif(__import__("shutil").which("lualatex") is None, reason="lualatex not installed")
def test_reference_compiles(make_project):
    from app.builder import Builder

    root = make_project({"main.tex": DOC.replace("\\cite{x}", "\\cite{siemens2000}")})
    add_web_reference(Project(root), {**FIELDS, "url": "https://x.org/a_b?c=1&d=2#e%20f"})
    result = Builder(root, "main.tex").run()
    assert result.status == "success", result.log[-2000:]
    aux = (root / ".build" / "main.aux").read_text(encoding="utf-8")
    assert "\\bibcite{siemens2000}{1}" in aux
    assert "Missing character" not in result.log


EXISTING_BIB = """@misc{FSGrules,
  author       = {{Formula Student Germany}},
  title        = {FSG Rules 2026 v1.1},
  year         = {2025},
  howpublished = {\\url{https://www.formulastudent.de/rules.pdf}},
  note         = {Accessed: 12-Feb-2026}
}
@misc{siemens2000,
  note = {older entry with the same key}
}
"""

# Like a thesis template: BibTeX + IEEEtran, hyperref loaded from an \input style file.
BIBTEX_PROJECT = {
    "main.tex": "\\documentclass{report}\n\\input{estilo}\n\\usepackage[catalan]{babel}\n\\begin{document}\n"
                "Text \\cite{FSGrules}.\n\\bibliographystyle{IEEEtran}\n\\bibliography{bibliografia}\n\\end{document}\n",
    "estilo.tex": "\\usepackage{hyperref}\n",
    "bibliografia.bib": EXISTING_BIB,
}


def test_bibtex_document_gets_a_bib_entry(make_project):
    root = make_project(BIBTEX_PROJECT)
    result = add_web_reference(Project(root), FIELDS)
    assert (result["mode"], result["file"], result["key"], result["changed"], result["url_package_added"]) == (
        "bibtex", "bibliografia.bib", "siemens2000b", ["bibliografia.bib"], False)
    bib = (root / "bibliografia.bib").read_text(encoding="utf-8")
    assert bib.startswith(EXISTING_BIB.rstrip("\n") + "\n\n@misc{siemens2000b,\n  note = {SIEMENS (Pàgina consultada")
    assert bib.endswith("\\url{http://www.siemens.es/html/prodsolu/prodserv.html}\\phantom{.}}\n}\n")
    assert bib.splitlines()[result["line"] - 1] == "@misc{siemens2000b,"
    assert "thebibliography" not in (root / "main.tex").read_text(encoding="utf-8")


def test_biblatex_document_gets_a_bib_entry(make_project):
    root = make_project({
        "main.tex": "\\documentclass{article}\n\\usepackage[backend=biber]{biblatex}\n\\addbibresource{refs/web.bib}\n"
                    "\\begin{document}\nText.\n\\printbibliography\n\\end{document}\n",
    })
    result = add_web_reference(Project(root), FIELDS)
    assert (result["mode"], result["file"], result["line"], result["url_package_added"]) == (
        "biblatex", "refs/web.bib", 1, True)  # the .bib is created; \url needs the url package
    assert (root / "refs" / "web.bib").read_text(encoding="utf-8").rstrip().endswith("prodserv.html}\\nopunct}\n}")


def test_printbibliography_without_resource_is_refused(make_project):
    root = make_project({"main.tex": DOC.replace("\\end{document}", "\\printbibliography\n\\end{document}")})
    with pytest.raises(UserError):
        add_web_reference(Project(root), FIELDS)


@pytest.mark.latex
@pytest.mark.skipif(__import__("shutil").which("lualatex") is None, reason="lualatex not installed")
def test_bibtex_ieeetran_prints_the_house_format(make_project):
    from app.builder import Builder

    root = make_project(BIBTEX_PROJECT)
    (root / "main.tex").write_text(BIBTEX_PROJECT["main.tex"].replace("\\cite{FSGrules}", "\\cite{FSGrules,siemens2000b}"),
                                   encoding="utf-8")
    add_web_reference(Project(root), FIELDS)
    result = Builder(root, "main.tex").run()
    assert result.status == "success", result.log[-2000:]
    bbl = " ".join((root / ".build" / "main.bbl").read_text(encoding="utf-8").split())
    # IEEEtran prints the note as-is, without adding a period after the URL
    assert ("\\bibitem{siemens2000b} SIEMENS (Pàgina consultada l’11 de febrer de 2000). SIEMENS. Productos y "
            "soluciones, [En línia]. Adreça URL: \\url{http://www.siemens.es/html/prodsolu/prodserv.html}\\phantom{.}") in bbl
    assert "\\phantom{.}." not in bbl


@pytest.mark.latex
@pytest.mark.skipif(__import__("shutil").which("lualatex") is None, reason="lualatex not installed")
def test_biblatex_reference_compiles(make_project):
    from app.builder import Builder

    root = make_project({
        "main.tex": "\\documentclass{article}\n\\usepackage[catalan]{babel}\n\\usepackage[backend=biber]{biblatex}\n"
                    "\\addbibresource{refs.bib}\n\\begin{document}\nText \\cite{siemens2000}.\n\\printbibliography\n\\end{document}\n",
    })
    add_web_reference(Project(root), FIELDS)
    result = Builder(root, "main.tex").run()
    assert result.status == "success", result.log[-2000:]
    assert "Pàgina consultada l’11 de febrer de 2000" in (root / ".build" / "main.bbl").read_text(encoding="utf-8")
