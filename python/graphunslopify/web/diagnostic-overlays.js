import { describeFinding } from "/diagnostics.js";

const kinds = new Set(["text", "legend", "bar", "bar_interval"]);
export function findingIdentity(item) {
  return JSON.stringify([item?.severity, item?.code, item?.message]);
}

/** Read-only selection; all repairs remain in the existing verifier-owned flow. */
export function createDiagnosticOverlays({ current, catalog, deactivateText }) {
  const $ = id => document.getElementById(id);
  const image = $("preview"), layer = $("diagnostic-targets"), picker = $("diagnostic-finding");
  let binding = null, result = null, active = false, selected = null;
  let targets = [], unlocated = new Map();

  function same() {
    try {
      const now = current();
      return binding && !result.stale && now.revision === binding.revision && now.dataId === binding.dataId &&
        now.result?.run_id === binding.runId && now.result?.report.spec_hash === binding.hash &&
        JSON.stringify(now.spec) === binding.spec;
    } catch { return false; }
  }
  function position() {
    const correct = image.complete && image.currentSrc === binding?.src &&
      image.naturalWidth === binding?.width && image.naturalHeight === binding?.height;
    if (image.complete && image.naturalWidth)
      $("figure-surface").style.setProperty("--figure-ratio", String(image.naturalWidth / image.naturalHeight));
    layer.hidden = !same() || !active || !correct;
  }
  function hide() {
    active = false; layer.hidden = true;
    $("show-diagnostics").setAttribute("aria-pressed", "false");
    $("diagnostic-review").hidden = true;
  }
  function clear() {
    hide(); binding = null; result = null; selected = null; targets = []; unlocated = new Map();
    layer.replaceChildren(); picker.replaceChildren(new Option("Choose a finding", ""));
    $("diagnostic-description").replaceChildren();
    $("diagnostic-location").textContent = "";
    $("show-diagnostics").disabled = true;
    for (const card of document.querySelectorAll("#findings .finding")) {
      card.classList.remove("selected-finding");
      card.querySelector(".finding-location")?.remove();
    }
  }
  function show() {
    if (!same()) { clear(); return false; }
    active = true; deactivateText();
    $("show-diagnostics").setAttribute("aria-pressed", "true");
    $("diagnostic-review").hidden = false;
    position(); return true;
  }
  function select(index, focus = true) {
    if (!Number.isInteger(index) || !result?.report.findings[index] || !show()) return;
    selected = index; picker.value = String(index);
    const finding = result.report.findings[index];
    $("diagnostic-description").replaceChildren();
    describeFinding($("diagnostic-description"), finding, catalog());
    const regions = targets.filter(target => target.finding_index === index);
    $("diagnostic-location").textContent = regions.length
      ? `${regions.length} measured region${regions.length === 1 ? "" : "s"} highlighted. Selecting a region keeps the figure unchanged.${binding.truncated ? " Some additional locations could not be captured." : ""}`
      : `Location unavailable: ${unlocated.get(index) || "This check has no reliable visible location."}`;
    for (const button of layer.children) button.classList.toggle("selected", Number(button.dataset.findingIndex) === index);
    for (const card of document.querySelectorAll("#findings .finding"))
      card.classList.toggle("selected-finding", card.dataset.identity === findingIdentity(finding));
    if (focus) $("diagnostic-description").focus({preventScroll: true});
  }
  image.addEventListener("load", position);
  $("show-diagnostics").onclick = () => {
    if (active) hide();
    else if (show() && selected !== null) select(selected, false);
  };
  picker.onchange = () => picker.value !== "" && select(Number(picker.value));
  $("close-diagnostics").onclick = () => { hide(); $("show-diagnostics").focus(); };
  $("diagnostic-review").addEventListener("keydown", event => {
    if (event.key === "Escape") { hide(); $("show-diagnostics").focus(); }
  });
  function mount(value) {
    clear(); result = value;
    const findings = value.report?.findings;
    if (!Array.isArray(findings) || value.stale) return;
    const map = value.diagnostic_map;
    const png = value.report.outputs.find(output => output.format === "png" && output.path.split(/[\\/]/).pop() === map?.image?.name);
    const valid = map?.available === true && map.schema_version === 1 && map.coordinates === "pixels_top_left" &&
      map.run_id === value.run_id && map.spec_hash === value.report.spec_hash && png?.sha256 === map.image?.sha256 &&
      Number.isInteger(map.image?.width) && map.image.width > 0 && Number.isInteger(map.image?.height) && map.image.height > 0 &&
      Array.isArray(map.targets) && map.targets.length <= 16384 && Array.isArray(map.unlocated);
    const now = current();
    binding = {revision: now.revision, dataId: now.dataId, runId: value.run_id, hash: value.report.spec_hash,
      width: valid ? map.image.width : 0, height: valid ? map.image.height : 0, src: image.src, spec: JSON.stringify(now.spec)};
    let metadataValid = valid;
    if (valid) {
      for (const target of map.targets) {
        const bounds = target?.bounds;
        if (!Number.isInteger(target?.finding_index) || !findings[target.finding_index] || target.finding_index < 0 ||
          !kinds.has(target.kind) || !Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(Number.isFinite)) { metadataValid = false; break; }
        const [x,y,w,h] = bounds;
        if (x < 0 || y < 0 || w <= 0 || h <= 0 || x+w > map.image.width+0.001 || y+h > map.image.height+0.001) { metadataValid = false; break; }
      }
    }
    if (metadataValid) {
      binding.truncated = map.truncated === true;
      targets = map.targets;
      for (const entry of map.unlocated)
        if (Number.isInteger(entry?.finding_index) && findings[entry.finding_index])
          unlocated.set(entry.finding_index, String(entry.reason || "No reliable visible location was captured."));
      for (const target of targets) {
        const finding = findings[target.finding_index], button = document.createElement("button");
        button.type = "button"; button.className = "diagnostic-target" + (finding.severity === "error" ? " error" : "");
        button.dataset.findingIndex = String(target.finding_index);
        const label = `Show finding: ${String(finding.code).replaceAll("_", " ")}`;
        button.setAttribute("aria-label", label); button.title = label;
        const [x,y,w,h] = target.bounds;
        button.style.left = `${100*x/map.image.width}%`; button.style.top = `${100*y/map.image.height}%`;
        button.style.width = `${100*w/map.image.width}%`; button.style.height = `${100*h/map.image.height}%`;
        button.onclick = () => select(target.finding_index);
        layer.append(button);
      }
    } else {
      targets = [];
      for (let index=0; index<findings.length; index++)
        unlocated.set(index, "Measured locations are unavailable for this preview.");
    }
    for (let index=0; index<findings.length; index++) {
      const finding = findings[index], located = targets.some(target => target.finding_index === index);
      picker.add(new Option(`${String(finding.code).replaceAll("_", " ")}${located ? "" : " (location unavailable)"}`, String(index)));
      for (const card of document.querySelectorAll("#findings .finding")) {
        if (card.dataset.identity !== findingIdentity(finding)) continue;
        const location = document.createElement(located ? "button" : "p"); location.className = "finding-location";
        if (located) { location.type = "button"; location.textContent = "Locate on figure"; location.onclick = () => select(index); }
        else { location.classList.add("muted"); location.textContent = "Location unavailable for this check."; }
        card.append(location);
      }
    }
    $("show-diagnostics").disabled = !findings.length;
    position();
  }
  return {clear, hide, mount};
}
