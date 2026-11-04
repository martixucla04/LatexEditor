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
