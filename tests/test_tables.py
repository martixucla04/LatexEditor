import shutil

import pytest

from app.project import Project
from app.tables import add_packages, default_columns, missing_packages, parse_cells, to_latex

# What Excel puts on the clipboard: CRLF rows, tabs, a quoted cell with a line break and quotes.
EXCEL = 'Cel·la\tTensió (V)\tNota\r\n1\t3,65\t"dues\r\nlínies ""ok"""\r\n2\t3,70\t50% & _x_\r\n\t\t\r\n'


def test_parse_excel_clipboard():
    assert parse_cells(EXCEL) == [
        ["Cel·la", "Tensió (V)", "Nota"],
        ["1", "3,65", 'dues\nlínies "ok"'],
        ["2", "3,70", "50% & _x_"],
    ]
    # empty columns at the edges go, short rows are padded
    assert parse_cells("\ta\tb\t\n\tc\n") == [["a", "b"], ["c", ""]]


def test_default_columns_right_align_numbers():
    rows = parse_cells(EXCEL)
    assert default_columns(rows, "tabular") == ["r", "r", "l"]
    assert default_columns(rows, "tabularx") == ["r", "r", "X"]


def test_tabular_in_a_float_with_booktabs():
    latex = to_latex(parse_cells(EXCEL), {"caption": "Mesures", "label": "tab:m"})
    assert latex == (
        "\\begin{table}[htbp]\n"
        "  \\centering\n"
        "  \\caption{Mesures}\\label{tab:m}\n"
        "  \\begin{tabular}{rrl}\n"
        "    \\toprule\n"
        "    \\textbf{Cel·la} & \\textbf{Tensió (V)} & \\textbf{Nota} \\\\\n"
        "    \\midrule\n"
        "    1 & 3,65 & dues línies \"ok\" \\\\\n"
        "    2 & 3,70 & 50\\% \\& \\_x\\_ \\\\\n"
        "    \\bottomrule\n"
        "  \\end{tabular}\n"
        "\\end{table}\n"
    )


def test_lines_columns_and_no_float():
    rows = [["a", "b"], ["1", "2"], ["3", "4"]]
    latex = to_latex(rows, {"float": False, "vlines": "all", "hlines": "all", "columns": ["c", "p"],
                            "bold_header": False})
    assert latex.splitlines() == [
        "\\begin{tabular}{|c|p{0.45\\linewidth}|}", "  \\hline", "  a & b \\\\", "  \\hline",
        "  1 & 2 \\\\", "  \\hline", "  3 & 4 \\\\", "  \\hline", "\\end{tabular}",
    ]
    # X only means something in tabularx
    assert "{X l}" not in to_latex(rows, {"columns": ["X", "l"]})
    assert "\\begin{tabular}{p{0.45\\linewidth}l}" in to_latex(rows, {"columns": ["X", "l"]})
    assert "\\begin{tabularx}{\\linewidth}{Xl}" in to_latex(rows, {"env": "tabularx", "columns": ["X", "l"]})


def test_longtable_repeats_the_header():
    latex = to_latex([["a"], ["1"]], {"env": "longtable", "caption": "C", "hlines": "frame"})
    assert latex.splitlines() == [
        "\\begin{longtable}{r}", "  \\caption{C} \\\\",
        "  \\hline", "  \\textbf{a} \\\\", "  \\hline", "  \\endfirsthead",
        "  \\hline", "  \\textbf{a} \\\\", "  \\hline", "  \\endhead",
        "  1 \\\\", "  \\hline", "\\end{longtable}",
    ]


def test_add_missing_packages_after_documentclass(make_project):
    root = make_project({"main.tex": "\\documentclass{article}\n\\begin{document}\n\\end{document}\n",
                         "pre.tex": "\\usepackage{booktabs}\n"})
    project = Project(root)
    project.set_main_file("main.tex")
    assert missing_packages(project, ["tabularx", "booktabs"]) == ["tabularx"]
    assert missing_packages(project, ["tabularx"], {"main.tex": "\\usepackage{array,tabularx}"}) == []
    assert add_packages(project, ["tabularx", "booktabs"])["added"] == ["tabularx"]
    assert (root / "main.tex").read_text(encoding="utf-8").startswith("\\documentclass{article}\n\\usepackage{tabularx}\n")


@pytest.mark.latex
@pytest.mark.skipif(shutil.which("lualatex") is None, reason="lualatex not installed")
@pytest.mark.parametrize("env", ["tabular", "tabularx", "longtable"])
def test_every_kind_of_table_compiles(make_project, env):
    from app.builder import Builder

    table = to_latex(parse_cells(EXCEL), {"env": env, "caption": "T", "label": "tab:t", "vlines": "inner"})
    root = make_project({"main.tex": "\\documentclass{article}\n\\usepackage{booktabs,tabularx,longtable}\n"
                                     f"\\begin{{document}}\n{table}\\end{{document}}\n"}, name=f"t-{env}")
    assert Builder(root, "main.tex").run().status == "success"
