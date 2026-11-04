# LaTeX Editor — Development Plan

A desktop LaTeX editor for research documents: import projects from `.zip`, edit LaTeX on the
left, see the LuaLaTeX-compiled PDF on the right.

## 1. Requirements (from Q&A)

| Topic | Decision |
|---|---|
| App type | Desktop window: Python + **pywebview** (Edge WebView2) with a web UI inside |
| Engine | **LuaLaTeX** (MiKTeX 25.4, LuaHBTeX 1.22 — already installed) |
| Compile trigger | On **Ctrl+S** and a **Compile** button |
| Layout | File tree · Code editor (left) · PDF viewer (right) · Error panel (bottom) |
| Projects | `.zip` extracted into a workspace folder (`Documents\LatexEditor\<project>`), saved there, **Export .zip** on demand, Recent Projects list |
| Editor features | Multi-file tree, syntax highlighting, autocomplete (commands, environments, `\ref`, `\cite`, file paths), **SyncTeX** both ways, clickable error panel |
| Build tools | Bibliography (biber **and** BibTeX, auto-detected), glossaries, makeindex |
| Extras | Spell check, find/replace across the project |
| UI language | English |
| Not in v1 | `--shell-escape` (minted etc.), Git history, document outline |

## 2. Environment findings

- Installed: `lualatex`, `biber`, `bibtex`, `makeindex`, `makeglossaries-lite`, `synctex`, `texlua`,
  Python 3.13, Git, WebView2 runtime.
- **Not installed:** Node.js (fine — we vendor prebuilt JS libraries, no build step) and **Perl**.
- Because there is no Perl, **`latexmk` and `makeglossaries` do not run**. The app will use its own
  Python build orchestrator instead (section 4.3) and `makeglossaries-lite` (runs on `texlua`).

## 3. Technology

| Layer | Choice | Why |
|---|---|---|
| Window | `pywebview` 5.x (WebView2 backend) | Native window, only needs Python |
| Python ↔ UI | pywebview `js_api` bridge | Direct function calls from JS, no web framework |
| PDF serving | Tiny stdlib HTTP server on `127.0.0.1:<random port>` with a session token | Streams large PDFs to PDF.js without base64 overhead |
| Code editor | **Monaco Editor** (prebuilt `min` build, vendored) | VS Code editor: highlighting, completion API, markers, find/replace, minimap |
| PDF viewer | **PDF.js** (`pdfjs-dist` prebuilt, vendored) | Text-selectable rendering, page/coordinate API needed for SyncTeX |
| Spell check | **typo.js** + Hunspell dictionaries (en, ca, es vendored; English first) in a Web Worker | Offline spell check rendered as Monaco squiggles; single browser-ready file (nspell needs a bundler) |
| Tests | `pytest` | Backend logic (zip import, build, log parser, SyncTeX, search) |
| Packaging | PyInstaller → single-folder `LatexEditor.exe` | Double-click to launch |

All JS libraries are downloaded once by `scripts/fetch_vendor.py` (pinned versions, sha512
checked) into `web/vendor/` (git-ignored), so the app works fully offline.

Pinned versions: pywebview 6.2.1, Monaco 0.57.0, PDF.js (`pdfjs-dist`) 6.4.299, typo.js 1.3.2,
`dictionary-en` 4.0.0, `dictionary-ca` 3.0.0, `dictionary-es` 4.0.0; dev: pytest 9.1.1,
PyInstaller 6.22.3.

## 4. Architecture

### 4.1 Folder structure

```
latexeditor/
  app/
    __main__.py      # `python -m app`
    main.py          # entry point: starts PDF server, creates window
    api.py           # class exposed to JS (open/save/compile/search/...)
    workspace.py     # import .zip, recent projects, file ops, export .zip
    project.py       # per-project settings (.latexeditor.json), main-file detection
    builder.py       # LuaLaTeX build orchestrator
    logparser.py     # .log -> errors/warnings with file + line
    synctex.py       # wrappers around `synctex view` / `synctex edit`
    search.py        # project-wide find/replace
    pdfserver.py     # localhost server for the output PDF
    settings.py      # app settings (theme, font size, dictionary, workspace path)
  web/
    index.html
    css/app.css
    js/
      app.js         # bootstrap: toolbar, panels, shortcuts, status bar
      layout.js      # resizable/collapsible panes, remembered in localStorage
      bridge.js      # promise wrapper around window.pywebview.api
      filetree.js
      editor.js      # Monaco setup, tabs, dirty state, save
      latex-lang.js  # Monarch tokenizer for LaTeX/BibTeX
      completion.js  # commands, environments, \ref, \cite, paths
      pdfview.js     # PDF.js viewer, zoom, keep scroll on reload
      errors.js      # error panel + Monaco markers
      synctex.js
      search.js      # project find/replace panel
      spell/         # spell-check worker
    smoke.html       # dev-only page for scripts/smoke_test.py
    vendor/          # monaco, pdfjs, typo, dictionaries (fetched, not hand-edited)
  scripts/
    fetch_vendor.py
    smoke_test.py    # lualatex + pywebview + vendor libraries end-to-end check
    ui_check.py      # launches the real app window and probes the UI via JS
  tests/
    fixtures/        # small sample projects as .zip
  requirements.txt
  PLAN.md
```

### 4.2 Project import & storage

1. User picks a `.zip` (or drags it onto the window).
2. Validate and extract into `Documents\LatexEditor\<name>` (unique name if it exists):
   - reject absolute paths / `..` entries (zip-slip), cap total size, skip `__MACOSX`, `.DS_Store`;
   - if the zip has a single top-level folder, unwrap it.
3. Detect the **main file**: `% !TEX root` magic comment → `main.tex` → the only `.tex` with
   `\documentclass` → ask the user. Stored in `<project>\.latexeditor.json` and changeable
   (right-click → "Set as main file").
4. Build artifacts go to `<project>\.build\` so the source folder stays clean.
5. **Export .zip**: sources only by default, optional "include PDF".
6. Recent Projects list on the start screen (stored in `%APPDATA%\LatexEditor\settings.json`).

### 4.3 Build pipeline (`builder.py`)

Runs in a background thread; a new compile cancels a running one; whole build has a timeout.

```
lualatex -synctex=1 -interaction=nonstopmode -file-line-error -halt-on-error=no
         -output-directory=.build main.tex
  if .build/main.bcf exists               -> biber   (biblatex)
  elif main.aux contains \bibdata         -> bibtex  (classic)
  if .glo/.acn present                    -> makeglossaries-lite
  if .idx present                         -> makeindex
  re-run lualatex while the log says "Rerun" / aux file changed (max 4 runs total)
```

- Auxiliary tools only run when their inputs changed (hash of `.bcf`, `.aux` bib lines, `.glo`, `.idx`),
  so most Ctrl+S builds are a single LuaLaTeX run.
- `TEXINPUTS`/`BIBINPUTS` set so files in subfolders and `.build` are found.
- `--shell-escape` is never passed in v1.
- MiKTeX "install missing packages on the fly" can show a dialog; the app detects a stalled
  build and tells the user to enable automatic installs in MiKTeX Console.
- Progress (`Compiling… / Done in 3.2 s / Failed`) is pushed to the UI via `window.evaluate_js`.

### 4.4 Error panel (`logparser.py`)

- Parse `file:line: message` (file-line-error) plus the classic `! …` / `l.123` format.
- Warnings: undefined references/citations, multiply defined labels, overfull/underfull boxes
  (collapsible group), missing files, biber/BibTeX errors from `.blg`.
- Each entry → row in the bottom panel + Monaco marker (squiggle) in the right file/line;
  clicking opens the file at that line. "Show raw log" toggle.

### 4.5 SyncTeX

- **Source → PDF** (Ctrl+click / Ctrl+Alt+J): `synctex view -i line:col:file -o .build/main.pdf`
  → page + box → scroll PDF.js there and flash a highlight.
- **PDF → Source** (double-click in PDF): convert click to PDF points →
  `synctex edit -o page:x:y:.build/main.pdf` → open file, go to line.

### 4.6 Editor intelligence

- Monarch tokenizer for LaTeX (commands, environments, math, comments, braces) and BibTeX.
- Completion providers:
  - built-in list of common LaTeX commands/environments with snippets
    (`\begin{figure}` → full block with `\caption`/`\label`);
  - `\ref{`, `\eqref{`, `\autoref{`, `\cref{` → labels scanned across the project;
  - `\cite{`, `\parencite{`, `\textcite{` … → keys parsed from `.bib` files (with title/author in the detail);
  - `\input{`, `\include{`, `\includegraphics{`, `\addbibresource{` → project file paths.
- Auto-close braces/environments, bracket matching, comment toggle (Ctrl+/).

### 4.7 Find / replace in project

- Panel with: text or regex, match case, whole word, file filter (`*.tex`, `*.bib`).
- Results grouped by file with line previews; click to jump.
- "Replace all" shows a preview of affected lines and saves the files (open tabs updated).

### 4.8 Spell check

- Web Worker running typo.js with the selected Hunspell dictionary (English first; Catalan and
  Spanish dictionaries can be added in Settings).
- Tokenizer skips commands, their key arguments (`\ref{}`, `\cite{}`, `\label{}`, `\begin{}`…),
  math (`$…$`, `\[…\]`, math environments) and comments.
- Misspellings shown as info-level squiggles; quick-fix menu with suggestions, "Add to project
  dictionary" (stored in `.latexeditor.json`).

## 5. Development phases

Each phase ends with something runnable and is tested before moving on.

| # | Phase | Deliverable / done when |
|---|---|---|
| 0 | **Setup** ✅ | `git init`, venv, `requirements.txt` / `requirements-dev.txt`, `fetch_vendor.py` downloads Monaco + PDF.js + typo.js + dictionaries, `smoke_test.py` passes |
| 1 | **Window & layout** ✅ | App opens a window with file tree · editor · PDF, draggable splitters, toolbar, status bar; `ui_check.py` passes |
| 2 | **Projects** | Import `.zip`, workspace folder, Recent Projects, file tree (open/new/rename/delete/upload image), tabs, Ctrl+S save, Export `.zip`, main-file detection |
| 3 | **Compile & PDF** | Build pipeline with LuaLaTeX + biber/BibTeX + glossaries/index; PDF shown on the right, keeps page/zoom after recompile; zoom/fit controls |
| 4 | **Error panel** | Parsed errors/warnings, markers in editor, click-to-jump, raw log view |
| 5 | **Editor intelligence** | LaTeX highlighting, autocomplete (commands, envs, refs, cites, paths), snippets |
| 6 | **SyncTeX** | Both directions working on multi-file projects |
| 7 | **Find/replace in project** | Search panel with regex, replace-all with preview |
| 8 | **Spell check** | English dictionary, suggestions, project dictionary |
| 9 | **Polish & package** | Light/dark theme, settings dialog (font size, dictionary, workspace path), unsaved-changes prompts, `LatexEditor.exe` via PyInstaller |

## 6. Testing

- **Unit tests (pytest):** zip import (zip-slip, nested folder unwrap, junk files), main-file
  detection, log parser on real MiKTeX logs, build decision logic (when to run biber/bibtex/glossaries),
  SyncTeX output parsing, project search/replace.
- **Integration tests:** fixture projects compiled end-to-end with the real MiKTeX:
  plain article; multi-file thesis with `\include`; biblatex+biber; natbib+BibTeX; glossaries+index;
  a deliberately broken document (errors must appear with correct file/line).
- **Manual checks per phase** with one of your real research projects.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| No Perl → `latexmk`/`makeglossaries` fail | Own orchestrator + `makeglossaries-lite` |
| LuaLaTeX is slow on big documents (first run builds font cache) | Background build, cancel-on-new-build, skip unnecessary aux tool runs, status indicator |
| MiKTeX missing-package popups stall builds | Detect stall, guide user to enable auto-install |
| PDF flicker / losing position on reload | Render new PDF off-screen, swap, restore page + scroll offset |
| Untrusted zips | Zip-slip checks, size limits, no shell-escape |
| typo.js suggestions are slow on large dictionaries | Run in a Web Worker, check visible ranges only, compute suggestions on demand |

## 8. Possible later features

Document outline panel, Git-based version snapshots, `--shell-escape` opt-in per project,
Catalan/Spanish UI, word count, image preview in file tree, templates for new projects.
