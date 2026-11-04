from app.completions import parse_bib, scan_project

BIB = r"""@string{jm = "Journal of Materials"}
@article{smith2020,
  author  = {Smith, Jane and Garc{\'i}a, Pau},
  title   = {Heat transfer in {layered} composites},
  journal = jm,
  year    = 2020,
}
@comment{ignored}
@book{doe2019, author="Doe, John", title="Composite Mechanics", publisher={Springer}, date={2019-05-01}}
@InProceedings{ lee:conf , title={Panels}, booktitle={Proc. Conf.}, year={2021}}
"""


def test_parse_bib():
    entries = parse_bib(BIB, "refs.bib")
    assert [e["key"] for e in entries] == ["smith2020", "doe2019", "lee:conf"]
    smith = entries[0]
    assert smith["title"] == "Heat transfer in layered composites"
    assert smith["author"] == "Smith, Jane and García, Pau"
    assert smith["year"] == "2020" and smith["line"] == 2
    assert entries[1]["year"] == "2019" and entries[1]["title"] == "Composite Mechanics"
    assert entries[2]["type"] == "inproceedings" and entries[2]["venue"] == "Proc. Conf."


def test_latex_accents_in_bib_fields():
    bib = r"""@book{x, author={Mart{\'\i}nez, Llu{\'i}s and Ca{\~n}ada, N{\"u}ria and G{\`o}mez, Fran{\c c}esc and Stra{\ss}e, P.},
title={Mec\`anica \& {Termodin\`amica}}}"""
    [entry] = parse_bib(bib, "r.bib")
    assert entry["author"] == "Martínez, Lluís and Cañada, Nüria and Gòmez, Françesc and Straße, P."
    assert entry["title"] == "Mecànica & Termodinàmica"


def test_scan_project(make_project):
    root = make_project({
        "main.tex": "\\documentclass{article}\n"
                    "\\newcommand{\\R}{\\mathbb{R}}\n"
                    "\\newcommand\\norm[1]{\\lVert#1\\rVert}\n"
                    "\\DeclareMathOperator{\\argmax}{arg\\,max}\n"
                    "\\newenvironment{proofsketch}{}{}\n"
                    "\\begin{document}\n"
                    "\\section{Intro}\\label{sec:intro}\n"
                    "% \\label{commented:out}\n"
                    "\\end{document}\n",
        "ch/one.tex": "\\begin{figure}\n\\caption{A plot}\n\\label{fig:plot}\n\\end{figure}\n",
        "refs.bib": BIB,
        "img/plot.png": b"png",
        ".build/main.aux": "\\label{hidden}",
    })
    data = scan_project(root)
    labels = {l["name"]: l for l in data["labels"]}
    assert sorted((l["name"], l["file"], l["line"]) for l in data["labels"]) == [
        ("fig:plot", "ch/one.tex", 3), ("sec:intro", "main.tex", 7)]
    assert labels["sec:intro"]["context"] == "\\section{Intro}"
    assert [(c["name"], c["args"]) for c in data["commands"]] == [("R", 0), ("norm", 1), ("argmax", 0)]
    assert [e["name"] for e in data["environments"]] == ["proofsketch"]
    assert len(data["citations"]) == 3
    assert sorted(data["files"]) == ["ch/one.tex", "img/plot.png", "main.tex", "refs.bib"]


def test_bibitems_are_citations(make_project):
    root = make_project({"main.tex": "\\begin{thebibliography}{9}\n\\bibitem{siemens2000} SIEMENS (Pàgina consultada). "
                                     "Adreça URL: \\url{http://x}\n\\end{thebibliography}\n"})
    [c] = scan_project(root)["citations"]
    assert (c["key"], c["type"], c["line"]) == ("siemens2000", "bibitem", 2)
    assert c["title"].endswith("Adreça URL: http://x")
