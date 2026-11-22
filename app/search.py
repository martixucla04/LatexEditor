"""Project-wide find and replace.

Matching is line by line (so ^ and $ anchor to lines). By default the query is
literal text, which suits LaTeX's many backslashes; with `regex` it is a Python
regular expression, and the replacement may use $1 or \\1 for groups.
"Whole word" only adds a boundary on sides where the query starts/ends with a
letter or digit, so "\\section" as a whole word still matches "\\section{" but
not "\\sectionmark".
"""

import fnmatch
import re
from pathlib import PurePosixPath

from .errors import UserError
from .project import MAX_TEXT_BYTES, Project, _decode
from .workspace import iter_project_files

DEFAULT_INCLUDE = "*.tex, *.bib, *.sty, *.cls"
MAX_MATCHES = 2000
PREVIEW_CHARS = 160


def compile_query(query: str, regex: bool = False, case: bool = False, word: bool = False) -> re.Pattern:
    if not query:
        raise UserError("Type something to search for.")
    body = query if regex else re.escape(query)
    if word:
        if re.match(r"\w", query) or regex:
            body = r"(?<!\w)" + body
        if re.search(r"\w$", query) or regex:
            body = body + r"(?!\w)"
    try:
        return re.compile(body, 0 if case else re.IGNORECASE)
    except re.error as exc:
        raise UserError(f"Invalid regular expression: {exc}") from exc


GROUP_REF = re.compile(r"\\\\|\\(\d)|\$(\d+)|\$\{(\d+)\}")


def _replacement(replacement: str, regex: bool):
    """Value for Pattern.sub: literal text, or in regex mode $1, ${1} and \\1 replaced by the
    groups and \\\\ by one backslash. Other backslashes stay as typed, so \\textbf{$1} works
    (Python's own template syntax would turn \\t into a tab)."""
    if not regex:
        return lambda _m: replacement

    def expand(m: re.Match) -> str:
        def group(ref: re.Match) -> str:
            if ref.group(0) == "\\\\":
                return "\\"
            n = int(ref.group(1) or ref.group(2) or ref.group(3))
            if n > (m.re.groups or 0):
                raise UserError(f"Invalid replacement: there is no group {n}.")
            return m.group(n) or ""
        return GROUP_REF.sub(group, replacement)

    return expand


def _included(rel: str, include: str) -> bool:
    patterns = [p.strip() for p in (include or DEFAULT_INCLUDE).split(",") if p.strip()]
    name = PurePosixPath(rel).name
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def _text_files(project: Project, include: str, only: list[str] | None = None):
    """(rel, path) for searchable text files."""
    wanted = set(only) if only is not None else None
    for path in iter_project_files(project.root):
        rel = project.rel(path)
        if wanted is not None and rel not in wanted:
            continue
        if not _included(rel, include):
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
        except OSError:
            continue
        yield rel, path


def _preview(line: str, start: int, end: int) -> tuple[str, int]:
    """A slice of `line` around the match and the match's offset in that slice."""
    lead = max(0, start - 40)
    text = line[lead:lead + PREVIEW_CHARS].rstrip("\r\n")
    if lead:
        text = "…" + text
        return text, start - lead + 1
    return text, start


def search(project: Project, query: str, regex=False, case=False, word=False, include=DEFAULT_INCLUDE) -> dict:
    pattern = compile_query(query, regex, case, word)
    files, total, truncated = [], 0, False
    for rel, path in _text_files(project, include):
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            continue
        text, _ = _decode(data)
        matches = []
        for number, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                if m.start() == m.end():
                    continue  # empty matches (e.g. "^") are not useful results
                preview, offset = _preview(line, m.start(), m.end())
                matches.append({
                    "line": number, "column": m.start() + 1, "length": m.end() - m.start(),
                    "preview": preview, "offset": offset,
                })
                total += 1
                if total >= MAX_MATCHES:
                    truncated = True
                    break
            if truncated:
                break
        if matches:
            files.append({"file": rel, "matches": matches})
        if truncated:
            break
    return {"files": files, "total": total, "truncated": truncated}


def replace(project: Project, query: str, replacement: str, regex=False, case=False, word=False,
            include=DEFAULT_INCLUDE, files: list[str] | None = None) -> dict:
    """Replace every match in the given files (default: all included files). Returns changed files."""
    pattern = compile_query(query, regex, case, word)
    repl = _replacement(replacement, regex)
    changed, count = [], 0
    for rel, path in _text_files(project, include, files):
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            continue
        text, encoding = _decode(data)
        out, n_file = [], 0
        for line in text.splitlines(keepends=True):
            body = line.rstrip("\r\n")
            ending = line[len(body):]
            try:
                new, n = pattern.subn(repl, body)
            except (re.error, IndexError) as exc:
                raise UserError(f"Invalid replacement: {exc}") from exc
            out.append(new + ending)
            n_file += n
        if n_file:
            project.write_file(rel, "".join(out), encoding)
            changed.append(rel)
            count += n_file
    return {"files": changed, "count": count}
