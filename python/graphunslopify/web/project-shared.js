/** Review canonical paper-wide intent before applying it; generation-fence every response. */
export function createSharedChangeReview({ api, context, onState, onApplied }) {
  const $ = (id) => document.getElementById(id);
  let proposal = null, generation = 0, loading = false, applying = false, reviewed = "", historyKey = "";
  const el = (tag, text, parent) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; parent?.append(node); return node; };
  const signature = () => {
    const c = context();
    return JSON.stringify([c.state?.revision, c.state?.inspection_revision, c.state?.history?.map(e => [e.id, e.integrity]), c.text, c.sourceDirty, c.entryDirty, $("shared-undo-event").value]);
  };
  function clear(message = "", notify = true) {
    generation++; proposal = null; loading = false; reviewed = "";
    $("shared-review-rows").replaceChildren(); $("shared-review-status").textContent = message;
    $("shared-review").hidden = !message; $("apply-shared-review").disabled = true;
    if (notify) onState();
  }
  function update() {
    const c = context(), choices = c.state?.history?.filter(e => e.shared_change) || [];
    const key = JSON.stringify(choices.map(e => [e.id, e.undo_of]));
    if (key !== historyKey) {
      const previous = $("shared-undo-event").value;
      $("shared-undo-event").replaceChildren();
      choices.forEach(e => { el("option", e.id.slice(0, 8) + " · " + (e.undo_of ? "Undo of " + e.undo_of.slice(0, 8) : "Saved shared settings"), $("shared-undo-event")).value = e.id; });
      if (choices.some(e => e.id === previous)) $("shared-undo-event").value = previous;
      historyKey = key;
    }
    if ((proposal || loading) && reviewed !== signature()) clear("Project inputs, history or draft changed. Review again before applying.", false);
    const busy = c.busy || applying || !c.available;
    $("shared-undo-event").disabled = busy || c.sourceDirty || c.entryDirty || c.sharedDirty || !choices.length;
    $("review-shared-undo").disabled = $("shared-undo-event").disabled || loading;
    $("apply-shared-review").disabled = busy || loading || !proposal?.can_apply;
    $("cancel-shared-review").disabled = applying;
  }
  function render(plan) {
    $("shared-review").hidden = false;
    $("shared-review-title").textContent = plan.operation === "undo" ? "Review undo" : "Review shared changes";
    $("shared-review-status").textContent = `${plan.affected_ids.length} of ${plan.figures.length} source-backed figures affected. ${plan.pdf_excluded.length} PDF${plan.pdf_excluded.length === 1 ? "" : "s"} outside restyling. ${plan.can_apply ? "Ready to apply reviewed intent." : "No change to apply, or figure intent needs correction."} Audit after saving to check actual outputs.`;
    $("apply-shared-review").textContent = plan.operation === "undo" ? "Apply reviewed undo" : "Apply reviewed settings";
    const root = $("shared-review-rows");root.replaceChildren();
    for (const row of plan.figures) {
      const box = el("article", undefined, root);box.className = "shared-review-row";box.dataset.figure = row.id;
      el("h4", row.id + " · " + (row.source_type === "script" ? "Authored Python: manual review" : row.affected ? "Intent changes" : "Effective intent unchanged"), box);
      el("p", row.reason, box).className = "muted";
      for (const change of row.changes) {
        const line = el("p", undefined, box);
        el("code", change.path, line);
        el("span", ": " + (change.before_present ? JSON.stringify(change.before) : "absent") + " → " + (change.after_present ? JSON.stringify(change.after) : "absent"), line);
      }
      row.errors.forEach(error => { el("p", error, box).className = "review-errors"; });
      const details = el("details", undefined, box);el("summary", "Resolved settings and static findings", details);
      el("pre", JSON.stringify({ before: row.before, after: row.after, findings: row.findings }, null, 2), details);
    }
    for (const pdf of plan.pdf_excluded) {
      const box = el("article", undefined, root);box.className = "shared-review-row";
      el("h4", "PDF · " + pdf.name, box);el("p", pdf.reason, box);
    }
  }
  async function request(undo = false) {
    const c = context();
    if (!c.available) throw Error("Wait for the current project inputs before reviewing shared settings.");
    if (c.busy || applying || c.sourceDirty || c.entryDirty || (undo && c.sharedDirty)) throw Error("Save or reload other drafts before reviewing this change.");
    const body = undo ? { undo_event: $("shared-undo-event").value, expected_revision: c.state.revision } : { shared: c.read(), expected_revision: c.state.revision };
    clear("Reading current inputs and resolving affected figures…", false);
    const id = generation;loading = true;reviewed = signature();onState();
    try {
      const plan = await api("/api/shared-review", body);
      if (id !== generation || reviewed !== signature()) return;
      proposal = plan;loading = false;render(plan);onState();
    } catch (problem) {
      if (id !== generation) return;
      clear("Shared review unavailable: " + problem.message);throw problem;
    }
  }
  async function apply() {
    const c = context();
    if (!proposal?.can_apply || reviewed !== signature() || !c.available || c.busy || applying) throw Error("Review current shared changes before applying.");
    const plan = proposal;
    applying = true;onState();
    try {
      const result = await api("/api/shared-apply", {
        ...(plan.undo_event ? { undo_event: plan.undo_event } : { shared: plan.shared }),
        expected_revision: plan.revision, proposal_token: plan.proposal_token,
      });
      clear("", false);await onApplied(result);
    } catch (problem) {
      clear("This change was not confirmed. Refresh and review again: " + problem.message, false);throw problem;
    } finally { applying = false;onState(); }
  }
  $("shared-undo-event").onchange = () => clear();
  $("cancel-shared-review").onclick = () => clear();
  return { request, apply, update, clear, pending: () => !!proposal || loading, loading: () => loading, applying: () => applying };
}
