import { createControls } from "/controls.js";
import { describeFinding } from "/diagnostics.js";
let diagnosticCatalog = {};
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="preview-token"]').content;
const client = crypto.randomUUID();
let revision = 0,
  data = null,
  palette = null,
  latest = null,
  timer = null,
  recipes = [],
  formSchema = null,
  selection = 0,
  paletteSelection = 0,
  maxUploadBytes = 100 * 1024 * 1024;
const initial = {
  kind: "line",
  x: { field: "epoch", label: "Epoch" },
  y: { field: "score", label: "Score" },
  output: { stem: "figure", formats: ["png", "svg", "pdf"] },
};
const controlHistory = [];
function controlError(text) {
  $("control-error").textContent = text;
  $("control-error").hidden = !text;
  if (text) status("Fix settings", "failed");
}
function changeControls(spec) {
  const before = $("spec").value;
  if (JSON.stringify(spec, null, 2) !== before) {
    controlHistory.push(before);
    if (controlHistory.length > 20) controlHistory.shift();
  }
  controls.discard();
  setSpec(spec);
  $("undo-controls").disabled = !controlHistory.length;
  schedule();
}
const controls = createControls($("settings"), {
  read: readSpec,
  change: changeControls,
  edit: invalidate,
  error: controlError,
});
function status(text, state = "") {
  $("status").textContent = text;
  $("status").dataset.state = state;
}
async function api(path, body, headers = {}) {
  if (body instanceof File && body.size > maxUploadBytes)
    throw Error(
      `Choose a file smaller than ${maxUploadBytes / 1024 / 1024} MiB, or increase --max-upload-mb.`,
    );
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "X-Preview-Token": token,
      ...(body instanceof File ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
    body:
      body === undefined
        ? undefined
        : body instanceof File
          ? body
          : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok)
    throw Error(result.error || "The request could not be completed");
  return result;
}
function readSpec() {
  const spec = JSON.parse($("spec").value);
  if (!spec || typeof spec !== "object" || Array.isArray(spec))
    throw Error("The specification must be a JSON object");
  return spec;
}
function setSpec(spec) {
  $("spec").value = JSON.stringify(spec, null, 2);
  syncFields(spec);
}
function invalidate() {
  revision++;
  latest = null;
  $("bundle").disabled = true;
  $("files").replaceChildren();
  $("preview").hidden = true;
  $("preview").removeAttribute("src");
  $("empty").hidden = false;
  $("empty").firstElementChild.textContent = data
    ? "Preview needs updating"
    : "Your figure will appear here";
  $("empty").lastElementChild.textContent = data
    ? "Render now or wait for live preview."
    : "Start with sample data, or choose a local file.";
  $("findings").replaceChildren();
  $("description-box").hidden = true;
  $("counts").textContent = "";
  $("claims").replaceChildren();
  status(data ? "Editing…" : "Choose data");
  clearTimeout(timer);
}
function schedule() {
  invalidate();
  timer = setTimeout(() => update(false), 500);
}
function options(select, values, current, none = false) {
  select.replaceChildren();
  if (none) select.add(new Option("None", ""));
  for (const value of [...new Set([...values, ...(current ? [current] : [])])])
    select.add(new Option(value.replaceAll("_", " "), value));
  select.value = current || "";
}
function syncFields(spec) {
  $("kind").value = spec.kind || "line";
  const columns = data ? data.columns.map((c) => c.name) : [];
  options($("x-field"), columns, spec.x?.field);
  options($("y-field"), columns, spec.y?.field);
  options($("group"), columns, spec.group, true);
  controls.sync(spec, formSchema, columns);
}
function showData(info) {
  data = info;
  $("data-summary").textContent = `${info.name} · ${info.rows} rows`;
  $("columns").replaceChildren(
    ...info.columns.map((column) => {
      const span = document.createElement("span");
      span.className = "chip";
      span.textContent = column.name;
      span.title = `${column.role} · ${column.distinct} distinct`;
      return span;
    }),
  );
}
function message(text, error = true) {
  const item = document.createElement("div");
  item.className = "finding" + (error ? " error" : "");
  item.textContent = text;
  $("findings").append(item);
}
function findings(items) {
  $("findings").replaceChildren();
  const seen = new Set();
  for (const item of items) {
    const key = item.code + item.message;
    if (seen.has(key)) continue;
    seen.add(key);
    const node = document.createElement("div");
    node.className = "finding" + (item.severity === "error" ? " error" : "");
    node.dataset.code = item.code;
    describeFinding(node, item, diagnosticCatalog);
    if (item.fix) {
      const detail = document.createElement("details"),
        summary = document.createElement("summary"),
        patch = document.createElement("pre");
      summary.textContent = "Review proposed change";
      patch.textContent = JSON.stringify(item.fix, null, 2);
      detail.append(summary, patch);
      node.append(detail);
      const button = document.createElement("button");
      button.textContent = "Apply fix";
      button.onclick = async () => {
        const current = revision;
        button.disabled = true;
        try {
          const fixed = await api("/api/fix", {
            spec: readSpec(),
            data_id: data.id,
            palette_id: palette?.id,
            code: item.code,
          });
          if (current !== revision) return;
          setSpec(fixed.spec);
          schedule();
        } catch (error) {
          if (current === revision) message(error.message);
        } finally {
          button.disabled = false;
        }
      };
      node.append(button);
    }
    $("findings").append(node);
  }
}
function artifact(run, name, download = false) {
  return (
    `/artifact/${run}/${encodeURIComponent(name)}?token=${encodeURIComponent(token)}` +
    (download ? "&download=true" : "")
  );
}
async function update(force) {
  if (!data) {
    status("Choose data");
    return;
  }
  let spec;
  try {
    spec = readSpec();
    syncFields(spec);
  } catch (error) {
    $("findings").replaceChildren();
    message("The specification cannot be read: " + error.message);
    status("Fix JSON", "failed");
    return;
  }
  const current = revision;
  status("Checking…");
  try {
    const payload = {
      spec,
      data_id: data.id,
      palette_id: palette?.id,
      client,
      generation: current,
    };
    const checked = await api("/api/validate", payload);
    if (current !== revision) return;
    findings(checked.findings || [], spec);
    if (checked.status === "invalid_spec") {
      findings(checked.issues.map((issue) => ({...issue, code: "invalid_spec", severity: "error", message: `${issue.path}: ${issue.message}`})));
      status("Fix specification", "failed");
      return;
    }
    if (!checked.ok) {
      status("Fix specification", "failed");
      return;
    }
    if (!force && !$("live").checked) {
      status("Ready to render");
      return;
    }
    status("Rendering…");
    const result = await api("/api/render", payload);
    if (current !== revision || result.stale) return;
    if (!result.report) {
      findings(result.translation.findings || [], spec);
      status("Fix specification", "failed");
      return;
    }
    latest = result.report.outputs.length ? result : null;
    setSpec(result.spec);
    const report = result.report;
    findings(
      [...(checked.findings || []), ...(report.findings || [])],
      result.spec,
    );
    status(
      { passed: "Verified", failed: "Failed checks", incomplete: "Incomplete" }[
        report.status
      ] || report.status,
      report.status,
    );
    for (const error of result.export_errors || []) {
      message(error);
      if (report.status === "passed") status("Missing exports", "incomplete");
    }
    const image = result.files.find((file) => file.format === "png");
    if (image) {
      $("preview").src = artifact(result.run_id, image.name);
      $("preview").alt = report.alt_text;
      $("preview").hidden = false;
      $("empty").hidden = true;
    } else {
      $("empty").firstElementChild.textContent = "No preview was produced";
      $("empty").lastElementChild.textContent =
        "Review the findings and update the specification.";
    }
    const counts = report.data.counts;
    $("counts").textContent =
      `${counts.read ?? 0} rows read · ${counts.after_filter ?? 0} after filters${counts.unit_column ? ` · units: ${counts.unit_column}` : ""}`;
    for (const claim of report.claims) {
      const node = document.createElement("div");
      node.className = "claim " + claim.verdict;
      node.textContent = `${claim.verdict.toUpperCase()} · ${claim.metric} · ${claim.subject}${claim.reference ? " vs " + claim.reference : ""}${claim.panel !== undefined ? " · panel " + (claim.panel + 1) : ""}: ${claim.detail}`;
      if (claim.interval_overlap && claim.interval_overlap[0] > 0)
        node.append(
          document.createTextNode(
            `. Uncertainty intervals overlap at ${claim.interval_overlap[0]} of ${claim.interval_overlap[1]} comparisons; the numeric claim does not establish a significant difference.`,
          ),
        );
      $("claims").append(node);
      if (["fails", "untested"].includes(claim.verdict)) {
        const guidance = document.createElement("div");
        describeFinding(guidance, {code: claim.verdict === "fails" ? "claim_failed" : "check_untested", message: claim.detail}, diagnosticCatalog);
        $("claims").append(guidance);
      }
    }
    $("description").textContent = report.alt_text;
    $("description-box").hidden = false;
    $("files").replaceChildren(
      ...result.files.map((file) => {
        const a = document.createElement("a");
        a.className = "download";
        a.textContent =
          file.format === "py"
            ? "Python"
            : file.name.endsWith(".figure.json")
              ? "Spec"
              : file.name.endsWith(".report.json")
                ? "Report"
                : file.format.toUpperCase();
        a.href = artifact(result.run_id, file.name, true);
        a.download = file.name;
        return a;
      }),
    );
    $("bundle").disabled = report.outputs.length === 0;
  } catch (error) {
    if (current !== revision) return;
    message(error.message);
    status("Needs attention", "failed");
  }
}
$("spec").addEventListener("input", () => {
  controlHistory.length = 0;
  $("undo-controls").disabled = true;
  controls.discard();
  try {
    syncFields(readSpec());
  } catch {
    controls.disable(
      "Correct the Advanced JSON object to use the settings controls.",
    );
  }
  schedule();
});
$("undo-controls").onclick = () => {
  if (!controlHistory.length) return;
  controls.discard();
  $("spec").value = controlHistory.pop();
  try {
    syncFields(readSpec());
  } catch {
    controls.disable("Correct Advanced JSON to use settings.");
  }
  $("undo-controls").disabled = !controlHistory.length;
  schedule();
};
$("format").onclick = () => {
  try {
    setSpec(readSpec());
  } catch (error) {
    message(error.message);
  }
};
$("render").onclick = () => {
  if (!controls.flush()) return;
  clearTimeout(timer);
  invalidate();
  update(true);
};
$("live").onchange = () => {
  if ($("live").checked) schedule();
};
for (const id of ["kind", "x-field", "y-field", "group"])
  $(id).onchange = () => {
    try {
      if (!controls.flush()) {
        syncFields(readSpec());
        return;
      }
      const spec = readSpec();
      if (id === "kind") spec.kind = $(id).value;
      else if (id === "group") {
        if ($(id).value) spec.group = $(id).value;
        else delete spec.group;
      } else {
        const axis = id[0];
        const previous = spec[axis] || {};
        const defaultLabel = (previous.field || "").replaceAll("_", " ");
        spec[axis] = {
          ...previous,
          field: $(id).value,
          label:
            previous.label && previous.label !== defaultLabel
              ? previous.label
              : $(id).value.replaceAll("_", " "),
        };
      }
      changeControls(spec);
    } catch (error) {
      message(error.message);
    }
  };
$("recipe").onchange = () => {
  const item = recipes.find((r) => r.name === $("recipe").value);
  if (item) {
    changeControls(structuredClone(item.spec));
    $("recipe-note").textContent = item.purpose;
  }
};
$("data-file").onchange = async () => {
  const file = $("data-file").files[0];
  if (!file) return;
  const operation = ++selection;
  invalidate();
  const current = revision;
  data = null;
  $("data-summary").textContent = "Reading " + file.name + "…";
  status("Reading data…");
  try {
    const info = await api("/api/upload", file, {
      "X-Filename": encodeURIComponent(file.name),
    });
    if (operation !== selection) return;
    showData(info);
    const suggestions = await api("/api/suggest", { data_id: data.id });
    if (operation !== selection) return;
    if (revision === current && suggestions.length)
      setSpec(suggestions[0].spec);
    else {
      try {
        syncFields(readSpec());
      } catch {}
    }
    schedule();
  } catch (error) {
    if (operation === selection) {
      message(error.message);
      status("Could not read data", "failed");
    }
  }
};
$("palette-file").onchange = async () => {
  const file = $("palette-file").files[0];
  if (!file) return;
  const operation = ++paletteSelection;
  invalidate();
  palette = null;
  try {
    const selected = await api("/api/upload", file, {
      "X-Filename": encodeURIComponent(file.name),
      "X-Palette": "true",
    });
    if (operation !== paletteSelection) return;
    palette = selected;
    schedule();
  } catch (error) {
    message(error.message);
  }
};
$("demo").onclick = async () => {
  const operation = ++selection;
  invalidate();
  data = null;
  status("Loading sample…");
  try {
    const demo = await api("/api/demo", {});
    if (operation !== selection) return;
    showData(demo.data);
    setSpec(demo.spec);
    schedule();
  } catch (error) {
    if (operation === selection) message(error.message);
  }
};
$("bundle").onclick = () => {
  if (latest) {
    const link = document.createElement("a");
    link.href = `/bundle/${latest.run_id}?token=${encodeURIComponent(token)}&data=${$("include-data").checked}`;
    link.download = "figure-bundle.zip";
    link.click();
  }
};
$("spec").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    $("render").click();
  }
});
setSpec(initial);
api("/api/info")
  .then((info) => {
    diagnosticCatalog = info.diagnostics;
    maxUploadBytes = info.max_upload_mb * 1024 * 1024;
    recipes = info.recipes;
    formSchema = info.schema;
    options($("kind"), info.kinds, "line");
    for (const recipe of recipes)
      $("recipe").add(
        new Option(recipe.name.replaceAll("_", " "), recipe.name),
      );
    syncFields(readSpec());
  })
  .catch((error) => message(error.message));
