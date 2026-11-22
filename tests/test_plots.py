import shutil
import subprocess

import pytest

from app.plots import INLINE_ROWS, parse_number, plot_latex, save_csv
from app.project import Project
from app.tables import insert_packages, parse_cells

EXCEL = "Temps (s)\tTensió (V)\tCorrent (A)\r\n0\t3,65\t1,2\r\n10\t3,61\t\r\n20\t3,58\t1,1\r\n"


def test_parse_number():
    assert parse_number("3,65") == (3.65, True)
    assert parse_number("1.234,5") == (1234.5, True)
    assert parse_number("-2.5") == (-2.5, False)
    assert parse_number("50 %")[0] == 50
    assert parse_number("25 °C")[0] == 25
    assert parse_number("1,234,567") == (1234567, False)
    assert parse_number("EM05")[0] is None


def test_line_plot_with_decimal_commas():
    result = plot_latex(None, parse_cells(EXCEL), {"caption": "Descàrrega", "label": "fig:descarrega"})
    latex = result["latex"]
    assert result["comma"] and result["csv"] is None and not result["warnings"]
    assert "        x y1 y2\n        0 3.65 1.2\n        10 3.61 nan\n" in latex  # empty cell -> gap
    assert "xlabel={Temps (s)}" in latex and "/pgf/number format/use comma" in latex
    assert "\\addplot+[mark=*] table[x=x, y=y2] {\\plotdata};" in latex
    assert "\\addlegendentry{Corrent (A)}" in latex  # two series: legend on
    assert latex.rstrip().endswith("\\caption{Descàrrega}\n    \\label{fig:descarrega}\n\\end{figure}")


def test_categories_as_bars():
    rows = parse_cells("Model\tCel·les\nEM04\t96\nEM05\t108\n")
    latex = plot_latex(None, rows, {"type": "bar"})["latex"]
    assert "ybar" in latex and "xticklabels={{EM04},{EM05}}" in latex
    assert plot_latex(None, rows, {"type": "line"})["warnings"]  # labels under a line plot: a note


def test_long_series_go_to_a_csv_file(make_project):
    project = Project(make_project({"main.tex": "\\documentclass{article}\n"}))
    rows = [["t", "v"]] + [[str(i), f"{i},5"] for i in range(INLINE_ROWS + 1)]
    result = plot_latex(project, rows, {"label": "fig:carrega"})
    assert result["csv_path"] == "data/carrega.csv"
    assert "table[x=x, y=y1, col sep=comma] {data/carrega.csv};" in result["latex"]
    save_csv(project, result["csv_path"], result["csv"])
    assert (project.root / "data/carrega.csv").read_text().startswith("x,y1\n0,0.5\n")
    assert plot_latex(project, rows, {"label": "fig:carrega"})["csv_path"] == "data/carrega-2.csv"


def test_pgfplots_gets_its_compat_line():
    assert insert_packages("\\documentclass{article}\n", ["pgfplots"]) == \
        "\\documentclass{article}\n\\usepackage{pgfplots}\n\\pgfplotsset{compat=1.18}\n"


def _has_pgfplots() -> bool:
    try:
        return bool(subprocess.run(["kpsewhich", "pgfplots.sty"], capture_output=True, text=True).stdout.strip())
    except OSError:
        return False


@pytest.mark.latex
@pytest.mark.skipif(shutil.which("lualatex") is None or not _has_pgfplots(), reason="lualatex/pgfplots not installed")
def test_plots_compile(make_project):
    from app.builder import Builder

    small = plot_latex(None, parse_cells(EXCEL), {"label": "fig:a", "caption": "A"})["latex"]
    bars = plot_latex(None, parse_cells("Model\tCel·les\nEM04\t96\nEM05\t108\n"), {"type": "bar", "caption": "B"})["latex"]
    root = make_project({"main.tex": ""})
    project = Project(root)
    long = plot_latex(project, [["t", "v"]] + [[str(i), str(i * i)] for i in range(80)], {"label": "fig:c", "caption": "C"})
    save_csv(project, long["csv_path"], long["csv"])
    (root / "main.tex").write_text(insert_packages("\\documentclass{article}\n", ["pgfplots"])
                                   + f"\\begin{{document}}\n{small}{bars}{long['latex']}\\end{{document}}\n", encoding="utf-8")
    result = Builder(root, "main.tex").run()
    assert result.status == "success", [p.message for p in result.problems if p.severity == "error"]
