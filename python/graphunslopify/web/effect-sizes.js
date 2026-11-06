export function createEffectExplorer(root, api) {
  const route = "/api/effect-sizes";
  const designs = {
    paired: ["Matched pairs", "Independent complete pairs with normally distributed within-pair differences."],
    pooled: ["Independent groups, common variance", "Independent normal groups with a common variance."],
    welch: ["Independent groups, Welch", "Independent normal groups with potentially unequal variances."],
  };
  function add(parent, tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  }
  function labeled(parent, text, tag) {
    const label = add(parent, "label", text);
    return add(label, tag);
  }
  function options(select, title, choices) {
    select.replaceChildren(new Option(title, ""), ...choices.map(([value, label]) => new Option(label, value)));
  }

  add(root, "p", "Compare signed mean differences and confidence intervals from a local CSV. Select the same outcome and study design for every contrast.");
  const file = labeled(root, "Effect comparison CSV", "input");
  file.type = "file"; file.accept = ".csv,text/csv";
  const status = add(root, "p");
  status.setAttribute("role", "status");
  const form = add(root, "form");
  const fields = add(form, "div");
  fields.className = "effect-fields";
  const design = labeled(fields, "Comparison design", "select");
  options(design, "Choose a design", Object.entries(designs).map(([key, value]) => [key, value[0]]));
  const outcome = labeled(fields, "Outcome column", "select");
  const group = labeled(fields, "Group column", "select");
  const unit = labeled(fields, "Independent unit", "select");
  const reduction = labeled(fields, "Repeated measurements", "select");
  reduction.add(new Option("Require one value per unit and group", "refuse"));
  reduction.add(new Option("Average valid values within each unit and group", "mean"));
  const confidence = labeled(fields, "Confidence level (0 to 1)", "input");
  confidence.type = "number"; confidence.step = "any"; confidence.min = "0.5"; confidence.max = "0.999"; confidence.value = "0.95";
  for (const field of [design, outcome, group, unit, confidence]) field.required = true;
  const contrasts = add(form, "div");
  const addContrast = add(form, "button", "Add another contrast");
  addContrast.type = "button";
  const assumptions = add(form, "p");
  const check = labeled(form, "I confirm the study design and independent units", "input");
  check.type = "checkbox"; check.required = true;
  check.closest("label").className = "power-confirm";
  const calculate = add(form, "button", "Compare effects");
  const result = add(root, "section");
  result.setAttribute("aria-label", "Effect comparison results");
  form.hidden = true;
  let bytes, fingerprint, columns = [], levels = [], sourceVersion = 0, resultVersion = 0;

  function invalidate() {
    resultVersion++;
    result.replaceChildren();
    calculate.disabled = !levels.length;
  }
  function unitOptions() {
    const previous = unit.value;
    const fields = columns.map(name => ["field:" + name, name]);
    if (design.value !== "paired") fields.unshift(["rows", "Each row is one independent unit"]);
    options(unit, "Choose units", fields);
    if (fields.some(([value]) => value === previous)) unit.value = previous;
    reduction.disabled = !unit.value.startsWith("field:");
    if (reduction.disabled) reduction.value = "refuse";
  }
  function insertContrast() {
    if (contrasts.childElementCount >= 12) return;
    const row = add(contrasts, "div");
    row.className = "effect-fields effect-contrast";
    const a = labeled(row, "Left group", "select");
    const b = labeled(row, "Right group", "select");
    const remove = add(row, "button", "Remove contrast");
    remove.type = "button";
    remove.className = "quiet";
    for (const [field, label] of [[a, "Choose left"], [b, "Choose right"]]) {
      field.required = true;
      options(field, label, levels.map(value => [value, value]));
    }
    remove.onclick = () => {
      row.remove();
      if (!contrasts.childElementCount) insertContrast();
      addContrast.disabled = contrasts.childElementCount >= 12;
      invalidate();
    };
    addContrast.disabled = contrasts.childElementCount >= 12;
    invalidate();
  }

  function checkSource(profile) {
    if (profile.source.sha256 !== fingerprint) throw Error("The analysis source differs from the selected CSV.");
  }
  file.onchange = async () => {
    const version = ++sourceVersion;
    bytes = null;
    levels = [];
    contrasts.replaceChildren();
    invalidate();
    form.hidden = true;
    const chosen = file.files[0];
    if (!chosen) { status.textContent = ""; return; }
    status.textContent = "Reading the CSV…";
    try {
      if (!chosen.size || chosen.size > 2 * 1024 * 1024) throw Error("Choose a nonempty UTF-8 CSV of at most 2 MiB.");
      const buffer = await chosen.arrayBuffer();
      const raw = new Uint8Array(buffer);
      let binary = "";
      for (let index = 0; index < raw.length; index += 16384) binary += String.fromCharCode(...raw.subarray(index, index + 16384));
      const encoded = btoa(binary);
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer)),
        value => value.toString(16).padStart(2, "0")).join("");
      const profile = await api(route, { mode: "profile", csv: encoded });
      if (version !== sourceVersion) return;
      fingerprint = digest;
      checkSource(profile);
      bytes = encoded;
      columns = profile.columns;
      const fields = columns.map(name => [name, name]);
      options(outcome, "Choose an outcome", fields);
      options(group, "Choose a group column", fields);
      unitOptions();
      check.checked = false;
      status.textContent = chosen.name + " · " + profile.source.records + " parsed records";
      form.hidden = false;
      addContrast.disabled = true;
    } catch (problem) {
      if (version === sourceVersion) status.textContent = problem.message;
    }
  };
  group.onchange = async () => {
    const version = ++sourceVersion;
    levels = [];
    contrasts.replaceChildren();
    invalidate();
    addContrast.disabled = true;
    if (!group.value) return;
    try {
      const profile = await api(route, { mode: "profile", csv: bytes, group: group.value });
      if (version !== sourceVersion) return;
      checkSource(profile);
      if (profile.level_count > 100) throw Error("Choose a group column with at most 100 distinct values.");
      if (profile.level_count < 2) throw Error("Choose a group column with at least two values.");
      levels = profile.levels;
      status.textContent = profile.level_count + " groups in " + group.value;
      insertContrast();
    } catch (problem) {
      if (version === sourceVersion) status.textContent = problem.message;
    }
  };
  design.onchange = () => {
    unitOptions();
    check.checked = false;
    assumptions.textContent = designs[design.value]?.[1] || "";
  };
  unit.onchange = unitOptions;
  addContrast.onclick = insertContrast;
  form.addEventListener("input", invalidate);

  const fmt = value => Number(value.toPrecision(5)).toString();
  function showLineage(details, provenance) {
    for (const [label, groups] of [
      ["Left unit records", provenance.left_units],
      ["Right unit records", provenance.right_units],
    ]) {
      const preview = groups.slice(0, 12).map(records => records.slice(0, 12).join(" + ") + (records.length > 12 ? " …" : ""));
      add(details, "p", label + " · " + (preview.join("; ") || "None") + (groups.length > 12 ? " …" : ""));
    }
    for (const [reason, records] of Object.entries(provenance.excluded)) {
      const label = reason[0].toUpperCase() + reason.slice(1).replaceAll("_", " ");
      add(details, "p", label + " · " + records.slice(0, 20).join(", ") + (records.length > 20 ? " …" : ""));
    }
    const raw = add(details, "details");
    add(raw, "summary", "Complete record lineage");
    raw.ontoggle = () => {
      if (raw.open && !raw.querySelector("pre")) add(raw, "pre", JSON.stringify(provenance, null, 2));
    };
  }

  function render(report) {
    add(result, "p", report.scope + " Source SHA-256 " + report.source.sha256 + ".");
    const scale = labeled(result, "Effect scale", "select");
    scale.add(new Option("Mean difference in outcome units", "raw"));
    scale.add(new Option("Standardized mean difference", "standardized"));
    const forest = add(result, "div");
    forest.className = "effect-forest";
    function draw() {
      forest.replaceChildren();
      const values = report.comparisons.map(row => row[scale.value]).filter(Boolean);
      const numbers = values.flatMap(metric => [metric.estimate, ...(metric.interval || [])]).filter(Number.isFinite);
      const bound = Math.max(...numbers.map(Math.abs), Number.MIN_VALUE);
      const low = Math.min(0, ...numbers.map(value => value / bound));
      const high = Math.max(0, ...numbers.map(value => value / bound));
      const position = value => high === low ? 50 : 100 * (value / bound - low) / (high - low);
      if (numbers.length && low !== high) {
        const axis = add(forest, "div");
        axis.className = "effect-axis";
        axis.setAttribute("aria-hidden", "true");
        add(axis, "span", fmt(low * bound));
        add(axis, "span", fmt(high * bound));
      }
      for (const row of report.comparisons) {
        const article = add(forest, "article");
        add(article, "h4", row.left + " minus " + row.right);
        const metric = row[scale.value];
        if (metric?.estimate !== null && metric?.estimate !== undefined) {
          const suffix = metric.interval ? " · " + fmt(report.inputs.confidence * 100) + "% CI [" + metric.interval.map(fmt).join(", ") + "]" : " · interval unavailable";
          add(article, "p", metric.label + " " + fmt(metric.estimate) + suffix + (metric.approximate ? " · Approximate interval" : ""));
          const track = add(article, "div");
          track.className = "effect-interval";
          track.setAttribute("aria-hidden", "true");
          track.style.setProperty("--effect-zero", position(0) + "%");
          track.style.setProperty("--effect-center", position(metric.estimate) + "%");
          if (metric.interval) {
            track.style.setProperty("--effect-left", position(metric.interval[0]) + "%");
            track.style.setProperty("--effect-width", position(metric.interval[1]) - position(metric.interval[0]) + "%");
          }
          add(track, "span"); add(track, "i");
        }
        add(article, "p", report.inputs.design === "paired" ? row.n_left + " complete pairs"
          : row.n_left + " left units · " + row.n_right + " right units");
        for (const note of row.notes) add(article, "p", note);
        const lineage = add(article, "details");
        add(lineage, "summary", "Contributing and excluded CSV records");
        lineage.ontoggle = () => {
          if (lineage.open && lineage.childElementCount === 1) showLineage(lineage, row.provenance);
        };
      }
    }
    scale.onchange = draw;
    draw();
  }
  form.onsubmit = async event => {
    event.preventDefault();
    if (!bytes || !levels.length) return;
    const version = ++resultVersion;
    calculate.disabled = true;
    status.textContent = "Comparing selected effects…";
    result.replaceChildren();
    try {
      const report = await api(route, { mode: "compare", csv: bytes, options: {
        design: design.value, outcome: outcome.value, group: group.value,
        unit: unit.value.startsWith("field:") ? unit.value.slice(6) : null,
        rows_are_units: unit.value === "rows", reduction: reduction.value,
        confidence: confidence.valueAsNumber, assumptions_confirmed: check.checked,
        contrasts: Array.from(contrasts.children, row => Array.from(row.querySelectorAll("select"), field => field.value)),
      }});
      if (version !== resultVersion) return;
      checkSource(report);
      render(report);
      status.textContent = report.status === "estimated" ? "Effect comparison ready." : "Some effects or intervals are unavailable.";
    } catch (problem) {
      if (version === resultVersion) status.textContent = problem.message;
    } finally {
      if (version === resultVersion) calculate.disabled = false;
    }
  };
}
