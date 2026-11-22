"""Python functions exposed to the web UI as window.pywebview.api.*

pywebview exposes every public method and walks public attributes, so internal
state is kept in underscore-prefixed attributes. Each call runs in its own
thread; exceptions reject the JS promise (UserError messages are shown as-is).
"""

import json
import platform
import shutil
import subprocess
import sys
import threading
from importlib.metadata import version
from pathlib import Path

import webview

from . import __version__, outline, references, reftypes, search, synctex
from .builder import Builder, BuildResult
from .completions import scan_project
from .errors import UserError
from .fsutil import reveal_in_explorer
from .logparser import collect_problems
from .pdfserver import PdfServer
from .project import Project
from .settings import Settings
from .workspace import check_link_folder, export_zip, import_zip


def detect_engine():
    """Return the LuaLaTeX path and version banner, or None if it is not installed."""
    path = shutil.which("lualatex")
    if path is None:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    banner = out.splitlines()[0].strip() if out else "version unknown"
    return {"path": path, "version": banner.removeprefix("This is ").strip()}


def ask_yes_no(title: str, message: str) -> bool:
    """Native Yes/No box; safe to call from the GUI thread (used while closing)."""
    if sys.platform != "win32":
        return True
    import ctypes

    MB_YESNO, MB_ICONWARNING, IDYES = 0x4, 0x30, 6
    return ctypes.windll.user32.MessageBoxW(None, message, title, MB_YESNO | MB_ICONWARNING) == IDYES


class Api:
    def __init__(self, settings: Settings | None = None):
        self._window = None
        self._engine = None
        self._settings = settings or Settings()
        self._project: Project | None = None
        self._dirty = False
        self._pdf_server: PdfServer | None = None
        self._builder: Builder | None = None
        self._builder_lock = threading.Lock()  # guards self._builder
        self._run_lock = threading.Lock()  # one build writes .build at a time

    def _attach(self, window):
        """Called by main.py once the window exists."""
        self._window = window
        window.events.closing += self._on_closing
        window.events.loaded += self._on_loaded

    def _on_loaded(self):
        # Files dragged onto the window: only a Python-side drop handler gets their full paths.
        from webview.dom import DOMEventHandler

        self._window.dom.document.events.drop += DOMEventHandler(self._on_drop, prevent_default=True)

    def _on_drop(self, event):
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if paths:
            folders = [p for p in paths if Path(p).is_dir()]
            self._window.evaluate_js(
                f"window.onFilesDropped && window.onFilesDropped({json.dumps(paths)}, {json.dumps(folders)})"
            )

    def _on_closing(self):
        if self._dirty and not ask_yes_no("LaTeX Editor", "You have unsaved changes. Quit without saving?"):
            return False  # cancels the close
        return True

    def _require_project(self) -> Project:
        if self._project is None:
            raise UserError("No project is open.")
        return self._project

    def _pdfs(self) -> PdfServer:
        if self._pdf_server is None:
            self._pdf_server = PdfServer()
        return self._pdf_server

    def _emit(self, event: dict):
        """Push a build progress event to the page (no-op without a real window)."""
        if self._window is not None:
            self._window.evaluate_js(f"window.onBuildEvent && window.onBuildEvent({json.dumps(event)})")

    def _open(self, root: Path) -> dict:
        self.cancel_build()
        if self._pdf_server:
            self._pdf_server.clear()
        self._project = Project(root)
        self._settings.add_recent(self._project.root, self._project.name)
        if self._window is not None:
            self._window.title = f"{self._project.name} - LaTeX Editor"
        return self._project.info()

    # -- app -------------------------------------------------------------------

    def app_info(self):
        if self._engine is None:
            self._engine = detect_engine() or False
        return {
            "version": __version__,
            "python": platform.python_version(),
            "pywebview": version("pywebview"),
            "engine": self._engine or None,
            "workspace": str(self._settings.workspace),
        }

    def get_preferences(self):
        """{theme, font_size, word_wrap, workspace}"""
        return self._settings.preferences()

    def set_preferences(self, changes: dict):
        try:
            return self._settings.update_preferences(changes or {})
        except OSError as exc:
            raise UserError(f"Could not use that folder: {exc}") from exc

    def choose_workspace_dialog(self):
        """Folder picker for where imported projects are stored; returns the preferences."""
        current = self._settings.preferences()["workspace"]
        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=current)
        if not paths:
            return None
        return self.set_preferences({"workspace": paths[0] if isinstance(paths, (list, tuple)) else paths})

    def set_dirty(self, dirty: bool):
        """The UI reports whether any open file has unsaved changes."""
        self._dirty = bool(dirty)

    # -- projects ----------------------------------------------------------------

    def recent_projects(self):
        return self._recent()

    def remove_recent(self, path: str):
        self._settings.remove_recent(path)
        return self._recent()

    def _recent(self) -> list[dict]:
        """Recent projects; `linked` marks folders opened in place, outside the projects folder."""
        workspace = self._settings.workspace.resolve()
        out = []
        for item in self._settings.recent():
            try:
                linked = not Path(item["path"]).resolve().is_relative_to(workspace)
            except OSError:
                linked = True
            out.append(dict(item, linked=linked))
        return out

    def import_zip_dialog(self):
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("ZIP archives (*.zip)",))
        if not paths:
            return None
        return self.import_zip(paths[0])

    def import_zip(self, zip_path: str):
        return self._open(import_zip(Path(zip_path), self._settings.workspace))

    def link_folder_dialog(self):
        """Folder picker: open an existing LaTeX folder in place, without copying it."""
        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not paths:
            return None
        return self.link_folder(paths[0] if isinstance(paths, (list, tuple)) else paths)

    def link_folder(self, path: str):
        """Open a folder anywhere on disk as the project; edits are saved straight into it."""
        return self._open(check_link_folder(Path(path)))

    def open_project(self, path: str):
        return self._open(Path(path))

    def close_project(self):
        self.cancel_build()
        if self._pdf_server:
            self._pdf_server.clear()
        self._project = None
        if self._window is not None:
            self._window.title = "LaTeX Editor"

    def project_info(self):
        return self._require_project().info()

    def export_zip_dialog(self, include_pdf: bool = False):
        project = self._require_project()
        dest = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=f"{project.name}.zip", file_types=("ZIP archives (*.zip)",)
        )
        if not dest:
            return None
        dest = Path(dest[0] if isinstance(dest, (list, tuple)) else dest)
        if dest.suffix.lower() != ".zip":
            dest = dest.with_name(dest.name + ".zip")
        count = export_zip(project.root, dest, project.pdf_path if include_pdf else None)
        return {"path": str(dest), "count": count}

    def reveal(self, rel: str = ""):
        reveal_in_explorer(self._require_project().path(rel))

    # -- files -------------------------------------------------------------------

    def tree(self):
        return self._require_project().tree()

    def read_file(self, rel: str):
        return self._require_project().read_file(rel)

    def save_file(self, rel: str, text: str, encoding: str = "utf-8"):
        return self._require_project().write_file(rel, text, encoding)

    def create_file(self, parent_rel: str, name: str):
        return self._require_project().create_file(parent_rel, name)

    def create_folder(self, parent_rel: str, name: str):
        return self._require_project().create_folder(parent_rel, name)

    def rename_path(self, rel: str, new_name: str):
        return self._require_project().rename(rel, new_name)

    def delete_path(self, rel: str):
        self._require_project().delete(rel)

    def add_files(self, parent_rel: str, paths: list[str]):
        """Copy files dropped onto the window into a project folder."""
        files = [p for p in paths if Path(p).is_file()]
        return self._require_project().add_files(parent_rel, files)

    def add_files_dialog(self, parent_rel: str = ""):
        project = self._require_project()
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True)
        return project.add_files(parent_rel, list(paths)) if paths else []

    def _synctex_pdf(self) -> tuple[Project, str]:
        project = self._require_project()
        pdf = project.pdf_path
        if pdf is None or not pdf.with_suffix(".synctex.gz").is_file():
            raise UserError("Compile the document first to jump between the source and the PDF.")
        return project, pdf.relative_to(project.root).as_posix()

    def synctex_forward(self, rel: str, line: int, column: int = 1):
        """Where a source line ended up in the PDF: [{page, x, y, w, h}] in PDF points."""
        project, pdf = self._synctex_pdf()
        project.path(rel)  # validates the path
        return synctex.forward(project.root, pdf, rel, int(line), int(column))

    def synctex_inverse(self, page: int, x: float, y: float):
        """Source location of a point in the PDF: {file, line} or None."""
        project, pdf = self._synctex_pdf()
        return synctex.inverse(project.root, pdf, int(page), float(x), float(y))

    def search_project(self, query: str, options: dict | None = None):
        """Find text in project files. options: regex, case, word (bools), include (globs)."""
        o = options or {}
        return search.search(self._require_project(), query, bool(o.get("regex")), bool(o.get("case")),
                             bool(o.get("word")), o.get("include") or search.DEFAULT_INCLUDE)

    def replace_in_project(self, query: str, replacement: str, options: dict | None = None, files=None):
        """Replace all matches in `files` (paths from a search). Returns {files, count}."""
        o = options or {}
        return search.replace(self._require_project(), query, replacement, bool(o.get("regex")),
                              bool(o.get("case")), bool(o.get("word")),
                              o.get("include") or search.DEFAULT_INCLUDE, files)

    def reference_types(self):
        """Reference types and their fields, for the Add reference dialog."""
        return reftypes.types()

    def preview_reference(self, kind: str, fields: dict):
        """Formatted text and a free citation key for the Add reference dialog."""
        project = self._require_project()
        text = reftypes.format_reference(kind, fields)
        key = fields.get("key") or references.suggest_key_for(kind, fields)
        return {"text": text, "key": references.unique_key(key, references.existing_keys(project))}

    def add_reference(self, kind: str, fields: dict):
        """Add a reference to the bibliography (see app/references.py)."""
        return references.add_reference(self._require_project(), kind, fields)

    def spell_settings(self):
        """{language: "en"|"ca"|"es"|"off", words: [project dictionary]}"""
        return self._require_project().spell_settings()

    def set_spell_language(self, language: str):
        return self._require_project().set_spell_language(language)

    def add_spell_word(self, word: str):
        return self._require_project().add_spell_word(word)

    def outline(self, overrides: dict | None = None):
        """Headings of the whole document in reading order; `overrides` = unsaved buffers {path: text}.

        Each heading gets `pdf: {page, y}` (PDF points from the page top) from the last build.
        """
        project = self._require_project()
        items = outline.outline(project, overrides)
        pdf = project.pdf_path
        if pdf is not None:
            where = synctex.line_positions(project.root, pdf.with_suffix(".synctex.gz"))
            for item in items:
                if (item["file"], item["line"]) in where:
                    page, y = where[(item["file"], item["line"])]
                    item["pdf"] = {"page": page, "y": y}
        return items

    def completion_data(self):
        """Labels, bibliography entries, user macros and files for autocomplete."""
        return scan_project(self._require_project().root)

    def set_main_file(self, rel: str):
        project = self._require_project()
        project.set_main_file(rel)
        return project.info()

    # -- building ------------------------------------------------------------------

    def compile(self):
        """Build the main file and return the result (blocks until done).

        Starting a new build cancels the running one; the cancelled call
        returns status "cancelled".
        """
        project = self._require_project()
        main = project.main_file
        if not main:
            raise UserError("No main file is set. Right-click a .tex file and choose \"Set as main file\".")
        if shutil.which("lualatex") is None:
            raise UserError("LuaLaTeX was not found. Install MiKTeX and make sure lualatex is on the PATH.")

        builder = Builder(project.root, main, on_event=self._emit)
        with self._builder_lock:
            previous, self._builder = self._builder, builder
        if previous is not None:
            previous.cancel()
        with self._run_lock:
            if self._builder is not builder:  # superseded while waiting for the previous build
                return BuildResult("cancelled", "Build cancelled").to_dict()
            result = builder.run()
        with self._builder_lock:
            if self._builder is builder:
                self._builder = None

        data = result.to_dict()
        data["pdf_url"] = self._pdfs().publish(Path(result.pdf)) if result.pdf else None
        return data

    def cancel_build(self):
        with self._builder_lock:
            builder = self._builder
        if builder is not None:
            builder.cancel()

    def last_build(self):
        """PDF URL, problems and log left by the previous build of this project (e.g. last session)."""
        project = self._require_project()
        pdf = project.pdf_path
        if pdf is None:
            return {"pdf_url": None, "problems": [], "log": ""}
        log_path = pdf.with_suffix(".log")
        try:
            log = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log = ""
        problems = collect_problems(project.root, project.build_dir, pdf.stem, log)
        return {
            "pdf_url": self._pdfs().publish(pdf) if pdf.is_file() else None,
            "problems": [p.to_dict() for p in problems],
            "log": log,
        }
