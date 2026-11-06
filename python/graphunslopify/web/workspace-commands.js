/** Shared command discovery. Actual workspace controls retain operation ownership. */
const categories = {
  command: "Command", chart: "Chart type", setting: "Setting", figure: "Figure",
};
const normalize = (value) => value.toLocaleLowerCase().replace(/[._-]+/g, " ").trim();
const chartAliases = {
  ecdf: "empirical cumulative distribution",
  kaplan_meier: "survival curve",
  qq: "quantile quantile",
};

export function chartEntries(schema, target, activate, enabled) {
  return (schema?.oneOf || []).map((branch) => {
    const kind = branch.properties.kind.const;
    return {
      id: "chart-" + kind, category: "chart", label: kind.replaceAll("_", " "),
      keywords: chartAliases[kind], target, enabled, activate: () => activate(kind),
      unavailable: "Choose an editable figure definition first.",
    };
  });
}

export function settingEntries(root, { group = "", reveal } = {}) {
  const selector = "input[id]:not([type=hidden]), select[id], textarea[id]";
  const inputs = root.matches(selector) ? [root] : [...root.querySelectorAll(selector)];
  return inputs.flatMap((control) => {
    const label = control.getAttribute("aria-label") || [...control.labels].map((wrapper) =>
      [...wrapper.childNodes].filter((child) => !child.contains(control))
        .map((child) => child.textContent.trim()).filter(Boolean).join(" ")
    ).filter(Boolean).join(" ");
    if (!label) return [];
    const section = control.closest("details")?.querySelector(":scope > summary")?.textContent;
    const context = [group, section].filter(Boolean).join(" · ");
    const hidden = control.closest("[hidden]");
    const revealSetting = hidden && hidden !== root && root.contains(hidden) ? reveal : undefined;
    return [{
      id: "setting-" + control.id, category: "setting", label, context,
      keywords: control.id, target: control, focusOnly: true, reveal: revealSetting, scope: root,
      unavailable: "This setting is unavailable in the current workspace state.",
    }];
  });
}

export function createWorkspaceCommands({ trigger, commands, entries = () => [] }) {
  const node = (tag, text, parent) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    parent?.append(element);
    return element;
  };
  const apple = /Mac|iPhone|iPad/.test(navigator.platform);
  const modifier = apple ? "⌘" : "Ctrl";
  const shortcutText = (key) => modifier + "+" + key.replace(/^[a-z]$/, (letter) => letter.toUpperCase());
  trigger.title = "Search the workspace (" + shortcutText("k") + ")";
  trigger.setAttribute("aria-keyshortcuts", "Control+K Meta+K");
  node("kbd", shortcutText("k"), trigger);
  const dialog = node("dialog", undefined, document.body);
  dialog.className = "workspace-commands";
  dialog.setAttribute("aria-labelledby", "workspace-command-heading");
  const head = node("div", undefined, dialog); head.className = "command-head";
  const heading = node("h2", "Workspace commands", head); heading.id = "workspace-command-heading";
  const dismiss = node("button", "Close", head); dismiss.type = "button"; dismiss.className = "quiet";
  const label = node("label", "Search the workspace", dialog); label.htmlFor = "workspace-command-query";
  const input = node("input", undefined, dialog); input.id = "workspace-command-query";
  input.type = "search"; input.autocomplete = "off"; input.placeholder = "Chart types, settings, figures, or commands…";
  input.setAttribute("role", "combobox"); input.setAttribute("aria-controls", "workspace-command-results");
  input.setAttribute("aria-autocomplete", "list"); input.setAttribute("aria-expanded", "false");
  const list = node("div", undefined, dialog); list.id = "workspace-command-results";
  list.setAttribute("role", "listbox"); list.setAttribute("aria-label", "Search results");
  const status = node("p", "", dialog); status.className = "muted command-status";
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const help = node("p", "Use ↑ / ↓ and Enter. Escape closes. Try chart scatter or setting DPI.", dialog);
  help.className = "muted command-help"; help.id = "workspace-command-help";
  input.setAttribute("aria-describedby", help.id);
  let previousFocus, selected = "", matches = [], rendered = "";
  const catalog = () => [...commands, ...entries()];
  const target = (command) => typeof command.target === "string"
    ? document.getElementById(command.target) : command.target;
  function available(command) {
    const control = target(command);
    if (!control?.isConnected || control.matches(":disabled") ||
        control.getAttribute("aria-disabled") === "true" ||
        (command.enabled && !command.enabled())) return false;
    for (let item = control; item; item = item.parentElement) {
      if (item.hidden && !(command.reveal && item !== command.scope && command.scope.contains(item)))
        return false;
    }
    return true;
  }
  function select(id) {
    selected = id;
    for (const option of list.children) {
      const active = option.dataset.command === selected;
      option.setAttribute("aria-selected", String(active));
      if (active) input.setAttribute("aria-activedescendant", option.id);
    }
  }
  function render() {
    const query = normalize(input.value);
    const terms = query.split(/\s+/).filter(Boolean);
    matches = catalog().filter((command) => {
      const category = categories[command.category || "command"];
      const keys = normalize([
        command.label, category, category + "s", command.context, command.keywords,
        command.shortcut ? shortcutText(command.shortcut) : "",
      ].join(" "));
      return terms.every((term) => keys.includes(term));
    });
    const results = matches.map((command) => ({command, enabled: available(command)}));
    const signature = JSON.stringify([query, results.map(({command, enabled}) =>
      [command.id, command.label, command.context, command.category, enabled])]);
    if (signature === rendered) return;
    rendered = signature;
    list.replaceChildren();
    input.removeAttribute("aria-activedescendant");
    for (const {command, enabled} of results) {
      const row = node("div", undefined, list); row.id = "workspace-command-" + command.id;
      row.className = "command-option"; row.dataset.command = command.id;
      row.dataset.category = command.category || "command";
      row.setAttribute("role", "option"); row.setAttribute("aria-disabled", String(!enabled));
      const text = node("div", undefined, row);
      node("strong", command.label, text);
      node("small", [categories[row.dataset.category], command.context].filter(Boolean).join(" · "), text);
      if (!enabled) node("small", command.unavailable || "Finish the current operation first.", text);
      if (command.shortcut) node("kbd", shortcutText(command.shortcut), row);
      row.addEventListener("mouseenter", () => select(command.id));
      row.addEventListener("mousedown", (event) => event.preventDefault());
      row.addEventListener("click", () => activate(command.id));
    }
    if (!matches.some((command) => command.id === selected)) selected = matches[0]?.id || "";
    select(selected);
    status.textContent = matches.length ? `${matches.length} matching result${matches.length === 1 ? "" : "s"}.` : "No results. Try a different search.";
  }
  function close() {
    if (!dialog.open) return;
    dialog.close(); input.setAttribute("aria-expanded", "false");
    if (previousFocus?.isConnected && !previousFocus.matches(":disabled") && !previousFocus.closest("[hidden]")) previousFocus.focus({ preventScroll: true });
  }
  function open(query = "") {
    if (!dialog.open) {
      if (document.querySelector("dialog[open]")) return;
      previousFocus = document.activeElement;
      dialog.showModal(); input.setAttribute("aria-expanded", "true");
    }
    input.value = query; selected = ""; rendered = ""; render(); input.focus(); input.select();
  }
  function activate(id, focusControl = true) {
    // Paper polling and control edits can replace the target while the palette is open.
    const command = catalog().find((item) => item.id === id);
    if (!command || !available(command)) {
      render(); status.textContent = command?.unavailable || "This result is no longer available.";
      return;
    }
    close();
    command.reveal?.();
    const control = target(command);
    for (let parent = control.parentElement; parent; parent = parent.parentElement) if (parent.tagName === "DETAILS") parent.open = true;
    if (focusControl || command.focusOnly) control.focus({ preventScroll: true });
    if (command.focusOnly) control.scrollIntoView({ block: "nearest" });
    else if (command.activate) command.activate();
    else control.click();
  }
  trigger.addEventListener("click", () => open());
  dismiss.addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  dialog.addEventListener("keydown", (event) => {
    if (event.key !== "Tab" || event.isComposing || event.altKey || event.ctrlKey || event.metaKey) return;
    // Native browser/platform settings may otherwise skip the Close button.
    event.preventDefault();
    const controls = [dismiss, input];
    let current = controls.indexOf(document.activeElement);
    if (current < 0) current = event.shiftKey ? 0 : -1;
    controls[(current + (event.shiftKey ? -1 : 1) + controls.length) % controls.length].focus();
  });
  input.addEventListener("input", render);
  input.addEventListener("keydown", (event) => {
    if (event.isComposing || event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === "Escape") {
      // A search input otherwise consumes Escape to clear its query first.
      event.preventDefault(); close();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!matches.length) return;
      const current = matches.findIndex((command) => command.id === selected);
      const index = (current + (event.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length;
      select(matches[index].id);
      document.getElementById("workspace-command-" + selected)?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      const command = matches.find((command) => command.id === selected);
      if (command) activate(command.id);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.repeat || event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey)) return;
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    if (key === "k" && !event.shiftKey) { event.preventDefault(); open(); return; }
    if (dialog.open || document.querySelector("dialog[open]")) return;
    const combo = (event.shiftKey ? "Shift+" : "") + key;
    const typing = event.target instanceof Element && !!event.target.closest("input,textarea,select,[contenteditable]:not([contenteditable='false'])");
    const options = commands.filter((command) => command.shortcut === combo && (!typing || (command.typingWithin && event.target.closest(command.typingWithin))));
    if (!options.length) return;
    event.preventDefault();
    const eligible = options.filter(available);
    if (eligible.length === 1) activate(eligible[0].id, false);
    else open(options[0].label);
  });
  const observer = new MutationObserver((records) => {
    if (dialog.open && records.some((record) => !dialog.contains(record.target))) render();
  });
  observer.observe(document.body, {
    subtree: true, childList: true, attributes: true,
    attributeFilter: ["disabled", "hidden", "aria-disabled", "readonly"],
  });
  return { open, close, refresh: render };
}
