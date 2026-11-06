function showCleaningPreview(result, status, output) {
  status.textContent = result.error || "Preparation inspected. Render to check the figure.";
  if (!result.rows) return;
  const paragraph = document.createElement("p");
  paragraph.textContent = [
    [result.rows.read, "parsed records"],
    [result.rows.after_filter, "after filters"],
    [result.rows.prepared, "prepared rows"],
    [result.rows.missing_plot_keys, "rows missing a plotting key"],
  ].filter(([count]) => count !== undefined).map(([count, label]) => count + " " + label).join(" · ");
  output.append(paragraph);
  function list(title, values) {
    if (!values.length) return;
    const heading = document.createElement("h3");
    heading.textContent = title;
    const items = document.createElement("ul");
    for (const value of values) {
      const item = document.createElement("li");
      item.textContent = value;
      items.append(item);
    }
    output.append(heading, items);
  }
  const source = result.columns.map(item => item.field + " (" + item.dtype + ") · " + item.missing + " missing");
  if (result.column_count > source.length) source.push("Showing " + source.length + " of " + result.column_count + " columns.");
  list("Parsed columns", source);
  const conversions = result.conversions.map(item => item.field + " · " + item.from_dtype + " → " +
    item.to_dtype + " (" + item.stage.replaceAll("_", " ") + "), " + item.became_missing +
    " became missing, " + item.infinite + " infinite");
  for (const step of result.identifier_steps) {
    conversions.push("Identifier fields: " + step.fields.join(", ") +
      (step.lexical_fields.length ? " · original text preserved for " + step.lexical_fields.join(", ") : ""));
  }
  if (result.conversion_count > result.conversions.length) {
    conversions.push("Showing " + result.conversions.length + " of " + result.conversion_count + " conversion groups.");
  }
  list("Type conversions", conversions);
  list("Declared filters", result.filters.map(item => item.field + " " + item.op + " · " +
    item.removed + " removed (" + item.before + " → " + item.after + ")"));
  const exclusions = result.exclusions.map(item => {
    const group = item.field || (item.step === null ? "" : "filter " + (item.step + 1));
    const samples = item.records.length < item.count ? " including " : " · records ";
    return item.count + " · " + item.reason.replaceAll("_", " ") + (group ? " · " + group : "") +
      samples + item.records.join(", ");
  });
  if (result.exclusion_count > exclusions.length) exclusions.push("Showing " + exclusions.length + " of " + result.exclusion_count + " exclusion groups.");
  list("Excluded source records", exclusions);
  list("Measurement checks", Object.entries(result.measurements).map(([field, counts]) =>
    field + " · " + counts.finite + " finite, " + counts.nonfinite + " missing or nonfinite"));
}

export function createCleaningPreview({ mount, context, api, flush = () => true }) {
  const run = mount.querySelector("#cleaning-run");
  const status = mount.querySelector("#cleaning-status");
  const results = mount.querySelector("#cleaning-results");
  let key, generation = 0, pending = false;
  function update() {
    const current = context();
    const next = current?.key;
    if (key !== next) {
      key = next;
      generation++;
      pending = false;
      status.textContent = "";
      results.replaceChildren();
    }
    run.disabled = !current || pending;
  }
  run.onclick = async () => {
    if (!flush()) return;
    const current = context();
    if (!current || pending) return;
    const expected = current.key;
    const attempt = generation;
    const isCurrent = () => generation === attempt && context()?.key === expected;
    pending = true;
    run.disabled = true;
    results.replaceChildren();
    status.textContent = "Preparing the current data…";
    try {
      const report = await api("/api/cleaning-preview", current.payload());
      if (isCurrent()) showCleaningPreview(report, status, results);
    } catch (error) {
      if (isCurrent()) status.textContent = error.message;
    } finally {
      if (isCurrent()) pending = false;
      update();
    }
  };
  update();
  return { update };
}
