"""Images pasted into a document: where to save them, their names and labels, and saving.

The image itself (crop, trimmed margins, background) is edited in the page; Python
only chooses names that are free and writes the PNG inside the project.
"""

import base64
import re
import unicodedata
from collections import Counter
from pathlib import PurePosixPath

from .completions import LABEL
from .errors import UserError
from .project import Project
from .workspace import iter_project_files

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
INCLUDEGRAPHICS = re.compile(r"^[^%\n]*\\includegraphics\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", re.M)
MAX_SLUG = 40


def slug(text: str, fallback: str = "figura") -> str:
    """'Arquitectura isoSPI (Font: \\cite{x})' -> 'arquitectura-isospi'."""
    text = re.sub(r"\\[A-Za-z@]+\*?(\{[^{}]*\})?", " ", text)  # drop commands with their argument
    text = re.sub(r"\(.*?\)|\$.*?\$", " ", text)
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", ascii_text)
    out = ""
    for word in words:
        if len(out) + len(word) + 1 > MAX_SLUG:
            break
        out = f"{out}-{word}" if out else word
    return out or fallback


def image_folders(project: Project, current_text: str = "") -> dict:
    """{folders, default}: project folders holding images (sorted), and the one to suggest:
    the folder of the last \\includegraphics in the current file, else the one with most
    images, else Imagenes/ if it exists, else figures/ (created on save)."""
    counts = Counter()
    for path in iter_project_files(project.root):
        if path.suffix.lower() in IMAGE_EXTS:
            counts[project.rel(path.parent) if path.parent != project.root else ""] += 1
    folders = sorted(counts)

    default = None
    used = INCLUDEGRAPHICS.findall(current_text or "")
    if used:
        parent = PurePosixPath(used[-1].strip()).parent.as_posix()
        default = "" if parent == "." else parent
    if default is None and counts:
        default = counts.most_common(1)[0][0]
    if default is None:
        default = "Imagenes" if (project.root / "Imagenes").is_dir() else "figures"
    if default not in folders:
        folders.append(default)
    return {"folders": folders, "default": default}


def _labels(project: Project) -> set[str]:
    labels = set()
    for path in iter_project_files(project.root):
        if path.suffix.lower() == ".tex":
            try:
                labels.update(LABEL.findall(path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return labels


def unique_label(label: str, taken: set[str]) -> str:
    if label not in taken:
        return label
    for suffix in "bcdefghijklmnopqrstuvwxyz":
        if label + suffix not in taken:
            return label + suffix
    n = 2
    while f"{label}-{n}" in taken:
        n += 1
    return f"{label}-{n}"


def _free_name(folder_path, name: str) -> str:
    stem, suffix = PurePosixPath(name).stem, PurePosixPath(name).suffix
    candidate, n = name, 2
    while (folder_path / candidate).exists():
        candidate = f"{stem}-{n}{suffix}"
        n += 1
    return candidate


def figure_names(project: Project, folder: str, caption: str, prefix: str = "fig") -> dict:
    """{file, label}: a free file name in `folder` and a free label for a figure captioned `caption`."""
    base = slug(caption)
    folder_path = project.path(folder) if folder else project.root
    return {"file": _free_name(folder_path, base + ".png"),
            "label": unique_label(f"{prefix}:{base}", _labels(project))}


def save_image(project: Project, folder: str, name: str, data_b64: str) -> str:
    """Write PNG data (base64) as `folder/name` in the project; returns its project-relative path.
    The name gets a number if that file already exists."""
    try:
        data = base64.b64decode(data_b64.split(",", 1)[-1], validate=True)
    except ValueError as exc:
        raise UserError("The image data could not be read.") from exc
    if not data.startswith(PNG_SIGNATURE):
        raise UserError("Only PNG images can be saved.")
    name = project._check_new_name(name if name.lower().endswith(".png") else name + ".png")
    folder_path = project.path(folder) if folder else project.root
    if folder_path.exists() and not folder_path.is_dir():
        raise UserError(f"{folder} is not a folder.")
    folder_path.mkdir(parents=True, exist_ok=True)
    target = folder_path / _free_name(folder_path, name)
    target.write_bytes(data)
    return project.rel(target)
