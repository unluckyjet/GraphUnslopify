import { createControls } from "/controls.js";
import { describeFinding } from "/diagnostics.js";
import { createScientificReview } from "/project-review.js";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="preview-token"]').content;
let state, info, record, event, selected = "", sharedRevision = "";
let sourceDirty = false, entryDirty = false, sharedDirty = false, running = false;
let sourceError = "", sharedError = "", sourceValid = false, sharedValid = true;
let navigation = 0, evidence = 0, refreshVersion = 0, saving = false, loadingFigure = false;
let historyChoice = 0, auditNavigation = 0;
let refreshFailure = "";
const undo = [];
const pretty = (value) => JSON.stringify(value, null, 2);
const words = (value) => String(value ?? "").replaceAll("_", " ");
const actionNames = { run: "Audit", settings: "Shared settings", figure: "Figure definition", entry: "Manifest binding" };
const el = (tag, text, parent) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent?.append(node);
  return node;
};
function error(message = "") { $("error").textContent = message; $("error").hidden = !message; }
function notice(message) { $("notice").textContent = message; }
const dirty = () => sourceDirty || entryDirty || sharedDirty;
let review;
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Preview-Token": token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || "The project request failed.");
  return result;
}
const protect = (path, query) => path + "?" + new URLSearchParams({ ...query, token });
function object(text, label) {
  const value = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error(label + " must be a JSON object.");
  return value;
}
function lockControls() {
  const busy = running || saving;
  $("audit").disabled = busy || dirty() || !state?.revision;
  $("running").hidden = !running;
  $("shared-controls").disabled = busy || sourceDirty || entryDirty || !sharedValid;
  $("shared-json").disabled = busy || sourceDirty || entryDirty;
  $("save-shared").disabled = busy || !sharedDirty || !!sharedError;
  $("discard-shared").disabled = busy || sourceDirty || entryDirty;
  $("figure-controls").disabled = busy || sharedDirty || entryDirty || !record?.editable || !sourceValid;
  $("definition").disabled = busy || sharedDirty || entryDirty || !record;
  $("definition").readOnly = !record?.editable;
  $("save-definition").disabled = busy || sharedDirty || entryDirty || !sourceDirty || !!sourceError || !record?.editable;
  $("entry").disabled = busy || sharedDirty || sourceDirty || !record;
  $("save-entry").disabled = busy || !entryDirty || sharedDirty || sourceDirty;
  $("reload-definition").disabled = busy || sharedDirty || !record;
  $("duplicate").disabled = busy || dirty() || !record;
  $("remove").disabled = busy || dirty() || !record || (state?.figures.length || 0) < 2;
  $("undo-controls").disabled = busy || sharedDirty || entryDirty || !undo.length;
  review?.update({ state, selected, dirty: dirty(), busy, info });
}
function draft(kind) {
  if (kind === "source") sourceDirty = true;
  if (kind === "entry") entryDirty = true;
  if (kind === "shared") sharedDirty = true;
  evidence++;
  $("preview").hidden = true;
  $("preview").removeAttribute("src");
  $("preview-note").hidden = false;
  $("preview-note").textContent = "Unsaved changes. Save and audit to check this version; saved history remains available below.";
  $("comparison").hidden = true;
  notice("Unsaved changes. Save or reload this section before editing another section or auditing.");
  lockControls();
}
function controlError(message) {
  sourceError = message;
  $("control-error").textContent = message;
  $("control-error").hidden = !message;
  lockControls();
}
function syncDefinition() {
  sourceValid = false;
  if (record?.source_type === "script") { $("figure-controls").hidden = true; lockControls(); return; }
  $("figure-controls").hidden = false;
  try {
    const value = object($("definition").value, "Definition");
    sourceValid = !!info.schema.oneOf.find((branch) => branch.properties.kind.const === value.kind);
    controls.sync(value, info.schema, record?.columns || []);
    if (sourceValid) controlError("");
  } catch (problem) { controls.disable(problem.message); }
  lockControls();
}
const controls = createControls($("figure-controls"), {
  read: () => object($("definition").value, "Definition"),
  edit: () => draft("source"),
  error: controlError,
  change: (value) => {
    undo.push($("definition").value);
    if (undo.length > 20) undo.shift();
    $("definition").value = pretty(value);
    draft("source"); syncDefinition();
  },
});
function sharedProblem(message = "") {
  const invalid = [...$("shared-controls").querySelectorAll("input")].find((input) => input.validity.badInput || !input.checkValidity());
  if (!message && invalid) message = "Correct " + invalid.getAttribute("aria-label") + " before saving.";
  sharedError = message;
  $("shared-error").textContent = message;
  $("shared-error").hidden = !message;
  lockControls();
}
function sharedForm() {
  $("shared-controls").replaceChildren();
  let shared;
  try { shared = object($("shared-json").value, "Shared settings"); for (const key of ["style", "output"]) if (key in shared && (!shared[key] || typeof shared[key] !== "object" || Array.isArray(shared[key]))) throw Error("Shared " + key + " must be an object. Correct the shared JSON."); sharedValid = true; }
  catch (problem) { sharedValid = false; sharedProblem(problem.message); return; }
  sharedProblem("");
  const labels = { preset: "Presentation preset", venue: "Manuscript venue", colour_safe: "Colour-safe appearance", grid: "Grid", size: "Column width", dpi: "Export DPI", palette_lock: "Shared palette file" };
  const add = (group, key, schema) => {
    if (!["string", "boolean", "number", "integer"].includes(schema.type)) return;
    const label = el("label", labels[key] || words(key), $("shared-controls"));
    const choices = schema.enum || (schema.type === "boolean" ? [true, false] : null);
    const input = el(choices ? "select" : "input", undefined, label);
    input.id = "shared-" + (group ? group + "-" : "") + key;
    input.setAttribute("aria-label", labels[key] || words(key));
    const old = group ? shared[group]?.[key] : shared[key];
    if (choices) {
      el("option", "Inherit definition", input).value = "";
      choices.forEach((choice) => { el("option", typeof choice === "boolean" ? choice ? "Yes" : "No" : words(choice), input).value = String(choice); });
      input.value = old === undefined ? "" : String(old);
    } else {
      input.type = ["number", "integer"].includes(schema.type) ? "number" : "text";
      if (schema.minimum !== undefined) input.min = schema.minimum;
      if (schema.maximum !== undefined) input.max = schema.maximum;
      input.value = old ?? "";
      input.placeholder = "Inherit definition";
    }
    input.oninput = () => {
      draft("shared");
      if (input.validity.badInput || !input.checkValidity()) { sharedProblem("Correct " + (labels[key] || words(key)) + " before saving."); return; }
      const next = object($("shared-json").value, "Shared settings");
      const parent = group ? (next[group] ||= {}) : next;
      if (input.value === "") delete parent[key];
      else parent[key] = schema.type === "boolean" ? input.value === "true" : ["integer", "number"].includes(schema.type) ? Number(input.value) : input.value;
      if (group && !Object.keys(parent).length) delete next[group];
      $("shared-json").value = pretty(next);
      sharedProblem("");
    };
  };
  for (const group of ["style", "output"]) {
    for (const [key, schema] of Object.entries(info.shared_schema.properties[group].properties)) add(group, key, schema);
  }
  add(null, "palette_lock", info.shared_schema.properties.palette_lock);
  sharedProblem();
}
function loadShared() {
  sharedDirty = false;
  sharedRevision = state.revision;
  $("shared-json").value = pretty(state.shared || {});
  sharedForm();
}
function options(select, values, previous) {
  select.replaceChildren();
  values.forEach(([value, label]) => { el("option", label, select).value = value; });
  if (values.some(([value]) => value === previous)) select.value = previous;
}
function lists() {
  $("figure-count").textContent = String(state.figures.length);
  $("project-name").textContent = state.project_name;
  $("project-status").textContent = state.status === "inputs_match_last_run" ? "Inputs match accepted audit" : state.status === "unavailable" ? "Project unavailable" : "Audit needed";
  $("project-status").dataset.state = state.status === "inputs_match_last_run" ? "passed" : "incomplete";
  $("figure-list").replaceChildren();
  state.figures.forEach((figure) => {
    const button = el("button", undefined, $("figure-list"));
    button.className = "figure-choice";
    button.dataset.figure = figure.id;
    button.setAttribute("aria-pressed", String(figure.id === selected));
    el("strong", figure.id, button);
    el("small", words(figure.kind || figure.source_type) + " · " + words(figure.last_status), button);
    el("small", "Inputs: " + words(figure.freshness), button);
    button.onclick = action(() => choose(figure.id));
  });
  const history = state.history.map((item) => [item.id, `${item.created_at ? item.created_at.slice(0, 19).replace("T", " ") + " UTC" : "Interrupted"} · ${actionNames[item.action] || "Event"} · ${words(item.status || item.phase)}`]);
  options($("history"), history, $("history").value);
  const currentBaseline = $("baseline").value;
  options($("baseline"), [["latest", "Latest intact audit"], ["", "No baseline"], ...state.history.filter((item) => item.action === "run" && item.integrity).map((item) => [item.id, item.id.slice(0, 8) + " · " + words(item.status)])], currentBaseline);
  $("history-integrity").textContent = state.history_integrity === "verified" ? "Saved receipts intact" : "Some history is incomplete or damaged";
  lockControls();
}
async function refresh({ reload = false } = {}) {
  const version = ++refreshVersion;
  const next = await api("/api/state");
  if (version !== refreshVersion) return;
  const changed = state && state.revision !== next.revision;
  const previousError = state?.error;
  state = next;
  running = state.job?.phase === "running";
  lists();
  if (state.error) error(state.error);
  else if ([previousError, refreshFailure].filter(Boolean).includes($("error").textContent)) error();
  refreshFailure = "";
  if (!dirty() && !loadingFigure && (reload || changed || !record)) {
    loadShared();
    const id = state.figures.some((figure) => figure.id === selected) ? selected : state.figures[0]?.id;
    if (id) await choose(id, true);
  }
  if (changed && dirty()) notice("Saved project inputs changed. Your draft is kept; reload and review before saving it.");
}
async function choose(identity, automatic = false) {
  if (!automatic && dirty()) {
    if (!confirm("Discard unsaved changes and load this figure?")) return;
    sourceDirty = entryDirty = sharedDirty = false;
    loadShared();
  }
  const version = ++navigation;
  selected = identity; record = null; loadingFigure = true;
  controls.discard(); lockControls();
  let next;
  try { next = await api("/api/figure?" + new URLSearchParams({ id: identity })); }
  finally { if (version === navigation) loadingFigure = false; }
  if (version !== navigation || automatic && dirty()) return;
  controls.discard();
  selected = identity; record = next; sourceDirty = entryDirty = false; undo.length = 0;
  $("selected-title").textContent = identity;
  $("source").textContent = "Original source: " + record.source;
  const overrides = ["data", "claims"].filter((key) => key in record.entry);
  $("source-note").textContent = [record.reason, overrides.length ? "The manifest overrides " + overrides.join(" and ") + "; edit the binding below to change those applied values." : "", record.shared_by.length > 1 ? "This source is also used by: " + record.shared_by.filter((id) => id !== identity).join(", ") : "", ...record.errors].filter(Boolean).join(" ");
  $("definition").value = record.text;
  $("entry").value = pretty(record.entry);
  if (record.source_type === "script") $("definition-panel").open = true;
  syncDefinition(); lists();
  if (!sourceValid && record.source_type === "spec") $("definition-panel").open = true;
}
function clearEvidence() {
  $("preview").hidden = true; $("preview").removeAttribute("src");
  $("preview-note").hidden = false;
  $("preview-note").textContent = "No static preview in this event.";
  $("checks").replaceChildren(); $("exports").replaceChildren();
  $("comparison").hidden = true; $("saved-source-panel").hidden = true;
  $("show-comparison").disabled = true; $("show-source").disabled = true;
}
async function loadEvent() {
  const version = ++evidence;
  clearEvidence();
  event = null;
  $("history-figure").replaceChildren();
  const id = $("history").value;
  if (!id) return;
  try {
    const next = await api("/api/event?" + new URLSearchParams({ id }));
    if (version !== evidence) return;
    event = next;
    const result = event.result;
    const figures = result.audit?.figures || result.before?.figures || result.snapshot?.figures || [];
    options($("history-figure"), figures.map((figure) => [figure.id, figure.id]), figures.some((figure) => figure.id === selected) ? selected : $("history-figure").value);
    $("event-summary").textContent = `${actionNames[event.action] || "Saved event"} · ${words(result.status)}` + (event.action === "run" ? ` · scientific checks: ${words(result.audit_status)}` : " · figures were not executed by this change");
    $("event-json").textContent = pretty(result);
    await showFigure();
    if (!figures.length) (result.errors || []).forEach((message) => el("p", message, $("checks")));
  } catch (problem) { if (version === evidence) { event = null; $("event-summary").textContent = problem.message; } }
}
async function showFigure() {
  const version = ++evidence;
  clearEvidence();
  if (!event) return;
  const id = $("history-figure").value;
  if (!id) return;
  $("show-source").disabled = false;
  const result = event.result;
  const figure = result.audit?.figures.find((item) => item.id === id);
  if (!figure) { el("p", event.action === "run" ? "This audit did not reach figure execution." : "This event records a definition/settings change, not an executed figure.", $("checks")); (result.errors || []).forEach((message) => el("p", message, $("checks"))); return; }
  el("p", "Scientific result: " + words(figure.status), $("checks"));
  el("p", result.exit_code === 0 ? "Paper accepted in this saved run." : "Paper not accepted in this saved run. Inspect its policy and findings.", $("checks"));
  const report = figure.report;
  [...(figure.errors || []), ...(figure.warnings || []), ...(result.errors || []), ...(result.policy_errors?.[id] || [])].forEach((message) => el("p", message, $("checks")));
  (report?.claims || []).forEach((claim) => {
    const message = `Claim ${words(claim.kind)}: ${claim.verdict}. ${claim.detail || ""}`;
    if (["fails", "untested"].includes(claim.verdict)) describeFinding(el("div", undefined, $("checks")),
      {code: claim.verdict === "fails" ? "claim_failed" : "check_untested", message}, info.diagnostics);
    else el("p", message, $("checks"));
  });
  (report?.findings || []).forEach((finding) => {
    const node = el("div", undefined, $("checks"));
    node.className = "finding" + (finding.severity === "error" ? " error" : "");
    describeFinding(node, finding, info.diagnostics);
  });
  if (report?.alt_text) { const details = el("details", undefined, $("checks")); el("summary", "Figure description", details); el("p", report.alt_text, details); }
  figure.outputs.forEach((output, index) => { const link = el("a", output.format.toUpperCase(), $("exports")); link.className = "download"; link.href = protect("/api/artifact", { event: event.id, figure: id, index }); });
  $("show-comparison").disabled = !result.baseline;
  const image = $("preview");
  const url = protect("/api/preview", { event: event.id, figure: id });
  try {
    const response = await fetch(url, { headers: { "X-Preview-Token": token } });
    if (!response.ok) throw Error((await response.json()).error || "Preview is unavailable.");
    const blob = await response.blob();
    if (version !== evidence) return;
    const source = await new Promise((accept, reject) => { const reader = new FileReader(); reader.onload = () => accept(reader.result); reader.onerror = () => reject(Error("Could not read the static preview.")); reader.readAsDataURL(blob); });
    if (version !== evidence) return;
    image.onload = () => { if (version === evidence) $("preview-note").hidden = true; };
    image.onerror = () => { if (version === evidence) { image.hidden = true; $("preview-note").textContent = "The browser could not display this static export."; } };
    image.alt = report?.alt_text || "Saved figure " + id;
    image.src = source; image.hidden = false;
  } catch (problem) { if (version === evidence) $("preview-note").textContent = problem.message; }
}
async function compare() {
  const version = evidence, id = $("history-figure").value;
  const result = await api("/api/comparison?" + new URLSearchParams({ event: event.id, figure: id }));
  if (version !== evidence) return;
  const root = $("comparison"); root.replaceChildren(); root.hidden = false;
  el("h3", "Before, after & difference", root);
  if (!result.available) { el("p", result.reason, root); return; }
  const grid = el("div", undefined, root); grid.className = "comparison-images";
  for (const key of ["before", "after", "difference"]) {
    const frame = el("figure", undefined, grid);
    if (result.images[key]) { const image = el("img", undefined, frame); image.alt = words(key) + " for " + id; image.src = result.images[key]; }
    el("figcaption", words(key) + (result[key]?.reason ? ": " + result[key].reason : ""), frame);
  }
  (result.changes || []).forEach((change) => el("p", change.message, root));
  if (result.metrics) el("p", `${result.metrics.visible_pixels_changed} of ${result.metrics.total_pixels} visible pixels changed; images were not resampled.`, root);
  else el("p", "Pixel metrics are unavailable for these formats or different canvas sizes.", root);
  el("p", result.scope, root).className = "muted";
}
function action(work) { return async () => { error(); try { await work(); } catch (problem) { error(problem.message); } }; }
review = createScientificReview({ api, protect, audit: () => $("audit").click(), edit: action(async (id) => { if (id !== selected) await choose(id); document.querySelector(".definition-card").scrollIntoView({ behavior: "smooth" }); }) });
async function save(route, body) {
  saving = true; lockControls();
  try { await api(route, body); sourceDirty = entryDirty = sharedDirty = false; await refresh({ reload: true }); await loadEvent(); notice("Saved. Audit the paper to check this version."); }
  finally { saving = false; lockControls(); }
}
$("definition").oninput = () => { navigation++; controls.discard(); draft("source"); syncDefinition(); };
$("entry").oninput = () => { navigation++; draft("entry"); };
$("shared-json").oninput = () => { draft("shared"); sharedForm(); };
$("save-definition").onclick = action(async () => { if (!controls.flush()) return; await save("/api/definition", { id: selected, spec: object($("definition").value, "Definition"), expected_revision: record.revision }); });
$("save-entry").onclick = action(() => save("/api/entry", { id: selected, entry: object($("entry").value, "Manifest binding"), expected_revision: record.revision }));
$("save-shared").onclick = action(() => save("/api/shared", { shared: object($("shared-json").value, "Shared settings"), expected_revision: sharedRevision }));
$("discard-shared").onclick = action(async () => { sharedDirty = false; await refresh({ reload: true }); notice("Loaded saved settings."); });
$("reload-definition").onclick = action(async () => { sourceDirty = entryDirty = false; await refresh({ reload: true }); notice("Loaded saved definition."); });
$("undo-controls").onclick = action(() => { const previous = undo.pop(); if (previous !== undefined) { controls.discard(); $("definition").value = previous; draft("source"); syncDefinition(); } });
$("duplicate").onclick = action(async () => {
  const id = $("new-id").value.trim(); if (!id) throw Error("Choose a unique new figure ID.");
  const entry = structuredClone(record.clone); entry.id = id;
  if (typeof entry.spec === "object" && entry.spec.output) entry.spec.output.stem = id;
  await save("/api/entry", { id, entry, mode: "add", expected_revision: record.revision });
  $("new-id").value = ""; await choose(id, true);
});
$("remove").onclick = action(async () => {
  if (!confirm("Remove " + selected + " from the paper manifest? Its source files, data and history are kept.")) return;
  await save("/api/entry", { id: selected, mode: "remove", expected_revision: record.revision });
});
$("refresh").onclick = action(async () => { if (dirty() && !confirm("Discard unsaved changes and refresh the project?")) return; sourceDirty = entryDirty = sharedDirty = false; await refresh({ reload: true }); await review.refresh(); await loadEvent(); notice("Project refreshed."); });
$("history").onchange = action(async () => { historyChoice++; await loadEvent(); });
$("history-figure").onchange = action(async () => { historyChoice++; await showFigure(); });
$("show-comparison").onclick = action(compare);
$("show-source").onclick = action(async () => { const version = evidence; const result = await api("/api/saved-source?" + new URLSearchParams({ event: event.id, figure: $("history-figure").value })); if (version !== evidence) return; $("saved-source").value = result.text; $("saved-source-label").textContent = result.context; $("saved-source-panel").hidden = false; $("saved-source-panel").open = true; });
$("audit").onclick = action(async () => {
  auditNavigation = historyChoice;
  await api("/api/run", { expected_revision: state.revision, baseline: $("baseline").value || null, fail_on_warning: $("fail-warning").checked, fail_on_change: $("fail-change").checked });
  running = true; lockControls(); notice("Paper audit started. Saved history remains available while it runs.");
});
async function poll() {
  try {
    const wasRunning = running;
    await refresh();
    if (wasRunning && !running) {
      if (state.job?.error) error(state.job.error);
      else notice("Audit finished: " + words(state.job?.result?.status) + ". Choose the newest history event to review it.");
      if (state.job?.result?.id && historyChoice === auditNavigation) { $("history").value = state.job.result.id; await loadEvent(); }
    }
  } catch (problem) { refreshFailure = "Could not refresh the project: " + problem.message; error(refreshFailure); review.unavailable(refreshFailure); }
  setTimeout(poll, 2500);
}
action(async () => { info = await api("/api/info"); await refresh({ reload: true }); await loadEvent(); notice("Ready. Review definitions and saved results, or audit the paper."); setTimeout(poll, 2500); })();
