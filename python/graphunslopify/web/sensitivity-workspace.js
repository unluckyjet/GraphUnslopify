const route = "/api/sensitivity";
const limit = 4;
const number = value => value == null ? "—" : String(Number(value.toPrecision(7)));

function add(parent, tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent.append(node);
  return node;
}
function field(parent, label, tag, options) {
  const node = add(add(parent, "label", label), tag);
  if (options) for (const [name, value] of options) node.add(new Option(name, value));
  return node;
}
function button(parent, text) {
  const node = add(parent, "button", text);
  node.type = "button";
  return node;
}
function previewChoices(root, choices, before) {
  const images = add(root, "div");
  images.className = "sensitivity-images";
  for (const choice of choices) {
    const tile = add(images, "article");
    add(tile, "h3", choice.label);
    if (choice.justification) add(tile, "p", choice.justification);
    add(tile, "p", choice.status === "checked" ? "Strict checks passed" :
      choice.status === "checked_with_failures" ? "Strict checks reported failures or incomplete evidence" : "The comparison could not be checked");
    if (choice.preview?.data_url) {
      const image = add(tile, "img");
      image.alt = choice.label + " native figure";
      image.src = choice.preview.data_url;
    } else if (choice.preview?.display_error) add(tile, "p", choice.preview.display_error);
    if (choice.counts) {
      add(tile, "p", choice.counts.read + " parsed · " + choice.counts.after_filter +
        " after filters · " + choice.counts.finite + " finite measurements");
    }
    for (const error of choice.errors || []) add(tile, "p", error);
    if (choice.findings?.length) {
      const checks = add(tile, "details");
      add(checks, "summary", "Verification findings");
      const list = add(checks, "ul");
      for (const entry of choice.findings) add(list, "li", entry.severity + " · " + entry.message);
    }
  }
  for (const choice of choices.slice(1)) {
    const section = add(root, "section");
    add(section, "h3", choice.label + " compared with " + before);
    const claimSection = add(section, "div");
    if (choice.claim_comparison?.length) {
      add(claimSection, "h4", "Claim verdicts");
      const list = add(claimSection, "ul");
      for (const claim of choice.claim_comparison) {
        add(list, "li", claim.before.subject + " · " + claim.before.kind.replaceAll("_", " ") +
          " · " + claim.before.verdict + " → " + claim.after.verdict +
          (claim.changed ? " (changed)" : ""));
      }
    } else if (choice.claim_comparison === null) add(claimSection, "p", "Aligned claim results are unavailable.");
    if (!choice.comparison?.length) {
      add(section, "p", "Aligned estimates are unavailable for this comparison.");
      continue;
    }
    const details = add(section, "details");
    details.open = choice.comparison.length <= 12;
    add(details, "summary", "Group estimates and intervals (" + choice.comparison.length + ")");
    const scroll = add(details, "div");
    scroll.className = "sensitivity-table";
    scroll.tabIndex = 0;
    scroll.setAttribute("aria-label", choice.label + " group comparison");
    const table = add(scroll, "table");
    const head = add(add(table, "thead"), "tr");
    for (const title of ["Group", before, "Alternative", "Change"]) add(head, "th", title).scope = "col";
    const tbody = add(table, "tbody");
    for (const row of choice.comparison) {
      const line = add(tbody, "tr");
      const item = row.before ?? row.after;
      add(line, "th", Object.entries(item.keys).map(([key, value]) => key + " = " + value).join(" · ")).scope = "row";
      for (const estimate of [row.before, row.after]) {
        const cell = add(line, "td");
        if (!estimate) {
          cell.textContent = "Group absent";
          continue;
        }
        add(cell, "span", number(estimate.estimate) + " · " + estimate.estimator);
        add(cell, "small", estimate.units + (estimate.unit_field ? " units by " + estimate.unit_field : " rows"));
        if (estimate.interval) {
          const interval = estimate.interval;
          const method = interval.bootstrap ? Math.round(interval.bootstrap.level * 1000) / 10 +
            "% percentile bootstrap" : interval.method;
          add(cell, "small", method + " [" + interval.bounds.map(number).join(", ") + "]");
        }
      }
      add(line, "td", number(row.difference));
    }
  }
}

export function createSensitivity({ mount, context, api, flush = () => true, sourceLabel }) {
  add(mount, "p", sourceLabel + " Compare up to four justified changes to the estimator, uncertainty or cohort. Each choice renders separately.");
  const status = add(mount, "p");
  status.setAttribute("role", "status");
  const fields = add(mount, "div");
  const addChoice = button(mount, "Add alternative");
  const review = button(mount, "Review alternatives");
  const disclosure = add(mount, "div");
  const result = add(mount, "section");
  result.setAttribute("aria-label", "Sensitivity comparison results");
  const cards = [];
  let key, generation = 0, pending = false;
  function invalidate() {
    generation++;
    pending = false;
    disclosure.replaceChildren();
    result.replaceChildren();
    status.textContent = "";
  }
  function update() {
    const current = context();
    if (key !== current?.key) {
      key = current?.key;
      invalidate();
    }
    review.disabled = !current || pending;
    addChoice.disabled = cards.length >= limit;
    for (const [index, item] of cards.entries()) {
      item.legend.textContent = "Alternative " + (index + 1);
      item.remove.disabled = cards.length <= 1;
    }
    if (!current && !status.textContent) status.textContent = "Choose a current figure and dataset to review alternatives.";
  }
  function insert() {
    if (cards.length >= limit) return;
    const card = add(fields, "fieldset");
    card.className = "sensitivity-choice";
    const legend = add(card, "legend");
    const label = field(card, "Alternative name", "input");
    label.maxLength = 80;
    const justification = field(card, "Statistical justification", "textarea");
    justification.rows = 2;
    justification.maxLength = 600;
    const grid = add(card, "div");
    grid.className = "sensitivity-fields";
    const aggregation = field(grid, "Summary estimator", "select", [
      ["Keep baseline", ""], ["Mean", "mean"], ["Median", "median"],
    ]);
    const method = field(grid, "Uncertainty method", "select", [
      ["Keep baseline", ""], ["No interval", "remove"], ["Percentile bootstrap confidence interval", "ci"],
      ["Standard deviation", "std"], ["Standard error", "sem"], ["Interquartile range", "iqr"], ["Range", "range"],
    ]);
    const level = field(grid, "Confidence level (0 to 1)", "input");
    level.type = "number"; level.min = "0.5"; level.max = "0.999"; level.step = "any";
    level.placeholder = "Keep baseline";
    const unitMode = field(grid, "Independent unit", "select", [
      ["Keep baseline", ""], ["Treat each row as a unit", "rows"], ["Use a column", "column"],
    ]);
    const unit = field(grid, "Unit column", "input");
    unit.closest("label").hidden = true;
    const filterMode = field(grid, "Cohort filters", "select", [
      ["Keep baseline", ""], ["Remove filters", "remove"], ["Replace filters", "replace"],
    ]);
    const filters = field(card, "Replacement filters (JSON array)", "textarea");
    filters.placeholder = '[{"field":"condition","op":"eq","value":"A"}]';
    filters.rows = 2;
    filters.closest("label").hidden = true;
    const remove = button(card, "Remove alternative");
    const item = { label, justification, aggregation, method, level, unitMode, unit, filterMode, filters, legend, remove };
    cards.push(item);
    remove.onclick = () => {
      if (cards.length <= 1) return;
      cards.splice(cards.indexOf(item), 1);
      card.remove();
      invalidate(); update();
    };
    card.addEventListener("input", () => {
      unit.closest("label").hidden = unitMode.value !== "column";
      filters.closest("label").hidden = filterMode.value !== "replace";
      const noInterval = method.value === "remove";
      level.disabled = noInterval || !!method.value && method.value !== "ci";
      unitMode.disabled = noInterval;
      unit.disabled = noInterval;
      invalidate(); update();
    });
    update();
  }
  function options() {
    return cards.map(card => {
      const changes = {};
      if (card.aggregation.value) changes.aggregation = card.aggregation.value;
      if (card.filterMode.value === "remove") changes.filter = null;
      if (card.filterMode.value === "replace") {
        changes.filter = JSON.parse(card.filters.value);
        if (!Array.isArray(changes.filter) || !changes.filter.length)
          throw Error("Provide a nonempty JSON filter array or select Remove filters.");
      }
      if (card.method.value === "remove") changes.uncertainty = null;
      else {
        const uncertainty = {};
        if (card.method.value) uncertainty.kind = card.method.value;
        if (!card.level.disabled && card.level.value) {
          if (!card.level.validity.valid) throw Error("Choose a confidence level between 0.5 and 0.999.");
          uncertainty.level = card.level.valueAsNumber;
        }
        if (card.unitMode.value === "rows") uncertainty.over = null;
        if (card.unitMode.value === "column") {
          if (!card.unit.value.trim()) throw Error("Enter the column for the independent unit.");
          uncertainty.over = card.unit.value.trim();
        }
        if (Object.keys(uncertainty).length) changes.uncertainty = uncertainty;
      }
      return { label: card.label.value, justification: card.justification.value, changes };
    });
  }
  function showResult(report) {
    status.textContent = report.status === "checked" ? "Comparison rendered and checked." :
      "Comparison contains failures or incomplete evidence. Review the individual checks.";
    add(result, "p", "Source SHA-256 " + report.source.sha256);
    add(result, "p", report.scope);
    add(result, "p", "Automatic axis limits can differ across previews. Use the group estimates to compare values directly.");
    previewChoices(result, report.choices, report.choices[0].label);
    const save = button(result, "Download comparison report");
    save.onclick = () => {
      const encoded = JSON.stringify(report, (name, value) => name === "data_url" ? undefined : value, 2);
      const url = URL.createObjectURL(new Blob([encoded], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "sensitivity-comparison.json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
  }
  function showReview(report, payload, expected, attempt) {
    status.textContent = "Review the baseline and alternatives before rendering.";
    add(disclosure, "p", "Source SHA-256 " + report.source.sha256);
    for (const choice of report.choices) {
      add(disclosure, "h3", choice.label);
      if (choice.justification) add(disclosure, "p", choice.justification);
      add(disclosure, "pre", JSON.stringify(choice.analysis, null, 2));
    }
    const consent = field(disclosure, "I reviewed the statistical choices and assumptions", "input");
    consent.type = "checkbox";
    consent.closest("label").className = "power-confirm";
    const render = button(disclosure, "Render reviewed comparison");
    render.disabled = true;
    consent.onchange = () => { render.disabled = !consent.checked || pending; };
    render.onclick = async () => {
      const stillCurrent = () => attempt === generation && context()?.key === expected;
      if (!consent.checked || pending || !stillCurrent()) return;
      pending = true; render.disabled = true; update();
      status.textContent = "Rendering and checking the baseline and each alternative…";
      try {
        const final = await api(route, { ...payload, mode: "render", ticket: report.ticket, reviewed: true });
        if (!stillCurrent()) return;
        if (final.source.sha256 !== report.source.sha256 ||
            final.source.palette_sha256 !== report.source.palette_sha256) throw Error("The comparison source differs from the review.");
        disclosure.replaceChildren();
        showResult(final);
      } catch (error) {
        if (stillCurrent()) status.textContent = error.message;
      } finally {
        if (stillCurrent()) { pending = false; render.disabled = !consent.checked; }
        update();
      }
    };
  }
  review.onclick = async () => {
    if (!flush()) return;
    const current = context();
    if (!current || pending) return;
    invalidate();
    const attempt = generation, expected = current.key;
    const stillCurrent = () => attempt === generation && context()?.key === expected;
    pending = true; update();
    status.textContent = "Preparing the statistical review…";
    try {
      const payload = { ...current.payload(), alternatives: options() };
      const report = await api(route, { ...payload, mode: "review" });
      if (stillCurrent()) showReview(report, payload, expected, attempt);
    } catch (error) {
      if (stillCurrent()) status.textContent = error.message;
    } finally {
      if (stillCurrent()) pending = false;
      update();
    }
  };
  addChoice.onclick = () => { invalidate(); insert(); };
  insert();
  return { update };
}
