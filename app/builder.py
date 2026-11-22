"""LaTeX build orchestrator (latexmk needs Perl, which MiKTeX setups often lack).

The engine is the project's choice: lualatex (default), pdflatex or xelatex.

One build:
    engine                         always (first run)
    biber   | bibtex               when the bibliography inputs changed
    makeglossaries-lite            when glossary entries changed
    makeindex                      when index entries changed
    engine                         again while the log asks for a rerun (max 5 runs)

Everything is written to <project>/.build. The commands run from the project
root, so \\input, \\includegraphics and .bib paths resolve like on Overleaf.
Hashes of each auxiliary tool's inputs are kept in .build/.latexeditor-build.json
so a typical build is a single LaTeX run.

Shortcuts, based on a size/mtime fingerprint of every project file:
    nothing changed since a clean build   -> no run at all ("Up to date")
    only .bib files changed               -> biber | bibtex, then LaTeX (skips the first run)
LaTeX itself cannot re-typeset just one changed file: page numbers, references and
the table of contents depend on the whole document.
"""

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from .logparser import LATEX_ENGINES, collect_problems
from .project import BUILD_DIR
from .workspace import iter_project_files

STATE_FILE = ".latexeditor-build.json"
MAX_LATEX_RUNS = 5
RUN_TIMEOUT_S = 600
SLOW_RUN_S = 30  # after this, hint that MiKTeX may be waiting on a package-install dialog

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

RERUN = re.compile(
    r"Rerun to get|Please rerun LaTeX|Label\(s\) may have changed|Rerun LaTeX"
    r"|Please \(re\)run Biber|rerunfilecheck.*Rerun|Package glossaries.*rerun",
    re.IGNORECASE,
)
RERUN_BIBER = re.compile(r"Please \(re\)run Biber", re.IGNORECASE)
BIBDATA = re.compile(r"\\bibdata\{([^}]*)\}")
BIBSTYLE = re.compile(r"\\bibstyle\{([^}]*)\}")
CITATION = re.compile(r"\\citation\{([^}]*)\}")
BCF_DATASOURCE = re.compile(r"<bcf:datasource[^>]*>([^<]+)</bcf:datasource>")
GLOSSARY_INPUTS = (".glo", ".acn", ".slo", ".glsdefs")


class BuildCancelled(Exception):
    pass


@dataclass
class Step:
    tool: str
    seconds: float
    exit_code: int
    output: str = ""


@dataclass
class BuildResult:
    status: str  # "success" | "errors" | "failed" | "cancelled"
    message: str
    pdf: str | None = None
    log: str = ""
    duration: float = 0.0
    steps: list[Step] = field(default_factory=list)
    problems: list = field(default_factory=list)  # logparser.Problem

    def to_dict(self) -> dict:
        return asdict(self)


def _hash(*parts: bytes) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(len(part).to_bytes(8, "little"))
        h.update(part)
    return h.hexdigest()


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    else:
        proc.kill()


class Builder:
    """Runs one build. Call run() in a worker thread; cancel() from any thread."""

    def __init__(self, root: Path, main_rel: str, on_event=None, engine: str = "lualatex"):
        self.root = Path(root)
        self.engine = engine if engine in LATEX_ENGINES else "lualatex"
        self.main_rel = main_rel
        self.jobname = PurePosixPath(main_rel).stem
        self.build_dir = self.root / BUILD_DIR
        self.on_event = on_event or (lambda event: None)
        self._cancelled = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.steps: list[Step] = []
        self.latex_runs = 0

    # -- control -------------------------------------------------------------------

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                _kill_tree(self._proc)

    def _out(self, ext: str) -> Path:
        return self.build_dir / f"{self.jobname}{ext}"

    def _run(self, tool: str, args: list[str], cwd: Path) -> Step:
        if self._cancelled.is_set():
            raise BuildCancelled()
        self.on_event({"type": "step", "tool": tool, "run": self.latex_runs})
        start = time.monotonic()
        with self._lock:
            self._proc = subprocess.Popen(
                [tool, *args], cwd=cwd,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        proc = self._proc
        warned = False
        while True:
            try:
                out, _ = proc.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                if self._cancelled.is_set():
                    _kill_tree(proc)
                    proc.communicate()
                    raise BuildCancelled()
                if elapsed > RUN_TIMEOUT_S:
                    _kill_tree(proc)
                    out, _ = proc.communicate()
                    out += f"\n[LaTeX Editor] {tool} stopped after {RUN_TIMEOUT_S} s.".encode()
                    break
                if elapsed > SLOW_RUN_S and not warned:
                    warned = True
                    self.on_event({"type": "slow", "tool": tool})
        with self._lock:
            self._proc = None
        if self._cancelled.is_set():
            raise BuildCancelled()
        step = Step(tool, round(time.monotonic() - start, 2), proc.returncode,
                    out.decode("utf-8", errors="replace")[-20000:])
        self.steps.append(step)
        return step

    # -- tools ---------------------------------------------------------------------

    def _latex(self) -> Step:
        self.latex_runs += 1
        return self._run(self.engine, [
            "-interaction=nonstopmode", "-file-line-error", "-synctex=1",
            f"-output-directory={BUILD_DIR}", f"-jobname={self.jobname}", self.main_rel,
        ], self.root)

    def _bib_files(self, names: list[str]) -> list[bytes]:
        out = []
        for name in names:
            name = name.strip()
            path = self.root / (name if name.endswith(".bib") else name + ".bib")
            out.append(_read(path))
        return out

    def _biber_inputs(self) -> str | None:
        bcf = _read(self._out(".bcf"))
        if not bcf:
            return None
        sources = BCF_DATASOURCE.findall(bcf.decode("utf-8", errors="replace"))
        return _hash(bcf, *self._bib_files(sources))

    def _bibtex_inputs(self) -> str | None:
        aux = _read(self._out(".aux")).decode("utf-8", errors="replace")
        data = BIBDATA.findall(aux)
        if not data:
            return None
        names = [n for group in data for n in group.split(",")]
        keys = "\n".join(sorted(CITATION.findall(aux)) + BIBSTYLE.findall(aux)).encode()
        return _hash(keys, *self._bib_files(names))

    def _glossary_inputs(self) -> str | None:
        files = [self._out(ext) for ext in GLOSSARY_INPUTS if self._out(ext).exists()]
        return _hash(*(_read(f) for f in files)) if files else None

    def _index_inputs(self, ext: str) -> str | None:
        data = _read(self._out(ext))
        return _hash(data) if self._out(ext).exists() else None

    # -- build ---------------------------------------------------------------------

    def _load_state(self) -> dict:
        try:
            return json.loads((self.build_dir / STATE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict) -> None:
        (self.build_dir / STATE_FILE).write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _aux_tools(self, state: dict, log: str) -> bool:
        """Run bibliography/glossary/index tools whose inputs changed. Returns True if any ran."""
        ran = False

        biber = self._biber_inputs()
        bibtex = None if biber else self._bibtex_inputs()
        if biber and (biber != state.get("biber") or not self._out(".bbl").exists() or RERUN_BIBER.search(log)):
            self._run("biber", [f"{BUILD_DIR}/{self.jobname}"], self.root)
            state["biber"] = biber
            ran = True
        elif bibtex and (bibtex != state.get("bibtex") or not self._out(".bbl").exists()):
            # From the project root, bibtex finds \bibdata paths relative to it.
            self._run("bibtex", [f"{BUILD_DIR}/{self.jobname}"], self.root)
            state["bibtex"] = bibtex
            ran = True

        glossaries = self._glossary_inputs()
        if glossaries and glossaries != state.get("glossaries"):
            # makeglossaries-lite cannot change directory, so it runs inside .build
            self._run("makeglossaries-lite", [self.jobname], self.build_dir)
            state["glossaries"] = glossaries
            ran = True

        index = self._index_inputs(".idx")
        if index and (index != state.get("index") or not self._out(".ind").exists()):
            self._run("makeindex", [f"{BUILD_DIR}/{self.jobname}.idx"], self.root)
            state["index"] = index
            ran = True

        nomencl = self._index_inputs(".nlo")
        if nomencl and (nomencl != state.get("nomencl") or not self._out(".nls").exists()):
            self._run("makeindex", [f"{BUILD_DIR}/{self.jobname}.nlo", "-s", "nomencl.ist",
                                    "-o", f"{BUILD_DIR}/{self.jobname}.nls"], self.root)
            state["nomencl"] = nomencl
            ran = True
        return ran

    def _fingerprint(self) -> dict:
        """Size and modification time of every project file (not .build): cheap change detection."""
        prints = {}
        for path in iter_project_files(self.root):
            try:
                st = path.stat()
            except OSError:
                continue
            prints[path.relative_to(self.root).as_posix()] = [st.st_size, st.st_mtime_ns]
        return prints

    def _read_log(self) -> str:
        return _read(self._out(".log")).decode("utf-8", errors="replace")

    def run(self) -> BuildResult:
        start = time.monotonic()
        started_at = time.time()
        self.build_dir.mkdir(exist_ok=True)
        pdf = self._out(".pdf")
        state = self._load_state()
        inputs = self._fingerprint()  # taken before building, so edits made meanwhile count next time
        same_setup = state.get("main") == self.main_rel and state.get("engine", "lualatex") == self.engine
        previous = state.get("inputs") if same_setup and pdf.exists() else None
        changed = None if previous is None else {
            rel for rel in previous.keys() | inputs.keys() if previous.get(rel) != inputs.get(rel)}

        # 1. Nothing changed since a clean build: the PDF is already current.
        if changed == set() and state.get("clean"):
            log = self._read_log()
            problems = collect_problems(self.root, self.build_dir, self.jobname, log)
            return BuildResult("success", "Up to date: nothing changed since the last build", str(pdf), log,
                               round(time.monotonic() - start, 2), [], [p.to_dict() for p in problems])

        try:
            step = None
            # 2. Only bibliography files changed: LaTeX's .bcf/.aux are still valid, so run
            #    biber/BibTeX first and then LaTeX once, instead of LaTeX, biber, LaTeX.
            if changed and all(rel.lower().endswith(".bib") for rel in changed):
                if self._aux_tools(state, self._read_log()):
                    self._save_state(state)
                    step = self._latex()

            if step is None:
                step = self._latex()
            log = self._read_log()
            produced = pdf.exists() and pdf.stat().st_mtime >= started_at - 1

            if produced:
                aux_ran = self._aux_tools(state, log)
                self._save_state(state)
                # After bibliography tools, LaTeX needs one run to read the new files and
                # usually one more to settle references. Stop early if a run fails.
                pending = 1 if aux_ran else 0
                while self.latex_runs < MAX_LATEX_RUNS and (pending or (step.exit_code == 0 and RERUN.search(log))):
                    pending = max(0, pending - 1)
                    step = self._latex()
                    log = _read(self._out(".log")).decode("utf-8", errors="replace")
                    if step.exit_code != 0:
                        break
                    if RERUN_BIBER.search(log) and self._aux_tools(state, log):
                        self._save_state(state)
                        pending = 1
        except BuildCancelled:
            return BuildResult("cancelled", "Build cancelled", steps=self.steps,
                               duration=round(time.monotonic() - start, 2))
        except FileNotFoundError as exc:
            return BuildResult("failed", f"Could not run {exc.filename}: is MiKTeX on the PATH?",
                               steps=self.steps, duration=round(time.monotonic() - start, 2))

        duration = round(time.monotonic() - start, 2)
        produced = pdf.exists() and pdf.stat().st_mtime >= started_at - 1
        problems = collect_problems(self.root, self.build_dir, self.jobname, log, self.steps)
        errors = sum(p.severity == "error" for p in problems)
        failed_tool = next((s for s in self.steps if s.tool not in LATEX_ENGINES and s.exit_code not in (0, None)), None)
        if not produced:
            status, message = "failed", "Compilation failed: no PDF was produced"
        elif step.exit_code != 0 or errors:
            noun = "error" if errors == 1 else "errors"
            status, message = "errors", f"Compiled with {errors} {noun}" if errors else "Compiled with errors"
        elif failed_tool:
            status, message = "errors", f"Compiled, but {failed_tool.tool} reported errors"
        else:
            status, message = "success", f"Compiled in {duration:.1f} s"

        # Remember what this build saw; only a clean build may be skipped next time
        # (after errors, rebuilding may help, e.g. once a missing package is installed).
        state.update(inputs=inputs, main=self.main_rel, engine=self.engine, clean=status == "success")
        self._save_state(state)
        return BuildResult(status, message, str(pdf) if produced else None, log, duration, self.steps,
                           [p.to_dict() for p in problems])
