const route = "/api/claim-links";
const statusNames = {
  supported: "Supported by the recorded check",
  contradiction: "Contradiction",
  untested: "Untested",
  stale_text: "Stale text",
  stale_figure: "Stale figure evidence",
};

function add(parent, tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent.append(node);
  return node;
}
function field(parent, label, tag) {
  return add(add(parent, "label", label), tag);
}
function button(parent, label) {
  const node = add(parent, "button", label);
  node.type = "button";
  return node;
}
function description(check) {
  const comparison = check.reference ? " vs " + check.reference : "";
  const panel = check.panel_name ? " · panel " + check.panel_name : "";
  const tolerance = check.tolerance == null ? "" : " · tolerance " + check.tolerance;
  return check.subject + comparison + " · " + check.kind.replaceAll("_", " ") +
    " · " + check.metric + panel + tolerance;
}
function location(anchor, found) {
  const source = anchor.kind === "caption" ? "Figure caption" : anchor.path;
  if (!found) return source;
  const lines = found.first_line === found.last_line
    ? "line " + found.first_line : "lines " + found.first_line + "–" + found.last_line;
  return source + " · " + lines;
}

export function createClaimLinks(mount, { api, current, openAudit }) {
  add(mount, "p", "Connect an exact manuscript or caption excerpt to a numerical check from the current paper audit. You confirm the correspondence.");
  const status = add(mount, "p");
  status.setAttribute("role", "status");
  const reload = button(mount, "Refresh claim links");
  reload.className = "quiet";
  const list = add(mount, "section");
  list.setAttribute("aria-label", "Saved claim links");
  const editor = add(mount, "fieldset");
  add(editor, "legend", "Link text to a figure check");
  const row = add(editor, "div");
  row.className = "claim-link-fields";
  const figure = field(row, "Claim figure", "select");
  const check = field(row, "Recorded figure check", "select");
  const kind = field(row, "Text source", "select");
  kind.add(new Option("Manuscript file", "manuscript"));
  kind.add(new Option("Figure caption", "caption"));
  const path = field(row, "Manuscript path relative to paper folder", "input");
  path.placeholder = "paper.tex";
  path.maxLength = 512;
  const excerpt = field(editor, "Exact excerpt", "textarea");
  excerpt.rows = 3; excerpt.maxLength = 2000;
  const reviewButton = button(editor, "Review claim link");
  const proposal = add(mount, "section");
  proposal.setAttribute("aria-label", "Claim link review");
  let key = null, epoch = 0, formVersion = 0, report = null, busy = false;
  const same = (expected, version) => epoch === version && current() === expected;

  function clearReview() {
    formVersion++;
    proposal.replaceChildren();
  }
  function controls() {
    editor.disabled = !report || busy || !key;
    reload.disabled = !key || busy;
    check.disabled = !figure.value;
    reviewButton.disabled = !check.value;
    path.closest("label").hidden = kind.value === "caption";
  }
  function setChecks() {
    const selected = report?.figures.find(item => item.id === figure.value);
    const old = check.value;
    check.replaceChildren(new Option("Choose a check", ""));
    for (const option of selected?.checks || []) {
      check.add(new Option(description(option.target), option.id));
    }
    if (selected?.checks.some(item => item.id === old)) check.value = old;
    controls();
  }
  function show(value) {
    report = value;
    const old = figure.value;
    figure.replaceChildren(new Option("Choose a figure", ""));
    for (const item of report.figures) {
      const option = new Option(item.id + (item.checks.length ? "" : " · " + item.reason), item.id);
      option.disabled = !item.checks.length;
      figure.add(option);
    }
    if (report.figures.some(item => item.id === old && item.checks.length)) figure.value = old;
    else if (report.figures.filter(item => item.checks.length).length === 1)
      figure.value = report.figures.find(item => item.checks.length).id;
    setChecks();
    list.replaceChildren();
    if (!report.links.length) add(list, "p", "No saved claim links.");
    for (const entry of report.links) {
      const card = add(list, "article");
      card.dataset.state = entry.status;
      add(card, "h3", statusNames[entry.status]);
      add(card, "blockquote", entry.anchor.text);
      add(card, "p", location(entry.anchor, entry.location) + " · " + entry.figure);
      add(card, "p", description(entry.check));
      if (entry.check_result) add(card, "p", entry.check_result.detail);
      if (entry.reason) add(card, "p", entry.reason);
      if (entry.evidence) {
        const inspect = button(card, "Open linked figure audit");
        inspect.className = "secondary";
        inspect.onclick = async () => {
          try { await openAudit(entry.evidence.event, entry.figure); }
          catch (error) { status.textContent = error.message; }
        };
      }
      const remove = button(card, "Remove this claim link");
      remove.className = "quiet";
      remove.onclick = () => mutate({ action: "remove", id: entry.id, links_revision: report.links_revision });
    }
    const needsReview = report.links.filter(item => item.status !== "supported").length;
    status.textContent = report.links.length + " saved · " + needsReview + " need review";
  }
  async function refresh() {
    const expected = current(), version = ++epoch;
    if (!expected) return;
    busy = true; clearReview(); controls();
    status.textContent = "Checking current text and saved audit evidence…";
    try {
      const result = await api(route);
      if (same(expected, version)) show(result);
    } catch (error) {
      if (same(expected, version)) {
        report = null; list.replaceChildren(); status.textContent = error.message;
      }
    } finally {
      if (same(expected, version)) { busy = false; controls(); }
    }
  }
  async function mutate(body) {
    const expected = current(), version = epoch;
    if (!expected || busy) return;
    busy = true; controls();
    for (const node of proposal.querySelectorAll("button, input")) node.disabled = true;
    try {
      await api(route, body);
      if (same(expected, version)) await refresh();
    } catch (error) {
      if (same(expected, version)) {
        status.textContent = error.message;
        clearReview();
      }
    } finally {
      if (same(expected, version)) { busy = false; controls(); }
    }
  }
  async function reviewLink() {
    const expected = current(), version = epoch;
    if (!expected || busy || !check.value) return;
    clearReview();
    const versionOfForm = formVersion;
    const anchor = { kind: kind.value, text: excerpt.value };
    if (kind.value === "manuscript") anchor.path = path.value;
    const draft = { figure: figure.value, check: check.value, anchor };
    busy = true; controls();
    try {
      const result = await api(route, { action: "review", draft });
      if (!same(expected, version) || versionOfForm !== formVersion) return;
      add(proposal, "h3", "Confirm the text and checked claim");
      add(proposal, "blockquote", result.link.anchor.text);
      add(proposal, "p", location(result.link.anchor, result.location) + " · " + result.link.figure);
      add(proposal, "p", description(result.link.check));
      add(proposal, "p", "Recorded verdict " + result.check_result.verdict + " · " + result.check_result.detail);
      const confirm = field(proposal, "I confirm this excerpt expresses the selected check", "input");
      confirm.type = "checkbox";
      confirm.closest("label").className = "power-confirm";
      const save = button(proposal, "Save confirmed claim link");
      save.disabled = true;
      confirm.onchange = () => { save.disabled = !confirm.checked || busy; };
      save.onclick = () => {
        if (confirm.checked && same(expected, version) && formVersion === versionOfForm)
          mutate({ action: "save", draft, confirmed: true, review_sha256: result.review_sha256 });
      };
      status.textContent = "Review the recorded check before linking.";
    } catch (error) {
      if (same(expected, version)) status.textContent = error.message;
    } finally {
      if (same(expected, version)) { busy = false; controls(); }
    }
  }
  function update() {
    const next = current();
    if (key === next) return;
    key = next;
    epoch++;
    busy = false; report = null; clearReview(); list.replaceChildren(); controls();
    status.textContent = key ? "Open the panel or refresh to see current checks." : "Choose a source-backed paper without an active audit.";
    if (key && mount.open) void refresh();
  }
  editor.addEventListener("input", () => { clearReview(); controls(); });
  figure.onchange = setChecks;
  reviewButton.onclick = reviewLink;
  reload.onclick = refresh;
  mount.addEventListener("toggle", () => { if (mount.open && key && !report && !busy) void refresh(); });
  controls();
  return { update };
}
