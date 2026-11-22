// LaTeX autocomplete: commands after "\", environments after \begin{ / \end{,
// labels after \ref{, bibliography keys after \cite{, project files after
// \input{ / \includegraphics{ / \addbibresource{, packages and classes.
// Project data (labels, .bib entries, user macros, files) comes from Python
// (app/completions.py); labels in unsaved buffers are scanned here so a label
// typed a moment ago can be referenced before saving.

import { CLASSES, COMMANDS, ENVIRONMENTS, PACKAGES } from "./latex-data.js";

const REF_COMMANDS = /^(?:ref|eqref|autoref|[cC]ref|cpageref|pageref|nameref|vref|labelcref|subref)$/;
const CITE_COMMANDS = /^(?:[cC]ite[a-z]*|[pP]arencite|[tT]extcite|[aA]utocite|[fF]ootcite|[sS]martcite|supercite|nocite|fullcite|footfullcite)s?$/;
const IMAGE_EXT = /\.(png|jpe?g|pdf|eps|svg|gif|bmp)$/i;
// Text before the cursor that ends in an empty image argument: \includegraphics[width=…]{
export const EMPTY_IMAGE_ARGUMENT = /\\(?:includegraphics|includesvg|includepdf)\*?(?:\[[^\]]*\]){0,2}\{$/;
const LABEL = /\\label\{([^}\s]+)\}/g;

let project = { labels: [], citations: [], commands: [], environments: [], files: [] };
let openBuffers = () => []; // [{ path, text, dirty }]

export function setProjectData(data) {
  project = data || { labels: [], citations: [], commands: [], environments: [], files: [] };
}

// Labels from disk, with files that have unsaved edits re-scanned from the editor.
function currentLabels() {
  const dirty = openBuffers().filter((b) => b.dirty && b.path.endsWith(".tex"));
  const dirtyPaths = new Set(dirty.map((b) => b.path));
  const labels = project.labels.filter((l) => !dirtyPaths.has(l.file));
  for (const buffer of dirty) {
    buffer.text.split("\n").forEach((line, i) => {
      const code = line.replace(/(?<!\\)%.*/, "");
      for (const m of code.matchAll(LABEL)) {
        labels.push({ name: m[1], file: buffer.path, line: i + 1, context: code.slice(0, m.index).trim() });
      }
    });
  }
  return labels;
}

// The environment that \end{ should close: the innermost \begin without an \end.
function openEnvironment(model, position) {
  const text = model.getValueInRange({ startLineNumber: 1, startColumn: 1, endLineNumber: position.lineNumber, endColumn: position.column });
  const stack = [];
  for (const m of text.replace(/(?<!\\)%.*$/gm, "").matchAll(/\\(begin|end)\{([^}]+)\}/g)) {
    if (m[1] === "begin") stack.push(m[2]);
    else if (stack[stack.length - 1] === m[2]) stack.pop();
  }
  return stack.pop() || null;
}

export function registerCompletions(monaco, { buffers }) {
  openBuffers = buffers;
  const Kind = monaco.languages.CompletionItemKind;
  const Rule = monaco.languages.CompletionItemInsertTextRule;

  function argumentItems(cmd, partial, range, model, position) {
    if (REF_COMMANDS.test(cmd)) {
      return currentLabels().map((l) => ({
        label: l.name,
        kind: Kind.Reference,
        detail: `${l.file}:${l.line}`,
        documentation: l.context || undefined,
        insertText: l.name,
        // \eqref lists equation labels first
        sortText: `${cmd === "eqref" && !l.name.startsWith("eq") ? 1 : 0}${l.name}`,
        range,
      }));
    }
    if (CITE_COMMANDS.test(cmd)) {
      return project.citations.map((c) => ({
        label: { label: c.key, description: c.year },
        kind: Kind.Value,
        detail: [c.author, c.year && `(${c.year})`].filter(Boolean).join(" "),
        documentation: { value: [`**${c.title || "(no title)"}**`, c.venue, `${c.type} · ${c.file}:${c.line}`].filter(Boolean).join("\n\n") },
        insertText: c.key,
        filterText: `${c.key} ${c.author} ${c.title}`,
        range,
      }));
    }
    // filterText starts with the file name, so typing "em01" finds Imagenes/Introduccio/em01.jpg
    const fileItems = (filter, transform) => project.files.filter(filter).map((f) => ({
      label: transform(f), kind: Kind.File, insertText: transform(f), range,
      filterText: `${f.split("/").pop()} ${transform(f)}`,
    }));
    switch (cmd) {
      case "input": case "include": case "subfile": case "includeonly": case "import":
        return fileItems((f) => f.endsWith(".tex"), (f) => f.replace(/\.tex$/, ""));
      case "includegraphics": case "includesvg": case "includepdf":
        return fileItems((f) => IMAGE_EXT.test(f), (f) => f);
      case "addbibresource":
        return fileItems((f) => f.endsWith(".bib"), (f) => f);
      case "bibliography":
        return fileItems((f) => f.endsWith(".bib"), (f) => f.replace(/\.bib$/, ""));
      case "usepackage": case "RequirePackage":
        return PACKAGES.map((p) => ({ label: p, kind: Kind.Module, insertText: p, range }));
      case "documentclass":
        return CLASSES.map((c) => ({ label: c, kind: Kind.Module, insertText: c, range }));
      case "begin":
        return environmentItems(range, true);
      case "end": {
        const open = openEnvironment(model, position);
        return environmentItems(range, false).map((item) => ({
          ...item, sortText: item.label === open ? "0" : `1${item.label}`, preselect: item.label === open,
        }));
      }
      default:
        return [];
    }
  }

  // After \begin{: insert the name, closing brace, body and \end{name}.
  function environmentItems(range, withBody) {
    const builtIn = ENVIRONMENTS.map(([name, body, doc]) => ({ name, body, doc }));
    const user = project.environments
      .filter((e) => !ENVIRONMENTS.some(([n]) => n === e.name))
      .map((e) => ({ name: e.name, body: "\n\t${0}\n", doc: `Defined in ${e.file}:${e.line}` }));
    return [...builtIn, ...user].map(({ name, body, doc }) => ({
      label: name,
      kind: Kind.Snippet,
      documentation: doc,
      insertText: withBody ? `${name}}${body}\\\\end{${name}}` : `${name}}`,
      insertTextRules: withBody ? Rule.InsertAsSnippet : undefined,
      range,
    }));
  }

  function commandItems(range) {
    const items = COMMANDS.map(([name, snippet, doc]) => ({
      label: `\\${name}`,
      kind: Kind.Function,
      detail: doc,
      insertText: `\\\\${snippet ?? name}`,
      insertTextRules: Rule.InsertAsSnippet,
      range,
    }));
    for (const c of project.commands) {
      const args = Array.from({ length: c.args }, (_, i) => `{\${${i + 1}}}`).join("");
      items.push({
        label: `\\${c.name}`,
        kind: Kind.Function,
        detail: `Defined in ${c.file}:${c.line}`,
        insertText: `\\\\${c.name}${args}`,
        insertTextRules: Rule.InsertAsSnippet,
        sortText: `0${c.name}`, // project macros first
        range,
      });
    }
    // "\begin{itemize}" etc. straight from "\beg…"
    for (const [name, body, doc] of ENVIRONMENTS) {
      items.push({
        label: `\\begin{${name}}`,
        kind: Kind.Snippet,
        detail: doc,
        insertText: `\\\\begin{${name}}${body}\\\\end{${name}}`,
        insertTextRules: Rule.InsertAsSnippet,
        range,
      });
    }
    return items;
  }

  monaco.languages.registerCompletionItemProvider("latex", {
    triggerCharacters: ["\\", "{", ","],
    provideCompletionItems(model, position) {
      const lineNumber = position.lineNumber;
      const before = model.getLineContent(lineNumber).slice(0, position.column - 1).replace(/(?<!\\)%.*$/, "");
      if (before.length < position.column - 1) return { suggestions: [] }; // inside a comment
      const after = model.getLineContent(lineNumber).slice(position.column - 1);

      // Inside an argument: \cmd[opt][opt]{partial
      const arg = /\\([A-Za-z]+)\*?((?:\[[^\]]*\]){0,2})\{([^{}]*)$/.exec(before);
      if (arg) {
        const partial = arg[3].slice(arg[3].lastIndexOf(",") + 1).trimStart();
        // Replace an auto-inserted "}" right after the cursor when the item brings its own.
        const eatBrace = (arg[1] === "begin" || arg[1] === "end") && after.startsWith("}");
        const range = new monaco.Range(lineNumber, position.column - partial.length, lineNumber, position.column + (eatBrace ? 1 : 0));
        return { suggestions: argumentItems(arg[1], partial, range, model, position) };
      }

      // A command name: \partial
      // An even run of backslashes is line breaks (\\), not a command: suggest nothing.
      const cmd = /(\\+)([A-Za-z@]*)$/.exec(before);
      if (cmd && cmd[1].length % 2 === 1) {
        const range = new monaco.Range(lineNumber, position.column - cmd[2].length - 1, lineNumber, position.column);
        return { suggestions: commandItems(range) };
      }
      return { suggestions: [] };
    },
  });

  // Hover over \ref{x} or \cite{key} to see where it points.
  monaco.languages.registerHoverProvider("latex", {
    provideHover(model, position) {
      const line = model.getLineContent(position.lineNumber);
      for (const m of line.matchAll(/\\([A-Za-z]+)\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}/g)) {
        const start = m.index + m[0].indexOf("{") + 2;
        const end = m.index + m[0].length;
        if (position.column < start || position.column > end) continue;
        // which comma-separated key is under the cursor
        let offset = start;
        const key = m[2].split(",").find((k) => {
          const hit = position.column >= offset && position.column <= offset + k.length;
          offset += k.length + 1;
          return hit;
        })?.trim();
        if (!key) return null;
        if (REF_COMMANDS.test(m[1])) {
          const label = currentLabels().find((l) => l.name === key);
          return { contents: [{ value: label ? `**${key}** — ${label.file}:${label.line}\n\n\`${label.context}\`` : `Label **${key}** is not defined in this project.` }] };
        }
        if (CITE_COMMANDS.test(m[1])) {
          const c = project.citations.find((e) => e.key === key);
          return { contents: [{ value: c ? `**${c.title || key}**\n\n${c.author}${c.year ? ` (${c.year})` : ""}${c.venue ? `\n\n*${c.venue}*` : ""}` : `No bibliography entry **${key}** in this project's .bib files.` }] };
        }
      }
      return null;
    },
  });
}
