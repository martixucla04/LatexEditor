"""Wrappers around the `synctex` command-line tool (forward and inverse search).

Coordinates are PDF points (1/72 in) measured from the top-left of the page,
which is what synctex uses. Commands run from the project root with the PDF
given relative to it, matching how the build ran, so the "./file.tex" names
recorded in .synctex.gz resolve.
"""

import re
import subprocess
from pathlib import Path, PurePosixPath

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TIMEOUT_S = 15


def _run(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(["synctex", *args], cwd=cwd, capture_output=True, timeout=TIMEOUT_S,
                              stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.decode("utf-8", errors="replace")


def _records(output: str) -> list[dict]:
    """Split "SyncTeX result" output into one dict per record (a record starts at Page:/Input:)."""
    records, current = [], None
    for line in output.splitlines():
        key, sep, value = line.partition(":")
        if not sep or key not in ("Output", "Page", "x", "y", "h", "v", "W", "H", "Input", "Line", "Column"):
            continue
        if key in ("Page", "Input") or current is None:
            current = {}
            records.append(current)
        current[key] = value.strip()
    return records


def forward(root: Path, pdf_rel: str, file_rel: str, line: int, column: int = 1) -> list[dict]:
    """Boxes in the PDF for a source line: [{page, x, y, w, h}] (top-left origin, points)."""
    out = _run(["view", "-i", f"{line}:{max(column, 0)}:{file_rel}", "-o", pdf_rel], root)
    boxes, seen = [], set()
    for rec in _records(out):
        try:
            page, h, v = int(rec["Page"]), float(rec["h"]), float(rec["v"])
            w, height = float(rec.get("W", 0)), float(rec.get("H", 0))
        except (KeyError, ValueError):
            continue
        box = {"page": page, "x": round(h, 2), "y": round(v - height, 2), "w": round(w, 2), "h": round(height, 2)}
        key = tuple(box.values())
        if key not in seen:
            seen.add(key)
            boxes.append(box)
    return boxes


def _to_project_path(root: Path, raw: str) -> str | None:
    """Project-relative POSIX path for an "Input:" path, or None if outside the project."""
    raw = raw.replace("\\", "/")
    # synctex prints "<root>/./<relative path as TeX opened it>"
    marker = raw.rfind("/./")
    rel = raw[marker + 3:] if marker >= 0 else None
    if rel is None:
        try:
            rel = Path(raw).resolve().relative_to(Path(root).resolve()).as_posix()
        except (ValueError, OSError):
            return None
    rel = PurePosixPath(re.sub(r"^(\./)+", "", rel)).as_posix()
    if ".." in PurePosixPath(rel).parts or not (Path(root) / rel).is_file():
        return None
    return rel


def inverse(root: Path, pdf_rel: str, page: int, x: float, y: float) -> dict | None:
    """Source location for a point on a PDF page: {file, line}, or None."""
    out = _run(["edit", "-o", f"{page}:{x:.2f}:{y:.2f}:{pdf_rel}"], root)
    for rec in _records(out):
        try:
            line = int(rec["Line"])
        except (KeyError, ValueError):
            continue
        file = _to_project_path(root, rec.get("Input", ""))
        if file and line > 0:
            return {"file": file, "line": line}
    return None


# -- every source line at once (for the outline), read straight from .synctex.gz --

# A line box, glue, kern or math record: type, input tag, line[, column]: h, v[: W, H, D].
# Vertical boxes ([, v) are left out: a tall one's top can be far above the line.
RECORD = re.compile(r"^[\(hxkg$](\d+),(\d+)(?:,-?\d+)?:(-?\d+),(-?\d+)(?::(-?\d+),(-?\d+))?")
SP_TO_BP = 72 / 72.27 / 65536  # TeX scaled points -> PDF points
HEADER_BAND_BP = 50  # running heads sit above this; headings in the text never do
_line_cache: dict[str, tuple[float, dict]] = {}


def line_positions(root: Path, synctex_path: Path) -> dict[tuple[str, int], tuple[int, float]]:
    """{(project file, line): (page, y)} for every source line that produced output.

    y is the top of the line's highest box in PDF points from the top of the page. A line
    with output on several pages counts on the last one (see below). Cached until the
    .synctex.gz changes.
    """
    import gzip

    key = str(synctex_path)
    try:
        mtime = synctex_path.stat().st_mtime
    except OSError:
        return {}
    if key in _line_cache and _line_cache[key][0] == mtime:
        return _line_cache[key][1]

    inputs: dict[str, str | None] = {}
    # (file, line) -> {page: [records below the header band, their min y, all records, min y]}
    seen: dict[tuple[str, int], dict[int, list]] = {}
    page = 0
    unit, mag = 1.0, 1000.0
    header_sp = None  # top band where running heads repeat section titles (credited to their \section line)
    try:
        with gzip.open(synctex_path, "rt", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                head = raw[:1]
                if head == "{":
                    page = int(raw[1:] or 0)
                elif head == "I" and raw.startswith("Input:"):
                    tag, _, path = raw[6:].rstrip("\n").partition(":")
                    inputs[tag] = _to_project_path(root, path)
                elif head == "U" and raw.startswith("Unit:"):
                    unit = float(raw[5:])
                elif head == "M" and raw.startswith("Magnification:"):
                    mag = float(raw[14:]) or 1000.0
                elif page and head in "(hxkg$":
                    m = RECORD.match(raw)
                    if not m:
                        continue
                    file = inputs.get(m.group(1))
                    if not file:
                        continue
                    h, v = int(m.group(3)), int(m.group(4)) - int(m.group(6) or 0)  # baseline - height = top
                    if h <= 0 or v <= 0:
                        continue  # boxes at the page origin (unplaced marks and the like)
                    if header_sp is None:
                        header_sp = HEADER_BAND_BP / (SP_TO_BP * unit * mag / 1000)
                    stats = seen.setdefault((file, int(m.group(2))), {}).setdefault(page, [0, None, 0, v])
                    if v >= header_sp:
                        stats[0] += 1
                        stats[1] = v if stats[1] is None else min(stats[1], v)
                    stats[2] += 1
                    stats[3] = min(stats[3], v)
    except (OSError, EOFError, ValueError):
        return {}

    scale = SP_TO_BP * unit * mag / 1000
    result = {}
    for loc, pages in seen.items():
        # The last page: a \chapter (or any line where a page break happens) also gets the frame
        # of the page shipped out before it. Header-band records only count if that is all there is.
        body = [p for p, s in pages.items() if s[0]]
        best = max(body or pages)
        result[loc] = (best, round(pages[best][1 if body else 3] * scale, 2))
    _line_cache[key] = (mtime, result)
    return result
