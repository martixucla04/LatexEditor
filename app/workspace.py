"""Importing project .zip files into the workspace and exporting them again."""

import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .errors import UserError

# App-owned entries inside a project folder: never shown in the tree or exported.
HIDDEN_NAMES = {".build", ".latexeditor.json", ".git"}

JUNK_DIRS = {"__MACOSX"}
JUNK_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

MAX_FILES = 20_000
MAX_TOTAL_BYTES = 1024**3  # 1 GiB uncompressed

INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.I)


def safe_folder_name(name: str) -> str:
    name = INVALID_CHARS.sub("_", name).strip(" .")
    return name or "project"


def unique_dir(parent: Path, name: str) -> Path:
    candidate = parent / name
    n = 2
    while candidate.exists():
        candidate = parent / f"{name} ({n})"
        n += 1
    return candidate


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _zip_members(zf: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, tuple[str, ...]]]:
    """Validated (info, path parts) for every file worth extracting."""
    members = []
    total = 0
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir() or _is_symlink(info):
            continue
        parts = PurePosixPath(name).parts
        if not parts or any(p in JUNK_DIRS for p in parts) or parts[-1] in JUNK_FILES or parts[-1].startswith("._"):
            continue
        if name.startswith("/") or ".." in parts or any(INVALID_CHARS.search(p) or RESERVED.match(p) for p in parts):
            raise UserError(f"The .zip contains an unsafe or invalid path: {info.filename}")
        total += info.file_size
        members.append((info, parts))

    if not members:
        raise UserError("The .zip file does not contain any files.")
    if len(members) > MAX_FILES:
        raise UserError(f"The .zip has too many files ({len(members)}; limit {MAX_FILES}).")
    if total > MAX_TOTAL_BYTES:
        raise UserError(f"The .zip is too large when extracted ({total / 1024**2:.0f} MB; limit 1024 MB).")
    return members


def import_zip(zip_path: Path, workspace: Path) -> Path:
    """Extract a project .zip into a new folder in the workspace and return it.

    A single top-level folder inside the zip is unwrapped, so both
    "paper.zip/main.tex" and "paper.zip/paper/main.tex" give the same layout.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UserError(f"Could not open {zip_path.name}: {exc}") from exc

    with zf:
        members = _zip_members(zf)
        tops = {parts[0] for _, parts in members}
        strip = 1 if len(tops) == 1 and all(len(parts) > 1 for _, parts in members) else 0

        workspace.mkdir(parents=True, exist_ok=True)
        staging = workspace / f".importing-{uuid.uuid4().hex[:8]}"
        staging.mkdir()
        try:
            for info, parts in members:
                target = staging.joinpath(*parts[strip:])
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            dest = unique_dir(workspace, safe_folder_name(zip_path.stem))
            staging.rename(dest)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise UserError(f"The .zip file is damaged: {exc}") from exc
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return dest


def check_link_folder(folder: Path) -> Path:
    """Validate a folder the user wants to open in place (no copy); returns it resolved.

    It must exist, must not be a whole drive and must hold at least one .tex
    file without being so large that the file tree would be unusable.
    """
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise UserError(f"Folder not found: {folder}")
    if folder.parent == folder:
        raise UserError(f"Choose the project folder, not the whole drive {folder}.")
    count = 0
    has_tex = False
    for path in iter_project_files(folder):
        count += 1
        has_tex = has_tex or path.suffix.lower() == ".tex"
        if count > MAX_FILES:
            raise UserError(f"{folder.name} has more than {MAX_FILES} files. Choose the folder of one LaTeX project.")
    if not has_tex:
        raise UserError(f"No .tex file was found in {folder}. Choose the folder that contains your LaTeX project.")
    return folder


def iter_project_files(root: Path):
    """All files in a project, skipping app-owned entries, in a stable order."""
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if path.name in HIDDEN_NAMES or path.name.startswith(".importing-"):
            continue
        if path.is_dir():
            yield from iter_project_files(path)
        elif path.is_file():
            yield path


def export_zip(root: Path, dest: Path, pdf: Path | None = None) -> int:
    """Write the project sources (plus optionally the PDF) to `dest`. Returns the file count."""
    tmp = dest.with_name(dest.name + ".part")
    count = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in iter_project_files(root):
            if path.resolve() in (dest.resolve(), tmp.resolve()):
                continue
            zf.write(path, path.relative_to(root).as_posix())
            count += 1
        if pdf is not None and pdf.is_file():
            zf.write(pdf, pdf.name)
            count += 1
    tmp.replace(dest)
    return count
