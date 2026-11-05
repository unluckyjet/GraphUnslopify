export async function verifiedObservationImage(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw Error("The traced PNG could not be read.");
  const raw = await response.arrayBuffer();
  const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", raw))]
    .map(value => value.toString(16).padStart(2, "0")).join("");
  if (raw.byteLength !== expected.bytes || hash !== expected.sha256)
    throw Error("The PNG changed since observation geometry was recorded.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(Error("The traced PNG could not be displayed."));
    reader.readAsDataURL(new Blob([raw], {type: "image/png"}));
  });
}

export function createObservationExplorer({api, token, client, current, supported, trace, deactivate}) {
  const $ = id => document.getElementById(id);
  const image = $("preview"), trigger = $("trace-observations"), panel = $("observation-explorer");
  const picker = $("observation-panel"), row = $("observation-row"), column = $("observation-column");
  const intervalIndex = $("observation-interval-index");
  const note = $("observation-status"), details = $("observation-details"), code = $("observation-code");
  const buttons = ["observation-pick", "observation-pick-interval", "observation-filters", "observation-preparation",
    "observation-graph", "observation-program"];
  let binding = null, active = false, version = 0, selection = null, history = [];

  function ready() {
    const state = current();
    return binding && state.generation === binding.render_generation
      && state.run === binding.run_id && image.dataset.phase === "final"
      && image.dataset.runId === binding.run_id && image.dataset.imageSha256 === binding.image_sha256
      && image.complete && image.naturalWidth === binding.width && image.naturalHeight === binding.height;
  }

  function refresh() {
    trigger.disabled = !supported() || (!!binding && !ready());
    trigger.textContent = binding ? "Inspect observations" : "Trace observations";
    trigger.setAttribute("aria-pressed", String(active));
    image.classList.toggle("observation-active", active && !!ready());
    for (const id of buttons) $(id).disabled = !active || !ready();
    $("observation-preparation").disabled ||= !binding?.preparation;
    $("observation-back").disabled = !active || !ready() || !history.length;
    $("observation-previous").disabled = !active || !ready() || !selection?.offset;
    $("observation-next").disabled = !active || !ready() || !selection?.more;
  }

  function hide() {
    version++;
    active = false;
    panel.hidden = true;
    refresh();
  }

  function clear() {
    binding = selection = null;
    history = [];
    note.textContent = "";
    details.replaceChildren();
    code.hidden = true;
    code.textContent = "";
    picker.replaceChildren();
    $("observation-cell-picker").hidden = true;
    $("observation-interval-picker").hidden = true;
    hide();
  }

  function open() {
    deactivate();
    active = true;
    panel.hidden = false;
    refresh();
  }

  function updatePicker() {
    const grid = binding?.grids[Number(picker.value)];
    if (!grid) return;
    row.max = String(grid.rows);
    column.max = String(grid.columns);
    row.value = column.value = "1";
  }

  function mount(result) {
    clear();
    const packet = result.observations;
    if (!packet) return;
    if (!packet.available) {
      panel.hidden = false;
      note.textContent = packet.error || "This render has no supported observation geometry.";
      return;
    }
    binding = {
      run_id: result.run_id,
      render_client: client,
      render_generation: result.generation,
      image_sha256: packet.image.sha256,
      width: packet.image.width,
      height: packet.image.height,
      grids: packet.grids,
      intervals: packet.intervals,
      filters: packet.filters,
      preparation: packet.preparation,
    };
    if (binding.intervals) {
      $("observation-interval-picker").hidden = false;
      intervalIndex.value = "1";
      intervalIndex.max = String(binding.intervals);
      note.textContent = "Click a visible error bar, or enter its interval number.";
    } else {
      $("observation-cell-picker").hidden = false;
      binding.grids.forEach((_, index) => picker.add(new Option("Panel " + (index + 1), String(index))));
      updatePicker();
      note.textContent = "Click a cell in the figure, or choose its panel, row, and column.";
    }
    open();
  }

  function requestOwner() {
    const {run_id, render_client, render_generation, image_sha256} = binding;
    return {run_id, render_client, render_generation, image_sha256};
  }

  function node(tag, value, parent = details) {
    const element = document.createElement(tag);
    element.textContent = value;
    parent.append(element);
    return element;
  }

  const readable = value => String(value).replaceAll("_", " ");

  function records(label, group) {
    node("h4", group.total + " " + label);
    if (group.items.length) node("p", group.items.map(item => String(item + 1)).join(", "));
  }

  function links(label, group) {
    if (!group.total) return;
    node("h4", label + " (" + group.total + ")");
    const list = node("ul", "");
    for (const item of group.items) {
      const text = item.record_ordinal === null ? readable(item.label) : "Record " + (item.record_ordinal + 1);
      const button = node("button", text, node("li", "", list));
      button.type = "button";
      button.className = "quiet";
      button.onclick = () => void select({node_id: item.id});
    }
  }

  function showSelection(value) {
    const item = value.node, metadata = item.metadata || {};
    let title = readable(item.operation || item.reason || item.kind);
    if (item.operation === "matrix_cell") title += " · " + metadata.row_label + " × " + metadata.column_label;
    if (item.operation === "summary_interval") {
      const keys = Object.entries(metadata.keys || {}).map(([name, value]) => readable(name) + " " + value);
      if (keys.length) title += " · " + keys.join(", ");
    }
    if (item.kind === "observation") title = "Record " + (item.record_ordinal + 1);
    node("h3", title);
    if ("value" in item) node("p", item.value === null ? "Value unavailable" : "Value " + JSON.stringify(item.value));
    if (item.detail_in_download) node("p", "The complete node detail is available in the graph download.");
    else if (Object.keys(metadata).length) {
      const view = node("details", "");
      node("summary", "Calculation details", view);
      node("pre", JSON.stringify(metadata, null, 2), view);
    }
    records("contributing records", value.contributing_records);
    records("excluded records", value.excluded_records);
    node("p", "Record numbers start at 1 in the parsed dataset. They may differ from file line numbers.").className = "muted";
    links("Calculation inputs", value.inputs);
    links("Scoped exclusions", value.excluded);
    return title;
  }

  async function select(target, offset = 0, remember = true) {
    if (!active || !ready()) return;
    const sequence = ++version;
    const previous = selection;
    note.textContent = "Checking the selected observation evidence…";
    try {
      const answer = await api("/api/observations/query", {...requestOwner(), ...target, offset});
      if (sequence !== version || !active || !ready()) return;
      details.replaceChildren();
      if (!answer.selection) {
        selection = null;
        note.textContent = binding.intervals ? "No visible interval occupies that position."
          : "No matrix cell occupies that position.";
      } else {
        if (remember && previous) history.push({target: previous.target, offset: previous.offset});
        const value = answer.selection;
        selection = {target, offset, size: answer.page_size,
          more: [value.contributing_records, value.excluded_records, value.inputs, value.excluded]
            .some(group => group.total > offset + answer.page_size)};
        const title = showSelection(value);
        note.textContent = offset ? title + ". Records and links from item " + (offset + 1) + "." : title;
      }
    } catch (problem) {
      if (sequence !== version || !active || !ready()) return;
      selection = null;
      details.replaceChildren();
      code.hidden = true;
      code.textContent = "";
      note.textContent = problem.message;
    } finally {
      if (sequence === version) refresh();
    }
  }

  async function getDocument(choice) {
    if (!active || !ready()) return;
    const sequence = ++version;
    try {
      const response = await fetch("/api/observations/download", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Preview-Token": token},
        body: JSON.stringify({...requestOwner(), document: choice}),
      });
      if (!response.ok) throw Error((await response.json()).error);
      const body = await response.blob();
      if (sequence !== version || !active || !ready()) return;
      if (choice === "program") {
        const text = await body.text();
        if (sequence !== version || !active || !ready()) return;
        code.textContent = text;
        code.hidden = false;
      } else {
        const url = URL.createObjectURL(body);
        const link = node("a", "", panel);
        link.href = url;
        link.download = "observation-graph.json";
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (problem) {
      if (sequence === version && active && ready()) note.textContent = problem.message;
    }
  }

  trigger.onclick = () => {
    if (binding) { if (active) hide(); else if (ready()) open(); }
    else trace();
  };
  $("observation-close").onclick = hide;
  picker.onchange = updatePicker;
  $("observation-pick").onclick = () => {
    if (row.checkValidity() && column.checkValidity())
      void select({cell: [Number(picker.value), row.valueAsNumber - 1, column.valueAsNumber - 1]});
  };
  $("observation-pick-interval").onclick = () => {
    if (intervalIndex.checkValidity()) void select({interval_index: intervalIndex.valueAsNumber - 1});
  };
  $("observation-filters").onclick = () => void select({node_id: binding?.filters});
  $("observation-preparation").onclick = () => void select({node_id: binding?.preparation});
  $("observation-back").onclick = () => {
    const previous = history.pop();
    if (previous) void select(previous.target, previous.offset, false);
  };
  $("observation-previous").onclick = () => {
    if (selection) void select(selection.target, Math.max(0, selection.offset - selection.size), false);
  };
  $("observation-next").onclick = () => {
    if (selection?.more) void select(selection.target, selection.offset + selection.size, false);
  };
  $("observation-graph").onclick = () => void getDocument("graph");
  $("observation-program").onclick = () => void getDocument("program");
  image.addEventListener("load", refresh);
  image.addEventListener("click", event => {
    if (!active || !ready()) return;
    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const xScale = binding.width / rect.width, yScale = binding.height / rect.height;
    const position = [(event.clientX - rect.left) * xScale, (event.clientY - rect.top) * yScale];
    const target = {position};
    if (binding.intervals) target.tolerance = Math.min(64, 2 * Math.max(xScale, yScale));
    void select(target);
  });
  return {mount, clear, hide, refresh};
}
