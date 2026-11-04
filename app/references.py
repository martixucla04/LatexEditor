"""Web references in the house style, added to the document's bibliography.

Format (one \\bibitem in thebibliography):

    Autor (Pàgina consultada <data>). Títol de la pàgina, [tipus de suport]. Adreça URL: <url>

    SIEMENS (Pàgina consultada l’11 de febrer de 2000). SIEMENS. Productos y soluciones,
    [En línia]. Adreça URL: http://www.siemens.es/html/prodsolu/prodserv.html

The \\bibitem goes before \\end{thebibliography} in the project file that has one,
or a new thebibliography is created before \\end{document} in the main file. URLs
use \\url, so the url package is added to the preamble when neither url nor
hyperref is loaded.
"""

import re
import unicodedata
from datetime import date

from .errors import UserError
from .project import Project
from .workspace import iter_project_files

MONTHS = ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost",
          "setembre", "octubre", "novembre", "desembre"]

LATEX_SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}

BIBITEM = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
END_THEBIBLIOGRAPHY = re.compile(r"^[ \t]*\\end\{thebibliography\}", re.M)
END_DOCUMENT = re.compile(r"^[ \t]*\\end\{document\}", re.M)
DOCUMENTCLASS_LINE = re.compile(r"^[^%\n]*\\documentclass.*$", re.M)
URL_PACKAGE = re.compile(r"^[^%\n]*\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(url|xurl|hyperref)\b[^}]*\}", re.M)
BIBLATEX_OR_BIBTEX = re.compile(r"^[^%\n]*(\\usepackage(?:\[[^\]]*\])?\{biblatex\}|\\bibliography\{|\\printbibliography)", re.M)


def catalan_date(d: date) -> str:
    """'l’11 de febrer de 2000', 'el 2 d’abril de 2024' (apostrophe before 1, 11 and vowels)."""
    day = f"l’{d.day}" if d.day in (1, 11) else f"el {d.day}"
    month = MONTHS[d.month - 1]
    article = "d’" if month[0] in "aeiou" else "de "
    return f"{day} {article}{month} de {d.year}"


def escape_latex(text: str) -> str:
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def _clean(field: str, name: str) -> str:
    value = re.sub(r"\s+", " ", (field or "")).strip()
    if not value:
        raise UserError(f"The {name} is required.")
    return value


def format_web_reference(author: str, consulted: str, title: str, medium: str, url: str) -> str:
    """LaTeX text of the reference (without \\bibitem). `consulted` is an ISO date (YYYY-MM-DD)."""
    author = _clean(author, "author")
    title = _clean(title, "page title")
    medium = _clean(medium or "En línia", "medium")
    url = _clean(url, "URL").replace(" ", "")
    try:
        day = date.fromisoformat(consulted)
    except (TypeError, ValueError) as exc:
        raise UserError("The consultation date is not valid.") from exc
    return (f"{escape_latex(author)} (Pàgina consultada {catalan_date(day)}). "
            f"{escape_latex(title)}, [{escape_latex(medium)}]. Adreça URL: \\url{{{url}}}")


def suggest_key(author: str, consulted: str) -> str:
    """'SIEMENS', 2000-02-11 -> 'siemens2000'; 'Equip Mediterrani' -> 'equipmediterrani2000'."""
    ascii_author = unicodedata.normalize("NFKD", author or "").encode("ascii", "ignore").decode()
    stem = re.sub(r"[^a-z0-9]", "", ascii_author.lower())[:24] or "web"
    return stem + (consulted or "")[:4]


def existing_keys(project: Project) -> set[str]:
    keys = set()
    for path in iter_project_files(project.root):
        if path.suffix.lower() == ".tex":
            text = path.read_text(encoding="utf-8", errors="replace")
            keys.update(BIBITEM.findall(text))
    return keys


def unique_key(key: str, taken: set[str]) -> str:
    key = re.sub(r"[^A-Za-z0-9:_\-.]", "", key) or "web"
    if key not in taken:
        return key
    for suffix in "bcdefghijklmnopqrstuvwxyz":
        if key + suffix not in taken:
            return key + suffix
    n = 2
    while f"{key}-{n}" in taken:
        n += 1
    return f"{key}-{n}"


def _read(project: Project, rel: str) -> tuple[str, str]:
    data = project.read_file(rel)
    return data["text"], data["encoding"]


def add_web_reference(project: Project, fields: dict) -> dict:
    """Add the reference as a \\bibitem. Returns {key, file, line, changed (files), url_package_added}."""
    main = project.main_file
    if not main:
        raise UserError("Set the main file first (right-click a .tex file, \"Set as main file\").")
    entry = format_web_reference(fields.get("author"), fields.get("consulted"), fields.get("title"),
                                 fields.get("medium"), fields.get("url"))
    key = unique_key(fields.get("key") or suggest_key(fields.get("author"), fields.get("consulted")),
                     existing_keys(project))
    item = f"\\bibitem{{{key}}} {entry}"

    main_text, main_encoding = _read(project, main)
    changed = []

    # The thebibliography that already exists (main file first), else a new one in the main file.
    candidates = [main] + sorted(project.rel(p) for p in iter_project_files(project.root)
                                 if p.suffix.lower() == ".tex" and project.rel(p) != main)
    for rel in candidates:
        text, encoding = (main_text, main_encoding) if rel == main else _read(project, rel)
        m = END_THEBIBLIOGRAPHY.search(text)
        if m:
            # line up with the existing items (else with \end{thebibliography})
            items = list(re.finditer(r"^([ \t]*)\\bibitem", text[:m.start()], re.M))
            indent = items[-1].group(1) if items else re.match(r"[ \t]*", text[m.start():]).group(0)
            text = text[:m.start()] + f"{indent}{item}\n\n" + text[m.start():]
            target, target_text = rel, text
            break
    else:
        if BIBLATEX_OR_BIBTEX.search(main_text):
            raise UserError("This document uses biblatex/BibTeX (\\printbibliography or \\bibliography{…}). "
                            "Add the reference to the .bib file instead, or remove that bibliography first.")
        m = END_DOCUMENT.search(main_text)
        if not m:
            raise UserError(f"No \\end{{document}} found in {main}.")
        block = f"\\begin{{thebibliography}}{{99}}\n\n{item}\n\n\\end{{thebibliography}}\n\n"
        main_text = main_text[:m.start()] + block + main_text[m.start():]
        target, target_text = main, main_text

    if target == main:
        main_text = target_text

    # \url needs the url (or hyperref) package.
    url_package_added = False
    if not URL_PACKAGE.search(main_text):
        dc = DOCUMENTCLASS_LINE.search(main_text)
        if dc:
            main_text = main_text[:dc.end()] + "\n\\usepackage{url}" + main_text[dc.end():]
            url_package_added = True

    if target != main:
        project.write_file(target, target_text, encoding)
        changed.append(target)
        if url_package_added:
            project.write_file(main, main_text, main_encoding)
            changed.append(main)
    else:
        project.write_file(main, main_text, main_encoding)
        changed.append(main)

    final_text = main_text if target == main else target_text
    line = final_text[:final_text.index(item)].count("\n") + 1
    return {"key": key, "file": target, "line": line, "changed": changed, "url_package_added": url_package_added}
