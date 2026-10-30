// Model content stays a proposal until explicit review and canonical strict rerender.
export function createDraftEditor({api, snapshot, identity, flush, apply}) {
  const $ = id => document.getElementById(id);
  let epoch = 0, provider = null, draftId = null, disclosure = null, proposal = null;
  let busy = false, configBusy = false, configDirty = false, dataId = null, units = Object.create(null);
  let configEpoch = 0;
  const say = text => { $("draft-status").textContent = text; };
  function current() { try { return snapshot(); } catch { return null; } }
  function buttons() {
    $("draft-disclose").disabled = busy || configBusy || configDirty || !provider?.configured || !current()?.data_id || !$("draft-prompt").value.trim();
    $("draft-send").disabled = busy || !disclosure || !$("draft-consent").checked;
    $("draft-apply").disabled = busy || !proposal || !$("draft-reviewed").checked;
    $("draft-save-provider").disabled = configBusy;
    $("draft-disable-provider").disabled = configBusy;
  }
  function clear({cancel = true} = {}) {
    const old = draftId;
    const hadDraft = Boolean(old || disclosure || proposal || busy);
    epoch++;
    draftId = null; disclosure = null; proposal = null; busy = false;
    for (const id of ["draft-disclosure", "draft-proposal", "draft-invalid", "draft-error"]) $(id).hidden = true;
    $("draft-consent").checked = false;
    $("draft-reviewed").checked = false;
    if (hadDraft) say("Draft cleared. Review a new request for the current figure and data.");
    if (cancel) api("/api/draft/cancel", {...identity(), draft_id: old}).catch(() => {});
    buttons();
  }
  function error(problem) {
    $("draft-error").textContent = problem.message;
    $("draft-error").hidden = false;
    if (problem.details?.invalid_draft) {
      $("draft-invalid-json").textContent = JSON.stringify(problem.details.invalid_draft, null, 2);
      $("draft-invalid").hidden = false;
    }
    say("No changes applied. Review a new request or use manual settings.");
  }
  function showProvider(info) {
    provider = info; configDirty = false;
    if (info.provider) {
      $("draft-endpoint").value = info.provider.endpoint;
      $("draft-model").value = info.provider.model;
      $("draft-protocol").value = info.provider.protocol;
    }
    $("draft-provider-note").textContent = info.configured
      ? `${info.provider.model} · ${info.provider.endpoint}. ${info.authorization_configured ? "Authorization configured for this session." : "No authorization key configured."}`
      : "No provider configured. Manual authoring works without a model.";
    buttons();
  }
  async function configure(enabled) {
    if (configBusy) return;
    clear();
    const stamp = configEpoch;
    configBusy = true; buttons();
    const payload = enabled ? {endpoint: $("draft-endpoint").value, model: $("draft-model").value, protocol: $("draft-protocol").value, api_key: $("draft-key").value} : {enabled: false};
    $("draft-key").value = "";
    try {
      const info = await api("/api/model-provider", payload);
      if (stamp !== configEpoch) return;
      showProvider(info);
      say("Provider saved for this session. Review what will be sent before requesting a draft.");
    } catch (problem) { if (stamp === configEpoch) error(problem); }
    finally { configBusy = false; buttons(); }
  }
  function context() {
    return {design: $("draft-design").value, unit_field: $("draft-experimental-unit").value || null, units: {...units}};
  }
  function showUnits() {
    $("draft-units").replaceChildren();
    for (const [name, unit] of Object.entries(units)) {
      const row = document.createElement("p"), remove = document.createElement("button");
      row.append(document.createTextNode(`${name}: ${unit} `));
      remove.className = "quiet"; remove.textContent = `Remove ${name} unit`;
      remove.onclick = () => { delete units[name]; clear(); showUnits(); };
      row.append(remove); $("draft-units").append(row);
    }
  }
  function refresh() {
    const value = current(), names = value?.columns || [];
    if (dataId !== value?.data_id) {
      dataId = value?.data_id; units = Object.create(null); showUnits();
      $("draft-design").value = "unspecified";
      $("draft-experimental-unit").value = "";
    }
    for (const [id, empty] of [["draft-unit-column", "Choose column"], ["draft-experimental-unit", "No unit column declared"]]) {
      const selected = $(id).value;
      $(id).replaceChildren(new Option(empty, ""), ...names.map(name => new Option(name, name)));
      $(id).value = names.includes(selected) ? selected : "";
    }
    buttons();
  }
  $("draft-protocol").addEventListener("change", () => { $("draft-endpoint").placeholder = $("draft-protocol").value === "chat" ? "http://127.0.0.1:11434/v1/chat/completions" : "https://api.openai.com/v1/responses"; });
  $("draft-save-provider").onclick = () => configure(true);
  $("draft-disable-provider").onclick = () => configure(false);
  for (const id of ["draft-endpoint", "draft-model", "draft-protocol", "draft-key"]) $(id).addEventListener("input", () => {
    configEpoch++; clear(); configDirty = true; buttons();
    $("draft-provider-note").textContent = "Configuration changed. Save it before requesting a draft; an empty key clears authorization.";
  });
  for (const id of ["draft-prompt", "draft-design", "draft-experimental-unit"]) $(id).addEventListener("input", () => { clear(); say("Review a new request before sending."); });
  $("draft-add-unit").onclick = () => {
    const name = $("draft-unit-column").value, unit = $("draft-unit-value").value.trim();
    if (!name || !unit) { error(Error("Choose a source column and enter its author-declared unit.")); return; }
    units[name] = unit; clear(); showUnits(); $("draft-unit-value").value = "";
  };
  $("draft-consent").onchange = buttons;
  $("draft-reviewed").onchange = buttons;
  $("draft-disclose").onclick = async () => {
    if (!flush()) { error(Error("Fix the pending settings before preparing a model request.")); return; }
    clear(); const stamp = epoch; busy = true; buttons(); say("Preparing disclosure; nothing sent to the model yet.");
    try {
      const selected = snapshot();
      const value = await api("/api/draft/disclose", {...selected, prompt: $("draft-prompt").value, author_context: context()});
      if (stamp !== epoch) return;
      disclosure = value; draftId = value.draft_id;
      $("draft-request-summary").textContent = `${selected.data_name}${selected.sheet ? " · " + selected.sheet : ""} · ${selected.rows} rows. ${value.provider.model} at ${value.provider.endpoint} · ${value.request_bytes.toLocaleString()} bytes. ${value.notice}`;
      $("draft-request-json").textContent = JSON.stringify(value.request, null, 2);
      $("draft-disclosure").hidden = false;
      say("Review the exact request and provider. Nothing has been sent to the model.");
    } catch (problem) { if (stamp === epoch) error(problem); }
    finally { if (stamp === epoch) { busy = false; buttons(); } }
  };
  $("draft-send").onclick = async () => {
    if (!disclosure || !$("draft-consent").checked) return;
    const stamp = epoch; disclosure = null; busy = true; buttons(); say("Model request sent. Current figure is unchanged.");
    try {
      const value = await api("/api/draft/propose", {...snapshot(), draft_id: draftId, consent: true});
      if (stamp !== epoch) return;
      proposal = value;
      const spec = value.spec;
      $("draft-source-choices").textContent = `Kind: ${spec.kind}. X: ${spec.x?.field || "none"}. Y: ${spec.y?.field || "none"}. Group: ${spec.group || "none"}. Title: ${spec.title || "none"}.`;
      for (const [id, items] of [["draft-assumptions", value.assumptions], ["draft-questions", value.questions]]) {
        $(id).replaceChildren();
        for (const text of items.length ? items : ["None supplied by the model."]) { const li = document.createElement("li"); li.textContent = text; $(id).append(li); }
      }
      $("draft-proposal-json").textContent = JSON.stringify(value.spec, null, 2);
      $("draft-proposal").hidden = false;
      say("Unapplied · unverified. Review source choices, assumptions, questions and wording.");
    } catch (problem) { if (stamp === epoch) error(problem); }
    finally { if (stamp === epoch) { busy = false; buttons(); } }
  };
  $("draft-apply").onclick = async () => {
    if (!proposal || !$("draft-reviewed").checked) return;
    const stamp = epoch; busy = true; buttons();
    try {
      const accepted = await api("/api/draft/accept", {...snapshot(), draft_id: draftId, reviewed: true});
      if (stamp !== epoch) return;
      clear({cancel: false}); apply(accepted.spec);
      say("Applied. Strict checks and exports are running; review the figure's verification result.");
    } catch (problem) { if (stamp === epoch) error(problem); }
    finally { if (stamp === epoch) { busy = false; buttons(); } }
  };
  $("draft-cancel").onclick = () => { clear(); say("Draft discarded. Current figure is unchanged."); };
  api("/api/model-provider").then(info => { if (configEpoch === 0) showProvider(info); }).catch(error);
  refresh();
  return {refresh, invalidate: () => { clear(); refresh(); }};
}
