"""Build pipeline tests against the real MiKTeX toolchain."""

import shutil
import threading
import time
import urllib.request

import pytest

from app.api import Api
from app.builder import Builder

pytestmark = [
    pytest.mark.latex,
    pytest.mark.skipif(shutil.which("lualatex") is None, reason="lualatex not installed"),
]

PLAIN = r"""\documentclass{article}
\begin{document}
\section{One}\label{s:one}
See Section~\ref{s:one}.
\end{document}
"""

BIBLATEX = r"""\documentclass{article}
\usepackage[backend=biber]{biblatex}
\addbibresource{refs.bib}
\begin{document}
Text \cite{smith2020}.
\printbibliography
\end{document}
"""

NATBIB = r"""\documentclass{article}
\usepackage[numbers]{natbib}
\begin{document}
Text \citep{doe2019}.
\bibliographystyle{plainnat}
\bibliography{bib/refs}
\end{document}
"""

GLOSSARY = r"""\documentclass{article}
\usepackage{makeidx}
\makeindex
\usepackage[acronym]{glossaries}
\makeglossaries
\newacronym{fem}{FEM}{finite element method}
\begin{document}
We use the \gls{fem}\index{FEM}.
\printglossaries
\printindex
\end{document}
"""

BIB = "@article{smith2020, author={Smith, Jane}, title={Heat}, journal={J}, year={2020}}\n"
BIB2 = "@book{doe2019, author={Doe, John}, title={Composites}, publisher={Springer}, year={2019}}\n"


def tools(result):
    return [s.tool for s in result.steps]


def log_of(root, name="main"):
    return (root / ".build" / f"{name}.log").read_text(encoding="utf-8", errors="replace")


def test_plain_document(make_project):
    root = make_project({"main.tex": PLAIN})
    result = Builder(root, "main.tex").run()
    assert result.status == "success", result.log[-2000:]
    assert (root / ".build" / "main.pdf").exists()
    assert (root / ".build" / "main.synctex.gz").exists()
    # first build needs a second run for the \ref
    assert tools(result) == ["lualatex", "lualatex"]
    # nothing changed: a single run is enough
    assert tools(Builder(root, "main.tex").run()) == ["lualatex"]


def test_biblatex_runs_biber_only_when_needed(make_project):
    root = make_project({"main.tex": BIBLATEX, "refs.bib": BIB})
    first = Builder(root, "main.tex").run()
    assert first.status == "success", first.log[-2000:]
    assert tools(first)[:3] == ["lualatex", "biber", "lualatex"]
    assert "Citation 'smith2020' undefined" not in log_of(root)

    assert "biber" not in tools(Builder(root, "main.tex").run())

    (root / "refs.bib").write_text(BIB.replace("Heat", "Cold"), encoding="utf-8")
    assert "biber" in tools(Builder(root, "main.tex").run())


def test_natbib_runs_bibtex_from_subfolder_bib(make_project):
    root = make_project({"main.tex": NATBIB, "bib/refs.bib": BIB2})
    result = Builder(root, "main.tex").run()
    assert result.status == "success", result.log[-2000:]
    assert "bibtex" in tools(result)
    assert "Citation `doe2019' on page 1 undefined" not in log_of(root)
    assert "doe2019" in (root / ".build" / "main.bbl").read_text()


def test_glossaries_and_index(make_project):
    root = make_project({"main.tex": GLOSSARY})
    result = Builder(root, "main.tex").run()
    assert result.status == "success", result.log[-2000:]
    assert "makeglossaries-lite" in tools(result)
    assert "makeindex" in tools(result)
    assert (root / ".build" / "main.acr").exists()
    assert (root / ".build" / "main.ind").exists()


def test_main_file_in_subfolder_and_accented_path(make_project):
    root = make_project({"tesi/main.tex": PLAIN.replace("One", "Introducció")}, name="Tesi Martí")
    result = Builder(root, "tesi/main.tex").run()
    assert result.status == "success", result.log[-2000:]
    assert result.pdf.endswith("main.pdf")


def test_errors_still_produce_pdf(make_project):
    root = make_project({"main.tex": PLAIN.replace("See", r"\undefinedmacro See")})
    result = Builder(root, "main.tex").run()
    assert result.status == "errors"
    assert result.pdf is not None
    assert "Undefined control sequence" in result.log


def test_fatal_error_fails(make_project):
    root = make_project({"main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{missing}\n"})
    result = Builder(root, "main.tex").run()
    assert result.status == "failed"
    assert result.pdf is None


def test_cancel(make_project):
    root = make_project({"main.tex": GLOSSARY})
    builder = Builder(root, "main.tex")
    results = []
    worker = threading.Thread(target=lambda: results.append(builder.run()))
    worker.start()
    time.sleep(0.5)
    builder.cancel()
    worker.join(30)
    assert results and results[0].status == "cancelled"


def test_api_compile_serves_pdf(settings, make_zip):
    api = Api(settings)
    api.import_zip(str(make_zip({"main.tex": PLAIN})))
    assert api.current_pdf() is None
    result = api.compile()
    assert result["status"] == "success"
    with urllib.request.urlopen(result["pdf_url"]) as resp:
        assert resp.headers["Content-Type"] == "application/pdf"
        assert resp.read(5) == b"%PDF-"
    # a wrong token is refused
    bad = result["pdf_url"].replace("/1.pdf", "").rsplit("/", 1)[0] + "/nope/1.pdf"
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(bad)
    assert api.current_pdf().startswith("http://127.0.0.1:")
