# LaTeX Editor

Desktop LaTeX editor for LuaLaTeX research documents: import a project `.zip`, edit on the
left, see the PDF on the right. See [PLAN.md](PLAN.md) for the design and how it was built.

## Features

- Import projects from `.zip` (button, Ctrl+O, or drag and drop onto the window); export back to `.zip`
- **Open folder** (Ctrl+Alt+O, or drop a folder onto the window): work on a LaTeX folder where it
  is, without copying it; saves go straight into it, and the app adds `.build/` (build output)
  and `.latexeditor.json` (main file, spelling language) there. Linked folders are labelled in
  the Recent lists
- **Recent** menu in the toolbar (Ctrl+Shift+O) to switch projects; the last project reopens at
  startup (can be turned off in Settings)
- File tree with new/rename/delete (Recycle Bin)/add files; tabs; Ctrl+S saves, Ctrl+Shift+S saves and compiles
- Formatting toolbar: bold/italic/underline (Ctrl+B/I/U, toggle), emphasis, monospace,
  super/subscript, inline math (Ctrl+M), €, °C, °, ±, µ, lists from selected lines, section, comment
- **Add reference** ([1] button, Ctrl+Shift+R): choose what you cite (book, part of a book,
  standard, commercial catalogue, periodical, journal article, newspaper article, official
  publication, web page), fill in the form and it is written in the house style, e.g.
  `KENNARD, L. “…”. Netware connection. Vol. 11 (2000), núm. 1, p. 6-20.`; `~\cite{key}` goes at the cursor,
  or untick "Cite it at the cursor" to only list it in the bibliography (`\nocite{key}` is added
  above `\bibliography`/`\printbibliography` for `.bib` entries). With BibTeX (`\bibliography{…}`, e.g. IEEEtran) or biblatex
  (`\addbibresource{…}`) it becomes an `@misc` entry in that `.bib` file; otherwise a `\bibitem` in
  the document's `thebibliography` (created if missing)
- **Paste tables from Excel**: pasting copied cells into a `.tex` file opens a dialog to choose
  `tabular`, `tabularx` (full width) or `longtable` (breaks across pages, header repeated), each
  column's alignment (left, centre, right, wrapped `p`, filling `X`; numbers default to right),
  vertical lines (none, outer, between columns, all), horizontal lines (booktabs, frame, every
  row, under the header, none), header row in bold, escaping of `& % $ # _`…, and a floating
  `table` with caption and label. A live preview shows the LaTeX; missing `\usepackage` lines
  (tabularx, longtable, booktabs) can be added to the preamble. "Paste as text" pastes the
  cells as they are. The options are remembered
- LuaLaTeX builds with biber/BibTeX, glossaries and index run automatically when needed;
  unchanged projects are not rebuilt and a `.bib`-only change skips the first LaTeX run
- PDF preview that keeps its zoom and position; SyncTeX (Ctrl+Alt+J ↔ double-click in the PDF)
- Problems panel with clickable errors and squiggles in the editor
- **Outline** to the right of the PDF (hide/show with the button at the end of the PDF toolbar):
  parts, chapters, sections and subsections in reading order (following `\input`/`\include`
  from the main file, unsaved edits included). A blue bar marks the heading the editor cursor is
  in, a fill the heading of the part of the PDF in view (positions from SyncTeX, updated on each
  compile). Click a heading to go there in both the code and the PDF
- **Equation preview**: with the cursor inside `$…$`, `\(…\)`, `\[…\]`, `$$…$$` or an
  `equation`/`align`/`gather`/`multline`… environment, the rendered math (MathJax) shows below it,
  or the error if it does not parse. Macros defined in the preamble are not known to the preview
- LaTeX/BibTeX highlighting; autocomplete for commands, environments, `\ref`, `\cite`, files.
  The project's images pop up as soon as the cursor is in an empty `\includegraphics{}` (e.g. from
  the `figure` snippet); type part of the file name (`em01`) to find one in any subfolder
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
