// LaTeX and BibTeX languages for Monaco: Monarch tokenizers (syntax colours),
// brackets, auto-closing pairs, % comments (Ctrl+/) and \begin…\end folding.
// Token names map to colours in the themes defined in editor.js.

const MATH_ENVS = "equation|align|gather|multline|flalign|alignat|eqnarray|math|displaymath|dmath|split";

const latexTokens = {
  defaultToken: "",
  tokenizer: {
    root: [
      [/(?<!\\)%.*$/, "comment"],
      // \begin{equation} … \end{equation} and friends: math mode
      [new RegExp(`(\\\\begin)(\\{)((?:${MATH_ENVS})\\*?)(\\})`),
        ["keyword.env", "delimiter.curly", "type.env", { token: "delimiter.curly", next: "@mathenv" }]],
      [/(\\(?:begin|end))(\{)([A-Za-z@*]+)(\})/, ["keyword.env", "delimiter.curly", "type.env", "delimiter.curly"]],
      [/(\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?)(?=[{[])/, "keyword.section"],
      [/(\\(?:label|ref|eqref|autoref|cref|Cref|pageref|nameref|vref))(\{)([^}]*)(\})/,
        ["keyword.ref", "delimiter.curly", "string.ref", "delimiter.curly"]],
      [/(\\(?:cite[a-zA-Z]*|[pPtT]extcite|parencite|[aA]utocite|footcite|nocite|fullcite|Cite[a-zA-Z]*))(\[[^\]]*\])?(\[[^\]]*\])?(\{)([^}]*)(\})/,
        ["keyword.ref", "string.option", "string.option", "delimiter.curly", "string.ref", "delimiter.curly"]],
      [/\\\[/, { token: "delimiter.math", next: "@displaymath" }],
      [/\\\(/, { token: "delimiter.math", next: "@parenmath" }],
      [/\$\$/, { token: "delimiter.math", next: "@dollardisplay" }],
      [/\$/, { token: "delimiter.math", next: "@inlinemath" }],
      [/\\[A-Za-z@]+\*?/, "keyword"],
      [/\\[^A-Za-z@]/, "keyword.escape"],
      [/[{}]/, "delimiter.curly"],
      [/[[\]]/, "delimiter.square"],
      [/[&~]/, "operator"],
      [/\d+(?:\.\d+)?(?:pt|mm|cm|in|em|ex|bp|pc|sp|mu)\b/, "number"],
    ],
    inlinemath: [
      [/(?<!\\)%.*$/, "comment"],
      [/\$/, { token: "delimiter.math", next: "@pop" }],
      { include: "@mathcommon" },
    ],
    dollardisplay: [
      [/(?<!\\)%.*$/, "comment"],
      [/\$\$/, { token: "delimiter.math", next: "@pop" }],
      { include: "@mathcommon" },
    ],
    displaymath: [
      [/(?<!\\)%.*$/, "comment"],
      [/\\\]/, { token: "delimiter.math", next: "@pop" }],
      { include: "@mathcommon" },
    ],
    parenmath: [
      [/(?<!\\)%.*$/, "comment"],
      [/\\\)/, { token: "delimiter.math", next: "@pop" }],
      { include: "@mathcommon" },
    ],
    mathenv: [
      [/(?<!\\)%.*$/, "comment"],
      [new RegExp(`(\\\\end)(\\{)((?:${MATH_ENVS})\\*?)(\\})`),
        ["keyword.env", "delimiter.curly", "type.env", { token: "delimiter.curly", next: "@pop" }]],
      [/(\\label)(\{)([^}]*)(\})/, ["keyword.ref", "delimiter.curly", "string.ref", "delimiter.curly"]],
      { include: "@mathcommon" },
    ],
    mathcommon: [
      [/\\[A-Za-z@]+/, "keyword.math"],
      [/\\./, "keyword.math"],
      [/[{}]/, "delimiter.curly"],
      [/[_^&]/, "operator.math"],
      [/\d+(\.\d+)?/, "number.math"],
      [/[^\\$%{}_^&\d\]\)]+/, "math"],
      [/./, "math"],
    ],
  },
};

const latexConfig = {
  comments: { lineComment: "%" },
  brackets: [["{", "}"], ["[", "]"], ["(", ")"]],
  autoClosingPairs: [
    { open: "{", close: "}" },
    { open: "[", close: "]" },
    { open: "(", close: ")" },
    { open: "\\(", close: "\\)" },
    { open: "\\[", close: "\\]" },
  ],
  surroundingPairs: [
    { open: "{", close: "}" },
    { open: "[", close: "]" },
    { open: "(", close: ")" },
    { open: "$", close: "$" },
    { open: "`", close: "'" },
  ],
  folding: {
    markers: { start: /^\s*\\begin\{/, end: /^\s*\\end\{/ },
  },
  // Words include a leading backslash so double-click selects a whole command.
  wordPattern: /\\?[A-Za-z@]+\*?|[^\s`~!@#$%^&*()\-=+[{\]}\\|;:'",.<>/?]+/,
  indentationRules: {
    increaseIndentPattern: /^\s*\\begin\{(?!document\})[^}]*\}/,
    decreaseIndentPattern: /^\s*\\end\{(?!document\})[^}]*\}/,
  },
};

const bibtexTokens = {
  ignoreCase: true,
  tokenizer: {
    root: [
      [/%.*$/, "comment"],
      [/(@)(string|preamble|comment)\b/, ["keyword.entry", "keyword.entry"]],
      [/(@)([A-Za-z]+)(\s*)([{(])(\s*)([^,\s{}()]+)/,
        ["keyword.entry", "keyword.entry", "", "delimiter.curly", "", "string.ref"]],
      [/([A-Za-z-]+)(\s*)(=)/, ["attribute.name", "", "operator"]],
      [/\{/, { token: "string", next: "@braced" }],
      [/"/, { token: "string", next: "@quoted" }],
      [/\d+/, "number"],
      [/#/, "operator"],
      [/[})]/, "delimiter.curly"],
    ],
    braced: [
      [/\{/, { token: "string", next: "@push" }],
      [/\}/, { token: "string", next: "@pop" }],
      [/\\[A-Za-z]+|\\./, "keyword"],
      [/[^{}\\]+/, "string"],
    ],
    quoted: [
      [/"/, { token: "string", next: "@pop" }],
      [/\\[A-Za-z]+|\\./, "keyword"],
      [/[^"\\]+/, "string"],
    ],
  },
};

const bibtexConfig = {
  comments: { lineComment: "%" },
  brackets: [["{", "}"], ["(", ")"]],
  autoClosingPairs: [{ open: "{", close: "}" }, { open: '"', close: '"' }],
  surroundingPairs: [{ open: "{", close: "}" }, { open: '"', close: '"' }],
};

// Colours for the token names above, per theme.
export const TOKEN_RULES = {
  light: [
    { token: "comment", foreground: "6a737d", fontStyle: "italic" },
    { token: "keyword", foreground: "0550ae" },
    { token: "keyword.escape", foreground: "0550ae" },
    { token: "keyword.env", foreground: "8250df" },
    { token: "type.env", foreground: "8250df", fontStyle: "bold" },
    { token: "keyword.section", foreground: "cf222e", fontStyle: "bold" },
    { token: "keyword.ref", foreground: "116329" },
    { token: "string.ref", foreground: "116329" },
    { token: "string.option", foreground: "953800" },
    { token: "delimiter.math", foreground: "b35900", fontStyle: "bold" },
    { token: "math", foreground: "b35900" },
    { token: "keyword.math", foreground: "953800" },
    { token: "operator.math", foreground: "953800" },
    { token: "number.math", foreground: "b35900" },
    { token: "number", foreground: "0a7d83" },
    { token: "operator", foreground: "cf222e" },
    { token: "delimiter.curly", foreground: "57606a" },
    { token: "delimiter.square", foreground: "57606a" },
    { token: "keyword.entry", foreground: "8250df", fontStyle: "bold" },
    { token: "attribute.name", foreground: "0550ae" },
    { token: "string", foreground: "24292f" },
  ],
  dark: [
    { token: "comment", foreground: "7d8590", fontStyle: "italic" },
    { token: "keyword", foreground: "79c0ff" },
    { token: "keyword.escape", foreground: "79c0ff" },
    { token: "keyword.env", foreground: "d2a8ff" },
    { token: "type.env", foreground: "d2a8ff", fontStyle: "bold" },
    { token: "keyword.section", foreground: "ff7b72", fontStyle: "bold" },
    { token: "keyword.ref", foreground: "7ee787" },
    { token: "string.ref", foreground: "7ee787" },
    { token: "string.option", foreground: "ffa657" },
    { token: "delimiter.math", foreground: "f0b72f", fontStyle: "bold" },
    { token: "math", foreground: "f0b72f" },
    { token: "keyword.math", foreground: "ffa657" },
    { token: "operator.math", foreground: "ffa657" },
    { token: "number.math", foreground: "f0b72f" },
    { token: "number", foreground: "56d4dd" },
    { token: "operator", foreground: "ff7b72" },
    { token: "delimiter.curly", foreground: "8b949e" },
    { token: "delimiter.square", foreground: "8b949e" },
    { token: "keyword.entry", foreground: "d2a8ff", fontStyle: "bold" },
    { token: "attribute.name", foreground: "79c0ff" },
    { token: "string", foreground: "e6edf3" },
  ],
};

export function registerLanguages(monaco) {
  monaco.languages.register({ id: "latex", extensions: [".tex", ".sty", ".cls", ".ltx"], aliases: ["LaTeX"] });
  monaco.languages.register({ id: "bibtex", extensions: [".bib"], aliases: ["BibTeX"] });
  monaco.languages.setMonarchTokensProvider("latex", latexTokens);
  monaco.languages.setLanguageConfiguration("latex", latexConfig);
  monaco.languages.setMonarchTokensProvider("bibtex", bibtexTokens);
  monaco.languages.setLanguageConfiguration("bibtex", bibtexConfig);
}
