/** Shared command discovery. Actual workspace controls retain operation ownership. */
export function createWorkspaceCommands({ trigger, commands }) {
  const node = (tag, text, parent) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    parent?.append(element);
    return element;
  };
  const apple = /Mac|iPhone|iPad/.test(navigator.platform);
  const modifier = apple ? "⌘" : "Ctrl";
  const shortcutText = (key) => modifier + "+" + key.replace(/^[a-z]$/, (letter) => letter.toUpperCase());
  trigger.title = "Search actions and keyboard shortcuts (" + shortcutText("k") + ")";
  trigger.setAttribute("aria-keyshortcuts", "Control+K Meta+K");
  node("kbd", shortcutText("k"), trigger);
  const dialog = node("dialog", undefined, document.body);
  dialog.className = "workspace-commands";
  dialog.setAttribute("aria-labelledby", "workspace-command-heading");
  const head = node("div", undefined, dialog); head.className = "command-head";
  const heading = node("h2", "Workspace commands", head); heading.id = "workspace-command-heading";
  const dismiss = node("button", "Close", head); dismiss.type = "button"; dismiss.className = "quiet";
  const label = node("label", "Search actions", dialog); label.htmlFor = "workspace-command-query";
  const input = node("input", undefined, dialog); input.id = "workspace-command-query";
  input.type = "search"; input.autocomplete = "off"; input.placeholder = "Search an action…";
  input.setAttribute("role", "combobox"); input.setAttribute("aria-controls", "workspace-command-results");
  input.setAttribute("aria-autocomplete", "list"); input.setAttribute("aria-expanded", "false");
  const list = node("div", undefined, dialog); list.id = "workspace-command-results";
  list.setAttribute("role", "listbox"); list.setAttribute("aria-label", "Matching actions");
  const status = node("p", "", dialog); status.className = "muted command-status";
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  node("p", "Use ↑ / ↓ and Enter. Escape closes. Unavailable actions explain what to finish first.", dialog).className = "muted command-help";
  let previousFocus, selected = "", matches = [], rendered = "";
  const target = (command) => document.getElementById(command.target);
  function available(command) {
    const control = target(command);
    return !!control && !control.matches(":disabled") && !control.closest("[hidden]") &&
      control.getAttribute("aria-disabled") !== "true" && (!command.enabled || command.enabled());
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
    const query = input.value.trim().toLocaleLowerCase();
    matches = commands.filter((command) => [command.label, command.keywords || "", command.shortcut ? shortcutText(command.shortcut) : ""].join(" ").toLocaleLowerCase().includes(query));
    const signature = JSON.stringify([query, matches.map((command) => [command.id, available(command)])]);
    if (signature === rendered) return;
    rendered = signature;
    list.replaceChildren();
    input.removeAttribute("aria-activedescendant");
    for (const command of matches) {
      const row = node("div", undefined, list); row.id = "workspace-command-" + command.id;
      row.className = "command-option"; row.dataset.command = command.id;
      row.setAttribute("role", "option"); row.setAttribute("aria-disabled", String(!available(command)));
      const text = node("div", undefined, row);
      node("strong", command.label, text);
      if (!available(command)) node("small", command.unavailable || "Finish the current operation first.", text);
      if (command.shortcut) node("kbd", shortcutText(command.shortcut), row);
      row.addEventListener("mouseenter", () => select(command.id));
      row.addEventListener("mousedown", (event) => event.preventDefault());
      row.addEventListener("click", () => activate(command));
    }
    if (!matches.some((command) => command.id === selected)) selected = matches[0]?.id || "";
    select(selected);
    status.textContent = matches.length ? `${matches.length} matching action${matches.length === 1 ? "" : "s"}.` : "No matching actions. Try a different search.";
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
  function activate(command, focusControl = true) {
    // The displayed eligibility may have changed while the search was open.
    if (!available(command)) { render(); status.textContent = command.unavailable || "Finish the current operation first."; return; }
    close();
    const control = target(command);
    for (let parent = control.parentElement; parent; parent = parent.parentElement) if (parent.tagName === "DETAILS") parent.open = true;
    if (focusControl || command.focusOnly) control.focus({ preventScroll: true });
    if (command.focusOnly) control.scrollIntoView({ block: "nearest" });
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
      if (command) activate(command);
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
    if (eligible.length === 1) activate(eligible[0], false);
    else open(options[0].label);
  });
  const observer = new MutationObserver((records) => {
    if (dialog.open && records.some((record) => !dialog.contains(record.target))) render();
  });
  observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ["disabled", "hidden", "aria-disabled"] });
  return { open, close, refresh: render };
}
