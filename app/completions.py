"""Project-wide data for editor autocomplete: labels, bibliography entries,
user-defined commands and environments, and project files.

Scanning is plain regex work over the project's .tex/.sty/.cls and .bib files;
it is fast enough to redo after every save.
"""

import re
import unicodedata
from pathlib import Path

from .workspace import iter_project_files

MAX_FILE_BYTES = 5 * 1024**2

LABEL = re.compile(r"\\label\{([^}\s]+)\}")
NEWCOMMAND = re.compile(
    r"\\(?:new|renew|provide)command\*?\s*\{?\s*(\\[A-Za-z@]+)\s*\}?\s*(?:\[(\d)\])?"
    r"|\\(?:DeclareMathOperator\*?|NewDocumentCommand|DeclareDocumentCommand)\s*\{?\s*(\\[A-Za-z@]+)"
    r"|\\def\s*(\\[A-Za-z@]+)"
)
NEWENVIRONMENT = re.compile(r"\\(?:new|renew)environment\*?\s*\{([A-Za-z*@]+)\}|\\NewDocumentEnvironment\s*\{([A-Za-z*@]+)\}")
BIBITEM = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
BIB_ENTRY = re.compile(r"@\s*([A-Za-z]+)\s*[{(]\s*([^,\s{}()]+)\s*,")
BIB_SKIP_TYPES = {"string", "comment", "preamble"}
BIB_FIELD = re.compile(r"([A-Za-z]+)\s*=\s*")


def _strip_comments(line: str) -> str:
    """Drop a % comment (but not an escaped \\%)."""
    return re.sub(r"(?<!\\)%.*", "", line)


def _read_value(text: str, pos: int) -> tuple[str, int]:
    """Read a BibTeX field value at `pos`: {braced}, "quoted" or a bare word/number."""
    if pos >= len(text):
        return "", pos
    if text[pos] == "{":
        depth, i = 0, pos
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[pos + 1:i], i + 1
            i += 1
        return text[pos + 1:], len(text)
    if text[pos] == '"':
        end = text.find('"', pos + 1)
        end = len(text) if end < 0 else end
        return text[pos + 1:end], end + 1
    m = re.match(r"[^,}\s]+", text[pos:])
    return (m.group(0), pos + m.end()) if m else ("", pos)


ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
           "=": "\u0304", ".": "\u0307", "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b"}
ACCENT = re.compile(r"\\(['`^\"~=.]|[cvuH](?=[\s{]))\s*\{?\s*(?:\\([ij])\b|([A-Za-z]))\s*\}?")
SPECIAL = {r"\ss": "ß", r"\o": "ø", r"\O": "Ø", r"\l": "ł", r"\L": "Ł", r"\ae": "æ", r"\AE": "Æ", r"\aa": "å", r"\AA": "Å"}


def _clean(value: str) -> str:
    """Field value as plain text: LaTeX accents become letters (Garc{\\'i}a -> García)."""
    value = ACCENT.sub(lambda m: unicodedata.normalize("NFC", (m.group(2) or m.group(3)) + ACCENTS[m.group(1)]), value)
    value = re.sub(r"\\(ss|o|O|l|L|ae|AE|aa|AA)\b\s*", lambda m: SPECIAL["\\" + m.group(1)], value)
    value = re.sub(r"\\[A-Za-z]+\s*|[{}]|\\(?=[&%$#_])", "", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_bib(text: str, file: str) -> list[dict]:
    entries = []
    matches = list(BIB_ENTRY.finditer(text))
    for n, m in enumerate(matches):
        kind = m.group(1).lower()
        if kind in BIB_SKIP_TYPES:
            continue
        body_end = matches[n + 1].start() if n + 1 < len(matches) else len(text)
        body = text[m.end():body_end]
        fields = {}
        pos = 0
        while True:
            f = BIB_FIELD.search(body, pos)
            if not f:
                break
            value, pos = _read_value(body, f.end())
            name = f.group(1).lower()
            if name in ("title", "author", "editor", "year", "date", "journal", "journaltitle", "booktitle"):
                fields.setdefault(name, _clean(value))
            pos = max(pos, f.end())
        line = text.count("\n", 0, m.start()) + 1
        year = fields.get("year") or fields.get("date", "")[:4]
        entries.append({
            "key": m.group(2),
            "type": kind,
            "title": fields.get("title", ""),
            "author": fields.get("author") or fields.get("editor", ""),
            "year": year,
            "venue": fields.get("journal") or fields.get("journaltitle") or fields.get("booktitle", ""),
            "file": file,
            "line": line,
        })
    return entries


def scan_tex(text: str, file: str, data: dict) -> None:
    for number, raw in enumerate(text.splitlines(), 1):
        line = _strip_comments(raw)
        if "\\" not in line:
            continue
        for m in LABEL.finditer(line):
            context = line[:m.start()].strip() or line[m.end():].strip()
            data["labels"].append({"name": m.group(1), "file": file, "line": number, "context": context[:120]})
        for m in NEWCOMMAND.finditer(line):
            name = m.group(1) or m.group(3) or m.group(4)
            args = int(m.group(2)) if m.group(2) else 0
            data["commands"].append({"name": name[1:], "args": args, "file": file, "line": number})
        for m in NEWENVIRONMENT.finditer(line):
            data["environments"].append({"name": m.group(1) or m.group(2), "file": file, "line": number})
        # \bibitem{key} text: manual bibliography entries are citable too
        for m in BIBITEM.finditer(line):
            text = re.sub(r"\\url\{([^}]*)\}", r"\1", line[m.end():]).strip()
            data["citations"].append({"key": m.group(1), "type": "bibitem", "title": text[:160], "author": "",
                                      "year": "", "venue": "", "file": file, "line": number})


def scan_project(root: Path) -> dict:
    root = Path(root)
    data = {"labels": [], "citations": [], "commands": [], "environments": [], "files": []}
    for path in iter_project_files(root):
        rel = path.relative_to(root).as_posix()
        data["files"].append(rel)
        suffix = path.suffix.lower()
        if suffix not in (".tex", ".sty", ".cls", ".bib", ".ltx"):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if suffix == ".bib":
            data["citations"].extend(parse_bib(text, rel))
        else:
            scan_tex(text, rel, data)
    return data
