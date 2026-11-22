"""Turn LaTeX logs and biber/BibTeX transcripts into a list of problems.

A problem has a severity ("error", "warning" or "info" for typesetting notes
such as overfull boxes), a message, and where possible a project-relative file
and line so the UI can jump there.

The LaTeX log does not say which file a warning belongs to; TeX only prints
"(./file.tex" when it opens a file and ")" when it closes it. We follow those
parentheses to know the current file, skipping message bodies (which may
contain unbalanced parentheses). MiKTeX wraps log lines at 79 bytes and
ignores max_print_line, so wrapped lines are joined first.
"""

import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

WRAP_WIDTH = 79
# The TeX engines a project can compile with (Problem.source "latex" covers all of them).
LATEX_ENGINES = {"lualatex": "LuaLaTeX", "pdflatex": "pdfLaTeX", "xelatex": "XeLaTeX"}

FILE_LINE_ERROR = re.compile(r"^((?:[A-Za-z]:)?[^:]*?\.\w+):(\d+): (.*)$")
BANG_ERROR = re.compile(r"^! (.*)$")
CONTEXT_LINE = re.compile(r"^l\.(\d+) (.*)$")
WARNING = re.compile(r"^(?:LaTeX|Package (\S+)|Class (\S+)|pdfTeX|LuaTeX)( Font)? Warning: (.*)$")
BADBOX = re.compile(r"^(Overfull|Underfull) \\[hv]box .*")
BADBOX_LINE = re.compile(r"(?:at lines? (\d+)|detected at line (\d+))")
INPUT_LINE = re.compile(r"on input line (\d+)")
MISSING_CHAR = re.compile(r"^Missing character: (.*)$")
FILE_TOKEN = re.compile(r'"([^"]+)"|((?:[A-Za-z]:)?[^\s()"{}<>\[\]]+)')

BIBER_LINE = re.compile(r"^\[\d+\] \S+> (ERROR|WARN) - (.*)$")
BIBER_SOURCE = re.compile(r"INFO - Found BibTeX data source '([^']+)'")
BIBER_TMP_LINE = re.compile(r"BibTeX subsystem: .*?, line (\d+), (.*)$")
BIBTEX_AT_LINE = re.compile(r"^(.*?)-+line (\d+) of file (.+)$")

SKIP_ERRORS = ("Emergency stop", "==> Fatal error occurred")


@dataclass
class Problem:
    severity: str  # "error" | "warning" | "info"
    message: str
    file: str | None = None  # project-relative POSIX path
    line: int | None = None
    source: str = "latex"
    context: str = ""  # source text before the error point (TeX's "l.N ..." line)
    external: str | None = None  # file outside the project (a package), for display only

    def to_dict(self) -> dict:
        return asdict(self)


def unwrap(text: str) -> list[str]:
    """Join lines that TeX broke at exactly WRAP_WIDTH bytes."""
    out, buf = [], ""
    for line in text.splitlines():
        buf += line
        if len(line.encode("utf-8")) == WRAP_WIDTH or len(line) == WRAP_WIDTH:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


class _Locator:
    """Maps paths printed in logs to project-relative paths."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def locate(self, raw: str | None) -> tuple[str | None, str | None]:
        """(project-relative path, external path)"""
        if not raw:
            return None, None
        raw = raw.strip().strip('"')
        path = Path(raw)
        try:
            full = (path if path.is_absolute() else self.root / path).resolve()
            rel = full.relative_to(self.root).as_posix()
        except (ValueError, OSError):
            return None, raw
        if rel.startswith(".build/") or rel == ".build":
            return None, None
        return rel, None


def _looks_like_file(token: str) -> bool:
    return (
        token.startswith(("./", "../", "/", '"'))
        or re.match(r"^[A-Za-z]:[/\\]", token) is not None
        or re.search(r"\.[A-Za-z][\w-]*$", token) is not None
    )


def parse_latex_log(text: str, root: Path) -> list[Problem]:
    locator = _Locator(root)
    lines = unwrap(text)
    stack: list[str | None] = []
    problems: list[Problem] = []

    def current_file():
        for item in reversed(stack):
            if item is not None:
                return item
        return None

    def add(severity, message, raw_file, line, context=""):
        rel, external = locator.locate(raw_file)
        problems.append(Problem(severity, message.strip(), rel, line, "latex", context, external))

    def block_end(start: int) -> int:
        """Index of the blank line ending the message block that starts at `start`."""
        j = start + 1
        while j < len(lines) and lines[j].strip():
            j += 1
        return j

    def context_after(start: int, end: int):
        for j in range(start, min(end + 1, len(lines))):
            m = CONTEXT_LINE.match(lines[j])
            if m:
                return int(m.group(1)), m.group(2)
        return None, ""

    i = 0
    while i < len(lines):
        line = lines[i]

        m = FILE_LINE_ERROR.match(line)
        if m and _looks_like_file(m.group(1)):
            end = block_end(i)
            ctx_line, before = context_after(i, end)
            add("error", m.group(3), m.group(1), int(m.group(2)) or ctx_line, before)
            i = end
            continue

        m = BANG_ERROR.match(line)
        if m:
            end = block_end(i)
            ctx_line, before = context_after(i, end)
            add("error", m.group(1), current_file(), ctx_line, before)
            i = end
            continue

        m = WARNING.match(line)
        if m:
            package = m.group(1) or m.group(2)
            message = m.group(4)
            j = i + 1
            # Package warnings continue on lines starting with "(package)", font warnings with "(Font)".
            prefix = f"({package})" if package else "(Font)" if m.group(3) else None
            while j < len(lines) and lines[j].strip() and (
                (prefix and lines[j].startswith(prefix)) or (not prefix and not lines[j].startswith("("))
            ):
                message += " " + (lines[j][len(prefix):] if prefix and lines[j].startswith(prefix) else lines[j]).strip()
                j += 1
            num = INPUT_LINE.search(message)
            severity = "info" if m.group(3) else "warning"  # font warnings are typesetting notes
            label = f"{package}: " if package else ""
            add(severity, label + message, current_file(), int(num.group(1)) if num else None)
            i = j
            continue

        m = BADBOX.match(line)
        if m:
            num = BADBOX_LINE.search(line)
            add("info", line, current_file(), int(num.group(1) or num.group(2)) if num else None)
            i = block_end(i)
            continue

        m = MISSING_CHAR.match(line)
        if m:
            add("warning", line, current_file(), None)
            i += 1
            continue

        # Not a message: follow file opens "(path" and closes ")".
        k = 0
        while k < len(line):
            ch = line[k]
            if ch == "(":
                tok = FILE_TOKEN.match(line, k + 1)
                name = tok and (tok.group(1) or tok.group(2))
                if name and _looks_like_file(tok.group(0)):
                    stack.append(name)
                    k = tok.end()
                    continue
                stack.append(None)
            elif ch == ")" and stack:
                stack.pop()
            k += 1
        i += 1

    errors = [p for p in problems if p.severity == "error"]
    if any(not p.message.startswith(SKIP_ERRORS) for p in errors):
        problems = [p for p in problems if not (p.severity == "error" and p.message.startswith(SKIP_ERRORS))]
    return _dedupe(problems)


def parse_biber_blg(text: str, root: Path) -> list[Problem]:
    locator = _Locator(root)
    problems = []
    source = None
    for line in text.splitlines():
        m = BIBER_SOURCE.search(line)
        if m:
            source = m.group(1)
            continue
        m = BIBER_LINE.match(line)
        if not m:
            continue
        severity = "error" if m.group(1) == "ERROR" else "warning"
        message = m.group(2)
        file, lineno = None, None
        tmp = BIBER_TMP_LINE.search(message)
        if tmp:
            # biber reports a temp copy of the .bib; the data source seen last is the real file
            lineno = int(tmp.group(1))
            file = source
            message = f"{PurePosixPath(source).name if source else 'bibliography'}: {tmp.group(2)}"
        rel, external = locator.locate(file)
        problems.append(Problem(severity, message, rel, lineno, "biber", external=external))
    return _dedupe(problems)


def parse_bibtex_blg(text: str, root: Path) -> list[Problem]:
    locator = _Locator(root)
    problems = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Warning--"):
            problems.append(Problem("warning", line[len("Warning--"):], source="bibtex"))
            continue
        m = BIBTEX_AT_LINE.match(line)
        if m:
            message = m.group(1).strip() or (lines[i - 1].strip() if i else "BibTeX error")
            if message.startswith("while executing"):
                continue  # trailer of a warning, points into the .bst style
            rel, external = locator.locate(m.group(3))
            problems.append(Problem("error", message, rel, int(m.group(2)), "bibtex", external=external))
        elif line.startswith("I couldn't open"):
            problems.append(Problem("error", line, source="bibtex"))
    return _dedupe(problems)


def _dedupe(problems: list[Problem]) -> list[Problem]:
    seen, out = set(), []
    for p in problems:
        key = (p.severity, p.message, p.file, p.line)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def collect_problems(root: Path, build_dir: Path, jobname: str, log: str | None = None,
                     steps=()) -> list[Problem]:
    """All problems of the last build: LaTeX log, bibliography transcript, failed tools."""
    root = Path(root)
    if log is None:
        try:
            log = (build_dir / f"{jobname}.log").read_text(encoding="utf-8", errors="replace")
        except OSError:
            log = ""
    problems = parse_latex_log(log, root)

    try:
        blg = (build_dir / f"{jobname}.blg").read_text(encoding="utf-8", errors="replace")
    except OSError:
        blg = ""
    if "biber" in blg[:2000].lower() or BIBER_LINE.search(blg):
        problems += parse_biber_blg(blg, root)
    elif blg.startswith("This is BibTeX"):
        problems += parse_bibtex_blg(blg, root)

    for step in steps:
        if step.tool not in LATEX_ENGINES and step.exit_code not in (0, None) \
                and not any(p.source == step.tool and p.severity == "error" for p in problems):
            problems.append(Problem("error", f"{step.tool} failed (exit code {step.exit_code}). See the Log tab.",
                                    source=step.tool))

    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(problems, key=lambda p: order[p.severity])
