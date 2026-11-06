/** Reviewed selected presentation, fenced by the existing project and operation owners. */
export function createSelectionReview({api, context, onState, onApplied, onError}) {
  const $ = id => document.getElementById(id);
  const fields = ["title", "x-label", "y-label", "legend-show", "legend-title",
    "legend-position", "legend-style", "preset", "venue", "grid", "despine", "size", "dpi"];
  const picked = new Set();
  let plan = null, epoch = 0, loading = false, applying = false, reviewed = "", listKey = "", historyKey = "";
  const el = (tag, text, parent) => { const n = document.createElement(tag);if (text !== undefined) n.textContent = text;parent?.append(n);return n; };
  const signature = () => { const c = context();return JSON.stringify([c.state?.revision, c.state?.inspection_revision, c.state?.history?.map(e => [e.id,e.integrity]), c.dirty, [...picked].sort(), fields.map(id => [$("selection-"+id).value,$("selection-"+id).validity.valid]), $("selection-undo-event").value]); };
  function clear(message = "", notify = true) {
    epoch++;plan = null;loading = false;reviewed = "";$("selection-rows").replaceChildren();
    $("selection-status").textContent = message;$("selection-proposal").hidden = !message;$("selection-apply").disabled = true;
    if (notify) onState();
  }
  function settings() {
    const value = {}, style = {}, output = {}, legend = {}, dpi = $("selection-dpi");
    const field = id => $("selection-" + id).value.trim();
    if (!dpi.checkValidity()) throw Error("Choose a whole-number raster DPI from 72 to 1200.");
    if (field("title")) value.title = field("title");
    for (const axis of ["x", "y"]) {
      const label = field(axis + "-label");
      if (label) value[axis] = { label };
    }
    for (const key of ["title", "position", "style"]) {
      const setting = field("legend-" + key);
      if (setting) legend[key] = setting;
    }
    if (field("legend-show")) legend.show = field("legend-show") === "true";
    for (const key of ["preset", "venue"]) if (field(key)) style[key] = field(key);
    for (const key of ["grid","despine"]) if (field(key)) style[key] = field(key) === "true";
    if (field("size")) output.size = field("size");
    if (dpi.value !== "") output.dpi = Number(dpi.value);
    if (Object.keys(style).length) value.style = style;
    if (Object.keys(output).length) value.output = output;
    if (Object.keys(legend).length) value.legend = legend;
    return value;
  }
  function update() {
    const c = context(), sources = [...(c.state?.figures || []).map(r => ({id:r.id,label:r.id+(r.source_type === "script" ? " · Authored Python, read-only" : " · JSON figure")})), ...(c.state?.inspections || []).map(r => ({id:"pdf:"+r.id,label:r.name+" · PDF visual evidence, read-only"}))];
    const key = JSON.stringify(sources);
    // An unavailable snapshot cannot establish that a selected source vanished.
    // Keep the user's choices disabled until a real inventory can reconcile them.
    if (c.state?.status !== "unavailable" && key !== listKey) {
      const valid = new Set(sources.map(r => r.id));for (const id of picked) if (!valid.has(id)) picked.delete(id);
      $("selection-figures").replaceChildren();
      for (const row of sources) {
        const label = el("label",undefined,$("selection-figures"));label.className = "check";
        const input = el("input",undefined,label);input.type = "checkbox";input.value = row.id;input.checked = picked.has(row.id);
        input.onchange = () => { if (input.checked) picked.add(row.id);else picked.delete(row.id);clear(); };
        label.append(document.createTextNode(row.label));
      }
      listKey = key;
    }
    const choices = c.state?.history?.filter(e => e.selection_change) || [], hkey = JSON.stringify(choices.map(e => [e.id,e.undo_of]));
    if (hkey !== historyKey) {
      const old = $("selection-undo-event").value;$("selection-undo-event").replaceChildren();
      choices.forEach(e => { el("option",e.id.slice(0,8)+" · "+(e.undo_of ? "Selection undo" : "Saved selected settings"),$("selection-undo-event")).value = e.id; });
      if (choices.some(e => e.id === old)) $("selection-undo-event").value = old;historyKey = hkey;
    }
    if ((plan || loading) && reviewed !== signature()) clear("Project inputs, history or selection changed. Review again before applying.",false);
    const busy = c.busy || applying || c.dirty || !c.state?.revision || c.state?.mode === "review_only";
    for (const id of ["figures","settings","all","none"]) $("selection-"+id).disabled = busy || loading;
    $("selection-count").textContent = `${picked.size} selected. Authored programs and PDFs are explicitly excluded from presentation changes.`;
    let valid = false;try { valid = Object.keys(settings()).length > 0; } catch { /* Preserve invalid input. */ }
    $("selection-review").disabled = busy || loading || !picked.size || !valid;
    $("selection-reset").disabled = busy || loading || !picked.size;
    $("selection-undo-event").disabled = busy || loading || !choices.length;$("selection-undo").disabled = $("selection-undo-event").disabled;
    $("selection-apply").disabled = busy || loading || !plan?.can_apply;$("selection-cancel").disabled = applying;
  }
  function render(value) {
    $("selection-proposal").hidden = false;
    $("selection-heading").textContent = value.operation === "undo" ? "Review selection undo" : value.operation === "reset" ? "Review return to paper defaults" : "Review selected changes";
    $("selection-status").textContent = `Settings change for ${value.affected_ids.length} selected figure${value.affected_ids.length === 1 ? "" : "s"}; ${value.excluded.length} read-only sources stay unchanged. ${value.can_apply ? "Ready to save reviewed intent." : "No change to save, or selected intent needs correction."} Run paper checks afterward; this review executes no figure programs.`;
    for (const row of value.figures) {
      const box = el("article",undefined,$("selection-rows"));box.className = "shared-review-row";el("h4",row.id,box);
      if (!row.changes.length && !row.notes?.length) el("p","Effective presentation is unchanged; the explicit selected policy may still change.",box);
      for (const note of row.notes || []) el("p", note, box);
      for (const d of row.changes) el("p",d.path+": "+(d.before_present ? JSON.stringify(d.before) : "absent")+" → "+(d.after_present ? JSON.stringify(d.after) : "absent"),box);
      row.errors.forEach(error => { el("p",error,box).className = "review-errors"; });
      const details = el("details",undefined,box);el("summary","Resolved presentation and static findings",details);el("pre",JSON.stringify({before:row.before,after:row.after,findings:row.findings},null,2),details);
    }
    for (const row of value.excluded) { const box = el("article",undefined,$("selection-rows"));box.className = "shared-review-row";el("h4",row.id+" · Unchanged",box);el("p",row.reason,box); }
  }
  async function request(operation = "apply") {
    const c = context();if (c.busy || c.dirty || applying || loading) throw Error("Finish other operations and drafts before reviewing selected changes.");
    const body = operation === "undo" ? {undo_event:$("selection-undo-event").value} : {ids:[...picked].sort(),...(operation === "reset" ? {reset:true} : {settings:settings()})};body.expected_revision = c.state.revision;
    clear("Resolving current selected presentation…",false);const id = epoch;loading = true;reviewed = signature();onState();
    try { const value = await api("/api/selection-review",body);if (id !== epoch || reviewed !== signature()) return;plan = value;loading = false;$("selection-rows").replaceChildren();render(value);onState(); }
    catch (error) { if (id !== epoch) return;clear("Selection review unavailable: "+error.message);throw error; }
  }
  async function apply() {
    const c = context();if (!plan?.can_apply || reviewed !== signature() || c.busy || c.dirty || applying) throw Error("Review the current selected changes before saving.");
    const value = plan;applying = true;onState();
    try { const result = await api("/api/selection-apply",{...(value.undo_event ? {undo_event:value.undo_event} : {ids:value.ids,settings:value.settings,reset:value.reset}),expected_revision:value.revision,proposal_token:value.proposal_token});clear("",false);await onApplied(result); }
    catch (error) { clear("Selected settings were not confirmed. Refresh and review again: "+error.message,false);throw error; }
    finally { applying = false;onState(); }
  }
  const action = fn => async () => { onError("");try { await fn(); } catch(error) { onError(error.message); } };
  $("selection-all").onclick = () => { picked.clear();context().state?.figures.filter(r => r.source_type === "spec").forEach(r => picked.add(r.id));listKey = "";clear(); };
  $("selection-none").onclick = () => { picked.clear();listKey = "";clear(); };
  fields.forEach(id => $("selection-"+id).oninput = () => clear());$("selection-undo-event").onchange = () => clear();
  $("selection-review").onclick = action(() => request());$("selection-reset").onclick = action(() => request("reset"));
  $("selection-undo").onclick = action(() => request("undo"));$("selection-apply").onclick = action(apply);$("selection-cancel").onclick = () => clear();
  return {update,clear,pending:() => !!plan || loading,applying:() => applying};
}
