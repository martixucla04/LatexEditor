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

# --- word count -------------------------------------------------------------------
# Not text: bodies of these environments, math, and commands whose arguments are names,
# keys, paths or sizes. Arguments of every other command (\textbf, \footnote, \caption,
# custom macros) are counted as text.
SKIP_ENVS = ("verbatim", "lstlisting", "minted", "comment", "thebibliography", "equation", "align",
             "gather", "multline", "eqnarray", "flalign", "alignat", "displaymath", "math", "tikzpicture")
SKIP_ENV = re.compile(r"\\begin\{(" + "|".join(SKIP_ENVS) + r")\*?\}.*?\\end\{\1\*?\}", re.S)
MATH = re.compile(r"\$\$.*?\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]", re.S)
ARG = r"(?:\s*\[[^\]]*\]|\s*\{[^{}]*\})*"
NON_TEXT_COMMANDS = re.compile(
    r"\\(?:label|ref|eqref|pageref|autoref|[cC]ref|cite\w*|nocite|includegraphics|input|include|subfile"
    r"|usepackage|documentclass|begin|end|url|bibliography|bibliographystyle|addbibresource"
    r"|printbibliography|newcommand|renewcommand|providecommand|setlength|addtolength|vspace|hspace"
    r"|graphicspath|pagestyle|thispagestyle|pagenumbering|setcounter|addtocounter|hypersetup|color"
    r"|definecolor|lstset|lstinputlisting|includepdf)\*?" + ARG)
HREF_URL = re.compile(r"\\href\s*\{[^{}]*\}")
COMMAND = re.compile(r"\\[A-Za-z@]+\*?(?:\s*\[[^\]]*\])?|\\.")
# letters/digits, joined by apostrophes, the Catalan middle dot, hyphens or decimal points/commas
WORD = re.compile(r"[^\W_]+(?:(?:['’·.\-]|(?<=\d),(?=\d))[^\W_]+)*")


def count_words(latex: str) -> int:
    """Words of running text in a piece of LaTeX (comments already removed)."""
    text = SKIP_ENV.sub(" ", latex)
    text = MATH.sub(" ", text)
    text = HREF_URL.sub(" ", text)
    text = NON_TEXT_COMMANDS.sub(" ", text)
    text = COMMAND.sub(" ", text)
    return len(WORD.findall(text))


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


BEGIN_DOCUMENT = re.compile(r"\\begin\{document\}")
END_DOCUMENT = re.compile(r"\\end\{document\}")


def outline(project: Project, overrides: dict[str, str] | None = None, totals: dict | None = None) -> list[dict]:
    """[{level, kind, title, file, line, words}] for the whole document.

    `words` counts the heading's title and text up to the next heading, subsections
    included; only text between \\begin{document} and \\end{document} counts. If given,
    `totals["words"]` gets the words of the whole document (text before the first heading too).
    `overrides` maps project paths to text that is newer than the file on disk
    (unsaved editor buffers). Without a main file every .tex file is read in name order.
    """
    overrides = overrides or {}
    items: list[dict] = []
    seen: set[str] = set()
    own = {"front": 0}  # words before the first heading

    def add_words(segment: str):
        n = count_words(segment)
        if items:
            items[-1]["own"] += n
        else:
            own["front"] += n

    def read(rel: str) -> str | None:
        if rel in overrides:
            return overrides[rel]
        try:
            data = project.read_file(rel)
        except Exception:  # missing or outside the project: \input of a file we can't show
            return None
        return data["text"] if data.get("kind") == "text" else None

    def walk(rel: str, depth: int, counting: bool):
        """Read `rel`; `counting` = this text is inside the document body (else the preamble)."""
        if rel in seen or depth > MAX_DEPTH:
            return
        seen.add(rel)
        text = read(rel)
        if text is None:
            return
        code = COMMENT.sub(lambda m: " " * len(m.group(0)), text)  # same offsets, comments blanked
        # The file holding \begin{document} counts only from there to \end{document}.
        begin = BEGIN_DOCUMENT.search(code)
        end = END_DOCUMENT.search(code)
        body_start = begin.end() if begin else (0 if counting else len(code))
        body_end = end.start() if end else len(code)

        def count(a: int, b: int):
            a, b = max(a, body_start), min(b, body_end)
            if a < b:
                add_words(code[a:b])

        pos = 0
        for m in TOKEN.finditer(code):
            count(pos, m.start())
            if m.group(1):
                title, after = _title(code, m.end())
                items.append({"level": LEVELS[m.group(1)], "kind": m.group(1), "title": clean_title(title),
                              "file": rel, "line": code.count("\n", 0, m.start()) + 1, "own": 0})
                count(m.end(), after - 1)  # the title's words
                pos = after
            else:
                target = m.group(3).strip()
                if not target.lower().endswith(".tex"):
                    target += ".tex"
                walk(target, depth + 1, body_start <= m.start() < body_end)
                pos = m.end()
        count(pos, len(code))

    main = project.main_file
    if main:
        walk(main, 0, False)
    else:
        for path in iter_project_files(project.root):
            if path.suffix.lower() == ".tex":
                walk(project.rel(path), 0, False)

    # A heading's words include its subsections'.
    for i, item in enumerate(items):
        words = item["own"]
        for later in items[i + 1:]:
            if later["level"] <= item["level"]:
                break
            words += later["own"]
        item["words"] = words
    if totals is not None:
        totals["words"] = own["front"] + sum(item["own"] for item in items)
    for item in items:
        del item["own"]
    return items
