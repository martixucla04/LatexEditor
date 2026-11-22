"""Spreadsheet cells as a pgfplots chart (the Plot mode of the paste-table dialog).

The pasted cells (app/tables.py parse_cells) become a data table: one X column and
one or more Y columns. Numbers written with a decimal comma (Excel in Catalan or
Spanish, "3,65") are stored with a point, and the axes can show commas again. Up to
INLINE_ROWS rows the data is written into the figure; longer series go to a CSV file
in data/ so the chapter text stays short.
"""

import re

from .errors import UserError
from .images import slug
from .project import Project
from .reftypes import escape_latex

INLINE_ROWS = 60
NUMBER = re.compile(r"^([-+−]?(?:\d[\d.,  ]*\d|\d))\s*(%|[^\d\s.,]{1,4})?$")
TYPES = ("line", "markers", "scatter", "bar")


def parse_number(cell: str) -> tuple[float | None, bool]:
    """(value, used a decimal comma) for '3,65', '1.234,5', '-2.5', '50 %', '25 °C'; (None, False) if not a number."""
    m = NUMBER.match(cell.strip())
    if not m:
        return None, False
    raw = m.group(1).replace("−", "-").replace(" ", "").replace(" ", "")
    comma = False
    if "," in raw and "." in raw:  # the last one is the decimal separator
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if decimal == "," else ",", "")
        comma = decimal == ","
    elif "," in raw:
        comma = raw.count(",") == 1
        raw = raw.replace(",", ".") if comma else raw.replace(",", "")
    try:
        return float(raw.replace(",", ".")), comma
    except ValueError:
        return None, False


def columns(rows: list[list[str]], header: bool = True) -> list[dict]:
    """[{name, numeric}] per column: numeric when every non-empty data cell is a number."""
    names = rows[0] if header and rows else []
    body = rows[1:] if header else rows
    width = len(rows[0]) if rows else 0
    out = []
    for j in range(width):
        cells = [r[j] for r in body if r[j].strip()]
        numeric = bool(cells) and all(parse_number(c)[0] is not None for c in cells)
        out.append({"name": (names[j] if j < len(names) else "") or f"Column {j + 1}", "numeric": numeric})
    return out


def default_options(rows: list[list[str]], header: bool = True) -> dict:
    cols = columns(rows, header)
    ys = [j for j, c in enumerate(cols) if c["numeric"] and j != 0]
    return {"x": 0, "ys": ys or [min(1, len(cols) - 1)]}


def _fmt(value: float) -> str:
    return f"{value:.10g}"


def plot_latex(project: Project | None, rows: list[list[str]], options: dict) -> dict:
    """{latex, csv_path, csv, comma, warnings}. Options (all optional): type line|markers|scatter|bar,
    header, x, ys, xlabel, ylabel, legend, grid, width, height, comma (None = as in the data),
    caption, label."""
    header = options.get("header", True) and len(rows) > 1
    cols = columns(rows, header)
    defaults = default_options(rows, header)
    x = options.get("x", defaults["x"])
    ys = [j for j in options.get("ys", defaults["ys"]) if 0 <= j < len(cols) and j != x]
    kind = options.get("type") if options.get("type") in TYPES else "markers"
    body = rows[1:] if header else rows
    warnings = []
    if not ys:
        return {"latex": "", "csv_path": None, "csv": None, "comma": False, "warnings": ["Choose at least one Y column."]}

    categorical = not cols[x]["numeric"]
    if categorical and kind != "bar":
        warnings.append(f"“{cols[x]['name']}” is not numeric: its values are shown as labels under the axis.")
    used_comma = False
    data = []  # [x, y1, y2…] as text
    labels = []
    for i, row in enumerate(body):
        values = []
        for j in ys:
            value, comma = parse_number(row[j]) if row[j].strip() else (None, False)
            used_comma |= comma
            values.append(_fmt(value) if value is not None else "nan")
        if all(v == "nan" for v in values):
            continue
        if categorical:
            labels.append(escape_latex(row[x].strip()))
            xs = str(len(labels))
        else:
            value, comma = parse_number(row[x])
            used_comma |= comma
            if value is None:
                continue
            xs = _fmt(value)
        data.append([xs, *values])
    if not data:
        return {"latex": "", "csv_path": None, "csv": None, "comma": used_comma,
                "warnings": warnings + ["No rows with numbers to plot."]}

    names = ["x"] + [f"y{n + 1}" for n in range(len(ys))]
    comma = options.get("comma")
    comma = used_comma if comma is None else bool(comma)
    width = float(options.get("width", 0.8))
    height = float(options.get("height", 0.6))
    label = (options.get("label") or "").strip()
    caption = (options.get("caption") or "").strip()

    axis = [f"width={width:g}\\textwidth", f"height={width * height:.2g}\\textwidth"]
    xlabel = options.get("xlabel", cols[x]["name"] if header else "")
    ylabel = options.get("ylabel", cols[ys[0]]["name"] if header and len(ys) == 1 else "")
    if xlabel.strip():
        axis.append(f"xlabel={{{escape_latex(xlabel.strip())}}}")
    if ylabel.strip():
        axis.append(f"ylabel={{{escape_latex(ylabel.strip())}}}")
    if options.get("grid", True):
        axis.append("grid=major")
    if kind == "bar":
        axis += ["ybar", "enlarge x limits=0.15"]
        if len(ys) > 1:
            axis.append(f"bar width={max(4, 18 // len(ys))}pt")
    if categorical:
        axis += ["xtick=data", "xticklabels={" + ",".join("{" + t + "}" for t in labels) + "}"]
    if comma:
        axis.append("/pgf/number format/use comma, /pgf/number format/1000 sep={}")
    legend = options.get("legend", len(ys) > 1)
    if legend:
        axis.append("legend pos=north west")
    axis.append("unbounded coords=jump")

    style = {"line": "no marks", "markers": "mark=*", "scatter": "only marks", "bar": ""}[kind]
    csv_path = csv = None
    if len(data) > INLINE_ROWS:
        csv_path = _free_csv(project, slug(label.split(":", 1)[-1] or caption, "dades"))
        csv = ",".join(names) + "\n" + "\n".join(",".join(r) for r in data) + "\n"
        source, options_tail = f"{{{csv_path}}}", ", col sep=comma"
        table = []
    else:
        source, options_tail = "{\\plotdata}", ""
        table = ["    \\pgfplotstableread{", "        " + " ".join(names),
                 *("        " + " ".join(r) for r in data), "    }\\plotdata"]

    plots = []
    for n, j in enumerate(ys):
        plots.append(f"            \\addplot+[{style}] table[x=x, y=y{n + 1}{options_tail}] {source};"
                     if style else f"            \\addplot table[x=x, y=y{n + 1}{options_tail}] {source};")
        if legend:
            plots.append(f"            \\addlegendentry{{{escape_latex(cols[j]['name'])}}}")

    latex = [
        "\\begin{figure}[ht]",
        "    \\centering",
        *table,
        "    \\begin{tikzpicture}",
        "        \\begin{axis}[",
        *(f"            {a}," for a in axis),
        "        ]",
        *plots,
        "        \\end{axis}",
        "    \\end{tikzpicture}",
        f"    \\caption{{{caption}}}",
        *([f"    \\label{{{label}}}"] if label else []),
        "\\end{figure}",
        "",
    ]
    preview = {  # for the dialog's quick drawing
        "x": [float(r[0]) for r in data],
        "series": [[None if r[n + 1] == "nan" else float(r[n + 1]) for r in data] for n in range(len(ys))],
        "names": [cols[j]["name"] for j in ys],
        "labels": labels,
    }
    return {"latex": "\n".join(latex), "csv_path": csv_path, "csv": csv, "comma": used_comma,
            "warnings": warnings, "preview": preview}


def _free_csv(project: Project | None, base: str) -> str:
    name, n = f"data/{base}.csv", 2
    while project is not None and (project.root / name).exists():
        name = f"data/{base}-{n}.csv"
        n += 1
    return name


def save_csv(project: Project, path: str, text: str) -> str:
    """Write the plot's data file; refuses to overwrite one that exists."""
    target = project.path(path)
    if target.suffix.lower() != ".csv":
        raise UserError(f"Not a .csv file: {path}")
    if target.exists():
        raise UserError(f"{path} already exists.")
    target.parent.mkdir(parents=True, exist_ok=True)
    project.write_file(path, text)
    return path
