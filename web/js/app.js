// App bootstrap and wiring: toolbar, project lifecycle, file tree actions,
// tabs, saving, keyboard shortcuts and the status bar.

import { call, BackendUnavailable } from "./bridge.js";
import * as editor from "./editor.js";
import { FileTree } from "./filetree.js";
import { initLayout, toggleSidebar, togglePanel } from "./layout.js";
import { chooseDialog, confirmDialog, contextMenu, promptDialog, showError, toast } from "./ui.js";

const $ = (id) => document.getElementById(id);
const dirname = (path) => (path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");
const basename = (path) => path.split("/").pop();

let project = null; // project info from Python (name, root, main_file, tree, ...)

export function setStatus(text, kind = "") {
  const el = $("status-message");
  el.textContent = text;
  el.className = kind;
}

// ---------------------------------------------------------------------------
// Project lifecycle
// ---------------------------------------------------------------------------

function setProjectUi(info) {
  const open = !!info;
  const name = $("project-menu");
  name.textContent = open ? info.name : "No project open";
  name.title = open ? info.root : "";
  name.classList.toggle("open", open);
  name.disabled = !open;
  $("btn-export").disabled = !open;
  for (const id of ["btn-new-file", "btn-new-folder", "btn-add-files"]) $(id).disabled = !open;
  $("welcome").hidden = open;
  editor.setProjectOpen(open);
  document.title = open ? `${info.name} - LaTeX Editor` : "LaTeX Editor";
}

async function confirmLeaveProject() {
  if (!project || !editor.anyDirty()) return true;
  return confirmDialog({
    title: "Unsaved changes",
    message: `Close ${project.name} and discard the unsaved changes?`,
    okLabel: "Discard changes",
    danger: true,
  });
}

async function showProject(info) {
  editor.closeAll();
  tree.expanded.clear();
  project = info;
  setProjectUi(info);
  tree.setTree(info.tree, info.main_file);
  if (!info.main_file) await chooseMainFile(info.main_candidates);
  if (project.main_file) {
    await openFile(project.main_file);
  }
  setStatus("Ready");
}

async function importZip() {
  if (!(await confirmLeaveProject())) return;
  setStatus("Choose a .zip file to import…");
  try {
    const info = await call("import_zip_dialog");
    if (info) {
      await showProject(info);
      toast(`Imported "${info.name}"`, "success");
    }
  } catch (err) {
    showError(err);
  } finally {
    if ($("status-message").textContent.startsWith("Choose")) setStatus("Ready");
  }
}

async function openProject(path) {
  if (!(await confirmLeaveProject())) return;
  try {
    await showProject(await call("open_project", path));
  } catch (err) {
    showError(err);
    renderRecent();
  }
}

async function closeProject() {
  if (!(await confirmLeaveProject())) return;
  editor.closeAll();
  await call("close_project");
  project = null;
  tree.setTree([], null);
  setProjectUi(null);
  renderRecent();
}

async function refreshProject() {
  project = await call("project_info");
  tree.setTree(project.tree, project.main_file);
}

async function chooseMainFile(candidates) {
  if (!candidates.length) {
    toast("No .tex file with \\documentclass was found. Right-click a file and choose \"Set as main file\".", "warning", 10000);
    return;
  }
  const choice = await chooseDialog({
    title: "Choose the main file",
    message: "Several files contain \\documentclass. Which one should be compiled?",
    options: candidates.map((c) => ({ value: c, label: c })),
  });
  if (choice) await setMainFile(choice);
}

async function setMainFile(path) {
  try {
    project = await call("set_main_file", path);
    tree.setTree(project.tree, project.main_file);
    toast(`Main file: ${path}`, "success");
  } catch (err) {
    showError(err);
  }
}

async function renderRecent() {
  const list = $("recent-projects");
  let items = [];
  try {
    items = await call("recent_projects");
  } catch (err) {
    if (!(err instanceof BackendUnavailable)) showError(err);
  }
  list.replaceChildren();
  if (!items.length) {
    list.innerHTML = '<li class="empty-state">No recent projects yet.</li>';
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    const open = document.createElement("button");
    open.className = "recent-item";
    open.disabled = !item.exists;
    open.title = item.exists ? item.path : `Folder not found: ${item.path}`;
    open.innerHTML = "<strong></strong><small></small>";
    open.querySelector("strong").textContent = item.name;
    open.querySelector("small").textContent = item.exists ? item.path : "Folder not found";
    open.addEventListener("click", () => openProject(item.path));

    const remove = document.createElement("button");
    remove.className = "recent-remove";
    remove.title = "Remove from list";
    remove.setAttribute("aria-label", `Remove ${item.name} from recent projects`);
    remove.addEventListener("click", async () => {
      await call("remove_recent", item.path);
      renderRecent();
    });
    li.append(open, remove);
    list.append(li);
  }
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

async function openFile(path, { focus = true } = {}) {
  if (editor.isOpen(path)) {
    editor.activate(path, { focus });
    return;
  }
  try {
    editor.openTab(path, await call("read_file", path), { focus });
  } catch (err) {
    showError(err);
  }
}

async function saveAll() {
  const files = editor.dirtyFiles();
  if (!files.length) return true;
  for (const file of files) {
    try {
      const encoding = await call("save_file", file.path, file.text, file.encoding);
      editor.markSaved(file.path, file.version, encoding);
      if (file.encoding && encoding !== file.encoding) {
        toast(`${basename(file.path)} contained characters its old encoding can't store, so it was saved as UTF-8.`, "warning", 8000);
      }
    } catch (err) {
      showError(err);
      setStatus(`Could not save ${basename(file.path)}`, "warning");
      return false;
    }
  }
  setStatus(files.length === 1 ? `Saved ${basename(files[0].path)}` : `Saved ${files.length} files`);
  return true;
}

async function exportZip() {
  if (editor.anyDirty() && !(await saveAll())) return;
  let includePdf = false;
  if (project.has_pdf) {
    const choice = await chooseDialog({
      title: "Export .zip",
      options: [
        { value: false, label: "Source files only" },
        { value: true, label: "Source files and the compiled PDF" },
      ],
      okLabel: "Continue",
    });
    if (choice === null) return;
    includePdf = choice;
  }
  try {
    const result = await call("export_zip_dialog", includePdf);
    if (result) toast(`Exported ${result.count} files to ${result.path}`, "success", 8000);
  } catch (err) {
    showError(err);
  }
}

// Folder new items go into: the folder itself, or the folder containing a file.
const targetFolder = (node) => (!node ? "" : node.type === "dir" ? node.path : dirname(node.path));

async function newItem(node, kind) {
  const parent = targetFolder(node);
  const name = await promptDialog({
    title: kind === "file" ? "New file" : "New folder",
    label: `Name (in ${parent || "the project root"})`,
    value: kind === "file" ? "untitled.tex" : "",
    okLabel: "Create",
    selectStem: true,
  });
  if (!name) return;
  try {
    const path = await call(kind === "file" ? "create_file" : "create_folder", parent, name);
    await refreshProject();
    if (kind === "file") {
      tree.setActive(path);
      await openFile(path);
    } else {
      tree.reveal(`${path}/x`);
      tree.render();
    }
  } catch (err) {
    showError(err);
  }
}

async function renameItem(node) {
  const name = await promptDialog({
    title: `Rename ${node.type === "dir" ? "folder" : "file"}`,
    label: "New name",
    value: node.name,
    okLabel: "Rename",
    selectStem: node.type !== "dir",
  });
  if (!name || name === node.name) return;
  try {
    const newPath = await call("rename_path", node.path, name);
    editor.renamePaths(node.path, newPath);
    tree.selected = newPath;
    await refreshProject();
    tree.rowFor(newPath)?.focus();
  } catch (err) {
    showError(err);
  }
}

async function deleteItem(node) {
  const ok = await confirmDialog({
    title: "Delete",
    message: `Move ${node.type === "dir" ? "the folder " : ""}"${node.name}" to the Recycle Bin?`,
    okLabel: "Move to Recycle Bin",
    danger: true,
  });
  if (!ok) return;
  try {
    await call("delete_path", node.path);
    editor.closeUnder(node.path);
    tree.selected = dirname(node.path) || null;
    await refreshProject();
    tree.rowFor(tree.selected)?.focus();
  } catch (err) {
    showError(err);
  }
}

async function addFiles(node) {
  try {
    const added = await call("add_files_dialog", targetFolder(node));
    if (added.length) {
      await refreshProject();
      tree.setActive(added[0]);
      toast(added.length === 1 ? `Added ${added[0]}` : `Added ${added.length} files`, "success");
    }
  } catch (err) {
    showError(err);
  }
}

const reveal = (path = "") => call("reveal", path).catch(showError);

function showTreeMenu(node, x, y) {
  if (!project) return;
  const isTex = node?.type === "file" && node.name.toLowerCase().endsWith(".tex");
  const items = [];
  if (node?.type === "file") {
    items.push({ label: "Open", action: () => openFile(node.path) });
    if (isTex && node.path !== project.main_file) {
      items.push({ label: "Set as main file", action: () => setMainFile(node.path) });
    }
    items.push("-");
  }
  items.push(
    { label: "New file…", action: () => newItem(node, "file") },
    { label: "New folder…", action: () => newItem(node, "folder") },
    { label: "Add files…", action: () => addFiles(node) },
  );
  if (node) {
    items.push(
      "-",
      { label: "Rename…", shortcut: "F2", action: () => renameItem(node) },
      { label: "Delete", shortcut: "Del", danger: true, action: () => deleteItem(node) },
    );
  }
  items.push("-", { label: "Reveal in Explorer", action: () => reveal(node?.path ?? "") });
  contextMenu(x, y, items);
}

const tree = new FileTree($("file-tree"), {
  onOpen: openFile,
  onContextMenu: showTreeMenu,
  onKey: (node, key) => (key === "F2" ? renameItem(node) : deleteItem(node)),
});

// ---------------------------------------------------------------------------
// Toolbar, panels, shortcuts
// ---------------------------------------------------------------------------

function initToolbar() {
  $("btn-import").addEventListener("click", importZip);
  $("welcome-import").addEventListener("click", importZip);
  $("btn-save").addEventListener("click", saveAll);
  $("btn-export").addEventListener("click", exportZip);
  $("btn-new-file").addEventListener("click", () => newItem(tree.find(tree.selected), "file"));
  $("btn-new-folder").addEventListener("click", () => newItem(tree.find(tree.selected), "folder"));
  $("btn-add-files").addEventListener("click", () => addFiles(tree.find(tree.selected)));
  $("project-menu").addEventListener("click", (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    contextMenu(rect.left, rect.bottom + 4, [
      { label: "Reveal in Explorer", action: () => reveal("") },
      { label: "Close project", action: closeProject },
    ]);
  });
}

function initPanelTabs() {
  const tabs = document.querySelectorAll(".panel-tab");
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      for (const t of tabs) {
        const active = t === tab;
        t.classList.toggle("active", active);
        t.setAttribute("aria-selected", active);
        document.querySelector(`[data-panel-body="${t.dataset.panel}"]`).hidden = !active;
      }
    });
  }
}

function initShortcuts() {
  const ctrl = {
    b: toggleSidebar,
    j: togglePanel,
    o: importZip,
    s: () => project && saveAll(),
    w: () => editor.getActivePath() && editor.closeTab(editor.getActivePath()),
    r: () => {}, // no page reload: it would drop unsaved edits
  };
  // Capture phase, so shortcuts work while Monaco has focus.
  window.addEventListener("keydown", (event) => {
    if (document.querySelector("dialog[open]")) return;
    if (event.key === "F5") {
      event.preventDefault();
      return;
    }
    if (!event.ctrlKey || event.altKey) return;
    if (event.key === "Tab") {
      event.preventDefault();
      editor.cycleTab(event.shiftKey ? -1 : 1);
      return;
    }
    if (event.shiftKey) return;
    const action = ctrl[event.key.toLowerCase()];
    if (!action) return;
    event.preventDefault();
    event.stopPropagation();
    action();
  }, true);

  // The browser's own context menu (Reload, Inspect…) is not useful here.
  window.addEventListener("contextmenu", (e) => {
    if (!e.target.closest("input, textarea, .monaco-editor")) e.preventDefault();
  });
}

async function showAppInfo() {
  const line = $("engine-line");
  const engine = $("status-engine");
  try {
    const info = await call("app_info");
    if (info.engine) {
      line.textContent = `LuaLaTeX ready: ${info.engine.version}`;
      line.className = "engine-line ok";
      engine.textContent = info.engine.version.split(" (")[0];
      engine.title = info.engine.path;
    } else {
      line.textContent = "LuaLaTeX was not found. Install MiKTeX or TeX Live and make sure lualatex is on the PATH.";
      line.className = "engine-line missing";
      engine.textContent = "LuaLaTeX not found";
      engine.className = "warning";
    }
    $("workspace-line").textContent = `Projects are stored in ${info.workspace}`;
    $("btn-import").disabled = false;
    $("welcome-import").disabled = false;
    setStatus("Ready");
  } catch (err) {
    line.textContent = err instanceof BackendUnavailable ? err.message : `Could not query the backend: ${err}`;
    line.className = "engine-line missing";
    setStatus(err.message, "warning");
  }
}

async function main() {
  initLayout();
  initPanelTabs();
  initToolbar();
  initShortcuts();
  setProjectUi(null);
  await editor.initEditor({
    onDirtyChange: (dirty) => {
      $("btn-save").disabled = !dirty;
      call("set_dirty", dirty).catch(() => {});
    },
    onActiveChange: (path) => tree.setActive(path),
    onCursor: (pos) => {
      $("status-cursor").textContent = pos ? `Ln ${pos.lineNumber}, Col ${pos.column}` : "";
    },
  });
  await Promise.all([showAppInfo(), renderRecent()]);
}

main().catch(showError);
