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
`dictionary-en` 4.0.0, `dictionary-en-gb` 3.0.0, `dictionary-ca` 3.0.0, `dictionary-es` 4.0.0; dev: pytest 9.1.1,
PyInstaller 6.22.3.

## 4. Architecture

### 4.1 Folder structure

```
latexeditor/
  app/
    __main__.py      # `python -m app`
    main.py          # entry point: starts PDF server, creates window
    api.py           # class exposed to JS (open/save/compile/search/...)
    errors.py        # UserError: messages shown to the user as-is
    fsutil.py        # Documents/AppData folders, Recycle Bin, atomic writes
    workspace.py     # import .zip, recent projects, file ops, export .zip
    project.py       # per-project settings (.latexeditor.json), main-file detection
    builder.py       # LuaLaTeX build orchestrator
    logparser.py     # .log -> errors/warnings with file + line
    synctex.py       # wrappers around `synctex view` / `synctex edit` (forward / inverse search)
    completions.py   # labels, .bib entries, user macros, files for autocomplete
    search.py        # project-wide find/replace
    pdfserver.py     # localhost server for the output PDF
    settings.py      # app settings (theme, font size, dictionary, workspace path)
  web/
    index.html
    css/app.css
    js/
      app.js         # bootstrap: toolbar, panels, shortcuts, status bar
      layout.js      # resizable/collapsible panes, remembered in localStorage
      bridge.js      # promise wrapper around window.pywebview.api (or dev_server.py with ?dev)
      ui.js          # toasts, modal dialogs, context menus
      filetree.js
      editor.js      # Monaco setup, tabs, dirty state, save
      latex-lang.js  # Monarch tokenizers + language config for LaTeX/BibTeX, token colours
      latex-data.js  # built-in commands, environments, packages, classes
      completion.js  # completion + hover providers (\ref, \cite, paths, \end{)
      pdfview.js     # PDF.js viewer, zoom, keep scroll on reload
      problems.js    # problems panel (markers live in editor.js)
      synctex.js
      search.js      # sidebar Search view (project find/replace)
      spell.js       # spell-check markers, quick fixes, language picker
      settings.js    # Settings dialog (theme, font size, wrap, projects folder)
      spell/worker.js  # typo.js dictionary + LaTeX-aware word extraction
    smoke.html       # dev-only page for scripts/smoke_test.py
    vendor/          # monaco, pdfjs, typo, dictionaries (fetched, not hand-edited)
  latexeditor.py     # launcher used by PyInstaller
  scripts/
    build_exe.py     # PyInstaller one-folder build + self-test of the .exe
    make_icon.py     # draws the app icon (.ico) without an imaging library
    fetch_vendor.py
    smoke_test.py    # lualatex + pywebview + vendor libraries end-to-end check
    ui_check.py      # launches the real app window and drives the UI via JS
    dev_server.py    # serves web/ + the real Api over HTTP for browser-based UI work
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
(cwd = project root)
lualatex -interaction=nonstopmode -file-line-error -synctex=1
         -output-directory=.build -jobname=main main.tex
  if .build/main.bcf exists               -> biber .build/main             (biblatex)
  elif main.aux contains \bibdata         -> bibtex .build/main            (classic)
  if .glo/.acn/.slo present               -> makeglossaries-lite main      (cwd = .build: it can't chdir)
  if .idx present                         -> makeindex .build/main.idx
  if .nlo present                         -> makeindex -s nomencl.ist      (nomencl)
  re-run lualatex after aux tools and while the log asks for a rerun (max 5 runs total)
```

Verified on this machine: biber/bibtex find `.bib` files relative to the project root and
non-ASCII project paths compile. MiKTeX's LuaTeX always wraps log lines at 79 bytes (it
ignores the `max_print_line` env var and `--cnf-line`), so the log parser unwraps them.

- Auxiliary tools only run when their inputs changed (hash of `.bcf` + the `.bib` files it
  lists, `.aux` citations + `.bib` files, `.glo`/`.acn`, `.idx`), stored in
  `.build/.latexeditor-build.json`, so most Ctrl+S builds are a single LuaLaTeX run.
- `compile()` blocks in its bridge thread and returns the result; a new compile cancels the
  running one (process tree killed with `taskkill /T`), and builds never overlap.
- `TEXINPUTS`/`BIBINPUTS` set so files in subfolders and `.build` are found.
- `--shell-escape` is never passed in v1.
- MiKTeX "install missing packages on the fly" can show a dialog; the app detects a stalled
  build and tells the user to enable automatic installs in MiKTeX Console.
- Progress (`Compiling… / Done in 3.2 s / Failed`) is pushed to the UI via `window.evaluate_js`.

### 4.4 Error panel (`logparser.py`)

- Join lines wrapped at 79 bytes, then follow `(file` / `)` to know the current file
  (message bodies are skipped so their parentheses don't confuse the stack).
- Parse `file:line: message` (file-line-error) plus the classic `! …` / `l.123` format;
  the `l.N` context gives the exact token to underline.
- Warnings: LaTeX/package/class warnings (with `(package)` continuation lines), missing
  characters; overfull/underfull boxes and font substitutions as "Typesetting" notes
  (hidden by default); biber/BibTeX errors from `.blg` (biber's temp-file line numbers are
  mapped back to the `.bib` data source); tools that failed without a parsed error.
- Each entry → row in the bottom panel + Monaco marker (squiggle) in the right file/line;
  clicking opens the file at that line. "Show raw log" toggle.

### 4.5 SyncTeX

- **Source → PDF** (Ctrl+Alt+J or "Find in PDF"): `synctex view -i line:col:file -o .build/main.pdf`
  (run from the project root) → boxes `h, v−H, W, H` in points from the page's top-left →
  PDF.js `convertToViewportPoint` (v6 has no rectangle variant) → scroll there and flash.
- **PDF → Source** (double-click in PDF): `convertToPdfPoint` → top-left points →
  `synctex edit -o page:x:y:.build/main.pdf` → `Input:` is `<root>/./<relative path>` (UTF-8)
  → open the file at the line and flash it.

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

- Sidebar view next to Files: text or regex, match case, whole word, file patterns (`*.tex, *.bib`).
- Matching is per line; literal by default (LaTeX backslashes need no escaping); regex
  replacements accept `$1` or `\1`. "Whole word" only adds boundaries next to letters/digits,
  so `\section` doesn't match `\sectionmark`.
- Results grouped by file with highlighted previews; click opens the file with the match selected.
- "Replace all" asks for confirmation, saves open files, rewrites files in their original
  encoding and line endings, and updates open tabs as one undoable edit.

### 4.8 Spell check

- Web Worker (`web/js/spell/worker.js`) running typo.js with the project's Hunspell dictionary:
  `en` (US), `en-GB`, `ca`, `es`, or off. Default from the main file's babel (last language or
  `main=`) / polyglossia (`\setdefaultlanguage`, `variant=british`); changeable from the status
  bar; stored with the project word list in `.latexeditor.json` (`"spell"`).
- Measured load times: en 0.1 s, en-GB 0.9 s, es 0.7 s, **ca ~11 s** (typo.js expands all affix
  forms); the dictionary stays loaded in the worker for the session. Suggestions take 1–3 s,
  so they are prefetched when the cursor rests on a misspelled word.
- The text is masked before word extraction: comments, commands, options `[...]`, non-prose
  arguments (`\ref`, `\cite`, `\label`, paths, `\begin{..}{..}`, `\url`, `\texttt`, units…),
  inline/display math and math/verbatim/code environments. Acronyms and mixed-case words
  (LaTeX, FEniCS) are skipped; hyphenated words are checked per part; elisions
  (`l'enginyeria`, `d'aquesta`) fall back to checking each part.
- Misspellings are "hint" markers (hover + Ctrl+. quick fixes: suggestions, "Add to project
  dictionary") drawn as a full-word pink wavy underline via a decoration.

## 5. Development phases

Each phase ends with something runnable and is tested before moving on.

| # | Phase | Deliverable / done when |
|---|---|---|
| 0 | **Setup** ✅ | `git init`, venv, `requirements.txt` / `requirements-dev.txt`, `fetch_vendor.py` downloads Monaco + PDF.js + typo.js + dictionaries, `smoke_test.py` passes |
| 1 | **Window & layout** ✅ | App opens a window with file tree · editor · PDF, draggable splitters, toolbar, status bar; `ui_check.py` passes |
| 2 | **Projects** ✅ | Import `.zip`, workspace folder, Recent Projects, file tree (open/new/rename/delete to Recycle Bin/add files), tabs, Ctrl+S save, Export `.zip`, main-file detection, unsaved-changes guard on quit |
| 3 | **Compile & PDF** ✅ | Build pipeline with LuaLaTeX + biber/BibTeX + glossaries/index (aux tools only when their inputs change); Ctrl+S saves and compiles, Compile/Stop button, progress in the status bar, raw log tab; PDF shown on the right, keeps zoom/scroll after recompile; zoom/fit controls, Ctrl+wheel |
| 4 | **Error panel** ✅ | Parsed errors/warnings with filters and badge, squiggles in the editor (F8 = next problem), click-to-jump, raw log view, problems restored when a project is reopened |
| 5 | **Editor intelligence** ✅ | LaTeX + BibTeX highlighting (math, refs, sections), autocomplete (commands, envs with snippets, `\end{` closes the open env, refs incl. unsaved labels, cites with author/year/title, files, packages, user macros), hover on `\ref`/`\cite`, folding, Ctrl+/ |
| 6 | **SyncTeX** ✅ | Ctrl+Alt+J / "Find in PDF" highlights the cursor's line in the PDF; double-click in the PDF opens the source line (with a flash); multi-file and accented paths |
| 7 | **Find/replace in project** ✅ | Sidebar Search view (Ctrl+Shift+F): literal/regex, case, whole word, file patterns; results grouped by file, click selects the match; Replace all with confirmation, saves open files first, open tabs updated (undoable); Monaco Ctrl+F/Ctrl+H in the current file |
| 8 | **Spell check** ✅ | English (US/UK), Català, Español in a Web Worker; language auto-detected from babel/polyglossia, switchable in the status bar; LaTeX-aware (skips commands, refs/cites, paths, math, comments, code); quick fixes with suggestions and "Add to project dictionary" |
| 9 | **Polish & package** ✅ | Settings dialog (Ctrl+,): theme System/Light/Dark with live preview, editor font size, word wrap, projects folder; drag and drop a .zip to import (or files to add them); persistent WebView2 profile (UI state survives restarts, caches cleared at launch); app icon; `dist/LatexEditor/LatexEditor.exe` via PyInstaller with an end-to-end `--self-test` |

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
| Stale UI files after an update (WebView2 keeps an HTTP/code cache in the persistent profile; pywebview's static server effectively sends only Last-Modified) | `Cache` and `Code Cache` are deleted at each launch; local storage is kept |
| pywebview fills `window.pywebview.api` in after creating it | `bridge.js` calls the live object and waits briefly for a function to appear; no "backend missing" timeout inside WebView2 |
| typo.js is slow on large dictionaries (Catalan loads in ~11 s, suggestions 1–3 s) | Web Worker, dictionary kept loaded for the session, status shows "loading", suggestions prefetched on cursor rest; possible later: cache the expanded dictionary in IndexedDB |

## 8. Upgrades after v1

- Dark mode: Monaco's right-click menu is placed beside the editor node and missed the theme's
  `--vscode-*` colours (transparent, black text); they are copied onto the container.
- Layout: the side panel used the class `sidebar`, which `pdf_viewer.css` also styles (fixed
  width, border), so it did not follow its grid column; renamed to `app-sidebar`. The code area
  keeps at least 200 px of height.
- Formatting toolbar (`format.js`) with toggling wraps and Ctrl+B/I/U/M; the file panel moved
  to Ctrl+Shift+B.
- Faster rebuilds (measured on the sample paper; each LuaLaTeX run ≈ 3 s, biber ≈ 3.4 s):
  nothing changed 3.1 s → 0.01 s (skipped after a clean build), `.bib`-only change
  9.3 s → 6.6 s (biber first, then one LaTeX run). A `.tex` edit stays one LaTeX run: LaTeX
  cannot re-typeset a single changed file, since page numbers and references span the document.

## 9. Possible later features

Document outline panel, Git-based version snapshots, `--shell-escape` opt-in per project,
Catalan/Spanish UI, word count, image preview in file tree, templates for new projects.
