import { describeFinding } from "/diagnostics.js";

const $ = (id) => document.getElementById(id);
const words = (value) => String(value ?? "unknown").replaceAll("_", " ");
const pretty = (value) => JSON.stringify(value, null, 2);
const node = (tag, text, parent) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  parent?.append(item);
  return item;
};
function detail(parent, label, value) {
  const box = node("details", undefined, parent);
  node("summary", label, box); node("pre", pretty(value), box);
}

export function createScientificReview({ api, protect, edit, audit }) {
  let context, generation = 0, signature = "", selectedInEditor = "";
  let loadedSignature = "", lastQuery = 0, pending = 0;
  const eventSelect = $("review-event"), figureSelect = $("review-figure");
  const status = $("review-status"), preview = $("review-preview");
  const groups = $("review-groups"), downloads = $("review-downloads");
  const note = $("review-preview-note");
  const current = () => !eventSelect.value;
  function clear(message) {
    preview.hidden = true; preview.removeAttribute("src");
    note.hidden = false; note.textContent = message;
    groups.replaceChildren(); downloads.replaceChildren();
    status.dataset.state = "unknown";
  }
  function unavailable(message) {
    generation++; signature = ""; loadedSignature = "";
    clear(message); status.textContent = message;
    $("review-context").textContent = "Current project evidence cannot be verified. Saved history remains below.";
    $("review-audit").disabled = true; $("review-edit").disabled = true;
  }
  function options(select, entries, previous) {
    select.replaceChildren();
    entries.forEach(([value, label]) => { node("option", label, select).value = value; });
    if (entries.some(([value]) => value === previous)) select.value = previous;
  }
  function card(name, title, value) {
    const root = node("article", undefined, groups);
    root.className = "review-group"; root.dataset.reviewGroup = name;
    node("h3", title, root);
    if (!value || value.state === "unavailable" && value.reason) {
      node("p", value?.reason || "No executed evidence is available.", root);
      return null;
    }
    return root;
  }
  function render(row, result) {
    clear("No verified static preview in this selection.");
    const saved = !current();
    const matching = row.matches_latest_accepted_inputs && !row.rerun_recommended;
    status.dataset.state = saved ? "saved" : matching && !context.busy ? "matches" : "needs-audit";
    status.textContent = saved
      ? `Saved audit ${result.selection.event}. These are historical results${context.dirty ? "; the current draft is unverified" : ""}.`
      : context.busy ? "An audit is running. These saved checks do not verify its result."
      : matching ? "Declared current inputs match this accepted saved audit."
      : row.evidence_state === "not_run" ? "No audit yet. Run paper checks to create evidence."
      : row.evidence_state === "unavailable" ? "Evidence is unavailable. Inspect history and run a new audit."
      : "Audit recommended. Saved results do not establish the current version.";
    $("review-context").textContent = `${row.id} · ${saved ? "selected saved run" : "current declared inputs"} · ${words(row.execution_status)} in the recorded execution. Reading this view performs no new scientific checks.`;
    const g = row.groups;
    let root = card("claims", "Claims", g.claims);
    if (root) {
      if (!g.claims.items?.length) node("p", "No supported claim was declared in this execution.", root);
      for (const claim of g.claims.items || []) {
        const item = node("div", undefined, root);
        item.className = "review-claim"; item.dataset.verdict = claim.verdict;
        node("strong", `${words(claim.kind)}: ${words(claim.verdict)}`, item);
        if (["fails", "untested"].includes(claim.verdict)) describeFinding(item,
          { code: claim.verdict === "fails" ? "claim_failed" : "check_untested", message: claim.detail || words(claim.verdict) }, context.info.diagnostics);
        else node("p", claim.detail || "Read the recorded claim details below.", item);
      }
      if (g.claims.untested?.length) detail(root, "Untested checks", g.claims.untested);
      node("p", "These verdicts cover declared comparisons, not every scientific claim.", root).className = "muted";
    }
    root = card("uncertainty", "Uncertainty", g.uncertainty);
    if (root) {
      node("p", g.uncertainty.settings ? "Recorded interval settings:" : "No uncertainty method was declared.", root);
      if (g.uncertainty.settings) {
        const list = node("dl", undefined, root);
        for (const [key, value] of Object.entries(g.uncertainty.settings)) {
          const label = { kind: "Interval method", level: "Confidence level", over: "Replicate unit", display: "Shown as" }[key] || words(key);
          const text = key === "kind" && value === "ci" ? "Confidence interval" : key === "level" && typeof value === "number" ? `${value * 100}%` : typeof value === "object" ? pretty(value) : words(value);
          node("dt", label, list); node("dd", text, list);
        }
      }
      detail(root, "Recorded sample counts", g.uncertainty.sample_evidence);
      detail(root, "Recorded random constants", g.uncertainty.random_constants);
      node("p", "Check whether the method and replicate units suit the study. An interval alone cannot establish that.", root).className = "muted";
    }
    root = card("legibility", "Legibility", g.legibility);
    if (root) {
      const findings = g.legibility.findings || [];
      node("p", g.legibility.inspection?.available ? `${findings.length} recorded finding${findings.length === 1 ? "" : "s"}.` : "Recorded inspection is unavailable.", root);
      for (const finding of findings) {
        const item = node("div", undefined, root); item.className = "finding";
        describeFinding(item, finding, context.info.diagnostics);
      }
      detail(root, "Recorded inspection measurements", g.legibility.inspection);
      node("p", "This view retains all recorded diagnostics; some also concern data or scientific checks.", root).className = "muted";
    }
    root = card("reproduction", "Reproduction", g.reproduction);
    if (root) {
      const r = g.reproduction;
      for (const line of [
        r.saved_exports_verified ? "Selected export bytes match their saved hashes." : "Selected exports are missing, changed or unverified.",
        `Scientific runtime: ${words(r.runtime?.state)}.`,
        `Auditor and compiler sources: ${words(r.audit_compiler_source?.state)}.`,
        `Dependency versions: ${words(r.environment?.state)}.`,
        r.source_input_scope === "declared_script_inputs_only" ? "Python imports and other script inputs are not fully known. Rerun the script." : r.source_input_scope === "canonical_spec_inputs" ? "Input matching covers the declared figure specification and files." : "Original input coverage is not recorded. Rerun before accepting this version.",
      ]) node("p", line, root);
      detail(root, "Source, data and environment details", r);
      node("p", "These are consistency checks. They do not perform a new reproduction or reverify all dependency bytes, fonts and external tools.", root).className = "muted";
    }
    const messages = [...row.errors, ...row.audit_errors, ...row.policy_errors];
    if (messages.length) {
      const errors = node("div", undefined, groups); errors.className = "review-errors";
      messages.forEach((message) => node("p", message, errors));
    }
  }
  async function load(background = false) {
    if (!context?.state || !figureSelect.value) { unavailable("Project unavailable. Refresh before reviewing a figure."); return; }
    const version = ++generation;
    const selectedEvent = eventSelect.value, identity = figureSelect.value;
    lastQuery = Date.now();
    if (!background) { clear("Reading saved evidence…"); status.textContent = "Reading scientific review…"; }
    if (current() && context.dirty) {
      status.textContent = "Unsaved draft. Save and audit before reviewing this version.";
      $("review-context").textContent = "Saved history remains available in the evidence selector and below.";
      note.textContent = "The draft has not been rendered or checked.";
      return;
    }
    pending++;
    try {
      const query = selectedEvent ? "?" + new URLSearchParams({ event: selectedEvent }) : "";
      const result = await api("/api/review" + query);
      if (version !== generation) return;
      if (result.current_revision !== context.state.revision) throw Error("Project inputs changed. Refresh before reviewing this version.");
      const row = result.figures.find((item) => item.id === identity);
      if (!row) throw Error("This binding is absent from the current project. Its saved source and results remain in the history below.");
      const incoming = pretty([row, result.selection, context.busy, context.dirty, eventSelect.value]);
      if (background && incoming === loadedSignature) return;
      render(row, result);
      loadedSignature = incoming;
      if (result.selection.state !== "intact_run" || !row.groups.reproduction.saved_exports_verified) return;
      const savedEvent = await api("/api/event?" + new URLSearchParams({ id: result.selection.event }));
      if (version !== generation) return;
      const figure = savedEvent.result.audit?.figures.find((item) => item.id === identity);
      for (const [index, output] of (figure?.outputs || []).entries()) {
        const link = node("a", "Saved " + output.format.toUpperCase(), downloads);
        link.className = "download";
        link.href = protect("/api/artifact", { event: savedEvent.id, figure: identity, index });
      }
      const response = await fetch(protect("/api/preview", { event: savedEvent.id, figure: identity }));
      if (!response.ok) throw Error((await response.json()).error || "Saved preview is unavailable.");
      const blob = await response.blob();
      const source = await new Promise((accept, reject) => {
        const reader = new FileReader(); reader.onload = () => accept(reader.result);
        reader.onerror = () => reject(Error("Saved preview could not be read.")); reader.readAsDataURL(blob);
      });
      if (version !== generation) return;
      preview.onload = () => { if (version === generation) { note.hidden = false; note.textContent = "Saved export from " + savedEvent.id + "."; } };
      preview.onerror = () => { if (version === generation) { preview.hidden = true; note.textContent = "The browser could not display the saved export."; } };
      preview.alt = figure?.report?.alt_text || "Saved figure " + identity;
      preview.src = source; preview.hidden = false;
    } catch (problem) {
      if (version !== generation) return;
      preview.hidden = true; preview.removeAttribute("src"); downloads.replaceChildren();
      status.dataset.state = "unknown"; status.textContent = problem.message;
      loadedSignature = "";
      note.hidden = false; note.textContent = "No current preview is available for this selection.";
    } finally { pending--; }
  }
  eventSelect.onchange = () => { signature = ""; load(); };
  figureSelect.onchange = () => { signature = ""; load(); };
  $("review-latest").onclick = () => { eventSelect.value = ""; signature = ""; load(); };
  $("review-audit").onclick = audit;
  $("review-edit").onclick = () => edit(figureSelect.value);
  return {
    refresh: () => load(),
    unavailable,
    update(next) {
      context = next;
      if (!next.state) return;
      if (!next.state.revision || !next.state.figures.length) {
        figureSelect.replaceChildren();
        unavailable("Project unavailable. " + (next.state.error || "No current figure evidence can be read."));
        return;
      }
      options(eventSelect, [["", "Current inputs"], ...next.state.history.filter((item) => item.action === "run" && item.integrity).map((item) => [item.id, "Saved " + item.id + " · " + words(item.status)])], eventSelect.value);
      const previous = selectedInEditor !== next.selected ? next.selected : figureSelect.value;
      selectedInEditor = next.selected;
      options(figureSelect, next.state.figures.map((item) => [item.id, item.id]), previous);
      $("review-audit").disabled = next.busy || next.dirty || !next.state.revision;
      $("review-edit").disabled = next.busy || next.dirty || !figureSelect.value;
      const key = pretty([next.state.revision, next.state.status, next.state.history.length, next.state.history_integrity,
        next.state.figures.map((item) => [item.id, item.freshness, item.last_accepted, item.artifacts_verified, item.errors]),
        next.dirty, next.busy, eventSelect.value, figureSelect.value]);
      if (signature !== key) { signature = key; load(); }
      else if (!pending && Date.now() - lastQuery >= 10000) load(true);
    },
  };
}
