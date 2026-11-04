# LaTeX Editor

Desktop LaTeX editor for LuaLaTeX projects: import a project `.zip`, edit on the left,
see the PDF on the right. See [PLAN.md](PLAN.md) for the design and roadmap.

## Requirements

- Windows with the WebView2 runtime (included in Windows 11)
- Python 3.13
- MiKTeX with `lualatex`, `biber`, `bibtex`, `makeindex`, `makeglossaries-lite`, `synctex`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python scripts\fetch_vendor.py
```

## Run

```powershell
.\.venv\Scripts\python -m app            # add --debug for the WebView developer tools
```

## Tests

```powershell
.\.venv\Scripts\python -m pytest         # unit tests
.\.venv\Scripts\python scripts\ui_check.py   # opens the app window, checks layout + backend, closes it
```

To work on the UI in a normal browser (no Python backend), serve `web/`:
`python -m http.server 8765 --directory web`.

## Check the setup

```powershell
.\.venv\Scripts\python scripts\smoke_test.py
```

Compiles a small document with LuaLaTeX and opens a window that loads Monaco, typo.js and
PDF.js. It closes itself and prints `OK` results for all three (`--keep-open` to look at it).
