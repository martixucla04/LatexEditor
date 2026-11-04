// Problems panel: errors, warnings and typesetting notes (overfull boxes, font
// substitutions) from the last build. Clicking a problem asks the app to open
// the file at that line. Typesetting notes are hidden by default.

const FILTER_KEY = "latexeditor.problemFilters";
const LABELS = { error: "Errors", warning: "Warnings", info: "Typesetting" };

const $ = (id) => document.getElementById(id);
const listEl = $("problem-list");
const emptyEl = $("problems-empty");
const filtersEl = $("problem-filters");
const badge = $("problem-count");

let problems = [];
let built = false;
let onOpen = () => {};
let visible = { error: true, warning: true, info: false };

try {
  Object.assign(visible, JSON.parse(localStorage.getItem(FILTER_KEY)) || {});
} catch {
  // keep defaults
}

export function initProblems(handlers) {
  onOpen = handlers.onOpen;
}

// list: problems from the backend, or null when nothing has been built yet.
export function setProblems(list) {
  built = list !== null;
  problems = list || [];
  render();
}

export function counts() {
  const c = { error: 0, warning: 0, info: 0 };
  for (const p of problems) c[p.severity]++;
  return c;
}

function location(p) {
  if (p.file) return p.line ? `${p.file}:${p.line}` : p.file;
  if (p.external) return `${p.external.split(/[\\/]/).pop()}${p.line ? `:${p.line}` : ""}`;
  return p.source !== "lualatex" ? p.source : "";
}

function renderFilters(c) {
  filtersEl.replaceChildren();
  filtersEl.hidden = !problems.length;
  for (const severity of ["error", "warning", "info"]) {
    const chip = document.createElement("button");
    chip.className = `chip ${severity}`;
    chip.setAttribute("aria-pressed", visible[severity]);
    chip.innerHTML = `<span class="sev-dot ${severity}"></span><span></span><span class="chip-count"></span>`;
    chip.children[1].textContent = LABELS[severity];
    chip.children[2].textContent = c[severity];
    chip.addEventListener("click", () => {
      visible[severity] = !visible[severity];
      try {
        localStorage.setItem(FILTER_KEY, JSON.stringify(visible));
      } catch {
        // not remembered
      }
      render();
    });
    filtersEl.append(chip);
  }
}

function render() {
  const c = counts();
  const shown = c.error + c.warning;
  badge.textContent = shown;
  badge.className = `badge ${c.error ? "error" : c.warning ? "warning" : ""}`;
  renderFilters(c);

  listEl.replaceChildren();
  const items = problems.filter((p) => visible[p.severity]);
  for (const p of items) {
    const li = document.createElement("li");
    li.className = `problem ${p.severity}`;
    li.classList.toggle("navigable", !!p.file);
    li.title = p.file ? "Go to this line" : p.external ? `In ${p.external}` : "";
    li.innerHTML = `<span class="sev-dot ${p.severity}"></span>
      <div class="problem-body"><div class="problem-message"></div><code class="problem-context"></code></div>
      <span class="problem-location"></span>`;
    li.querySelector(".problem-message").textContent = p.message;
    const context = li.querySelector(".problem-context");
    context.textContent = p.context;
    context.hidden = !p.context;
    li.querySelector(".problem-location").textContent = location(p);
    if (p.file) {
      li.tabIndex = 0;
      li.addEventListener("click", () => onOpen(p));
      li.addEventListener("keydown", (e) => {
        if (e.key === "Enter") onOpen(p);
      });
    }
    listEl.append(li);
  }

  emptyEl.hidden = items.length > 0;
  if (!built) emptyEl.textContent = "No problems. Compile the document to check it.";
  else if (!problems.length) emptyEl.textContent = "No problems in the last build.";
  else emptyEl.textContent = "All problems are hidden by the filters above.";
}

render();
