"""Document outline: the \\part … \\subsubsection headings in reading order.

Reading starts at the main file and follows \\input / \\include / \\subfile into the
other .tex files, so chapters written in the main file and sections in included
files come out in the order they appear in the PDF.
"""

import re

from .project import Project
from .workspace import iter_project_files

LEVELS = {"part": 0, "chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4}
# \section*[short]{  or  \input{file}  (the heading title is read with brace matching)
TOKEN = re.compile(r"\\(?:(part|chapter|section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{"
                   r"|(input|include|subfile)\s*\{([^}]+)\})")
COMMENT = re.compile(r"(?<!\\)%.*")
MAX_DEPTH = 20


def _title(text: str, start: int) -> tuple[str, int]:
    """Text of the {…} group whose "{" is just before `start`, and the index after it."""
    depth = 1
    i = start
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1], i


def clean_title(title: str) -> str:
    """'Estat de l\\textquotesingle{}art~\\textbf{x}' -> readable text for the outline."""
    raw = title
    title = re.sub(r"\\(?:label|index|footnote)\{[^{}]*\}", "", title)
    title = re.sub(r"\\[A-Za-z@]+\*?\s*(?:\[[^\]]*\])?", "", title)  # drop command names, keep their text
    title = title.replace("~", " ").replace("{", "").replace("}", "").replace("$", "")
    # A title that is only a macro (\chapter*{\TituloResumen}) shows the macro's name.
    return re.sub(r"\s+", " ", title).strip() or raw.strip() or "(untitled)"


def outline(project: Project, overrides: dict[str, str] | None = None) -> list[dict]:
    """[{level, kind, title, file, line}] for the whole document.

    `overrides` maps project paths to text that is newer than the file on disk
    (unsaved editor buffers). Without a main file every .tex file is read in name order.
    """
    overrides = overrides or {}
    items: list[dict] = []
    seen: set[str] = set()

    def read(rel: str) -> str | None:
        if rel in overrides:
            return overrides[rel]
        try:
            data = project.read_file(rel)
        except Exception:  # missing or outside the project: \input of a file we can't show
            return None
        return data["text"] if data.get("kind") == "text" else None

    def walk(rel: str, depth: int):
        if rel in seen or depth > MAX_DEPTH:
            return
        seen.add(rel)
        text = read(rel)
        if text is None:
            return
        code = COMMENT.sub(lambda m: " " * len(m.group(0)), text)  # same offsets, comments blanked
        for m in TOKEN.finditer(code):
            if m.group(1):
                title, _ = _title(code, m.end())
                items.append({"level": LEVELS[m.group(1)], "kind": m.group(1), "title": clean_title(title),
                              "file": rel, "line": code.count("\n", 0, m.start()) + 1})
            else:
                target = m.group(3).strip()
                if not target.lower().endswith(".tex"):
                    target += ".tex"
                walk(target, depth + 1)

    main = project.main_file
    if main:
        walk(main, 0)
    else:
        for path in iter_project_files(project.root):
            if path.suffix.lower() == ".tex":
                walk(project.rel(path), 0)
    return items
