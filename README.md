# LaTeX Editor

Desktop LaTeX editor for LuaLaTeX research documents: import a project `.zip`, edit on the
left, see the PDF on the right. See [PLAN.md](PLAN.md) for the design and how it was built.

## Features

- Import projects from `.zip` (button, Ctrl+O, or drag and drop onto the window); export back to `.zip`
- **Recent** menu in the toolbar (Ctrl+Shift+O) to switch projects; the last project reopens at
  startup (can be turned off in Settings)
- File tree with new/rename/delete (Recycle Bin)/add files; tabs; Ctrl+S saves and compiles
- Formatting toolbar: bold/italic/underline (Ctrl+B/I/U, toggle), emphasis, monospace,
  super/subscript, inline math (Ctrl+M), €, °C, °, ±, µ, lists from selected lines, section, comment
- **Add web reference** ([1] button, Ctrl+Shift+R): fills in
  `Autor (Pàgina consultada l’11 de febrer de 2000). Títol, [En línia]. Adreça URL: …` as a
  `\bibitem` in the document's `thebibliography` (created if missing) and puts `~\cite{key}` at the cursor
- LuaLaTeX builds with biber/BibTeX, glossaries and index run automatically when needed;
  unchanged projects are not rebuilt and a `.bib`-only change skips the first LaTeX run
- PDF preview that keeps its zoom and position; SyncTeX (Ctrl+Alt+J ↔ double-click in the PDF)
- Problems panel with clickable errors and squiggles in the editor
- LaTeX/BibTeX highlighting; autocomplete for commands, environments, `\ref`, `\cite`, files
- Project-wide search and replace (Ctrl+Shift+F)
- Spell check: English (US/UK), Català, Español; language from babel/polyglossia
- Settings (Ctrl+,): light/dark theme, font size, word wrap, projects folder

## Requirements

- Windows 10/11 with the WebView2 runtime (included in Windows 11)
- MiKTeX with `lualatex`, `biber`, `bibtex`, `makeindex`, `makeglossaries-lite`, `synctex`
  on the PATH (Perl is **not** needed)
- To run from source or build: Python 3.13

## Use the packaged app

Build it once (see below), then run `dist\LatexEditor\LatexEditor.exe`. The whole
`dist\LatexEditor` folder is the app: copy it anywhere and keep the files together.
Projects are stored in `Documents\LatexEditor` (changeable in Settings); app settings in
`%APPDATA%\LatexEditor`.

## Setup from source

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python scripts\fetch_vendor.py
```

## Run

```powershell
.\.venv\Scripts\python -m app            # add --debug for the WebView developer tools
```

## Build the .exe

```powershell
.\.venv\Scripts\python scripts\build_exe.py
```

Creates `dist\LatexEditor\LatexEditor.exe` (~60 MB folder) and then runs it with
`--self-test`: it must load the UI, import and compile a sample project, serve the PDF and
spell-check, or the build reports FAIL.

## Tests

```powershell
.\.venv\Scripts\python -m pytest                 # unit tests + real LuaLaTeX builds (~60 s)
.\.venv\Scripts\python -m pytest -m "not latex"  # skip the LuaLaTeX build tests
.\.venv\Scripts\python scripts\ui_check.py       # drives the real app window end to end
```

To work on the UI in a normal browser with the real Python API behind it:

```powershell
.\.venv\Scripts\python scripts\dev_server.py   # then open http://127.0.0.1:8765/index.html?dev
```

It uses a temporary workspace; native file dialogs are answered from a queue
(`POST /dev/dialog {"result": [...]}`).
