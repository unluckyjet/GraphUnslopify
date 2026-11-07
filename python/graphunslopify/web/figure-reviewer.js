/** One explicitly consented, evidence-bound reviewer workflow for both workspaces. */
export function createFigureReviewer({mount, token, context, loadIntent}) {
  const node = (tag, text, parent) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = String(text ?? "");
    parent?.append(e); return e;
  };
  const field = (label, tag, id, parent) => {
    const box = node("label", label, parent), e = node(tag, undefined, box);
    e.id = "reviewer-" + id; return e;
  };
  const button = (text, id, parent) => {
    const e = node("button", text, parent); e.type = "button"; e.id = "reviewer-" + id; return e;
  };
  const checkbox = (text, id, parent) => {
    const label = node("label", undefined, parent); label.className = "check";
    const e = node("input", undefined, label); e.type = "checkbox"; e.id = "reviewer-" + id;
    label.append(document.createTextNode(text)); return e;
  };
  const root = node("details", undefined, mount); root.id = "figure-reviewer";
  node("summary", "Ask a skeptical reviewer", root);
  node("p", "Ask about selected figure evidence. Recorded checks stay separate from unverified model suggestions. Suggestions never change your figures.", root).className = "muted";
  const settings = node("details", undefined, root); settings.id = "reviewer-settings";
  node("summary", "Reviewer model · this session only", settings);
  const providerNote = node("p", "Reading provider settings…", settings); providerNote.id = "reviewer-provider-note";
  const protocol = field("Protocol", "select", "protocol", settings);
  protocol.add(new Option("Responses API", "responses")); protocol.add(new Option("Compatible Chat Completions API", "chat"));
  const endpoint = field("Full API endpoint", "input", "endpoint", settings); endpoint.type = "text"; endpoint.autocomplete = "off";
  const model = field("Model identifier", "input", "model", settings); model.type = "text"; model.maxLength = 200; model.autocomplete = "off";
  const apiKey = field("API key, if required", "input", "key", settings); apiKey.type = "password"; apiKey.autocomplete = "off";
  node("p", "Use HTTPS or loopback HTTP. Settings and keys are held in this server session. Re-enter the key when saving; a blank key clears authorization.", settings).className = "muted";
  const saveProvider = button("Save reviewer provider", "save-provider", settings);
  const disableProvider = button("Disable reviewer", "disable-provider", settings); disableProvider.className = "quiet";
  const selectionLabel = node("p", "Render a figure or load paper evidence first.", root); selectionLabel.id = "reviewer-selection-context";
  const figures = node("fieldset", undefined, root); figures.id = "reviewer-figures";
  node("legend", "Figures to review · choose 1–20", figures);
  const figureChoices = node("div", undefined, figures);
  const question = field("Reviewer question", "textarea", "question", root); question.rows = 3; question.maxLength = 12000;
  question.value = "What would a skeptical reviewer criticize about these figures?";
  const authorContext = field("Author context (optional)", "textarea", "context", root); authorContext.rows = 2; authorContext.maxLength = 8000;
  if (loadIntent) {
    const memory = node("details", undefined, root);
    memory.id = "reviewer-intent-memory";
    node("summary", "Add accepted research wording", memory);
    node("p", "Choose entries to copy into the editable author context.", memory).className = "muted";
    const choices = node("fieldset", undefined, memory);
    node("legend", "Accepted project wording", choices);
    const entries = node("div", undefined, choices);
    const add = button("Add selected wording to context", "add-intent", memory);
    const note = node("p", "", memory);
    note.setAttribute("role", "status");
    let memoryRevision, loading = false;
    const selected = () => [...entries.querySelectorAll("input:checked")];
    const controls = () => { choices.disabled = loading; add.disabled = loading || !selected().length; };
    const show = (state) => {
      memoryRevision = state.revision;
      entries.replaceChildren();
      for (const [category, values] of Object.entries(state.entries)) {
        for (const [name, wording] of Object.entries(values)) {
          const label = node("label", undefined, entries); label.className = "check";
          const input = node("input", undefined, label); input.type = "checkbox";
          const title = category.replaceAll("_", " ");
          input.value = `${title} · ${JSON.stringify(name)} → ${JSON.stringify(wording)}`;
          label.append(document.createTextNode(input.value));
        }
      }
      note.textContent = entries.childElementCount ? "" : "No accepted wording in this project yet.";
    };
    async function load(operation) {
      if (loading) return;
      loading = true; controls();
      try { operation(await loadIntent()); }
      catch (error) { note.textContent = error.message; }
      finally { loading = false; controls(); }
    }
    memory.addEventListener("toggle", () => { if (memory.open) void load(show); });
    choices.addEventListener("change", controls);
    add.onclick = () => void load(state => {
      if (state.revision !== memoryRevision) {
        show(state);
        note.textContent = "Accepted wording changed. Select entries again.";
        return;
      }
      const text = [authorContext.value, "Accepted project wording", ...selected().map(input => input.value)].filter(Boolean).join("\n");
      if (text.length > authorContext.maxLength) {
        note.textContent = "Choose fewer entries or shorten the existing author context.";
        return;
      }
      authorContext.value = text;
      authorContext.dispatchEvent(new Event("input"));
      for (const input of selected()) input.checked = false;
      note.textContent = "Added to author context. Review the exact model request before sending.";
    });
    controls();
  }
  const structured = checkbox("Request schema-constrained replies", "structured", settings); structured.checked = true;
  const prepare = button("Review the model request", "disclose", root);
  const status = node("p", "Nothing sent to a model.", root); status.id = "reviewer-status"; status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const disclosureBox = node("section", undefined, root); disclosureBox.id = "reviewer-disclosure"; disclosureBox.hidden = true;
  const destination = node("p", "", disclosureBox); destination.id = "reviewer-destination";
  const notice = node("p", "", disclosureBox); notice.className = "muted";
  const exact = node("details", undefined, disclosureBox); node("summary", "Exact request bytes, excluding authorization", exact);
  const digest = node("p", "", exact); digest.id = "reviewer-request-digest";
  const body = node("pre", "", exact); body.id = "reviewer-request-body";
  const consent = checkbox("I reviewed this destination and exact request and agree to send it", "consent", disclosureBox);
  const start = button("Send reviewed request", "start", disclosureBox);
  const evidence = node("section", undefined, root); evidence.id = "reviewer-evidence"; evidence.hidden = true;
  const advice = node("section", undefined, root); advice.id = "reviewer-advice"; advice.hidden = true;
  const downloads = node("div", undefined, root); downloads.className = "reviewer-actions";
  const saveRequest = button("Save disclosed request", "download-request", downloads);
  const saveResult = button("Save reviewer result", "download-result", downloads);
  const cancel = button("Cancel / clear review", "cancel", downloads); cancel.className = "quiet";
  const downloadScope = node("p", "", root); downloadScope.className = "muted"; downloadScope.id = "reviewer-download-scope";
  node("p", "Disclosures expire after 10 minutes. Cancellation stops this local request; information already sent cannot be recalled from a provider.", root).className = "muted";

  const client = crypto.randomUUID(), encoder = new TextEncoder();
  let generation = 0, source = null, sourceKey = "", disclosure = null, result = null;
  let phase = "idle", busy = false, closed = false, provider = null, providerDirty = false, configVersion = 0;
  let timer = null, expiry = null, polling = false;
  const selected = () => [...figureChoices.querySelectorAll("input:checked")].map(e => e.value);
  const currentContext = () => { try { return context(); } catch { return null; } };
  const current = (version, key) => !closed && generation === version && sourceKey === key && currentContext()?.key === key;
  const control = (version = generation, id = disclosure?.review_id) => ({client, generation: version, ...(id ? {review_id: id} : {})});
  async function request(action, value, {raw = false, keepalive = false} = {}) {
    const serialized = value === undefined ? undefined : JSON.stringify(value);
    if (serialized && encoder.encode(serialized).length > 65536) throw Error("Shorten the question or context; reviewer controls are limited to 64 KiB.");
    const response = await fetch("/api/reviewer/" + action, {
      method: value === undefined ? "GET" : "POST", keepalive,
      headers: {"X-Preview-Token": token, "Content-Type": "application/json"},
      ...(serialized === undefined ? {} : {body: serialized}),
    });
    const bytes = await response.arrayBuffer();
    // Disclosure repeats the <=1 MiB body as parsed JSON, literal text and evidence.
    // The separate downloaded-document contract remains 4 MiB.
    if (bytes.byteLength > (raw ? 4 : 8) * 1024 * 1024) throw Error("Reviewer response exceeds the size limit.");
    if (!response.ok) {
      let message = "Reviewer request could not be completed.";
      try { message = JSON.parse(new TextDecoder().decode(bytes)).error || message; } catch {}
      throw Error(message);
    }
    if (raw) {
      if (!response.headers.get("Content-Type")?.startsWith("application/json")) throw Error("Expected a reviewer JSON document.");
      return bytes;
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  function controls() {
    root.dataset.phase = phase;
    const count = selected().length;
    prepare.disabled = closed || busy || !source || !provider?.configured || providerDirty || !question.value.trim() || count < 1 || count > 20;
    consent.disabled = busy || phase !== "disclosed";
    start.disabled = busy || phase !== "disclosed" || !disclosure || !consent.checked;
    saveRequest.disabled = busy || !disclosure || !["disclosed", "completed"].includes(phase);
    saveResult.disabled = busy || phase !== "completed" || !result;
    cancel.disabled = !busy && !disclosure && !result && phase === "idle";
  }
  function invalidate(message = "Review the current evidence and prepare a fresh request.") {
    generation++; clearTimeout(timer); clearTimeout(expiry); timer = expiry = null;
    const cancellation = request("cancel", control(generation, null));
    // Ordinary edits cancel best-effort. Preparation awaits the original promise
    // and refuses if cancellation cannot be acknowledged.
    void cancellation.catch(() => {});
    disclosure = result = null; phase = "idle"; busy = false; consent.checked = false;
    disclosureBox.hidden = evidence.hidden = advice.hidden = true;
    body.textContent = digest.textContent = destination.textContent = notice.textContent = "";
    evidence.replaceChildren(); advice.replaceChildren(); status.textContent = message; controls();
    return cancellation;
  }
  function fail(problem) { invalidate(problem.message || String(problem)); phase = "failed"; controls(); }
  function refresh() {
    const next = currentContext(), key = next?.key || "";
    if (key !== sourceKey) {
      source = next; sourceKey = key;
      invalidate(next ? "Review this evidence and prepare a model request." : "Render a figure or load clean paper evidence before reviewing.");
      figureChoices.replaceChildren();
      for (const row of next?.figures || []) {
        const label = node("label", undefined, figureChoices); label.className = "check";
        const input = node("input", undefined, label); input.type = "checkbox"; input.value = row.key;
        input.checked = (next.selected || []).includes(row.key);
        label.append(document.createTextNode(row.label || row.key));
        input.onchange = () => invalidate();
      }
    } else source = next;
    selectionLabel.textContent = next?.label || "Render a figure or load clean paper evidence first.";
    downloadScope.textContent = next?.source_kind === "editor-render"
      ? "Editor requests are ephemeral snapshots. They cannot be replayed as saved paper CLI requests."
      : next ? "Saved paper requests can be replayed through the CLI while their evidence, source and provider context still match." : "";
    controls();
  }
  function adoptProvider(info, fill = true) {
    provider = info;
    if (fill && info.provider) { endpoint.value = info.provider.endpoint; model.value = info.provider.model; protocol.value = info.provider.protocol; }
    providerNote.textContent = info.configured ? `Configured: ${info.provider.model}. Authorization ${info.authorization_configured ? "configured" : "not configured"}.` : "No reviewer provider configured.";
    controls();
  }
  async function loadProvider() {
    const version = configVersion;
    try { const info = await request("provider"); if (!closed && version === configVersion && !providerDirty) adoptProvider(info); }
    catch (problem) { if (!closed && version === configVersion) providerNote.textContent = problem.message; }
  }
  for (const input of [endpoint, model, apiKey, protocol]) input.addEventListener(input === protocol ? "change" : "input", () => {
    configVersion++; providerDirty = true; invalidate("Save the changed reviewer provider and prepare a new request.");
  });
  for (const input of [question, authorContext]) input.addEventListener("input", () => invalidate());
  structured.onchange = () => invalidate(); consent.onchange = controls;
  async function configure(enabled) {
    const value = enabled ? {endpoint: endpoint.value.trim(), model: model.value.trim(), protocol: protocol.value, api_key: apiKey.value} : {enabled: false};
    apiKey.value = ""; const version = ++configVersion; providerDirty = true; invalidate("Saving reviewer provider…"); busy = true; controls();
    try {
      const info = await request("provider", value);
      if (closed || version !== configVersion) return;
      providerDirty = false; adoptProvider(info); settings.open = false; status.textContent = enabled ? "Provider saved. Review a request before sending anything." : "Reviewer disabled. Your figures are unchanged.";
    } catch (problem) { if (!closed && version === configVersion) { providerDirty = true; providerNote.textContent = problem.message; } }
    finally { if (!closed && version === configVersion) { busy = false; controls(); } }
  }
  saveProvider.onclick = () => configure(true); disableProvider.onclick = () => configure(false);
  function renderEvidence(packet) {
    evidence.replaceChildren(); evidence.hidden = false;
    node("h3", "Recorded deterministic evidence", evidence);
    node("p", packet.scope || "Saved evidence; no new scientific execution.", evidence).className = "muted";
    for (const row of packet.figures) {
      const article = node("article", undefined, evidence); article.dataset.figureKey = row.key;
      node("h4", row.key, article); node("p", `Recorded execution: ${row.execution_status}. Evidence: ${row.evidence_state}.`, article);
      for (const [key, value] of Object.entries(row.groups || {})) {
        const details = node("details", undefined, article); node("summary", key[0].toUpperCase() + key.slice(1), details);
        node("pre", JSON.stringify(value, null, 2), details);
      }
    }
    if (packet.recorded_failures?.length) { const details = node("details", undefined, evidence); node("summary", "Recorded failures", details); node("pre", JSON.stringify(packet.recorded_failures, null, 2), details); }
  }
  prepare.onclick = async () => {
    refresh(); if (prepare.disabled) return;
    const captured = structuredClone(source), keys = selected();
    const cancellation = invalidate("Preparing a local disclosure. Nothing sent to a model.");
    const version = generation, key = captured.key; busy = true; controls();
    try {
      // This cancellation uses the new generation. It must finish before that
      // generation's disclosure can exist, or it can cancel the new plan itself.
      await cancellation;
      if (!current(version, key)) return;
      const collection = captured.source_kind === "editor-render" ? await request("collection", captured.payload) : captured.collection;
      if (!current(version, key)) return;
      const value = await request("disclose", {...captured.payload, ...control(version, null), expected_revision: collection.evidence_revision,
        figures: keys, question: question.value, author_context: authorContext.value, structured_output: structured.checked});
      if (!current(version, key)) return;
      if (value.generation !== version || value.source_kind !== captured.source_kind || typeof value.request_body !== "string") throw Error("Reviewer disclosure does not match this workspace.");
      const bytes = encoder.encode(value.request_body);
      const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(n => n.toString(16).padStart(2, "0")).join("");
      if (!current(version, key)) return;
      if (bytes.length !== value.request_bytes || hash !== value.request_sha256 || value.binding !== collection.evidence_revision) throw Error("The exact reviewer request could not be verified.");
      disclosure = value; phase = "disclosed"; disclosureBox.hidden = false;
      destination.textContent = `${value.provider.model} · ${value.provider.endpoint} · ${value.provider.protocol}`;
      notice.textContent = value.notice; body.textContent = value.request_body;
      digest.textContent = `${value.request_bytes} UTF-8 bytes · SHA256 ${value.request_sha256}`;
      renderEvidence(value.deterministic_evidence);
      status.textContent = "Inspect this destination, evidence and exact request. Nothing sent to a model.";
      expiry = setTimeout(() => { if (current(version, key)) invalidate("Reviewer disclosure expired. Prepare a fresh request."); }, 600000);
    } catch (problem) { if (current(version, key)) fail(problem); }
    finally { if (current(version, key)) { busy = false; controls(); } }
  };
  function renderAdvice(value) {
    advice.replaceChildren(); advice.hidden = false;
    node("h3", "Unverified model suggestions", advice);
    node("p", "A completed request does not certify scientific correctness. Cited IDs only identify supplied evidence. No changes applied.", advice).className = "muted";
    const content = value.qualitative.content;
    node("p", content.summary, advice);
    for (const item of content.suggestions) {
      const article = node("article", undefined, advice);
      node("h4", `${item.figure_key} · ${item.topic}`, article);
      node("p", item.suggestion, article); node("p", item.why, article);
      node("p", "Supplied references: " + item.evidence_ids.join(", "), article).className = "muted";
    }
    if (content.author_questions.length) { node("h4", "Questions for the author", advice); const list = node("ul", undefined, advice); content.author_questions.forEach(text => node("li", text, list)); }
  }
  async function poll(version, key, id) {
    if (!current(version, key)) return;
    if (polling) { timer = setTimeout(() => poll(version, key, id), 200); return; }
    polling = true;
    try {
      const value = await request("status", control(version, id));
      if (!current(version, key)) return;
      if (value.phase === "running") { timer = setTimeout(() => poll(version, key, id), 500); return; }
      if (value.phase !== "completed") throw Error(value.error || "Reviewer request did not complete. Prepare a fresh disclosure.");
      const answer = value.result;
      if (answer?.status !== "completed" || answer.applied !== false || answer.scientific_acceptance !== "not_established" || answer.binding !== disclosure?.binding || answer.request_sha256 !== disclosure.request_sha256 || answer.consent_sha256 !== disclosure.consent_sha256) throw Error("Reviewer result does not match the disclosed request.");
      result = answer; phase = "completed"; renderAdvice(answer); status.textContent = "Request completed. Model suggestions are unverified; recorded checks are unchanged."; controls();
    } catch (problem) { if (current(version, key)) fail(problem); }
    finally { polling = false; }
  }
  start.onclick = async () => {
    refresh(); if (start.disabled) return;
    const version = generation, key = sourceKey, id = disclosure.review_id;
    phase = "running"; busy = true; result = null; advice.hidden = true; advice.replaceChildren(); controls();
    status.textContent = "Sending the explicitly reviewed request…";
    try {
      await request("start", {...control(version, id), consent: true, consent_sha256: disclosure.consent_sha256});
      if (!current(version, key)) return;
      busy = false; status.textContent = "Waiting for the reviewer. Your figure and recorded checks stay unchanged."; controls(); void poll(version, key, id);
    } catch (problem) { if (current(version, key)) fail(problem); }
    finally { if (current(version, key)) { busy = false; controls(); } }
  };
  async function download(which) {
    refresh(); if ((which === "request" ? saveRequest : saveResult).disabled) return;
    const version = generation, key = sourceKey, id = disclosure.review_id; busy = true; controls();
    try {
      const bytes = await request("download", {...control(version, id), which}, {raw: true});
      if (!current(version, key)) return;
      const url = URL.createObjectURL(new Blob([bytes], {type: "application/json"}));
      const link = node("a", undefined, root); link.href = url;
      link.download = which === "result" ? "figure-review-result.json" : source.source_kind === "editor-render" ? "editor-figure-review-request.json" : "paper-figure-review-request.json";
      link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (problem) { if (current(version, key)) fail(problem); }
    finally { if (current(version, key)) { busy = false; controls(); } }
  }
  saveRequest.onclick = () => download("request"); saveResult.onclick = () => download("result");
  cancel.onclick = () => invalidate("Reviewer request cancelled. Nothing was applied; information already sent cannot be recalled.");
  window.addEventListener("pagehide", () => {
    closed = true; generation++; clearTimeout(timer); clearTimeout(expiry);
    void request("cancel", control(generation, null), {keepalive: true}).catch(() => {});
  });
  refresh(); controls(); void loadProvider();
  return {refresh, clear: () => invalidate()};
}
