// Spell checking for .tex files: a Web Worker (spell/worker.js) holds the
// dictionary; misspellings become "hint" markers styled as a wavy underline,
// and quick fixes (Ctrl+.) offer suggestions or "Add to project dictionary".
// The language and the project's word list live in the project config.

import { call } from "./bridge.js";
import { contextMenu, showError, toast } from "./ui.js";

export const LANGUAGES = { en: "English (US)", "en-GB": "English (UK)", ca: "Català", es: "Español", off: "Off" };
const SOURCE = "spelling";
const DEBOUNCE_MS = 400;
const ADD_COMMAND = "latexeditor.addSpellWord";

let monaco = null;
let worker = null;
let language = "off";
let ready = false;
let projectOpen = false;
let nextId = 1;
const pending = new Map(); // request id -> resolve
const suggestionCache = new Map();
const models = new Set();
const timers = new WeakMap();
const decorations = new WeakMap(); // model -> decoration ids (the full-word underline)

// Hint markers drive hover and quick fixes, but Monaco only draws a short mark
// under their first letters, so the whole word gets its own underline decoration.
function setIssues(model, issues) {
  monaco.editor.setModelMarkers(model, SOURCE, issues.map((i) => ({
    severity: monaco.MarkerSeverity.Hint,
    source: SOURCE,
    message: `“${i.word}” is not in the ${LANGUAGES[language]} dictionary`,
    startLineNumber: i.line,
    startColumn: i.column,
    endLineNumber: i.line,
    endColumn: i.column + i.length,
  })));
  decorations.set(model, model.deltaDecorations(decorations.get(model) || [], issues.map((i) => ({
    range: new monaco.Range(i.line, i.column, i.line, i.column + i.length),
    options: { inlineClassName: "spell-error", stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges },
  }))));
}
const statusEl = document.getElementById("status-spell");

function setStatus(text, title = "Spell-check language (click to change)") {
  statusEl.textContent = text;
  statusEl.title = title;
  statusEl.hidden = !projectOpen;
}

function request(message) {
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    worker.postMessage({ ...message, id });
  });
}

function onWorkerMessage({ data }) {
  if (data.type === "ready") {
    ready = data.lang === language;
    if (ready) {
      setStatus(`Spelling: ${LANGUAGES[language]}`);
      checkAll();
    }
  } else if (data.type === "error") {
    setStatus("Spelling: unavailable", data.message);
  } else if (pending.has(data.id)) {
    pending.get(data.id)(data);
    pending.delete(data.id);
  }
}

function clearMarkers() {
  for (const model of models) {
    if (!model.isDisposed()) setIssues(model, []);
  }
}

async function check(model) {
  if (model.isDisposed() || !ready || language === "off") return;
  const version = model.getVersionId();
  const { issues } = await request({ type: "check", text: model.getValue() });
  if (model.isDisposed() || model.getVersionId() !== version) return; // edited meanwhile; a newer check is queued
  setIssues(model, issues);
}

function schedule(model, delay = DEBOUNCE_MS) {
  clearTimeout(timers.get(model));
  timers.set(model, setTimeout(() => check(model), delay));
}

function checkAll() {
  for (const model of [...models]) {
    if (model.isDisposed()) models.delete(model);
    else schedule(model, 0);
  }
}

// Spell-check a LaTeX editor model from now on (called by editor.js when a .tex tab opens).
export function attachSpell(model) {
  if (!monaco || models.has(model)) return;
  models.add(model);
  model.onDidChangeContent(() => schedule(model));
  model.onWillDispose(() => models.delete(model));
  schedule(model, 0);
}

async function suggestions(word) {
  if (!suggestionCache.has(word)) {
    suggestionCache.set(word, request({ type: "suggest", word }).then((r) => r.list));
  }
  return suggestionCache.get(word);
}

async function addWord(word) {
  try {
    await call("add_spell_word", word);
    worker.postMessage({ type: "add", word });
    checkAll();
    toast(`Added “${word}” to the project dictionary`, "success");
  } catch (err) {
    showError(err);
  }
}

async function setLanguage(lang) {
  try {
    applySettings(await call("set_spell_language", lang));
  } catch (err) {
    showError(err);
  }
}

function applySettings(settings) {
  suggestionCache.clear();
  language = settings.language;
  ready = false;
  clearMarkers();
  if (language === "off") {
    setStatus("Spelling: Off");
    return;
  }
  setStatus(`Spelling: loading ${LANGUAGES[language]}…`, "Loading the dictionary (Català takes about 10 seconds the first time)");
  worker.postMessage({ type: "init", lang: language, words: settings.words });
}

// settings from api.spell_settings(), or null when no project is open.
export function setSpellProject(settings) {
  projectOpen = !!settings;
  if (!settings) {
    language = "off";
    ready = false;
    clearMarkers();
    setStatus("");
    return;
  }
  applySettings(settings);
}

export function initSpell(monacoRef) {
  monaco = monacoRef;
  worker = new Worker(new URL("./spell/worker.js", import.meta.url));
  worker.onmessage = onWorkerMessage;
  worker.onerror = (e) => setStatus("Spelling: unavailable", e.message);

  monaco.editor.registerCommand(ADD_COMMAND, (_accessor, word) => addWord(word));

  // typo.js needs 1-3 s per suggestion list, and the quick-fix menu does not wait
  // that long: start computing as soon as the cursor rests on a misspelled word.
  monaco.editor.onDidCreateEditor((ed) => {
    let timer = null;
    ed.onDidChangeCursorPosition(({ position }) => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const model = ed.getModel();
        if (!model || !ready) return;
        const marker = monaco.editor.getModelMarkers({ owner: SOURCE, resource: model.uri }).find((m) =>
          m.startLineNumber === position.lineNumber && m.startColumn <= position.column && position.column <= m.endColumn);
        if (marker) {
          suggestions(model.getValueInRange(new monaco.Range(marker.startLineNumber, marker.startColumn, marker.endLineNumber, marker.endColumn)));
        }
      }, 250);
    });
  });

  monaco.languages.registerCodeActionProvider("latex", {
    async provideCodeActions(model, _range, context) {
      const markers = context.markers.filter((m) => m.source === SOURCE);
      const actions = [];
      for (const marker of markers) {
        const range = new monaco.Range(marker.startLineNumber, marker.startColumn, marker.endLineNumber, marker.endColumn);
        const word = model.getValueInRange(range);
        (await suggestions(word)).forEach((s, i) => actions.push({
          title: `Change to “${s}”`,
          kind: "quickfix",
          diagnostics: [marker],
          isPreferred: i === 0,
          edit: { edits: [{ resource: model.uri, textEdit: { range, text: s }, versionId: model.getVersionId() }] },
        }));
        actions.push({
          title: `Add “${word}” to the project dictionary`,
          kind: "quickfix",
          diagnostics: [marker],
          command: { id: ADD_COMMAND, title: "Add to dictionary", arguments: [word] },
        });
      }
      return { actions, dispose() {} };
    },
  }, { providedCodeActionKinds: ["quickfix"] });

  statusEl.addEventListener("click", () => {
    const rect = statusEl.getBoundingClientRect();
    // opens upwards from the status bar (contextMenu keeps it on screen)
    contextMenu(rect.left, rect.top - 160, Object.entries(LANGUAGES).map(([code, name]) => ({
      label: `${code === language ? "✓ " : ""}${name}`,
      action: () => setLanguage(code),
    })));
  });
}
