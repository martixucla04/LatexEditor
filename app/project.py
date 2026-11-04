"""An open project folder: file access, the file tree and the main-file setting."""

import base64
import json
import re
import shutil
from pathlib import Path, PurePosixPath

from .errors import UserError
from .fsutil import atomic_write_bytes, move_to_trash
from .workspace import HIDDEN_NAMES, INVALID_CHARS, RESERVED, iter_project_files

CONFIG_NAME = ".latexeditor.json"
BUILD_DIR = ".build"

MAX_TEXT_BYTES = 20 * 1024**2
MAX_IMAGE_BYTES = 15 * 1024**2
IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".bmp": "image/bmp", ".webp": "image/webp",
}

MAGIC_ROOT = re.compile(r"^\s*%\s*!\s*TeX\s+root\s*=\s*(.+?)\s*$", re.I | re.M)
DOCUMENTCLASS = re.compile(r"^[^%\n]*\\documentclass", re.M)


def _decode(data: bytes) -> tuple[str, str]:
    """Text and the encoding to save it back with."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "cp1252"


class Project:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise UserError(f"The project folder no longer exists: {self.root}")
        self.config = {}
        try:
            self.config = json.loads((self.root / CONFIG_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not self.main_file:
            main, _ = self.detect_main_file()
            if main:
                self.set_main_file(main)

    # -- paths -------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.root.name

    def path(self, rel: str) -> Path:
        """Absolute path for a project-relative POSIX path, refusing anything outside the project."""
        parts = PurePosixPath(rel.replace("\\", "/")).parts
        if ".." in parts or (parts and parts[0] in HIDDEN_NAMES):
            raise UserError(f"Invalid path: {rel}")
        path = self.root.joinpath(*parts).resolve()
        if path != self.root and self.root not in path.parents:
            raise UserError(f"Invalid path: {rel}")
        return path

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    @property
    def build_dir(self) -> Path:
        return self.root / BUILD_DIR

    # -- config --------------------------------------------------------------

    def _save_config(self) -> None:
        atomic_write_bytes(self.root / CONFIG_NAME, json.dumps(self.config, indent=2).encode("utf-8"))

    @property
    def main_file(self) -> str | None:
        main = self.config.get("main_file")
        return main if main and (self.root / main).is_file() else None

    def set_main_file(self, rel: str) -> None:
        path = self.path(rel)
        if path.suffix.lower() != ".tex" or not path.is_file():
            raise UserError("The main file must be an existing .tex file.")
        self.config["main_file"] = self.rel(path)
        self._save_config()

    @property
    def pdf_path(self) -> Path | None:
        main = self.main_file
        return self.build_dir / (PurePosixPath(main).stem + ".pdf") if main else None

    def detect_main_file(self) -> tuple[str | None, list[str]]:
        """(main file, candidates). Main is None when the choice is ambiguous."""
        tex_files = [p for p in iter_project_files(self.root) if p.suffix.lower() == ".tex"]
        with_class = []
        for path in tex_files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if DOCUMENTCLASS.search(text):
                with_class.append(path)
                continue
            magic = MAGIC_ROOT.search(text[:4096])
            if magic:
                target = (path.parent / magic.group(1).strip()).resolve()
                if target.is_file() and self.root in target.parents:
                    return self.rel(target), []

        if len(with_class) == 1:
            return self.rel(with_class[0]), []
        for path in with_class:
            if path.parent == self.root and path.name.lower() == "main.tex":
                return self.rel(path), []
        # Shallow files first: the main file is usually at the top level.
        candidates = sorted((self.rel(p) for p in with_class), key=lambda r: (r.count("/"), r.lower()))
        return None, candidates

    # -- tree ----------------------------------------------------------------

    def tree(self, folder: Path | None = None) -> list[dict]:
        folder = folder or self.root
        entries = []
        for path in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if path.name in HIDDEN_NAMES or path.name.startswith(".importing-"):
                continue
            node = {"name": path.name, "path": self.rel(path), "type": "dir" if path.is_dir() else "file"}
            if path.is_dir():
                node["children"] = self.tree(path)
            entries.append(node)
        return entries

    # -- files ---------------------------------------------------------------

    def read_file(self, rel: str) -> dict:
        path = self.path(rel)
        if not path.is_file():
            raise UserError(f"File not found: {rel}")
        size = path.stat().st_size
        mime = IMAGE_TYPES.get(path.suffix.lower())
        if mime:
            if size > MAX_IMAGE_BYTES:
                return {"kind": "binary", "size": size}
            data = base64.b64encode(path.read_bytes()).decode()
            return {"kind": "image", "url": f"data:{mime};base64,{data}", "size": size}
        if size > MAX_TEXT_BYTES:
            return {"kind": "binary", "size": size}
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            return {"kind": "binary", "size": size}
        text, encoding = _decode(data)
        return {"kind": "text", "text": text, "encoding": encoding, "size": size}

    def write_file(self, rel: str, text: str, encoding: str = "utf-8") -> str:
        """Save text; returns the encoding used (falls back to UTF-8 if needed)."""
        path = self.path(rel)
        try:
            data = text.encode(encoding)
        except (UnicodeEncodeError, LookupError):
            encoding = "utf-8"
            data = text.encode(encoding)
        atomic_write_bytes(path, data)
        return encoding

    def _check_new_name(self, name: str) -> str:
        name = name.strip()
        if not name or name in (".", "..") or "/" in name or "\\" in name \
                or INVALID_CHARS.search(name) or RESERVED.match(name) or name in HIDDEN_NAMES:
            raise UserError(f"Invalid name: {name!r}")
        return name

    def _new_path(self, parent_rel: str, name: str) -> Path:
        parent = self.path(parent_rel)
        if not parent.is_dir():
            raise UserError(f"Folder not found: {parent_rel}")
        path = parent / self._check_new_name(name)
        if path.exists():
            raise UserError(f"'{name}' already exists.")
        return path

    def create_file(self, parent_rel: str, name: str) -> str:
        path = self._new_path(parent_rel, name)
        path.write_bytes(b"")
        return self.rel(path)

    def create_folder(self, parent_rel: str, name: str) -> str:
        path = self._new_path(parent_rel, name)
        path.mkdir()
        return self.rel(path)

    def rename(self, rel: str, new_name: str) -> str:
        path = self.path(rel)
        if path == self.root or not path.exists():
            raise UserError(f"Cannot rename {rel}")
        target = path.with_name(self._check_new_name(new_name))
        if target.exists() and target.name.lower() != path.name.lower():
            raise UserError(f"'{new_name}' already exists.")
        path.rename(target)
        new_rel = self.rel(target)
        main = self.config.get("main_file")
        if main and (main == rel or main.startswith(rel + "/")):
            self.config["main_file"] = new_rel + main[len(rel):]
            self._save_config()
        return new_rel

    def delete(self, rel: str) -> None:
        path = self.path(rel)
        if path == self.root or not path.exists():
            raise UserError(f"Cannot delete {rel}")
        move_to_trash(path)

    def add_files(self, parent_rel: str, sources: list[str]) -> list[str]:
        """Copy files from elsewhere on disk into a project folder."""
        parent = self.path(parent_rel)
        added = []
        for src in map(Path, sources):
            target = parent / src.name
            n = 2
            while target.exists():
                target = parent / f"{src.stem} ({n}){src.suffix}"
                n += 1
            shutil.copy2(src, target)
            added.append(self.rel(target))
        return added

    def info(self) -> dict:
        main, candidates = (self.main_file, []) if self.main_file else self.detect_main_file()
        pdf = self.pdf_path
        return {
            "name": self.name,
            "root": str(self.root),
            "main_file": main,
            "main_candidates": candidates,
            "tree": self.tree(),
            "has_pdf": bool(pdf and pdf.is_file()),
        }
