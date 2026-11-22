"""Error report of the last build, written to be pasted into a chat with an AI assistant.

Markdown with what the assistant needs to answer without asking back: the engine, the
main file, each error with its message, file and line, the source lines around it and
TeX's context line, the warnings in short, and the part of the log where each error is.
"""

from .errors import UserError
from .logparser import BANG_ERROR, FILE_LINE_ERROR, SKIP_ERRORS, unwrap
from .project import Project

MAX_ERRORS = 10
MAX_WARNINGS = 25
SOURCE_LINES = 3  # before and after the error line
LOG_LINES = 8  # from each error in the log
MAX_LOG_LINES = 80


def _source(project: Project, rel: str, line: int) -> str:
    try:
        data = project.read_file(rel)
    except (UserError, OSError):  # renamed/deleted since the build: report without it
        return ""
    if data.get("kind") != "text":
        return ""
    lines = data["text"].splitlines()
    if not 1 <= line <= len(lines):
        return ""
    first, last = max(1, line - SOURCE_LINES), min(len(lines), line + SOURCE_LINES)
    width = len(str(last))
    return "\n".join(f"{'>' if n == line else ' '} {n:>{width}} | {lines[n - 1]}" for n in range(first, last + 1))


def _log_excerpt(log: str) -> str:
    """The lines of each error in the LaTeX log ("! …" or "file:line: …") and the few after it."""
    lines = [line.rstrip() for line in unwrap(log)]
    out, taken = [], set()
    for i, line in enumerate(lines):
        if not (BANG_ERROR.match(line) or FILE_LINE_ERROR.match(line)) or i in taken:
            continue
        if any(skip in line for skip in SKIP_ERRORS):  # follow-ups of the real error
            continue
        block = [n for n in range(i, min(len(lines), i + LOG_LINES)) if n not in taken]
        if out:
            out.append("...")
        out += [lines[n] for n in block]
        taken.update(block)
        if len(out) >= MAX_LOG_LINES:
            break
    return "\n".join(out[:MAX_LOG_LINES])


def _where(p: dict) -> str:
    if p.get("file"):
        return f"{p['file']}, line {p['line']}" if p.get("line") else p["file"]
    if p.get("external"):
        return f"{p['external']} (outside the project)"
    return p.get("source") or ""


def error_report(project: Project, problems: list[dict], engine: str | None = None) -> str:
    """Markdown report of the errors and warnings in `problems` (as the Problems panel has them)."""
    errors = [p for p in problems if p.get("severity") == "error"]
    warnings = [p for p in problems if p.get("severity") == "warning"]
    if not errors and not warnings:
        return ""
    main = project.main_file or "(not set)"
    out = [
        f"I'm compiling a LaTeX document with {engine or 'LaTeX'} (main file: {main}) "
        + ("and it gives these errors. Please explain what is wrong and how to fix each one."
           if errors else "and it gives these warnings. Please explain what they mean and how to fix them."),
    ]

    for n, p in enumerate(errors[:MAX_ERRORS], 1):
        out += ["", f"## Error {n}: {p.get('message', '').strip()}"]
        where = _where(p)
        if where:
            out.append(f"Where: {where}")
        if p.get("source") and p["source"] != "latex":
            out.append(f"Reported by: {p['source']}")
        code = _source(project, p["file"], p["line"]) if p.get("file") and p.get("line") else ""
        if code:
            out += ["```latex", code, "```"]
        if p.get("context"):
            out.append(f"TeX stopped here: `{p['context'].strip()}`")
    if len(errors) > MAX_ERRORS:
        out += ["", f"({len(errors) - MAX_ERRORS} more errors not listed.)"]

    if warnings:
        out += ["", f"## Warnings ({len(warnings)})"]
        for p in warnings[:MAX_WARNINGS]:
            where = _where(p)
            out.append(f"- {p.get('message', '').strip()}" + (f" ({where})" if where else ""))
        if len(warnings) > MAX_WARNINGS:
            out.append(f"- … and {len(warnings) - MAX_WARNINGS} more")

    pdf = project.pdf_path
    try:
        log = pdf.with_suffix(".log").read_text(encoding="utf-8", errors="replace") if pdf else ""
    except OSError:
        log = ""
    excerpt = _log_excerpt(log) if errors else ""
    if excerpt:
        out += ["", "## From the LaTeX log", "```", excerpt, "```"]
    return "\n".join(out) + "\n"
