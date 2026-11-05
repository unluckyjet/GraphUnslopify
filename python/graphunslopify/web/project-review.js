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

function scorecard(parent, value) {
  if (!value) return;
  const box = node("section", undefined, parent); box.className = "component-scorecard";
  node("h4", "Reproducibility scorecard", box);
  node("p", "Available, Partial and Missing describe evidence here. Scientific outcomes remain separate; this view does not rerun the figures.", box).className = "muted";
  node("p", `Recorded scientific outcome: ${words(value.scientific_status)}.`, box);
  for (const component of value.components) {
    const item = node("div", undefined, box); item.className = "scorecard-component";
    item.dataset.component = component.id; item.dataset.availability = component.state;
    node("strong", component.label, item);
    const label = words(component.state); node("span", label[0].toUpperCase() + label.slice(1), item).className = "availability";
    node("p", component.summary, item);
    detail(item, "Evidence details", component.evidence);
  }
}

export function createScientificReview({ api, protect, edit, audit, inspect, exportPacket, selection = () => {}, onEvidenceChange = () => {} }) {
  let context, generation = 0, signature = "", selectedInEditor = "";
  let loadedSignature = "", lastQuery = 0, pending = 0;
  let desiredSelection = "", loadedRow = null, pageSource = "";
  let loadedCollection = null, exporting = false;
  let foregroundQuery = 0, loadedSelectors = null;
  const eventSelect = $("review-event"), figureSelect = $("review-figure");
  const status = $("review-status"), preview = $("review-preview");
  const groups = $("review-groups"), downloads = $("review-downloads");
  const note = $("review-preview-note");
  const pageSelect = $("review-page");
  const current = () => !eventSelect.value;
  function exportControls() {
    $("review-export").disabled = exporting || pending > 0 || context?.busy || context?.dirty || !loadedCollection?.evidence_revision;
    eventSelect.disabled = exporting; figureSelect.disabled = exporting; pageSelect.disabled = exporting;
    $("review-latest").disabled = exporting;
  }
  function clear(message) {
    preview.hidden = true; preview.removeAttribute("src");
    note.hidden = false; note.textContent = message;
    groups.replaceChildren(); downloads.replaceChildren();
    $("review-page-label").hidden = true;
    status.dataset.state = "unknown";
  }
  function unavailable(message) {
    generation++; signature = ""; loadedSignature = "";
    loadedCollection = null; exportControls();
    foregroundQuery = 0; loadedSelectors = null; onEvidenceChange();
    clear(message); status.textContent = message;
    $("review-context").textContent = "Current project evidence cannot be verified. Saved history remains below.";
    $("review-audit").disabled = true; $("review-edit").disabled = true;
    $("review-inspect").disabled = true;
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
      : context.busy ? "A project operation is running. These checks describe their saved execution."
      : matching ? "Declared current inputs match this accepted saved audit."
      : row.evidence_state === "not_run" ? "No audit yet. Run paper checks to create evidence."
      : row.evidence_state === "unavailable" ? "Evidence is unavailable. Inspect history and run a new audit."
      : "Audit recommended. Saved results do not establish the current version.";
    $("review-context").textContent = `${row.id} · ${saved ? "selected saved run" : "current declared inputs"} · ${words(row.execution_status)} in the recorded execution. Reading this view performs no new scientific checks.`;
    if (result.native_run) $("review-context").textContent += ` Whole-paper audit: ${words(result.native_run.status)} · exit ${result.native_run.exit_code}.`;
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
      if (r.execution) node("p", r.execution.mode === "reused" ? `Reused accepted evidence; original execution ${r.execution.origin_event}. This figure was not executed again.` : `Figure execution: ${words(r.execution.mode)}.`, root);
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
    scorecard(groups.querySelector('[data-review-group="reproduction"]'), row.scorecard);
    const messages = [...row.errors, ...row.audit_errors, ...row.policy_errors];
    if (messages.length) {
      const errors = node("div", undefined, groups); errors.className = "review-errors";
      messages.forEach((message) => node("p", message, errors));
    }
  }
  function renderPdf(row, result) {
    clear("No intact saved page preview is available.");
    const evidence = row.inspection, saved = evidence.explicit_history_selection;
    const available = evidence.evidence_state === "saved_visual_evidence";
    status.dataset.state = saved || !available ? "saved" : "visual-only";
    const label = saved ? "Saved historical PDF inspection" : available ? "Source-free PDF inspection" : evidence.inspection ? "Historical PDF visual evidence" : "PDF visual evidence unavailable";
    status.textContent = `${label} · ${words(row.execution_status)}. Numerical claims and original data remain untested.`;
    $("review-context").textContent = `${row.name} · source ${words(row.freshness)} · saved inspection ${evidence.event}. Page rendering does not locate figures automatically.`;
    let root = card("claims", "Claims", row.groups.claims);
    if (root) { node("p", row.groups.claims.reason, root).dataset.verdict = "untested"; }
    root = card("uncertainty", "Uncertainty", row.groups.uncertainty);
    if (root) node("p", row.groups.uncertainty.reason, root);
    root = card("legibility", "Legibility", row.groups.legibility);
    const page = row.groups.legibility.pages.find((item) => String(item.page) === pageSelect.value);
    if (root) {
      node("p", row.groups.legibility.reason, root);
      if (page) {
        for (const check of page.visual?.checks || []) {
          const label = check.name === "text_size" ? "Text size" : check.name === "raster_resolution" ? "Image resolution" : words(check.name);
          let text = `${label}: ${words(check.status)}.`;
          if (check.name === "text_size" && typeof check.minimum_pt === "number") text += ` Minimum measured text ${check.minimum_pt.toPrecision(3)}pt; review threshold ${check.threshold_pt}pt.`;
          if (check.name === "raster_resolution" && typeof check.minimum_dpi === "number") text += ` Minimum measured image resolution ${check.minimum_dpi.toPrecision(3)}dpi; review threshold ${check.threshold_dpi}dpi.`;
          node("p", text, root);
        }
        detail(root, `Page ${page.page} recorded visual measurements`, page.visual);
        node("p", `Text: ${words(page.text?.status)}. These measurements do not establish scientific correctness.`, root);
      }
      detail(root, "PDF renderer and DPI", row.groups.legibility.renderer);
    }
    root = card("reproduction", "Reproduction", row.groups.reproduction);
    if (root) {
      node("p", evidence.assets_verified ? "Saved page, text and report bytes match their recorded hashes." : "Saved visual assets are unavailable or changed.", root);
      node("p", evidence.freshness === "unchanged" ? "The current PDF bytes match this inspection's source hash." : "The current PDF is changed or unavailable. Saved evidence remains historical.", root);
      node("p", "Original data and plotting programs were not reproduced. No native plotting program executes during PDF inspection.", root);
      if (evidence.origin === "uploaded_local_copy") node("p", "The uploaded source copy stays in this local project; original PDFs are excluded from inspection history.", root);
      detail(root, "Recorded and current PDF source hashes", row.groups.reproduction);
      scorecard(root, row.scorecard);
    }
    for (const message of row.errors) node("p", message, groups).className = "review-errors";
    $("review-page-label").hidden = !pageSelect.options.length;
    $("review-inspect").textContent = pageSelect.options.length ? "Inspect selected page again" : "Inspect page 1 again";
    node("p", "To correct a source-free figure, edit its original source and inspect an updated PDF. These page metrics do not infer numerical claims.", groups).className = "muted";
    return page;
  }
  async function displayPreview(path, version, alt, caption) {
    const response = await fetch(path);
    if (!response.ok) throw Error((await response.json()).error || "Saved preview is unavailable.");
    const blob = await response.blob();
    const source = await new Promise((accept, reject) => {
      const reader = new FileReader(); reader.onload = () => accept(reader.result);
      reader.onerror = () => reject(Error("Saved preview could not be read.")); reader.readAsDataURL(blob);
    });
    if (version !== generation) return;
    preview.onload = () => { if (version === generation) { note.hidden = false; note.textContent = caption; } };
    preview.onerror = () => { if (version === generation) { preview.hidden = true; note.textContent = "The browser could not display the saved export."; } };
    preview.alt = alt; preview.src = source; preview.hidden = false;
  }
  async function pdfPreview(row, page, version) {
    if (!row.inspection.assets_verified) return;
    for (const [index, asset] of row.inspection.assets.entries()) {
      if (!asset.path.endsWith(".png") && !asset.path.endsWith(".json") && !asset.path.endsWith(".txt")) continue;
      const link = node("a", "Saved " + asset.path.split("/").at(-1), downloads);
      link.className = "download";
      link.href = protect("/api/pdf-asset", { event: row.inspection.event, index });
    }
    if (!page) return;
    const index = row.inspection.assets.findIndex((asset) => asset.path === "packet/" + page.preview.path);
    if (index < 0) throw Error("The selected page is absent from the saved asset inventory.");
    await displayPreview(protect("/api/pdf-asset", { event: row.inspection.event, index, view: 1 }), version,
      `Saved PDF page ${page.page} from ${row.name}`,
      `Saved page ${page.page} from ${row.inspection.event}. Numerical claims remain untested.`);
  }
  async function load(background = false) {
    if (!context?.state || !figureSelect.value) { unavailable("Project unavailable. Refresh before reviewing a figure."); return; }
    const version = ++generation;
    const selectedEvent = eventSelect.value, identity = figureSelect.value;
    lastQuery = Date.now();
    if (!background) { foregroundQuery = version; loadedRow = null; loadedCollection = null; loadedSelectors = null; onEvidenceChange(); $("review-inspect").disabled = true; clear("Reading saved evidence…"); status.textContent = "Reading scientific review…"; }
    $("review-export").disabled = true;
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
      if (result.inspection_revision && result.inspection_revision !== context.state.inspection_revision) throw Error("PDF source or visual evidence changed. Refresh before reviewing this version.");
      const row = result.figures.find((item) => (item.key || item.id) === identity);
      if (!row) throw Error("This binding is absent from the current project. Its saved source and results remain in the history below.");
      loadedRow = row;
      loadedCollection = result;
      $("review-inspect").disabled = row.source_type !== "pdf" || context.busy || context.dirty || !(context.state.inspections || []).find((item) => item.id === row.id)?.current_sha256;
      if (row.source_type === "pdf") {
        options(pageSelect, row.groups.legibility.pages.map((page) => [String(page.page), "Page " + page.page]), pageSource === row.id ? pageSelect.value : "");
        pageSource = row.id;
      }
      loadedSelectors = [selectedEvent, identity, row.source_type === "pdf" ? pageSelect.value : ""];
      const incoming = pretty([row, result.selection, result.native_run, result.evidence_revision, context.busy, context.dirty, eventSelect.value, row.source_type === "pdf" ? pageSelect.value : ""]);
      if (background && incoming === loadedSignature) return;
      if (row.source_type === "pdf") {
        const page = renderPdf(row, result); loadedSignature = incoming;
        await pdfPreview(row, page, version); return;
      }
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
      await displayPreview(protect("/api/preview", { event: savedEvent.id, figure: identity }), version,
        figure?.report?.alt_text || "Saved figure " + identity, "Saved export from " + savedEvent.id + ".");
    } catch (problem) {
      if (version !== generation) return;
      preview.hidden = true; preview.removeAttribute("src"); downloads.replaceChildren();
      status.dataset.state = "unknown"; status.textContent = problem.message;
      loadedSignature = "";
      loadedCollection = null;
      note.hidden = false; note.textContent = "No current preview is available for this selection.";
    } finally { pending--; if (foregroundQuery === version) foregroundQuery = 0; exportControls(); onEvidenceChange(); }
  }
  eventSelect.onchange = () => { desiredSelection = ""; signature = ""; update(context); };
  figureSelect.onchange = () => { desiredSelection = ""; signature = ""; update(context); };
  function reloadSelection() {
    signature = "";
    return context?.state ? update(context) : load();
  }
  pageSelect.onchange = reloadSelection;
  $("review-latest").onclick = () => { eventSelect.value = ""; return reloadSelection(); };
  $("review-audit").onclick = audit;
  $("review-edit").onclick = () => edit(figureSelect.value);
  $("review-inspect").onclick = () => {
    if (loadedRow?.source_type !== "pdf" || loadedRow.key !== figureSelect.value) return;
    inspect?.(loadedRow.id, pageSelect.value ? [Number(pageSelect.value)] : [1], loadedRow.groups.legibility.renderer?.dpi || 144);
  };
  $("review-export").onclick = async () => {
    if (exporting || pending || context?.busy || context?.dirty || !loadedCollection) return;
    const snapshot = loadedCollection;
    exporting = true; exportControls();
    try { await exportPacket?.(snapshot); }
    finally { exporting = false; exportControls(); }
  };
  function update(next) {
      context = next;
      exportControls();
      onEvidenceChange();
      if (!next.state) return;
      if (!next.state.revision || !(next.state.figures.length + (next.state.inspections?.length || 0))) {
        figureSelect.replaceChildren();
        unavailable(next.state.mode === "review_only" && !next.state.error ? "Review-only project. Add a PDF to create visual evidence; numerical claims remain untested." : "Project unavailable. " + (next.state.error || "No current figure evidence can be read."));
        return;
      }
      options(eventSelect, [["", "Current inputs"], ...next.state.history.filter((item) => ["run", "inspection"].includes(item.action) && item.integrity).map((item) => [item.id, "Saved " + item.id + " · " + words(item.action) + " · " + words(item.status)])], eventSelect.value);
      const previous = desiredSelection || (selectedInEditor !== next.selected ? next.selected : figureSelect.value);
      selectedInEditor = next.selected;
      const saved = next.state.history.find((item) => item.id === eventSelect.value);
      const entries = saved?.action === "inspection" ? [["pdf:" + saved.inspection_id, "PDF · " + saved.inspection_id]] : next.state.figures.map((item) => [item.id, item.id]);
      if (!saved) entries.push(...(next.state.inspections || []).map((item) => ["pdf:" + item.id, "PDF · " + item.name]));
      options(figureSelect, entries, previous);
      if (entries.some(([key]) => key === desiredSelection)) desiredSelection = "";
      const pdf = figureSelect.value.startsWith("pdf:");
      selection(pdf ? "pdf" : "native", figureSelect.value);
      $("review-inspect").hidden = !pdf;
      $("review-inspect").disabled = next.busy || next.dirty || !next.state.inspection_revision || loadedRow?.key !== figureSelect.value || !(next.state.inspections || []).find((item) => "pdf:" + item.id === figureSelect.value)?.current_sha256;
      $("review-audit").disabled = next.busy || next.dirty || !next.state.revision || !next.state.figures.length;
      $("review-audit").textContent = pdf ? "Check source-backed figures" : "Run paper checks";
      $("review-edit").disabled = next.busy || next.dirty || !figureSelect.value || pdf;
      const key = pretty([next.state.revision, next.state.status, next.state.history.length, next.state.history_integrity,
        next.state.figures.map((item) => [item.id, item.freshness, item.last_accepted, item.artifacts_verified, item.errors]),
        next.state.inspection_revision, next.state.inspections,
        next.dirty, next.busy, eventSelect.value, figureSelect.value]);
      // Every foreground query records its signature, including page/latest
      // navigation. Otherwise the next unchanged state poll cancels its review.
      if (signature !== key) { signature = key; return load(); }
      else if (!pending && Date.now() - lastQuery >= 10000) return load(true);
  }
  function reviewerContext() {
    if (!context?.state || context.dirty || context.busy || context.reviewerBusy || foregroundQuery || !loadedCollection?.evidence_revision) return null;
    if (loadedCollection.current_revision !== context.state.revision || loadedCollection.inspection_revision && loadedCollection.inspection_revision !== context.state.inspection_revision) return null;
    const selected = figureSelect.value, page = selected.startsWith("pdf:") ? pageSelect.value : "";
    if (pretty(loadedSelectors) !== pretty([eventSelect.value, selected, page])) return null;
    return {
      key: pretty([loadedCollection.evidence_revision, eventSelect.value, selected, page]),
      source_kind: "paper-project", collection: loadedCollection,
      payload: {event: eventSelect.value || null}, selected: [selected],
      figures: loadedCollection.figures.map(row => ({key: row.key || row.id, label: row.source_type === "pdf" ? `PDF · ${row.name || row.id}` : row.id || row.key})),
      label: eventSelect.value ? `Saved historical evidence · ${eventSelect.value}` : "Current declared inputs · saved check evidence",
    };
  }
  return {
    reviewerContext,
    refresh: reloadSelection, unavailable, update,
    selected: () => figureSelect.value,
    select(key) {
      if (exporting) return;
      const saved = context?.state.history.find((item) => item.id === eventSelect.value);
      if (saved && ((key.startsWith("pdf:") ? saved.action !== "inspection" || "pdf:" + saved.inspection_id !== key : saved.action !== "run"))) eventSelect.value = "";
      desiredSelection = key; signature = ""; update(context);
    },
    openEvent(identity) { if (exporting) return; eventSelect.value = identity; desiredSelection = ""; signature = ""; update(context); },
  };
}
