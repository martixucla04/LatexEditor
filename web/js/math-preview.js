// Equation preview: while the cursor is inside math ($…$, \(…\), \[…\], $$…$$ or an
// equation/align/gather/multline… environment), a box under it shows the math
// rendered by MathJax (vendored, SVG output, loaded the first time it is needed).

const MATH_ENVS = "equation|align|gather|multline|eqnarray|flalign|alignat|displaymath|math";
// Display math in a window of text: an environment, \[ … \] or $$ … $$ (not \\[2pt] line breaks).
const DISPLAY = new RegExp(
  String.raw`\\begin\{(${MATH_ENVS})(\*?)\}[\s\S]*?\\end\{\1\2\}` +
  String.raw`|(?<!\\)\\\[([\s\S]*?)\\\]` +
  String.raw`|(?<!\\)\$\$([\s\S]*?)(?<!\\)\$\$`, "g");
const INLINE = /(?<!\\)\$((?:[^$\\]|\\.)+?)(?<!\\)\$|(?<!\\)\\\(([\s\S]*?)\\\)/g;
const WINDOW_LINES = 60; // how far up/down an environment may reach
const DELAY_MS = 150;

let monaco = null;
let editor = null;
let widget = null;
let node = null;
let position = null;
let timer = null;
let lastTex = null;
let mathJax = null; // Promise of window.MathJax once loaded

// Comments blanked with spaces, so offsets still match the editor text.
const stripComments = (text) => text.replace(/(?<!\\)%.*$/gm, (m) => " ".repeat(m.length));

// The math around `pos`: { tex, display, line, column } or null.
export function findMath(model, pos) {
  const first = Math.max(1, pos.lineNumber - WINDOW_LINES);
  const last = Math.min(model.getLineCount(), pos.lineNumber + WINDOW_LINES);
  const range = { startLineNumber: first, startColumn: 1, endLineNumber: last, endColumn: model.getLineMaxColumn(last) };
  const text = stripComments(model.getValueInRange(range));
  const cursor = model.getOffsetAt(pos) - model.getOffsetAt({ lineNumber: first, column: 1 });

  for (const m of text.matchAll(DISPLAY)) {
    if (m.index > cursor) break;
    const end = m.index + m[0].length;
    if (cursor > end) continue;
    const endPos = model.getPositionAt(model.getOffsetAt({ lineNumber: first, column: 1 }) + end);
    // A whole environment is passed to MathJax (it knows align, gather…); \label would be "multiply defined".
    const tex = (m[1] ? m[0] : (m[3] ?? m[4])).replace(/\\label\{[^}]*\}/g, "");
    return { tex, display: true, line: endPos.lineNumber, column: 1 };
  }

  const line = stripComments(model.getLineContent(pos.lineNumber));
  const col = pos.column - 1;
  for (const m of line.matchAll(INLINE)) {
    if (m.index > col) break;
    if (col <= m.index + m[0].length) {
      return { tex: m[1] ?? m[2], display: false, line: pos.lineNumber, column: m.index + 1 };
    }
  }
  return null;
}

function loadMathJax() {
  if (!mathJax) {
    mathJax = new Promise((resolve, reject) => {
      window.MathJax = {
        // no \href/\class/\style: a formula in a project from someone else must not get a javascript: link
        tex: { tags: "none", packages: { "[-]": ["html"] } },
        svg: { fontCache: "local" },
        options: { enableMenu: false },
        startup: {
          typeset: false,
          ready() {
            window.MathJax.startup.defaultReady();
            // its CSS hides the screen-reader copy of each formula (otherwise shown twice)
            document.head.append(window.MathJax.svgStylesheet());
            resolve(window.MathJax);
          },
        },
      };
      const script = document.createElement("script");
      script.src = "vendor/mathjax/tex-svg-full.js";
      script.onerror = () => reject(new Error("Could not load the equation renderer (vendor/mathjax)."));
      document.head.append(script);
    });
  }
  return mathJax;
}

async function render(math) {
  if (math.tex.trim() === "") return hide();
  position = { lineNumber: math.line, column: math.column };
  if (math.tex === lastTex) {
    editor.layoutContentWidget(widget);
    return;
  }
  lastTex = math.tex;
  try {
    const MathJax = await loadMathJax();
    if (lastTex !== math.tex) return; // the cursor moved on while loading
    MathJax.texReset();
    const out = await MathJax.tex2svgPromise(math.tex, { display: math.display });
    if (lastTex !== math.tex) return;
    const error = out.querySelector("[data-mjx-error]");
    node.classList.toggle("error", !!error);
    node.replaceChildren(error ? document.createTextNode(error.getAttribute("data-mjx-error")) : out);
  } catch (err) {
    node.classList.add("error");
    node.textContent = err.message;
  }
  node.hidden = false;
  editor.layoutContentWidget(widget);
}

function hide() {
  lastTex = null;
  position = null;
  if (node) node.hidden = true;
  editor.layoutContentWidget(widget);
}

function update() {
  const model = editor.getModel();
  const pos = editor.getPosition();
  if (!model || !pos || model.getLanguageId() !== "latex") return hide();
  const math = findMath(model, pos);
  if (math) render(math);
  else hide();
}

export function initMathPreview(monacoApi, editorInstance) {
  monaco = monacoApi;
  editor = editorInstance;
  node = document.createElement("div");
  node.className = "math-preview";
  node.hidden = true;
  widget = {
    getId: () => "latexeditor.mathPreview",
    getDomNode: () => node,
    getPosition: () => position && {
      position,
      preference: [monaco.editor.ContentWidgetPositionPreference.BELOW, monaco.editor.ContentWidgetPositionPreference.ABOVE],
    },
  };
  editor.addContentWidget(widget);
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(update, DELAY_MS);
  };
  editor.onDidChangeCursorPosition(schedule);
  editor.onDidChangeModelContent(schedule);
  editor.onDidChangeModel(hide);
}
