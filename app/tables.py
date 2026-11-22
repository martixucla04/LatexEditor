"""Tables pasted from Excel (or any spreadsheet) as LaTeX.

Excel puts the copied cells on the clipboard as tab-separated text: rows end in CRLF, and
a cell holding a tab, a line break or a quote is quoted, with quotes doubled. to_latex() writes
them as tabular, tabularx or longtable with the column types, rules and caption chosen in
the paste dialog (web/js/tables.js).
"""

import re

from .project import Project
from .reftypes import escape_latex
from .workspace import iter_project_files

ENVIRONMENTS = ("tabular", "tabularx", "longtable")
NUMBER = re.compile(r"^[-+−]?[\d.,  ]*\d[\d.,  ]*\s*(%|€|\$|°C?|[a-zA-Zµ]{1,3})?$")
DOCUMENTCLASS_LINE = re.compile(r"^[^%\n]*\\documentclass.*$", re.M)


def parse_cells(text: str) -> list[list[str]]:
    """Clipboard text -> rows of cells, without the empty rows and columns at the edges."""
    rows, row, cell, i, quoted = [], [], [], 0, False
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == '"' and text[i + 1:i + 2] == '"':
                cell.append('"')
                i += 1
            elif ch == '"':
                quoted = False
            else:
                cell.append(ch)
        elif ch == '"' and not cell:
            quoted = True
        elif ch == "\t":
            row.append("".join(cell))
            cell = []
        elif ch == "\n":
            row.append("".join(cell))
            rows.append(row)
            row, cell = [], []
        else:
            cell.append(ch)
        i += 1
    if cell or row:
        row.append("".join(cell))
        rows.append(row)

    rows = [[c.strip() for c in r] for r in rows]
    while rows and not any(rows[-1]):
        rows.pop()
    while rows and not any(rows[0]):
        rows.pop(0)
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]
    used = [j for j in range(width) if any(r[j] for r in rows)]
    if used:
        rows = [r[used[0]:used[-1] + 1] for r in rows]
    return rows


def numeric_columns(rows: list[list[str]], header: bool = True) -> list[bool]:
    """Columns whose non-empty cells (after the header row) are all numbers."""
    body = rows[1:] if header and len(rows) > 1 else rows
    width = len(rows[0]) if rows else 0
    out = []
    for j in range(width):
        cells = [r[j] for r in body if r[j]]
        out.append(bool(cells) and all(NUMBER.match(c) for c in cells))
    return out


def default_columns(rows: list[list[str]], env: str, header: bool = True) -> list[str]:
    """Numbers right-aligned; text left (tabularx: X, sharing the width)."""
    text = "X" if env == "tabularx" else "l"
    return ["r" if n else text for n in numeric_columns(rows, header)]


def needed_packages(options: dict) -> list[str]:
    packages = []
    if options.get("env") in ("tabularx", "longtable"):
        packages.append(options["env"])
    if options.get("hlines") == "booktabs":
        packages.append("booktabs")
    return packages


def to_latex(rows: list[list[str]], options: dict) -> str:
    """LaTeX source of the table. Options (all optional):
    env tabular|tabularx|longtable; columns [l|c|r|p|X per column]; vlines none|outer|inner|all;
    hlines none|header|frame|all|booktabs; header (first row is the header); bold_header;
    float (table environment, centred); caption; label; escape (LaTeX special characters).
    """
    if not rows:
        return ""
    env = options.get("env") if options.get("env") in ENVIRONMENTS else "tabular"
    header = options.get("header", True) and len(rows) > 1
    width = len(rows[0])
    columns = list(options.get("columns") or [])[:width]
    columns += default_columns(rows, env, header)[len(columns):]
    share = f"{0.9 / width:.2f}".rstrip("0")
    spec_of = {"l": "l", "c": "c", "r": "r", "p": f"p{{{share}\\linewidth}}",
               "X": "X" if env == "tabularx" else f"p{{{share}\\linewidth}}"}
    vlines = options.get("vlines", "none")
    sep = "|" if vlines in ("inner", "all") else ""
    edge = "|" if vlines in ("outer", "all") else ""
    spec = edge + sep.join(spec_of.get(c, "l") for c in columns) + edge

    hlines = options.get("hlines", "booktabs")
    rule = {"top": "", "mid": "", "row": "", "bottom": ""}
    if hlines == "booktabs":
        rule.update(top="\\toprule", mid="\\midrule", bottom="\\bottomrule")
    elif hlines == "header":
        rule.update(mid="\\hline")
    elif hlines == "frame":
        rule.update(top="\\hline", mid="\\hline", bottom="\\hline")
    elif hlines == "all":
        rule.update(top="\\hline", mid="\\hline", row="\\hline", bottom="\\hline")

    def cell(text: str, bold: bool) -> str:
        text = " ".join(text.split())  # line breaks inside a cell
        if options.get("escape", True):
            text = escape_latex(text)
        return f"\\textbf{{{text}}}" if bold and text else text

    def line(row: list[str], bold: bool = False) -> str:
        return "  " + " & ".join(cell(c, bold) for c in row) + " \\\\"

    caption, label = options.get("caption", "").strip(), options.get("label", "").strip()
    caption_lines = []
    if caption:
        caption_lines.append(f"\\caption{{{caption}}}" + (f"\\label{{{label}}}" if label else ""))
    elif label:
        caption_lines.append(f"\\label{{{label}}}")

    head = []
    if rule["top"]:
        head.append("  " + rule["top"])
    if header:
        head.append(line(rows[0], options.get("bold_header", True)))
        if rule["mid"]:
            head.append("  " + rule["mid"])
    body_rows = rows[1:] if header else rows
    body = []
    for k, row in enumerate(body_rows):
        body.append(line(row))
        if rule["row"] and k < len(body_rows) - 1:
            body.append("  " + rule["row"])
    if rule["bottom"]:
        body.append("  " + rule["bottom"])

    if env == "longtable":
        out = [f"\\begin{{longtable}}{{{spec}}}"]
        if caption_lines:
            out.append("  " + caption_lines[0] + " \\\\")
        if header:  # the header again at the top of every following page
            out += head + ["  \\endfirsthead"] + head + ["  \\endhead"]
        else:
            out += head
        return "\n".join(out + body + ["\\end{longtable}"]) + "\n"

    begin = f"\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}" if env == "tabularx" else f"\\begin{{tabular}}{{{spec}}}"
    table = [begin, *head, *body, f"\\end{{{env}}}"]
    if not options.get("float", True):
        return "\n".join(table) + "\n"
    inner = ["  " + t for t in table]
    above = options.get("caption_position", "top") != "bottom"
    out = ["\\begin{table}[htbp]", "  \\centering"]
    out += (["  " + c for c in caption_lines] if above else []) + inner
    out += [] if above else ["  " + c for c in caption_lines]
    return "\n".join(out + ["\\end{table}"]) + "\n"


def _loaded(text: str, package: str) -> bool:
    return re.search(rf"^[^%\n]*\\usepackage(?:\[[^\]]*\])?\{{[^}}]*\b{package}\b", text, re.M) is not None


def missing_packages(project: Project, packages: list[str], overrides: dict | None = None) -> list[str]:
    """The packages no .tex file of the project loads (`overrides`: unsaved text by path)."""
    texts = dict(overrides or {})
    for path in iter_project_files(project.root):
        rel = project.rel(path)
        if rel.endswith(".tex") and rel not in texts:
            texts[rel] = project.read_file(rel).get("text", "")
    return [p for p in packages if not any(_loaded(t, p) for t in texts.values())]


def add_packages(project: Project, packages: list[str]) -> dict:
    """Write \\usepackage lines for the missing `packages` after \\documentclass in the main file."""
    missing = missing_packages(project, packages)
    main = project.main_file
    if not missing or not main:
        return {"added": [], "file": main, "changed": []}
    data = project.read_file(main)
    text = data["text"]
    dc = DOCUMENTCLASS_LINE.search(text)
    if not dc:
        return {"added": [], "file": main, "changed": []}
    text = text[:dc.end()] + "".join(f"\n\\usepackage{{{p}}}" for p in missing) + text[dc.end():]
    project.write_file(main, text, data.get("encoding", "utf-8"))
    return {"added": missing, "file": main, "changed": [main]}
