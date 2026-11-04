// Formatting toolbar above the editor (bold, italic, symbols, lists…) and the
// Ctrl+B / Ctrl+I / Ctrl+U shortcuts. Wrapping commands toggle: applying Bold
// to text that is already \textbf{…} removes it again.

import * as editor from "./editor.js";
import { openReferenceDialog } from "./references.js";

// [id, button label (HTML), tooltip, action]
const wrap = (before, after = "}") => () => editor.toggleWrap(before, after);
const insert = (text) => () => editor.insertText(text);

export const ACTIONS = [
  ["bold", "<b>B</b>", "Bold \\textbf (Ctrl+B)", wrap("\\textbf{")],
  ["italic", "<i>I</i>", "Italic \\textit (Ctrl+I)", wrap("\\textit{")],
  ["underline", "<u>U</u>", "Underline \\underline (Ctrl+U)", wrap("\\underline{")],
  ["emph", "<i>e</i>", "Emphasis \\emph", wrap("\\emph{")],
  ["mono", "<code>T</code>", "Monospace \\texttt", wrap("\\texttt{")],
  "|",
  ["superscript", "x<sup>2</sup>", "Superscript \\textsuperscript", wrap("\\textsuperscript{")],
  ["subscript", "x<sub>2</sub>", "Subscript \\textsubscript", wrap("\\textsubscript{")],
  ["math", "<i>$x$</i>", "Inline math $…$ (Ctrl+M)", wrap("$", "$")],
  "|",
  ["euro", "€", "Euro sign €", insert("€")],
  ["celsius", "°C", "Degrees Celsius °C", insert("°C")],
  ["degree", "°", "Degree sign °", insert("°")],
  ["plusminus", "±", "Plus-minus ±", insert("±")],
  ["micro", "µ", "Micro sign µ", insert("µ")],
  "|",
  ["itemize", "•≡", "Bulleted list (selected lines become items)", () => editor.makeList("itemize")],
  ["enumerate", "1≡", "Numbered list (selected lines become items)", () => editor.makeList("enumerate")],
  ["section", "§", "Section heading \\section", wrap("\\section{")],
  ["reference", "<code>[1]</code>", "Add a web reference to the bibliography and \\cite it here (Ctrl+Shift+R)", openReferenceDialog],
  ["comment", "%", "Comment / uncomment lines (Ctrl+/)", () => editor.runAction("editor.action.commentLine")],
];

const byId = Object.fromEntries(ACTIONS.filter((a) => a !== "|").map((a) => [a[0], a[3]]));

export function initFormatBar() {
  const bar = document.getElementById("format-bar");
  for (const action of ACTIONS) {
    if (action === "|") {
      bar.append(Object.assign(document.createElement("span"), { className: "format-sep" }));
      continue;
    }
    const [id, label, title, run] = action;
    const button = document.createElement("button");
    button.className = "format-btn";
    button.dataset.action = id;
    button.innerHTML = label;
    button.title = title;
    button.setAttribute("aria-label", title);
    // Keep the editor's focus and selection when the button is pressed.
    button.addEventListener("mousedown", (e) => e.preventDefault());
    button.addEventListener("click", run);
    bar.append(button);
  }
  editor.addEditorKeybindings([
    ["CtrlCmd+KeyB", byId.bold],
    ["CtrlCmd+KeyI", byId.italic],
    ["CtrlCmd+KeyU", byId.underline],
    ["CtrlCmd+KeyM", byId.math],
  ]);
}
