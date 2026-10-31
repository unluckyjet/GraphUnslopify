import { createControls } from "/controls.js";
import { createTextEditor } from "/text-editing.js";
import { describeFinding } from "/diagnostics.js";
import { createDraftEditor } from "/drafts.js";
import { createDiagnosticOverlays, findingIdentity } from "/diagnostic-overlays.js";
import { createStagedPreview } from "/staged-preview.js";
let draftEditor = null;
let diagnosticCatalog = {};
let suggested = [], suggestedData = null;
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="preview-token"]').content;
const client = crypto.randomUUID();
let revision = 0,
  data = null,
  workbook = null,
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
const stagedPreview = createStagedPreview({
  token, client,
  current: () => ({generation: revision, data_id: data?.id, palette_id: palette?.id}),
  mount: ({url, stage, identity}) => {
    latest = null;
    textEditor.clear();
    diagnosticOverlays.clear();
    $("bundle").disabled = true;
    $("files").replaceChildren();
    const image = $("preview");
    image.src = url;
    image.alt = "Unverified figure preview. Checks and exports are still running.";
    image.dataset.phase = "unverified";
    image.dataset.generation = String(identity.generation);
    image.dataset.imageSha256 = stage.image.sha256;
    image.hidden = false;
    $("figure-surface").hidden = false;
    $("empty").hidden = true;
    status("Unverified preview", "unverified");
  },
});
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
const textEditor = createTextEditor({
  current: () => ({revision, dataId: data?.id, result: latest, spec: readSpec()}),
  apply: spec => { changeControls(spec); clearTimeout(timer); update(true); },
});
const diagnosticOverlays = createDiagnosticOverlays({
  current: () => ({revision, dataId: data?.id, result: latest, spec: readSpec()}),
  catalog: () => diagnosticCatalog,
  deactivateText: () => textEditor.hide(),
});
$("edit-figure-text").addEventListener("click", () => diagnosticOverlays.hide());
draftEditor = createDraftEditor({
  api, identity: () => ({client, generation: revision}), flush: () => controls.flush(),
  snapshot: () => ({client, generation: revision, spec: readSpec(), data_id: data?.id, palette_id: palette?.id, data_name: data?.name, rows: data?.rows, sheet: data?.profile?.sheet, columns: data?.columns.map(column => column.name) || []}),
  apply: spec => { changeControls(spec); clearTimeout(timer); update(true); },
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
  if (!response.ok) {
    const problem = Error(result.error || "The request could not be completed");
    problem.details = result;
    throw problem;
  }
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
  stagedPreview.invalidate();
  draftEditor?.invalidate();
  latest = null;
  textEditor.clear();
  diagnosticOverlays.clear();
  $("figure-surface").hidden = true;
  $("bundle").disabled = true;
  $("files").replaceChildren();
  $("preview").hidden = true;
  $("preview").removeAttribute("src");
  for (const key of ["phase", "generation", "imageSha256", "runId"])
    delete $("preview").dataset[key];
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
  draftEditor?.refresh();
  $("kind").value = spec.kind || "line";
  const columns = data ? data.columns.map((c) => c.name) : [];
  options($("x-field"), columns, spec.x?.field);
  options($("y-field"), columns, spec.y?.field);
  options($("group"), columns, spec.group, true);
  controls.sync(spec, formSchema, columns);
}
function showData(info) {
  data = info;
  const sheet = info.profile?.sheet;
  $("data-summary").textContent = `${info.name}${sheet ? " · " + sheet : ""} · ${info.rows} rows`;
  const table = document.createElement("table");
  table.setAttribute("aria-label", "Dataset columns");
  const head = table.createTHead().insertRow();
  for (const label of ["Field", "Type", "Rows"]) {
    const cell = document.createElement("th");
    cell.scope = "col"; cell.textContent = label; head.append(cell);
  }
  const body = table.createTBody();
  const count = (n) => typeof n === "number" ? String(n) : "Unknown";
  for (const column of info.columns) {
    const row = body.insertRow();
    const name = row.insertCell();
    name.textContent = column.name;
    const role = document.createElement("small");
    role.textContent = `${column.role} guess`; name.append(role);
    row.insertCell().textContent = column.dtype || "Unknown";
    const counts = row.insertCell();
    counts.textContent = `${count(column.non_missing)} present`;
    const missing = document.createElement("small");
    missing.textContent = `${count(column.missing)} missing`;
    if (column.missing > 0) missing.className = "missing";
    counts.append(missing);
    if (column.nonfinite > 0) {
      const unavailable = document.createElement("small");
      unavailable.textContent = `${column.nonfinite} nonfinite`;
      unavailable.className = "missing"; counts.append(unavailable);
    }
  }
  $("columns").replaceChildren(table);
  $("profile-note").hidden = false;
  $("profile-note").textContent = "Roles are guesses. Row counts do not establish independent experimental samples.";
}
function clearDataViews() {
  $("columns").replaceChildren();
  $("profile-note").hidden = true;
  showDesigns([], null);
}
function showDesigns(items, identity) {
  suggested = items; suggestedData = identity;
  $("designs").hidden = !items.length;
  $("apply-design").disabled = !items.length;
  $("design-choice").replaceChildren(...items.map((item, index) =>
    new Option(`${item.spec.kind.replaceAll("_", " ")} · ${item.spec.x.field} / ${item.spec.y.field}`, String(index))));
  showDesignReason();
}
function showDesignReason() {
  const item = suggested[Number($("design-choice").value)];
  $("design-note").textContent = item?.why || "";
}
function showWorkbook(info) {
  workbook = info.sheets?.length ? {
    id: info.workbook_id || info.id, name: info.name,
    activeSheet: info.profile?.sheet, sheets: info.sheets,
  } : null;
  $("worksheet-box").hidden = !workbook;
  $("include-data-label").textContent = workbook
    ? "Include entire workbook (all worksheets) in ZIP"
    : "Include source data in ZIP";
  $("worksheet").replaceChildren(
    new Option("Choose a worksheet…", ""),
    ...(workbook?.sheets || []).map((sheet) => new Option(sheet, sheet)),
  );
  $("worksheet").value = workbook?.activeSheet || "";
}
function bindData(spec, info) {
  spec.data = {path: info.profile.path, format: info.format,
    columns: info.columns.map((column) => column.name),
    ...(info.format === "excel" ? {sheet: info.profile.sheet} : {}),
  };
  return spec;
}
async function activateData(info, operation, current, recommend = true) {
  const suggestions = await api("/api/suggest", {data_id: info.id});
  if (operation !== selection) return;
  showData(info);
  showDesigns(suggestions, info.id);
  if (workbook) workbook.activeSheet = info.profile.sheet;
  if (recommend && revision === current && suggestions.length)
    setSpec(bindData(suggestions[0].spec, info));
  else {
    try { setSpec(bindData(readSpec(), info)); } catch {}
  }
  schedule();
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
    const key = findingIdentity(item);
    if (seen.has(key)) continue;
    seen.add(key);
    const node = document.createElement("div");
    node.className = "finding" + (item.severity === "error" ? " error" : "");
    node.dataset.code = item.code;
    node.dataset.identity = key;
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
          changeControls(fixed.spec);
          clearTimeout(timer);
          await update(true);
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
    status(workbook ? "Choose a worksheet" : "Choose data");
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
  // A new check cancels any review tied to the previous rendered result.
  textEditor.clear();
  diagnosticOverlays.clear();
  const current = revision;
  const attempt = stagedPreview.begin({generation: current, data_id: data.id, palette_id: palette?.id});
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
    if (!attempt.isCurrent()) return;
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
    const final = api("/api/render", {...payload, ...attempt.payload});
    attempt.start();
    const result = await final;
    attempt.finish();
    if (!attempt.isCurrent() || result.stale) return;
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
      $("preview").dataset.phase = "final";
      $("preview").dataset.generation = String(current);
      $("preview").dataset.runId = result.run_id;
      delete $("preview").dataset.imageSha256;
      $("preview").hidden = false;
      $("figure-surface").hidden = false;
      textEditor.mount(result);
      diagnosticOverlays.mount(result);
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
    if (!attempt.isCurrent()) return;
    message(error.message);
    status("Needs attention", "failed");
  } finally {
    attempt.finish();
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
async function uploadData(file) {
  if (!file) return;
  const operation = ++selection;
  data = null;
  showWorkbook({});
  $("include-data").checked = false;
  clearDataViews();
  invalidate();
  const current = revision;
  $("data-summary").textContent = "Reading " + file.name + "…";
  status("Reading data…");
  try {
    const info = await api("/api/upload", file, {
      "X-Filename": encodeURIComponent(file.name),
    });
    if (operation !== selection) return;
    showWorkbook(info);
    if (info.requires_sheet) {
      $("data-summary").textContent = `${info.name} · choose a worksheet`;
      status("Choose a worksheet");
      return;
    }
    await activateData(info, operation, current);
  } catch (error) {
    if (operation === selection) {
      message(error.message);
      status("Could not read data", "failed");
    }
  }
}
$("data-file").onchange = () => uploadData($("data-file").files[0]);
$("design-choice").onchange = showDesignReason;
$("apply-design").onclick = () => {
  const item = suggested[Number($("design-choice").value)];
  if (item && data?.id === suggestedData)
    changeControls(bindData(structuredClone(item.spec), data));
};
const drop = $("data-drop");
let dragDepth = 0;
drop.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
});
drop.addEventListener("dragenter", (event) => {
  event.preventDefault(); dragDepth++; drop.dataset.dragging = "true";
});
drop.addEventListener("dragleave", () => {
  if (--dragDepth <= 0) { dragDepth = 0; delete drop.dataset.dragging; }
});
drop.addEventListener("drop", (event) => {
  event.preventDefault(); dragDepth = 0; delete drop.dataset.dragging;
  const files = event.dataTransfer?.files;
  if (!files || files.length !== 1) { message("Choose one dataset file at a time."); return; }
  $("data-file").value = "";
  uploadData(files[0]);
});
document.addEventListener("dragover", (event) => {
  if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
});
document.addEventListener("drop", (event) => {
  if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
});
$("worksheet").onchange = async () => {
  if (!workbook) return;
  const source = workbook, sheet = $("worksheet").value;
  const recommend = !source.activeSheet;
  const operation = ++selection;
  data = null;
  clearDataViews();
  invalidate();
  const current = revision;
  if (!sheet) {
    $("data-summary").textContent = `${source.name} · choose a worksheet`;
    status("Choose a worksheet");
    return;
  }
  $("data-summary").textContent = `${source.name} · reading ${sheet}…`;
  status("Reading worksheet…");
  try {
    const info = await api("/api/select-sheet", {data_id: source.id, sheet});
    if (operation !== selection || workbook !== source) return;
    await activateData(info, operation, current, recommend);
  } catch (error) {
    if (operation === selection) {
      message(error.message);
      status("Could not read worksheet", "failed");
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
  data = null;
  showWorkbook({});
  $("include-data").checked = false;
  clearDataViews();
  invalidate();
  status("Loading sample…");
  try {
    const demo = await api("/api/demo", {});
    if (operation !== selection) return;
    showData(demo.data);
    setSpec(demo.spec);
    const suggestions = await api("/api/suggest", {data_id: demo.data.id});
    if (operation !== selection) return;
    showDesigns(suggestions, demo.data.id);
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
    stagedPreview.configure(info.staged_preview);
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
