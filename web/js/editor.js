// Monaco editor with one tab per open file. Each tab keeps its own model,
// view state (cursor/scroll) and saved version, so dirty state and position
// survive tab switches. Images and binary files open in a read-only viewer.

import { registerCompletions } from "./completion.js";
import { registerLanguages, TOKEN_RULES } from "./latex-lang.js";
import { attachSpell, initSpell } from "./spell.js";
import { confirmDialog } from "./ui.js";

const LANGUAGE_BY_EXT = {
  tex: "latex", sty: "latex", cls: "latex", ltx: "latex", dtx: "latex", ins: "latex", clo: "latex", bbx: "latex", cbx: "latex",
  bib: "bibtex", bst: "plaintext",
  md: "markdown", lua: "lua", json: "json", yaml: "yaml", yml: "yaml", xml: "xml", py: "python",
};

const $ = (id) => document.getElementById(id);
const tabsEl = $("tabs");
const editorEl = $("editor");
const fileViewEl = $("file-view");
const noFileEl = $("no-file");
const formatBarEl = $("format-bar");

let monaco = null;
let editor = null;
let projectOpen = false;
let activePath = null;
let modelCounter = 0;
const tabs = new Map(); // path -> { path, kind, model, viewState, encoding, savedVersion, data }
let problemsByPath = new Map(); // path -> build problems located in that file
let handlers = { onDirtyChange() {}, onActiveChange() {}, onCursor() {} };
let lastDirty = false;

const extOf = (path) => (path.includes(".") ? path.split(".").pop().toLowerCase() : "");
const nameOf = (path) => path.split("/").pop();

function loadMonaco() {
  return new Promise((resolve, reject) => {
    window.require.config({ paths: { vs: "vendor/monaco/vs" } });
    window.require(["vs/editor/editor.main"], () => resolve(window.monaco), reject);
  });
}

let currentTheme = null;

function applyTheme() {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  currentTheme = dark ? "latex-dark" : "latex-light";
  monaco.editor.setTheme(currentTheme);
  shareThemeVariables();
}

// Monaco's right-click menu lives next to the editor DOM node, not inside it, so it
// doesn't inherit the theme's --vscode-* colours (in dark mode it rendered transparent
// with black text). Copy them onto the container the menu is placed in.
let sharedTheme = null; // theme whose colours are already on the container

function shareThemeVariables() {
  if (!editor) return;
  const theme = currentTheme;
  if (sharedTheme === theme) return;
  requestAnimationFrame(() => {
    const node = editor.getDomNode();
    if (!node) return;
    const cs = getComputedStyle(node);
    let copied = 0;
    for (let i = 0; i < cs.length; i++) {
      const name = cs[i];
      if (name.startsWith("--vscode-")) {
        editorEl.style.setProperty(name, cs.getPropertyValue(name));
        copied++;
      }
    }
    if (copied) sharedTheme = theme; // none yet = no file shown yet; retry on the next model
  });
}

export async function initEditor(options) {
  handlers = { ...handlers, ...options };
  monaco = await loadMonaco();
  registerLanguages(monaco);
  initSpell(monaco);
  registerCompletions(monaco, {
    buffers: () => [...tabs.values()].filter((t) => t.model)
      .map((t) => ({ path: t.path, text: isDirty(t) ? t.model.getValue() : "", dirty: isDirty(t) })),
  });
  // Nested braces get muted colours (Monaco's default gold would clash with math colouring).
  monaco.editor.defineTheme("latex-light", {
    base: "vs", inherit: true, rules: TOKEN_RULES.light,
    colors: {
      "editorBracketHighlight.foreground1": "#57606a",
      "editorBracketHighlight.foreground2": "#6e7781",
      "editorBracketHighlight.foreground3": "#8c959f",
    },
  });
  monaco.editor.defineTheme("latex-dark", {
    base: "vs-dark", inherit: true, rules: TOKEN_RULES.dark,
    colors: {
      "editor.background": "#26272b",
      "editorGutter.background": "#26272b",
      "editorBracketHighlight.foreground1": "#8b949e",
      "editorBracketHighlight.foreground2": "#a5adb6",
      "editorBracketHighlight.foreground3": "#6e7681",
    },
  });
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

  editor = monaco.editor.create(editorEl, {
    model: null,
    automaticLayout: true,
    fontFamily: '"Cascadia Code", "Cascadia Mono", Consolas, monospace',
    fontSize: 14,
    lineHeight: 21,
    wordWrap: "on",
    wrappingIndent: "same",
    tabSize: 2,
    minimap: { enabled: true, renderCharacters: false },
    scrollBeyondLastLine: false,
    renderLineHighlight: "all",
    smoothScrolling: true,
    // Accented letters (Catalan/Spanish) are normal text, not suspicious characters.
    unicodeHighlight: { ambiguousCharacters: false, invisibleCharacters: true },
    fixedOverflowWidgets: true,
    // Suggestions only come from the LaTeX provider (commands, refs, cites…);
    // word-based ones would pop up constantly while writing prose.
    wordBasedSuggestions: "off",
    suggest: { showWords: false, preview: true },
    quickSuggestions: { other: true, comments: false, strings: false },
    snippetSuggestions: "inline",
    dropIntoEditor: { enabled: false }, // dropped files are imported/added, not pasted as text
  });
  editor.onDidChangeCursorPosition((e) => handlers.onCursor(e.position));
  // The themed DOM only exists once a file is shown, so share the colours then too.
  editor.onDidChangeModel(shareThemeVariables);
  shareThemeVariables();
  updateView();
  return monaco;
}

export function setEditorOptions({ fontSize, wordWrap }) {
  if (!editor) return;
  editor.updateOptions({ fontSize, lineHeight: Math.round(fontSize * 1.5), wordWrap: wordWrap ? "on" : "off" });
}

// Re-read the page theme (after the Settings dialog changed it).
export function refreshTheme() {
  if (monaco) applyTheme();
}

export function setProjectOpen(open) {
  projectOpen = open;
  updateView();
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

const isDirty = (tab) => tab.kind === "text" && tab.model.getAlternativeVersionId() !== tab.savedVersion;

export function anyDirty() {
  return [...tabs.values()].some(isDirty);
}

function notifyDirty() {
  const dirty = anyDirty();
  if (dirty !== lastDirty) {
    lastDirty = dirty;
    handlers.onDirtyChange(dirty);
  }
}

// focus: move keyboard focus to the editor (false keeps it in the file tree).
export function openTab(path, data, { focus = true } = {}) {
  if (!tabs.has(path)) {
    const tab = { path, kind: data.kind, data, encoding: data.encoding, viewState: null };
    if (data.kind === "text") {
      const language = LANGUAGE_BY_EXT[extOf(path)] || "plaintext";
      const uri = monaco.Uri.parse(`inmemory://tab/${++modelCounter}/${encodeURIComponent(nameOf(path))}`);
      tab.model = monaco.editor.createModel(data.text, language, uri);
      tab.savedVersion = tab.model.getAlternativeVersionId();
      tab.model.onDidChangeContent(() => {
        renderTabs();
        notifyDirty();
      });
      if (extOf(path) === "tex") attachSpell(tab.model);
    }
    tabs.set(path, tab);
    applyMarkers(tab);
  }
  activate(path, { focus });
}

export const isOpen = (path) => tabs.has(path);
export const getActivePath = () => activePath;
export const openPaths = () => [...tabs.keys()];

export function activate(path, { focus = true } = {}) {
  const current = tabs.get(activePath);
  if (current?.kind === "text") current.viewState = editor.saveViewState();
  activePath = tabs.has(path) ? path : null;
  const tab = tabs.get(activePath);
  if (tab?.kind === "text") {
    editor.setModel(tab.model);
    if (tab.viewState) editor.restoreViewState(tab.viewState);
    if (focus) editor.focus();
    handlers.onCursor(editor.getPosition());
  } else {
    editor.setModel(null);
    handlers.onCursor(null);
  }
  updateView();
  renderTabs();
  handlers.onActiveChange(activePath);
}

export function cycleTab(step) {
  const paths = openPaths();
  if (paths.length < 2) return;
  const i = paths.indexOf(activePath);
  activate(paths[(i + step + paths.length) % paths.length]);
}

function dropTab(path) {
  const tab = tabs.get(path);
  if (!tab) return;
  const paths = openPaths();
  const index = paths.indexOf(path);
  tabs.delete(path);
  if (activePath === path) {
    activePath = null; // don't save view state of the closing tab
    const next = paths[index + 1] ?? paths[index - 1] ?? null;
    activate(next && tabs.has(next) ? next : null);
  }
  tab.model?.dispose();
  renderTabs();
  notifyDirty();
}

export async function closeTab(path, { force = false } = {}) {
  const tab = tabs.get(path);
  if (!tab) return true;
  if (!force && isDirty(tab)) {
    const discard = await confirmDialog({
      title: "Unsaved changes",
      message: `${nameOf(path)} has unsaved changes. Close it and discard them?`,
      okLabel: "Discard changes",
      danger: true,
    });
    if (!discard) return false;
  }
  dropTab(path);
  return true;
}

export function closeAll() {
  for (const path of openPaths()) dropTab(path);
}

// Close tabs for a deleted file or folder (and everything below it).
export function closeUnder(rel) {
  for (const path of openPaths()) {
    if (path === rel || path.startsWith(rel + "/")) dropTab(path);
  }
}

// Follow a rename of a file or folder.
export function renamePaths(oldRel, newRel) {
  const entries = [...tabs.entries()].map(([path, tab]) => {
    if (path === oldRel || path.startsWith(oldRel + "/")) {
      tab.path = newRel + path.slice(oldRel.length);
      if (tab.model) monaco.editor.setModelLanguage(tab.model, LANGUAGE_BY_EXT[extOf(tab.path)] || "plaintext");
      if (activePath === path) activePath = tab.path;
    }
    return [tab.path, tab];
  });
  tabs.clear();
  for (const [path, tab] of entries) {
    tabs.set(path, tab);
    applyMarkers(tab);
  }
  renderTabs();
  handlers.onActiveChange(activePath);
}

// ---------------------------------------------------------------------------
// Build problems as editor markers (squiggles; F8 jumps between them)
// ---------------------------------------------------------------------------

export function setProblems(problems) {
  problemsByPath = new Map();
  for (const p of problems || []) {
    if (!p.file || !p.line) continue;
    if (!problemsByPath.has(p.file)) problemsByPath.set(p.file, []);
    problemsByPath.get(p.file).push(p);
  }
  for (const tab of tabs.values()) applyMarkers(tab);
}

const SEVERITY = () => ({
  error: monaco.MarkerSeverity.Error,
  warning: monaco.MarkerSeverity.Warning,
  info: monaco.MarkerSeverity.Info,
});

// Where on the line to put the squiggle: TeX's context shows the source text up to
// the error point, so underline the last token before it; otherwise the whole line.
function markerRange(model, p) {
  const line = Math.min(Math.max(1, p.line), model.getLineCount());
  const text = model.getLineContent(line);
  const before = (p.context || "").replace(/^\.\.\./, "");
  const at = before ? text.indexOf(before) : -1;
  if (at >= 0) {
    const end = at + before.length;
    const tokenStart = Math.max(before.lastIndexOf("\\"), before.search(/\S+$/));
    return { line, start: at + Math.max(0, tokenStart) + 1, end: end + 1 };
  }
  const first = text.search(/\S/);
  return { line, start: first >= 0 ? first + 1 : 1, end: text.length + 1 };
}

function applyMarkers(tab) {
  if (!tab.model) return;
  const severity = SEVERITY();
  const markers = (problemsByPath.get(tab.path) || []).map((p) => {
    const r = markerRange(tab.model, p);
    return {
      severity: severity[p.severity],
      message: p.message,
      source: p.source,
      startLineNumber: r.line,
      startColumn: r.start,
      endLineNumber: r.line,
      endColumn: Math.max(r.end, r.start + 1),
    };
  });
  monaco.editor.setModelMarkers(tab.model, "latex-build", markers);
}

// Files with unsaved edits: [{ path, text, encoding, version }]
export function dirtyFiles() {
  return [...tabs.values()].filter(isDirty).map((tab) => ({
    path: tab.path,
    text: tab.model.getValue(),
    encoding: tab.encoding,
    version: tab.model.getAlternativeVersionId(),
  }));
}

// Record a successful save of the content as it was at `version`.
export function markSaved(path, version, encoding) {
  const tab = tabs.get(path);
  if (!tab) return;
  tab.savedVersion = version;
  if (encoding) tab.encoding = encoding;
  renderTabs();
  notifyDirty();
}

export function focusEditor() {
  if (tabs.get(activePath)?.kind === "text") editor.focus();
}

// ---------------------------------------------------------------------------
// Formatting helpers (used by format.js)
// ---------------------------------------------------------------------------

const textTabActive = () => tabs.get(activePath)?.kind === "text";

// Wrap each selection in before…after, or remove the wrapper if it is already there
// (around the selection, or the selection itself starts/ends with it). An empty
// selection inserts before|after with the cursor in between.
export function toggleWrap(before, after) {
  if (!textTabActive()) return;
  const model = editor.getModel();
  const edits = [];
  const selections = [];
  for (const sel of editor.getSelections()) {
    const text = model.getValueInRange(sel);
    const start = model.getOffsetAt(sel.getStartPosition());
    const end = model.getOffsetAt(sel.getEndPosition());
    const full = model.getValue();
    const outerBefore = full.slice(Math.max(0, start - before.length), start);
    const outerAfter = full.slice(end, end + after.length);
    const pos = (offset) => model.getPositionAt(offset);
    const range = (a, b) => monaco.Range.fromPositions(pos(a), pos(b));

    const wrapLength = before.length + after.length;
    if (outerBefore === before && outerAfter === after) {
      // \textbf{[sel]} -> [sel]  (also \textbf{|} -> | for a second Ctrl+B)
      edits.push({ range: range(end, end + after.length), text: "" }, { range: range(start - before.length, start), text: "" });
      selections.push({ at: start, start: start - before.length, length: text.length, delta: -wrapLength });
    } else if (text.length > wrapLength && text.startsWith(before) && text.endsWith(after)) {
      // [\textbf{x}] -> [x]
      const inner = text.slice(before.length, text.length - after.length);
      edits.push({ range: sel, text: inner });
      selections.push({ at: start, start, length: inner.length, delta: -wrapLength });
    } else {
      edits.push({ range: sel, text: before + text + after });
      selections.push({ at: start, start: start + before.length, length: text.length, delta: wrapLength });
    }
  }
  applyEdits(edits, selections);
}

// selections: [{at, start, length, delta}] in offsets of the text before editing, where
// `start` already accounts for the selection's own edit; `delta` is its length change.
function applyEdits(edits, selections) {
  const model = editor.getModel();
  editor.pushUndoStop();
  editor.executeEdits("format", edits);
  // Each selection moves by the length changes of the edits before it.
  const sorted = [...selections].sort((a, b) => a.at - b.at);
  let shift = 0;
  for (const s of sorted) {
    s.start += shift;
    shift += s.delta;
  }
  editor.setSelections(selections.map((s) => {
    const a = model.getPositionAt(s.start);
    const b = model.getPositionAt(s.start + s.length);
    return new monaco.Selection(a.lineNumber, a.column, b.lineNumber, b.column);
  }));
  editor.pushUndoStop();
  editor.focus();
}

// Replace the selections with `text` (symbols such as € or °C).
export function insertText(text) {
  if (!textTabActive()) return;
  editor.pushUndoStop();
  editor.executeEdits("format", editor.getSelections().map((range) => ({ range, text, forceMoveMarkers: true })));
  editor.pushUndoStop();
  editor.focus();
}

// Turn the selected lines into \item lines of a list (or insert an empty list).
export function makeList(env) {
  if (!textTabActive()) return;
  const model = editor.getModel();
  const sel = editor.getSelection();
  const indent = model.getLineContent(sel.startLineNumber).match(/^\s*/)[0];
  const snippet = editor.getContribution("snippetController2");
  if (sel.isEmpty()) {
    snippet.insert(`\\\\begin{${env}}\n\t\\\\item $0\n\\\\end{${env}}`);
  } else {
    const endLine = sel.endColumn === 1 && sel.endLineNumber > sel.startLineNumber ? sel.endLineNumber - 1 : sel.endLineNumber;
    const range = new monaco.Range(sel.startLineNumber, 1, endLine, model.getLineMaxColumn(endLine));
    const items = model.getValueInRange(range).split(/\r?\n/).filter((l) => l.trim())
      .map((l) => `${indent}  \\item ${l.trim().replace(/^\\item\s*/, "")}`);
    editor.executeEdits("format", [{ range, text: [`${indent}\\begin{${env}}`, ...items, `${indent}\\end{${env}}`].join("\n") }]);
  }
  editor.focus();
}

export function runAction(id) {
  if (!textTabActive()) return;
  editor.focus();
  editor.getAction(id)?.run();
}

// [["CtrlCmd+KeyB", fn], …]: editor-level shortcuts (they win over Monaco's defaults,
// e.g. Ctrl+I "trigger suggest" and Ctrl+U "cursor undo").
export function addEditorKeybindings(bindings) {
  for (const [combo, fn] of bindings) {
    const key = combo.split("+").reduce((acc, part) => acc | (part in monaco.KeyMod ? monaco.KeyMod[part] : monaco.KeyCode[part]), 0);
    editor.addCommand(key, fn);
  }
}

// Selected text in the active file (single line only), for pre-filling the search box.
export function selectionText() {
  if (tabs.get(activePath)?.kind !== "text") return "";
  const text = editor.getModel().getValueInRange(editor.getSelection());
  return text.includes("\n") ? "" : text;
}

// Select `length` characters at line:column of the active file and scroll there.
export function selectRange(line, column, length) {
  const model = editor.getModel();
  if (!model) return;
  const range = new monaco.Range(line, column, line, column + length);
  editor.setSelection(range);
  editor.revealRangeInCenterIfOutsideViewport(range);
  editor.focus();
}

// Replace an open tab's content with what is now on disk (after a project-wide replace).
// Done as an edit, so Ctrl+Z still undoes it in the editor.
export function reloadFile(path, data) {
  const tab = tabs.get(path);
  if (!tab?.model || data.kind !== "text" || tab.model.getValue() === data.text) return;
  tab.model.pushStackElement(); // its own undo step, separate from earlier typing
  tab.model.pushEditOperations([], [{ range: tab.model.getFullModelRange(), text: data.text }], () => null);
  tab.model.pushStackElement();
  tab.savedVersion = tab.model.getAlternativeVersionId();
  tab.encoding = data.encoding;
  renderTabs();
  notifyDirty();
}

// Cursor of the active text file: { path, line, column } or null.
export function cursor() {
  const tab = tabs.get(activePath);
  if (tab?.kind !== "text") return null;
  const pos = editor.getPosition();
  return { path: tab.path, line: pos.lineNumber, column: pos.column };
}

let flashDecorations = null;

// Briefly highlight a whole line of the active file (after a jump from the PDF).
export function flashLine(line) {
  flashDecorations?.clear();
  flashDecorations = editor.createDecorationsCollection([{
    range: new monaco.Range(line, 1, line, 1),
    options: { isWholeLine: true, className: "line-flash" },
  }]);
  const current = flashDecorations;
  setTimeout(() => current.clear(), 1600);
}

// Put the cursor on `line` of the active file (at the problem's squiggle when known).
export function revealLine(line, problem = null) {
  const model = editor.getModel();
  if (!model) return;
  const target = Math.min(Math.max(1, line), model.getLineCount());
  const column = problem ? markerRange(model, { ...problem, line: target }).start : 1;
  editor.revealLineInCenter(target);
  editor.setPosition({ lineNumber: target, column });
  editor.focus();
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function updateView() {
  const tab = tabs.get(activePath);
  editorEl.hidden = tab?.kind !== "text";
  formatBarEl.hidden = tab?.kind !== "text" || tab.model.getLanguageId() !== "latex";
  fileViewEl.hidden = !tab || tab.kind === "text";
  noFileEl.hidden = !projectOpen || !!tab;
  if (tab && tab.kind !== "text") {
    fileViewEl.replaceChildren();
    if (tab.kind === "image") {
      const img = document.createElement("img");
      img.src = tab.data.url;
      img.alt = nameOf(tab.path);
      fileViewEl.append(img);
    } else {
      const p = document.createElement("p");
      p.className = "empty-state";
      p.textContent = `${nameOf(tab.path)} is a binary file (${(tab.data.size / 1024).toFixed(0)} KB) and can't be shown here.`;
      fileViewEl.append(p);
    }
  }
}

function renderTabs() {
  const names = openPaths().map(nameOf);
  tabsEl.replaceChildren();
  for (const tab of tabs.values()) {
    const name = nameOf(tab.path);
    const el = document.createElement("div");
    el.className = "tab";
    el.classList.toggle("active", tab.path === activePath);
    el.classList.toggle("dirty", isDirty(tab));
    el.setAttribute("role", "tab");
    el.setAttribute("aria-selected", tab.path === activePath);
    el.title = tab.path;

    const label = document.createElement("span");
    label.className = "tab-label";
    label.textContent = name;
    // Same file name open twice: show the folder to tell them apart.
    if (names.filter((n) => n === name).length > 1 && tab.path.includes("/")) {
      const dir = document.createElement("small");
      dir.textContent = tab.path.slice(0, tab.path.lastIndexOf("/"));
      label.append(dir);
    }

    const close = document.createElement("button");
    close.className = "tab-close";
    close.title = "Close (Ctrl+W)";
    close.setAttribute("aria-label", `Close ${name}`);
    close.addEventListener("click", (e) => {
      e.stopPropagation();
      closeTab(tab.path);
    });

    el.append(label, close);
    el.addEventListener("click", () => activate(tab.path));
    el.addEventListener("auxclick", (e) => {
      if (e.button === 1) closeTab(tab.path);
    });
    tabsEl.append(el);
  }
  tabsEl.querySelector(".tab.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
}
