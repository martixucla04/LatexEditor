// Project search in the sidebar: find text (literal or regex, case, whole word)
// across project files, show matches grouped by file, open a match on click,
// and replace all matches after a confirmation.

import { call } from "./bridge.js";
import { ensureSidebar } from "./layout.js";
import { confirmDialog, showError, toast } from "./ui.js";

const OPTIONS_KEY = "latexeditor.searchOptions";
const DEFAULT_INCLUDE = "*.tex, *.bib";
const DEBOUNCE_MS = 300;

const $ = (id) => document.getElementById(id);
const input = $("search-input");
const replaceInput = $("replace-input");
const includeInput = $("search-include");
const summary = $("search-summary");
const resultsEl = $("search-results");
const toggles = { case: $("search-case"), word: $("search-word"), regex: $("search-regex") };

let handlers = { onOpenMatch() {}, beforeReplace: async () => true, afterReplace() {} };
let projectOpen = false;
let lastResult = null;
let lastQuery = "";
let timer = null;
let runId = 0;
const collapsed = new Set();

function options() {
  return {
    case: toggles.case.getAttribute("aria-pressed") === "true",
    word: toggles.word.getAttribute("aria-pressed") === "true",
    regex: toggles.regex.getAttribute("aria-pressed") === "true",
    include: includeInput.value.trim() || DEFAULT_INCLUDE,
  };
}

function saveOptions() {
  try {
    localStorage.setItem(OPTIONS_KEY, JSON.stringify(options()));
  } catch {
    // not remembered
  }
}

function loadOptions() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(OPTIONS_KEY)) || {};
  } catch {
    // defaults
  }
  for (const [name, button] of Object.entries(toggles)) button.setAttribute("aria-pressed", !!saved[name]);
  includeInput.value = saved.include || DEFAULT_INCLUDE;
}

// ---------------------------------------------------------------------------
// Sidebar views (Files | Search)
// ---------------------------------------------------------------------------

export function showSidebarView(name) {
  ensureSidebar();
  for (const tab of document.querySelectorAll(".sidebar-tab")) {
    const active = tab.dataset.view === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active);
  }
  for (const body of document.querySelectorAll("[data-view-body]")) body.hidden = body.dataset.viewBody !== name;
  $("file-actions").hidden = name !== "files";
}

// Open the Search view, optionally pre-filled (e.g. with the editor selection).
export function showSearch(text = "") {
  showSidebarView("search");
  if (text && !text.includes("\n")) {
    input.value = text;
    scheduleSearch(0);
  }
  input.focus();
  input.select();
}

// ---------------------------------------------------------------------------
// Searching
// ---------------------------------------------------------------------------

function scheduleSearch(delay = DEBOUNCE_MS) {
  clearTimeout(timer);
  timer = setTimeout(runSearch, delay);
}

export async function runSearch() {
  const query = input.value;
  const id = ++runId;
  if (!projectOpen || !query) {
    lastResult = null;
    render();
    return;
  }
  summary.textContent = "Searching…";
  try {
    const result = await call("search_project", query, options());
    if (id !== runId) return; // a newer search started
    lastResult = result;
    lastQuery = query;
    render();
  } catch (err) {
    if (id !== runId) return;
    lastResult = null;
    resultsEl.replaceChildren();
    summary.textContent = err.message;
    summary.className = "search-summary error";
  }
}

function render() {
  summary.className = "search-summary";
  resultsEl.replaceChildren();
  $("btn-replace-all").disabled = !lastResult?.total;
  if (!lastResult) {
    summary.textContent = projectOpen ? "" : "Open a project to search it.";
    return;
  }
  const { files, total, truncated } = lastResult;
  if (!total) {
    summary.textContent = `No results for “${lastQuery}”.`;
    return;
  }
  summary.textContent = `${total}${truncated ? "+" : ""} result${total === 1 ? "" : "s"} in ${files.length} file${files.length === 1 ? "" : "s"}`
    + (truncated ? " (showing the first ones)" : "");

  for (const group of files) {
    const section = document.createElement("div");
    section.className = "search-file";
    const header = document.createElement("button");
    header.className = "search-file-header";
    header.innerHTML = '<span class="chevron"></span><span class="search-file-name"></span><span class="search-file-dir"></span><span class="badge"></span>';
    const slash = group.file.lastIndexOf("/");
    header.querySelector(".search-file-name").textContent = group.file.slice(slash + 1);
    header.querySelector(".search-file-dir").textContent = slash > 0 ? group.file.slice(0, slash) : "";
    header.querySelector(".badge").textContent = group.matches.length;
    header.title = group.file;
    const open = !collapsed.has(group.file);
    header.querySelector(".chevron").classList.toggle("open", open);
    header.addEventListener("click", () => {
      if (collapsed.has(group.file)) collapsed.delete(group.file);
      else collapsed.add(group.file);
      render();
    });
    section.append(header);

    if (open) {
      const list = document.createElement("ul");
      for (const m of group.matches) {
        const li = document.createElement("li");
        li.className = "search-match";
        li.tabIndex = 0;
        li.title = `${group.file}:${m.line}`;
        const line = document.createElement("span");
        line.className = "search-line";
        line.textContent = m.line;
        const text = document.createElement("span");
        text.className = "search-text";
        const mark = document.createElement("mark");
        mark.textContent = m.preview.slice(m.offset, m.offset + m.length);
        text.append(m.preview.slice(0, m.offset), mark, m.preview.slice(m.offset + m.length));
        li.append(line, text);
        const go = () => handlers.onOpenMatch(group.file, m.line, m.column, m.length);
        li.addEventListener("click", go);
        li.addEventListener("keydown", (e) => {
          if (e.key === "Enter") go();
        });
        list.append(li);
      }
      section.append(list);
    }
    resultsEl.append(section);
  }
}

async function replaceAll() {
  if (!lastResult?.total) return;
  const { files, total } = lastResult;
  const replacement = replaceInput.value;
  const ok = await confirmDialog({
    title: "Replace all",
    message: `Replace ${total} match${total === 1 ? "" : "es"} of “${lastQuery}” with “${replacement}” in ${files.length} file${files.length === 1 ? "" : "s"}? Open files are saved first.`,
    okLabel: "Replace all",
    danger: true,
  });
  if (!ok || !(await handlers.beforeReplace())) return;
  try {
    const result = await call("replace_in_project", lastQuery, replacement, options(), files.map((f) => f.file));
    toast(`Replaced ${result.count} match${result.count === 1 ? "" : "es"} in ${result.files.length} file${result.files.length === 1 ? "" : "s"}`, "success");
    await handlers.afterReplace(result.files);
  } catch (err) {
    showError(err);
  }
  runSearch();
}

// ---------------------------------------------------------------------------

export function setSearchProject(open) {
  projectOpen = open;
  lastResult = null;
  collapsed.clear();
  render();
}

export function initSearch(options) {
  handlers = { ...handlers, ...options };
  loadOptions();
  for (const tab of document.querySelectorAll(".sidebar-tab")) {
    tab.addEventListener("click", () => {
      showSidebarView(tab.dataset.view);
      if (tab.dataset.view === "search") input.focus();
    });
  }
  for (const button of Object.values(toggles)) {
    button.addEventListener("click", () => {
      button.setAttribute("aria-pressed", button.getAttribute("aria-pressed") !== "true");
      saveOptions();
      scheduleSearch(0);
    });
  }
  input.addEventListener("input", () => scheduleSearch());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") scheduleSearch(0);
  });
  includeInput.addEventListener("change", () => {
    saveOptions();
    scheduleSearch(0);
  });
  replaceInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey) replaceAll();
  });
  $("btn-replace-all").addEventListener("click", replaceAll);
  render();
}
