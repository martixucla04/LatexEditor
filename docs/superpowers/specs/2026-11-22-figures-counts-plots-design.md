# Paste images as figures, word/page counts per chapter, Excel data as plots

Three features for LaTeX Editor, built in this order. They share the existing paste
machinery (`web/js/editor.js` paste hook, `web/js/tables.js` dialog pattern) and the
outline (`app/outline.py`, `web/js/outline.js`).

## Why

The user writes a thesis (Catalan, `\input` chapters in `Contenido/`, images in
`Imagenes/<chapter>/…`, many measurements). Today, adding a diagram or a datasheet
capture means saving the screenshot by hand, finding the folder, writing the figure
block and then resizing it; length is unknown until the PDF is read; measurement data
from Excel can only become tables.

## 1. Paste a screenshot as a figure

**What:** Ctrl+V with an image on the clipboard, in a `.tex` file, opens a "Paste image"
dialog. Images are usually diagrams and datasheet captures; the one thing always fixed
by hand today is the size.

Dialog:
- Preview of the image on a canvas. **Crop**: drag a rectangle on the preview; Reset undoes it.
  **Trim margins**: cuts the uniform border (same colour as the corners, with tolerance).
- **Background** (no AI): None / Make white / Make transparent, with a tolerance slider.
  Flood fill from every edge pixel through pixels close to the edge colour; lines that do
  not touch the edge are kept. Default None. (AI removal with ISNet is a later, separate
  feature: decided as native onnxruntime in Python, model bundled in the app.)
- **Caption**, **Label** (`fig:` + slug of the caption until edited), **Width** slider 0.3–1.0
  of `\textwidth`, step 0.05, default 0.8, with a small page outline showing the width.
- **Folder**: a dropdown of the project's folders that contain images; default = the folder of
  the last `\includegraphics` in the current file, else the folder with most images, else
  `Imagenes/` if it exists, else `figures/` (created).
- **File name**: slug of the caption + `.png` (made unique), editable.
- **Source** (optional, free text): appended to the caption as ` (Font: <text>)`. *My call*: the
  user did not say how sources must be credited; free text lets them type `\cite{key}` or a name.
- Buttons: **Save image only** (writes the file, inserts nothing), Cancel, **Insert**.
- Remembered between uses (localStorage): width, background mode, tolerance, folder.

Inserted (the thesis' own style):
```latex
\begin{figure}[ht]
    \centering
    \includegraphics[width=0.8\textwidth]{Imagenes/BMU/isoSPI/arquitectura-isospi.png}
    \caption{Arquitectura isoSPI (Font: \cite{ltc6811})}
    \label{fig:arquitectura-isospi}
\end{figure}
```
Paths are relative to the project root (as in the thesis; LaTeX runs from the root). If no
`.tex` file loads `graphicx`, it is added to the preamble (`tables.add_packages`).

**How:** all image editing (crop, trim, background) in the page with a canvas; the result is
sent to Python as base64 PNG. New API `save_image(folder, name, data)`: validates the folder
is inside the project (`Project.path`), refuses non-PNG data, makes the name unique, writes
the bytes, returns the project-relative path. Caption, label and source are inserted as typed
(LaTeX allowed), not escaped. Images over 4000 px on a side are not downscaled (*my call*: keep
what was pasted).

## 2. Word and page count per chapter

**What:** the outline shows, next to every heading, its words and pages, e.g. `3.4k w · 12 p`
(exact numbers in the tooltip), and a total line at the bottom of the outline: `18,230 words ·
64 pages`. A heading's counts include its subsections.

**Words** (Python, no texcount: it needs Perl). Text from `\begin{document}` to
`\end{document}` in reading order (the outline already follows `\input`/`\include`), counted
per heading. Counted: prose, heading titles, captions, footnotes, table cells. Not counted:
comments, math (`$…$`, `\(…\)`, `\[…\]`, `$$…$$`, equation-like environments), command names,
the arguments of `\label \ref \eqref \cite \includegraphics \input \include \usepackage
\begin \end \url \href`'s URL, `verbatim`/`lstlisting` bodies, and the bibliography
(`thebibliography`, `\bibliography`, `\printbibliography`). A word is a run of letters/digits,
including apostrophes and the Catalan middle dot (`col·lecció` = 1 word).

**Pages:** from the PDF positions the outline already gets from SyncTeX: a heading spans from
its page to the page before the next heading of the same or higher level (the last one to the
last page of the PDF). Shown only after a compile; `?` when a heading has no position. Pages
before the first heading (cover, table of contents) are not attributed to any chapter; the
total uses the PDF's page count.

**How:** `app/outline.py` gains the counts in the same walk (it already blanks comments and
tracks file/line); `Api.outline` adds `words` and, when positions exist, `pages`, plus a total.
Unsaved edits count (the outline already receives unsaved buffers). Refreshes when the outline
refreshes (edit, compile).

## 3. Excel data as a plot

**What:** the Paste table dialog gets a switch at the top: **Table | Plot**. Plot writes a
`pgfplots` chart from the same pasted cells.

Plot options:
- **Type**: Line, Line with markers (default), Scatter (markers only), Bar.
- **X column** (default: the first column) and **Y columns** (checkboxes; default: the other
  numeric columns). A non-numeric X column gives categories (`symbolic x coords`), allowed
  with Bar only; other types then show a note.
- **Axis labels**: from the header cells, editable (escaped like table cells).
- **Legend** on/off (on when there are 2+ Y columns), **grid** on/off (default on).
- **Width** (fraction of `\textwidth`, default 0.8) and height (default 0.6 × width).
- **Decimal comma**: numbers like `3,65` (Excel in Catalan) are converted to `3.65` in the
  data; when the source used commas, axis numbers are shown with a comma
  (`/pgf/number format/use comma`), with a checkbox to turn it off.
- Caption and label (`fig:`), floating `figure` like the image paste.

Data goes inline (`\addplot table [x=…, y=…] {…};` with a column-name header) up to 60 rows;
above that it is saved as `data/<label>.csv` (folder created) and read with
`\addplot table [col sep=comma, …] {data/<label>.csv};` (*my call*: keeps long measurement
series out of the chapter text).

Preview: a quick SVG drawing of the chart in the dialog (approximate) plus the LaTeX code;
the real look is in the PDF after compiling.

Packages: `pgfplots` is added to the preamble if missing, followed by
`\pgfplotsset{compat=1.18}` (the installed version is 1.18.1).

**How:** Python `app/plots.py` (parse numbers, build the LaTeX, write the CSV), using
`tables.parse_cells`, tested with pytest including a real compile; the dialog in
`web/js/tables.js` gets the switch and the plot form.

## Goals, non-goals, anti-goals

- Goal: each feature works from one paste or one look at the outline, in the thesis' style.
- Non-goals: AI background removal (later), editing a figure or plot after insertion,
  formats other than PNG, two Y axes, word limits or warnings, counting words in the PDF.
- Anti-goals: anything that changes or reformats existing figures, uploads images, or slows
  typing (counting runs in Python, after the outline's debounce).

## Approaches considered

- Images: editing in the page (canvas, chosen: instant, no new dependency) vs in Python with
  Pillow (new dependency for crop/trim). AI background removal: native onnxruntime + ISNet
  (chosen for later) vs ONNX Runtime Web vs @imgly/background-removal (AGPL, slower, CDN).
- Words: own counter (chosen) vs texcount (needs Perl, not installed).
- Plots: pgfplots (chosen: vector, document fonts, no new dependency) vs PNG via matplotlib
  (new Python dependency, fonts do not match). Preview: SVG approximation (chosen, instant) vs
  compiling a standalone snippet (exact, 2–3 s per change).

## Calls made after the builder check (marked *my call*)

1. **Paste routing.** Cells from Excel open the paste-table dialog in the mode used last
   (Table the first time); the Table | Plot switch is a mode of that same dialog.
2. **Image vs table on the clipboard.** Excel also puts a picture of the copied cells on the
   clipboard, so a table wins: the image dialog opens only when the clipboard has an image file
   and no text at all (changed while building: Word also puts a picture next to copied text,
   so any text means a normal or table paste; a screenshot or a browser's "Copy image" has none).
3. **Word count details.** Starred and unnumbered headings and `\part` count like others; the
   arguments of unknown commands (`\textbf{…}`, `\foreignlanguage{…}{…}`, custom macros) count
   as text, except for the argument lists named above; `\newcommand` bodies sit in the preamble
   and do not count; `.tex` files not reached through `\input`/`\include` do not count.
4. **Image folders.** The whole project is scanned with `iter_project_files` (already skips
   `.build`, `.git`, hidden app files; limited to the files the tree shows); every folder that
   directly holds a `.png/.jpg/.jpeg/.pdf/.eps/.svg` file is listed, nested ones included,
   sorted by path. Done once when the dialog opens.
5. **pgfplots missing.** No fallback in the app: MiKTeX installs missing packages on the fly, and
   a missing package shows up in Problems. The real-compile test is skipped when `pgfplots.sty`
   is not found (`kpsewhich`).
6. **Unique names.** Labels (`fig:…`) are made unique against the labels already in the project
   (`a`, `b`… suffixes, as for citation keys); file names against the folder's files.

## Left to the builder

Slug rules, dialog layout details, tolerance scale, SVG preview styling, exact pgfplots style
keys, test names.
