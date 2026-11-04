// Spell-check worker: loads a Hunspell dictionary with typo.js (slow for
// Catalan, ~10 s, so it runs off the UI thread and stays loaded) and finds
// misspelled words in LaTeX source, skipping commands, their non-prose
// arguments, math, comments and verbatim-like environments.
//
// Messages in:  {type: "init", lang, words}  {type: "check", id, text}
//               {type: "suggest", id, word}   {type: "add", word}
// Messages out: {type: "ready", lang, ms}     {type: "error", message}
//               {type: "result", id, issues: [{line, column, length, word}]}
//               {type: "suggestions", id, word, list}

/* global Typo, importScripts */
importScripts("../../vendor/typo/typo.js");

const DICTIONARIES = new URL("../../vendor/dictionaries/", self.location.href).href;
const TYPO_LOCALE = { en: "en_US", "en-GB": "en_GB", ca: "ca", es: "es" };

// Commands whose arguments are not prose: how many {…} groups to skip (Infinity = all).
const SKIP_ARGS = new Map(Object.entries({
  label: 1, ref: 1, eqref: 1, autoref: 1, cref: 1, Cref: 1, cpageref: 1, pageref: 1, nameref: 1, vref: 1, subref: 1,
  cite: 1, citep: 1, citet: 1, citealp: 1, citeauthor: 1, citeyear: 1, parencite: 1, textcite: 1, autocite: 1,
  footcite: 1, smartcite: 1, supercite: 1, nocite: 1, fullcite: 1, Cite: 1, Parencite: 1, Textcite: 1, Autocite: 1,
  input: 1, include: 1, includeonly: 1, subfile: 1, includegraphics: 1, includepdf: 1, includesvg: 1, lstinputlisting: 1,
  // begin: the environment name and arguments such as {ll} (tabular) or {0.5\linewidth} (minipage)
  usepackage: 1, RequirePackage: 1, documentclass: 1, begin: Infinity, end: 1, url: 1, href: 1, path: 1,
  bibliography: 1, bibliographystyle: 1, addbibresource: 1, graphicspath: 1,
  newcommand: Infinity, renewcommand: Infinity, providecommand: Infinity, newenvironment: Infinity,
  renewenvironment: Infinity, DeclareMathOperator: Infinity, NewDocumentCommand: Infinity, def: 0,
  setlength: 2, addtolength: 2, setcounter: 2, addtocounter: 2, hspace: 1, vspace: 1, color: 1, textcolor: 1,
  colorbox: 1, definecolor: 3, pagestyle: 1, thispagestyle: 1, geometry: 1, hypersetup: 1, newtheorem: 1,
  selectlanguage: 1, foreignlanguage: 1, setmainlanguage: 1, setotherlanguage: 1, setdefaultlanguage: 1,
  setotherlanguages: 1, setmainfont: 1, setsansfont: 1, setmonofont: 1, newfontfamily: 2, fontspec: 1,
  si: 1, SI: 2, qty: 2, unit: 1, num: 1, ang: 1, multicolumn: 2, multirow: 2, rule: 2, raisebox: 1,
  newacronym: 2, newglossaryentry: Infinity, gls: 1, Gls: 1, glspl: 1, acrshort: 1, acrlong: 1, ac: 1,
  texttt: 1, verb: 0, makeatletter: 0, tikz: 1, node: 0, draw: 0,
}));

// Environments with no prose: math and code. Matched without a trailing "*".
const SKIP_ENVS = new Set([
  "equation", "align", "gather", "multline", "flalign", "alignat", "eqnarray", "math", "displaymath", "dmath",
  "verbatim", "Verbatim", "lstlisting", "minted", "comment", "tikzpicture", "axis", "filecontents", "algorithmic",
]);

const WORD = /[\p{L}\p{M}][\p{L}\p{M}'’·]*[\p{L}\p{M}]|[\p{L}]/gu;

let typo = null;
let lang = null;
let projectWords = new Set();
const cache = new Map();

// ---------------------------------------------------------------------------
// Masking: replace everything that is not prose with spaces (columns preserved)
// ---------------------------------------------------------------------------

// Index just past a balanced {…} or […] group starting at `i`, or -1.
function skipGroup(line, i, open, close) {
  if (line[i] !== open) return -1;
  let depth = 0;
  for (let j = i; j < line.length; j++) {
    if (line[j] === "\\") { j++; continue; }
    if (line[j] === open) depth++;
    else if (line[j] === close && --depth === 0) return j + 1;
  }
  return line.length;
}

function maskLines(text) {
  const lines = text.split("\n");
  const out = [];
  let env = null; // inside a SKIP_ENVS environment (its name)
  let math = null; // closing delimiter of a multi-line display math block

  for (const line of lines) {
    const chars = line.split("");
    const blank = (from, to) => {
      for (let k = from; k < Math.min(to, chars.length); k++) chars[k] = " ";
    };
    let i = 0;
    while (i < line.length) {
      if (env) {
        const end = line.indexOf(`\\end{${env}`, i);
        if (end < 0) { blank(i, line.length); break; }
        const close = line.indexOf("}", end);
        const after = close < 0 ? line.length : close + 1;
        blank(i, after);
        i = after;
        env = null;
        continue;
      }
      if (math) {
        const end = line.indexOf(math, i);
        if (end < 0) { blank(i, line.length); break; }
        blank(i, end + math.length);
        i = end + math.length;
        math = null;
        continue;
      }
      const ch = line[i];
      if (ch === "%") { blank(i, line.length); break; }
      if (ch === "$") {
        const display = line[i + 1] === "$";
        const delim = display ? "$$" : "$";
        const end = line.indexOf(delim, i + delim.length);
        if (end < 0) { blank(i, line.length); if (display) math = "$$"; break; }
        blank(i, end + delim.length);
        i = end + delim.length;
        continue;
      }
      if (ch !== "\\") { i++; continue; }

      const next = line[i + 1];
      if (next === "(" || next === "[") {
        const delim = next === "(" ? "\\)" : "\\]";
        const end = line.indexOf(delim, i + 2);
        if (end < 0) { blank(i, line.length); math = delim; break; }
        blank(i, end + 2);
        i = end + 2;
        continue;
      }
      const m = /^\\([A-Za-z@]+)\*?/.exec(line.slice(i));
      if (!m) { blank(i, i + 2); i += 2; continue; } // \%, \&, \' …
      const name = m[1];
      let j = i + m[0].length;
      if (name === "begin") {
        const env_ = /^\{([A-Za-z@]+)\*?\}/.exec(line.slice(j));
        if (env_ && SKIP_ENVS.has(env_[1])) {
          blank(i, j + env_[0].length);
          i = j + env_[0].length;
          env = env_[1];
          continue;
        }
      }
      if (name === "verb") {
        const delim = line[j];
        const end = line.indexOf(delim, j + 1);
        j = end < 0 ? line.length : end + 1;
        blank(i, j);
        i = j;
        continue;
      }
      // Options [..] after any command are not prose; skip non-prose {..} arguments.
      let args = SKIP_ARGS.get(name) ?? 0;
      for (;;) {
        while (line[j] === " ") j++;
        if (line[j] === "[") {
          j = skipGroup(line, j, "[", "]");
        } else if (line[j] === "{" && args > 0) {
          j = skipGroup(line, j, "{", "}");
          args--;
        } else {
          break;
        }
      }
      blank(i, j);
      i = Math.max(j, i + 1);
    }
    out.push(chars.join(""));
  }
  return out;
}

// ---------------------------------------------------------------------------
// Checking
// ---------------------------------------------------------------------------

function isCorrect(word) {
  if (projectWords.has(word) || projectWords.has(word.toLowerCase())) return true;
  let ok = cache.get(word);
  if (ok === undefined) {
    const plain = word.replace(/’/g, "'");
    ok = typo.check(plain);
    // Elisions and contractions: "l'investigació", "d'aquesta" → check the parts.
    if (!ok && /'/.test(plain)) {
      ok = plain.split("'").every((part) => part.length < 2 || typo.check(part) || projectWords.has(part));
    }
    cache.set(word, ok);
  }
  return ok;
}

function skipWord(word) {
  if (word.length < 2) return true;
  if (word === word.toUpperCase()) return true; // acronyms: FEM, ISO
  if (/\p{Ll}\p{Lu}/u.test(word)) return true; // mixed case: LaTeX, iPhone
  return false;
}

function check(text) {
  const issues = [];
  maskLines(text).forEach((line, index) => {
    for (const m of line.matchAll(WORD)) {
      // Hyphenated compounds are checked part by part.
      for (const part of m[0].split("-")) {
        if (skipWord(part) || isCorrect(part)) continue;
        const column = m.index + m[0].indexOf(part) + 1;
        issues.push({ line: index + 1, column, length: part.length, word: part });
      }
    }
  });
  return issues;
}

async function load(newLang) {
  const t0 = performance.now();
  const [aff, dic] = await Promise.all(["index.aff", "index.dic"].map((f) =>
    fetch(`${DICTIONARIES}${newLang}/${f}`).then((r) => {
      if (!r.ok) throw new Error(`dictionary ${newLang} not found`);
      return r.text();
    })));
  typo = new Typo(TYPO_LOCALE[newLang] || newLang, aff, dic);
  lang = newLang;
  cache.clear();
  return Math.round(performance.now() - t0);
}

self.onmessage = async ({ data }) => {
  try {
    switch (data.type) {
      case "init":
        projectWords = new Set(data.words || []);
        cache.clear();
        if (data.lang !== lang) {
          const ms = await load(data.lang);
          self.postMessage({ type: "ready", lang, ms });
        } else {
          self.postMessage({ type: "ready", lang, ms: 0 });
        }
        break;
      case "check":
        if (!typo) return;
        self.postMessage({ type: "result", id: data.id, issues: check(data.text) });
        break;
      case "suggest":
        self.postMessage({ type: "suggestions", id: data.id, word: data.word, list: typo ? typo.suggest(data.word, 5) : [] });
        break;
      case "add":
        projectWords.add(data.word);
        cache.delete(data.word);
        break;
      default:
        break;
    }
  } catch (err) {
    self.postMessage({ type: "error", message: String(err && err.message || err) });
  }
};
