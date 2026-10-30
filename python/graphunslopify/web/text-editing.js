/** Text intent only. The renderer owns units, computed details and geometry. */
export function proposeTextEdit(original, target, text) {
  if (typeof text !== "string" || !text.trim()) throw Error("Enter visible wording.");
  const path = target?.path;
  if (!target?.editable || !Array.isArray(path)) throw Error("This text is read-only.");
  const spec = structuredClone(original);
  let before;
  if (target.role === "title" && path.length === 1 && path[0] === "title") {
    before = spec.title;
    if (typeof before !== "string") throw Error("The title changed; render again.");
    spec.title = text;
  } else if (target.role === "axis_label" && path.length === 2 &&
    ["x", "y", "y2"].includes(path[0]) && path[1] === "label") {
    const axis = spec[path[0]];
    if (!axis || axis.field !== target.source || typeof axis.label !== "string")
      throw Error("The source field changed; render again.");
    before = axis.label;
    axis.label = text;
  } else if (target.role === "legend_title" && path.length === 2 &&
    path[0] === "legend" && path[1] === "title") {
    before = spec.legend?.title;
    if (typeof before !== "string") throw Error("The legend title changed; render again.");
    spec.legend.title = text;
  } else if (target.role === "annotation" && path.length === 3 &&
    path[0] === "annotate" && path[2] === "text" && Number.isInteger(path[1]) && path[1] >= 0) {
    const annotation = spec.annotate?.[path[1]];
    before = annotation?.text;
    if (typeof before !== "string") throw Error("The annotation changed; render again.");
    annotation.text = text;
  } else if (["reference_label", "layer_label"].includes(target.role) && path.length === 3 &&
    path[0] === (target.role === "reference_label" ? "reference_lines" : "layers") &&
    path[2] === "label" && Number.isInteger(path[1]) && path[1] >= 0) {
    const item = spec[path[0]]?.[path[1]];
    before = item?.label;
    if (typeof before !== "string" || !target.source ||
      (target.role === "reference_label" && (item.axis !== target.source.axis || item.value !== target.source.value)) ||
      (target.role === "layer_label" && (path[1] !== target.source.layer || item.mark !== target.source.mark)))
      throw Error("The reference or layer changed; render again.");
    item.label = text;
  } else if (target.role === "legend_entry" && path.length === 4 &&
    path[0] === "legend" && path[1] === "labels" && path[3] === "text" &&
    Number.isInteger(path[2]) && path[2] >= 0 && typeof target.source === "string") {
    spec.legend ??= {};
    if (typeof spec.legend !== "object" || Array.isArray(spec.legend)) throw Error("The series changed; render again.");
    const labels = spec.legend.labels || [];
    if (!Array.isArray(labels) || path[2] > labels.length)
      throw Error("The series names changed; render again.");
    const current = labels[path[2]];
    if (current && current.series !== target.source)
      throw Error("The source series changed; render again.");
    before = current?.text ?? target.source;
    labels[path[2]] = { series: target.source, text };
    spec.legend.labels = labels;
  } else throw Error("This text has no supported editing target.");
  return { spec, before, after: text };
}

export function createTextEditor({ current, apply }) {
  const $ = id => document.getElementById(id);
  const image = $("preview"), layer = $("text-targets"), picker = $("text-target");
  let binding = null, targets = [], selected = null, proposal = null, active = false;
  const names = { title: "Title", axis_label: "Axis label", legend_title: "Legend title",
    legend_entry: "Series name", annotation: "Annotation", reference_label: "Reference label", layer_label: "Layer label" };
  function error(message = "") {
    $("text-error").textContent = message;
    $("text-error").hidden = !message;
  }
  function same() {
    try {
      const now = current();
      return binding && now.revision === binding.revision && now.dataId === binding.dataId &&
        now.result?.run_id === binding.runId && now.result?.report.spec_hash === binding.hash &&
        JSON.stringify(now.spec) === binding.spec;
    } catch { return false; }
  }
  function resetDraft() {
    selected = null; proposal = null;
    $("text-draft").hidden = $("text-review").hidden = true;
    $("text-meaning").checked = false;
    $("apply-text").disabled = true;
    error();
  }
  function clear() {
    binding = null; targets = [];
    resetDraft();
    layer.replaceChildren(); layer.hidden = true;
    picker.replaceChildren(new Option("Choose text to edit", ""));
    $("text-editor").hidden = true;
    $("edit-figure-text").disabled = true;
  }
  function select(index, focus = true) {
    resetDraft();
    if (!same() || !targets[index]) return;
    try {
      selected = targets[index];
      const probe = proposeTextEdit(current().spec, selected, "probe");
      $("text-wording").value = probe.before;
      $("text-source").textContent = selected.role === "legend_entry"
        ? `Source series: ${selected.source}. This name applies wherever that series appears.`
        : selected.role === "axis_label"
          ? `Source field: ${selected.source}. Units and scaling stay unchanged; shared labels change together.`
          : selected.role === "reference_label"
            ? `Reference ${selected.source.axis} = ${selected.source.value}. Only its wording changes; the reference value stays unchanged.`
            : selected.role === "layer_label"
              ? `Layer ${selected.source.layer + 1}: ${selected.source.mark}. Its observations, filters and coordinates stay unchanged.`
          : selected.role === "annotation"
            ? "This wording applies wherever the same annotation appears. Its data attachment stays unchanged."
            : "Only this wording changes. Data, units and claim subjects stay unchanged.";
      $("text-rendered").textContent = `Currently shown: ${selected.text}`;
      picker.value = String(index);
      $("text-draft").hidden = false;
      if (focus) $("text-wording").focus();
    } catch (problem) { error(problem.message); }
  }
  function position() {
    if (image.complete && image.naturalWidth)
      $("figure-surface").style.setProperty("--figure-ratio", String(image.naturalWidth / image.naturalHeight));
    layer.hidden = !same() || !active || !image.complete ||
      image.naturalWidth !== binding?.width || image.naturalHeight !== binding?.height;
  }
  image.addEventListener("load", position);
  $("edit-figure-text").onclick = () => {
    if (!same()) return;
    active = !active;
    $("edit-figure-text").setAttribute("aria-pressed", String(active));
    $("text-editor").hidden = !active;
    position();
  };
  picker.onchange = () => picker.value === "" ? resetDraft() : select(Number(picker.value));
  $("cancel-text").onclick = () => { resetDraft(); picker.value = ""; };
  $("text-wording").oninput = () => {
    proposal = null; $("text-review").hidden = true;
    $("text-meaning").checked = false; $("apply-text").disabled = true; error();
  };
  $("review-text").onclick = () => {
    if (!same() || !selected) { clear(); return; }
    try {
      proposal = proposeTextEdit(current().spec, selected, $("text-wording").value);
      if (proposal.before === proposal.after) throw Error("Change the wording before reviewing.");
      $("text-change").textContent = `Change “${proposal.before}” to “${proposal.after}”.`;
      $("text-review").hidden = false;
      $("text-meaning").checked = false;
      $("apply-text").disabled = true;
      error();
    } catch (problem) { proposal = null; error(problem.message); }
  };
  $("text-meaning").onchange = () => {
    $("apply-text").disabled = !proposal || !$("text-meaning").checked || !same();
  };
  $("apply-text").onclick = () => {
    if (!same() || !proposal || !$("text-meaning").checked) return;
    const next = proposal.spec;
    clear(); apply(next);
  };
  function mount(result) {
    clear();
    const map = result.edit_map;
    const png = result.report?.outputs.find(output => output.format === "png" && output.path.split(/[\\/]/).pop() === map?.image?.name);
    if (!map?.available || map.schema_version !== 1 || map.coordinates !== "pixels_top_left" || map.run_id !== result.run_id || map.spec_hash !== result.report.spec_hash ||
      !png || png.sha256 !== map.image.sha256 || !Array.isArray(map.targets) ||
      !(map.image.width > 0 && map.image.height > 0)) return;
    const now = current();
    binding = { revision: now.revision, dataId: now.dataId, runId: result.run_id,
      hash: map.spec_hash, width: map.image.width, height: map.image.height, spec: JSON.stringify(now.spec) };
    for (const target of map.targets) {
      if (!target.editable || !Array.isArray(target.bounds) || target.bounds.length !== 4 ||
        !target.bounds.every(Number.isFinite)) continue;
      const [x, y, width, height] = target.bounds;
      if (x < 0 || y < 0 || width <= 0 || height <= 0 ||
        x + width > map.image.width + 0.001 || y + height > map.image.height + 0.001) continue;
      try { proposeTextEdit(now.spec, target, "probe"); } catch { continue; }
      const index = targets.length;
      targets.push(target);
      const label = `${names[target.role] || "Text"}: ${target.text}`;
      picker.add(new Option(label, String(index)));
      const button = document.createElement("button");
      button.type = "button"; button.className = "text-target";
      button.setAttribute("aria-label", `Edit ${label}`); button.title = label;
      button.style.left = `${100 * x / map.image.width}%`;
      button.style.top = `${100 * y / map.image.height}%`;
      button.style.width = `${100 * width / map.image.width}%`;
      button.style.height = `${100 * height / map.image.height}%`;
      button.onclick = () => select(index);
      layer.append(button);
    }
    $("edit-figure-text").disabled = !targets.length;
    $("text-editor").hidden = !active || !targets.length;
    $("edit-figure-text").setAttribute("aria-pressed", String(active));
    position();
  }
  return { clear, mount };
}
