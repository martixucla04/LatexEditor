// Project file tree: folders expand/collapse, files open on click, right-click
// (or the keyboard) asks the app for actions. The tree never talks to Python.

const ICONS = {
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/>',
  tex: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 15h6M9 18h4"/>',
  bib: '<path d="M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M5 18a2 2 0 0 1 2-2h11M9 8h6"/>',
  image: '<rect x="4" y="5" width="16" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="m20 16-5-5-7 8"/>',
  pdf: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 16h6"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
};

const KIND_BY_EXT = {
  tex: "tex", sty: "tex", cls: "tex", ltx: "tex", dtx: "tex",
  bib: "bib", bst: "bib",
  png: "image", jpg: "image", jpeg: "image", gif: "image", svg: "image", eps: "image", bmp: "image", webp: "image",
  pdf: "pdf",
};

function iconFor(node) {
  if (node.type === "dir") return "folder";
  const ext = node.name.includes(".") ? node.name.split(".").pop().toLowerCase() : "";
  return KIND_BY_EXT[ext] || "file";
}

export class FileTree {
  // onOpen(path, { focus }), onContextMenu(node | null, x, y), onKey(node, key)
  // A click on a file opens it with the focus in the editor; a click on a folder keeps focus
  // here (F2/Del, arrows); Enter on a file also moves the focus to the editor.
  constructor(container, handlers) {
    this.container = container;
    this.handlers = handlers;
    this.nodes = [];
    this.expanded = new Set();
    this.selected = null;
    this.active = null;
    this.mainFile = null;

    container.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const row = e.target.closest(".tree-row");
      const node = row ? this.find(row.dataset.path) : null;
      if (node) this.select(node.path);
      handlers.onContextMenu(node, e.clientX, e.clientY);
    });
    container.addEventListener("keydown", (e) => this.onKeyDown(e));
  }

  setTree(nodes, mainFile) {
    this.nodes = nodes;
    this.mainFile = mainFile;
    this.render();
  }

  find(path, nodes = this.nodes) {
    for (const node of nodes) {
      if (node.path === path) return node;
      if (node.children) {
        const hit = this.find(path, node.children);
        if (hit) return hit;
      }
    }
    return null;
  }

  // Expand the folders containing `path` so it is visible.
  reveal(path) {
    const parts = path.split("/");
    for (let i = 1; i < parts.length; i++) this.expanded.add(parts.slice(0, i).join("/"));
  }

  setActive(path) {
    this.active = path;
    if (path) {
      this.reveal(path);
      this.selected = path;
    }
    this.render();
  }

  select(path) {
    this.selected = path;
    for (const row of this.container.querySelectorAll(".tree-row")) {
      row.classList.toggle("selected", row.dataset.path === path);
    }
  }

  render() {
    const scroll = this.container.scrollTop;
    const hadFocus = this.container.contains(document.activeElement);
    this.container.replaceChildren();
    if (!this.nodes.length) {
      this.container.innerHTML = '<p class="empty-state">This project has no files.</p>';
      return;
    }
    const list = document.createElement("ul");
    list.className = "tree";
    list.setAttribute("role", "tree");
    this.renderNodes(this.nodes, list, 0);
    this.container.append(list);
    this.container.scrollTop = scroll;
    // Re-rendering replaces the rows; keep keyboard focus on the selected one.
    if (hadFocus) this.rowFor(this.selected)?.focus({ preventScroll: true });
  }

  rowFor(path) {
    return path ? this.container.querySelector(`.tree-row[data-path="${CSS.escape(path)}"]`) : null;
  }

  renderNodes(nodes, parent, depth) {
    for (const node of nodes) {
      const li = document.createElement("li");
      const row = document.createElement("div");
      const isDir = node.type === "dir";
      const open = isDir && this.expanded.has(node.path);
      row.className = "tree-row";
      row.dataset.path = node.path;
      row.tabIndex = -1;
      row.setAttribute("role", "treeitem");
      if (isDir) row.setAttribute("aria-expanded", open);
      row.style.paddingLeft = `${8 + depth * 14}px`;
      row.classList.toggle("selected", node.path === this.selected);
      row.classList.toggle("active", node.path === this.active);
      row.title = node.path;

      const chevron = isDir ? `<span class="chevron${open ? " open" : ""}"></span>` : '<span class="chevron-space"></span>';
      const kind = iconFor(node);
      row.innerHTML = `${chevron}<svg class="file-icon ${kind}" viewBox="0 0 24 24">${ICONS[kind]}</svg>`;
      const label = document.createElement("span");
      label.className = "tree-label";
      label.textContent = node.name;
      row.append(label);
      if (node.path === this.mainFile) {
        row.insertAdjacentHTML("beforeend", '<span class="main-badge" title="Main file (compiled)">main</span>');
      }

      row.addEventListener("click", () => {
        this.select(node.path);
        // a file: the cursor goes to the editor, so Ctrl+C/V/Z act on the text right away
        if (isDir) {
          row.focus();
          this.toggle(node.path);
        } else {
          this.handlers.onOpen(node.path, { focus: true });
        }
      });

      li.append(row);
      if (open && node.children.length) {
        const ul = document.createElement("ul");
        ul.setAttribute("role", "group");
        this.renderNodes(node.children, ul, depth + 1);
        li.append(ul);
      }
      parent.append(li);
    }
  }

  toggle(path) {
    if (this.expanded.has(path)) this.expanded.delete(path);
    else this.expanded.add(path);
    this.render();
    this.rowFor(path)?.focus();
  }

  onKeyDown(e) {
    const rows = [...this.container.querySelectorAll(".tree-row")];
    const index = rows.findIndex((r) => r.dataset.path === this.selected);
    const node = this.find(this.selected);
    const focusRow = (row) => {
      if (!row) return;
      this.select(row.dataset.path);
      row.focus();
    };

    switch (e.key) {
      case "ArrowDown": focusRow(rows[index + 1] ?? rows[0]); break;
      case "ArrowUp": focusRow(rows[index - 1] ?? rows[0]); break;
      case "ArrowRight": if (node?.type === "dir" && !this.expanded.has(node.path)) this.toggle(node.path); break;
      case "ArrowLeft": if (node?.type === "dir" && this.expanded.has(node.path)) this.toggle(node.path); break;
      case "Enter": if (node) node.type === "dir" ? this.toggle(node.path) : this.handlers.onOpen(node.path, { focus: true }); break;
      case "F2":
      case "Delete":
        if (node) this.handlers.onKey(node, e.key);
        break;
      default:
        return;
    }
    e.preventDefault();
  }
}
