"""References in the house style, added to the document's bibliography.

The text of each entry comes from app/reftypes.py (books, parts of books, standards,
catalogues, periodicals, journal and newspaper articles, official publications, web
pages). Where it goes depends on how the document makes its bibliography:
- biblatex (\\addbibresource) or BibTeX (\\bibliography): an @misc entry in that .bib
  whose `note` is the formatted text, which every style prints as-is;
- otherwise a \\bibitem before \\end{thebibliography} in the project file that has one,
  or in a new thebibliography before \\end{document} in the main file.
A reference that is not cited in the text (fields["cite"] false) is still listed: a
\\bibitem always is, and for a .bib entry \\nocite{key} is written just before the
\\bibliography{…} / \\printbibliography line.
URLs use \\url, so the url package is added to the preamble when no .tex file of the
project loads url or hyperref.
"""

import re
import unicodedata

from .errors import UserError
from .project import Project
from .reftypes import catalan_date, escape_latex, format_reference, key_parts  # noqa: F401 (re-exported)
from .workspace import iter_project_files

BIBITEM = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
END_THEBIBLIOGRAPHY = re.compile(r"^[ \t]*\\end\{thebibliography\}", re.M)
END_DOCUMENT = re.compile(r"^[ \t]*\\end\{document\}", re.M)
DOCUMENTCLASS_LINE = re.compile(r"^[^%\n]*\\documentclass.*$", re.M)
URL_PACKAGE = re.compile(r"^[^%\n]*\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(url|xurl|hyperref)\b[^}]*\}", re.M)
ADDBIBRESOURCE = re.compile(r"^[^%\n]*\\addbibresource(?:\[[^\]]*\])?\{([^}]+)\}", re.M)
BIBLIOGRAPHY = re.compile(r"^[^%\n]*\\bibliography\{([^}]+)\}", re.M)
PRINTBIBLIOGRAPHY = re.compile(r"^[^%\n]*\\printbibliography", re.M)
# Start of the line that prints the bibliography, where \nocite goes.
BIBLIOGRAPHY_LINE = re.compile(r"^[ \t]*(?=[^%\n]*\\(?:bibliography\{|printbibliography))", re.M)
BIB_KEY = re.compile(r"@\s*[A-Za-z]+\s*[{(]\s*([^,\s{}()]+)\s*,")


def format_web_reference(author: str, consulted: str, title: str, medium: str, url: str) -> str:
    """LaTeX text of a web-page reference. `consulted` is an ISO date (YYYY-MM-DD)."""
    return format_reference("web", {"author": author, "consulted": consulted, "title": title,
                                    "medium": medium, "url": url})


def suggest_key(who: str, when: str) -> str:
    """'SIEMENS', '2000-02-11' -> 'siemens2000'; 'Equip Mediterrani' -> 'equipmediterrani2000'."""
    ascii_who = unicodedata.normalize("NFKD", who or "").encode("ascii", "ignore").decode()
    stem = re.sub(r"[^a-z0-9]", "", ascii_who.lower())[:24] or "ref"
    year = re.search(r"\d{4}", when or "")
    return stem + (year.group(0) if year else "")


def suggest_key_for(kind: str, fields: dict) -> str:
    return suggest_key(*key_parts(kind, fields))


def existing_keys(project: Project) -> set[str]:
    keys = set()
    for path in iter_project_files(project.root):
        suffix = path.suffix.lower()
        if suffix in (".tex", ".bib"):
            text = path.read_text(encoding="utf-8", errors="replace")
            keys.update(BIBITEM.findall(text) if suffix == ".tex" else BIB_KEY.findall(text))
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


def _tex_sources(project: Project, main: str) -> dict[str, tuple[str, str]]:
    """{rel: (text, encoding)} for the project's .tex files, main file first."""
    rels = [main] + sorted(project.rel(p) for p in iter_project_files(project.root)
                           if p.suffix.lower() == ".tex" and project.rel(p) != main)
    sources = {}
    for rel in rels:
        data = project.read_file(rel)
        if data["kind"] == "text":
            sources[rel] = (data["text"], data["encoding"])
    return sources


def bibliography_setup(sources: dict) -> tuple[str, str | None]:
    """("biblatex", bib), ("bibtex", bib) or ("manual", None) from \\addbibresource / \\bibliography."""
    for text, _ in sources.values():
        m = ADDBIBRESOURCE.search(text)
        if m:
            return "biblatex", m.group(1).strip()
        m = BIBLIOGRAPHY.search(text)
        if m:
            name = m.group(1).split(",")[0].strip()
            return "bibtex", name if name.lower().endswith(".bib") else name + ".bib"
    return "manual", None


def _add_to_bib(project: Project, bib: str, key: str, entry: str, mode: str) -> tuple[str, int]:
    """Append an @misc entry whose note is the formatted reference. Returns (bib rel, line)."""
    # The note is printed as-is by BibTeX styles (IEEEtran, plain…) and biblatex, which then add
    # a final period; the house format sometimes has none (after a URL or an ISBN). BibTeX skips
    # its period when the text already ends in punctuation (an invisible \phantom{.} where it
    # does not); biblatex has \nopunct.
    if mode == "biblatex":
        ending = "\\nopunct"
    else:
        ending = "" if entry.endswith((".", "?", "!")) else "\\phantom{.}"
    record = f"@misc{{{key},\n  note = {{{entry}{ending}}}\n}}\n"
    path = project.path(bib)
    if path.is_file():
        data = project.read_file(bib)
        text, encoding = data["text"], data["encoding"]
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text, encoding = "", "utf-8"
    head = text.rstrip("\r\n")
    text = (head + "\n\n" if head else "") + record
    project.write_file(project.rel(path), text, encoding)
    return project.rel(path), head.count("\n") + (3 if head else 1)


def add_web_reference(project: Project, fields: dict) -> dict:
    return add_reference(project, "web", fields)


def add_reference(project: Project, kind: str, fields: dict) -> dict:
    """Add a reference of type `kind` (see reftypes.types()) to the document's bibliography.

    With biblatex (\\addbibresource) or BibTeX (\\bibliography) it becomes an @misc entry
    in that .bib file; otherwise a \\bibitem in thebibliography. Returns
    {key, file, line, changed (files), url_package_added, mode, nocite_file}.
    With fields["cite"] false the reference is listed without a \\cite in the text.
    """
    main = project.main_file
    if not main:
        raise UserError("Set the main file first (right-click a .tex file, \"Set as main file\").")
    entry = format_reference(kind, fields)
    key = unique_key(fields.get("key") or suggest_key_for(kind, fields), existing_keys(project))
    sources = _tex_sources(project, main)
    mode, bib = bibliography_setup(sources)
    changed = []

    nocite_file = None
    if mode != "manual":
        target, line = _add_to_bib(project, bib, key, entry, mode)
        changed.append(target)
        if fields.get("cite") is False:
            nocite_file = _add_nocite(sources, main, key)
            changed.append(nocite_file)
    else:
        if any(PRINTBIBLIOGRAPHY.search(text) for text, _ in sources.values()):
            raise UserError("This document prints a biblatex bibliography but no \\addbibresource{…} was found.")
        item = f"\\bibitem{{{key}}} {entry}"
        # The thebibliography that already exists (main file first), else a new one in the main file.
        for rel, (text, encoding) in sources.items():
            m = END_THEBIBLIOGRAPHY.search(text)
            if m:
                # line up with the existing items (else with \end{thebibliography})
                items = list(re.finditer(r"^([ \t]*)\\bibitem", text[:m.start()], re.M))
                indent = items[-1].group(1) if items else re.match(r"[ \t]*", text[m.start():]).group(0)
                text = text[:m.start()] + f"{indent}{item}\n\n" + text[m.start():]
                break
        else:
            rel, (text, encoding) = main, sources[main]
            m = END_DOCUMENT.search(text)
            if not m:
                raise UserError(f"No \\end{{document}} found in {main}.")
            text = text[:m.start()] + f"\\begin{{thebibliography}}{{99}}\n\n{item}\n\n\\end{{thebibliography}}\n\n" + text[m.start():]
        sources[rel] = (text, encoding)
        target, line = rel, text[:text.index(item)].count("\n") + 1
        changed.append(rel)

    # \url needs the url (or hyperref) package, loaded in any of the project's .tex files.
    url_package_added = False
    if "\\url{" in entry and not any(URL_PACKAGE.search(text) for text, _ in sources.values()):
        text, encoding = sources[main]
        dc = DOCUMENTCLASS_LINE.search(text)
        if dc:
            text = text[:dc.end()] + "\n\\usepackage{url}" + text[dc.end():]
            sources[main] = (text, encoding)
            url_package_added = True
            if target == main:
                line += 1
            if main not in changed:
                changed.append(main)

    for rel in changed:
        if rel in sources:
            project.write_file(rel, *sources[rel])
    return {"key": key, "file": target, "line": line, "changed": changed,
            "url_package_added": url_package_added, "mode": mode, "nocite_file": nocite_file}


def _add_nocite(sources: dict, main: str, key: str) -> str:
    """Write \\nocite{key} above the line that prints the bibliography (else before
    \\end{document} of the main file), so an uncited .bib entry is still listed. Returns the file."""
    for rel, (text, encoding) in sources.items():
        m = BIBLIOGRAPHY_LINE.search(text)
        if m:
            break
    else:
        rel, (text, encoding) = main, sources[main]
        m = END_DOCUMENT.search(text)
        if not m:
            raise UserError(f"No \\end{{document}} found in {main}.")
    indent = re.match(r"[ \t]*", text[m.start():]).group(0)
    sources[rel] = (text[:m.start()] + f"{indent}\\nocite{{{key}}}\n" + text[m.start():], encoding)
    return rel
