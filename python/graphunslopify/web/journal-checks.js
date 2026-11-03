// Dated journal evidence belongs to one owned export and one editor selection.
export function createJournalChecks(root, { api, current, reviewPdf }) {
  const node = (tag, text, parent = root) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    parent.append(element);
    return element;
  };
  const details = node("details"); details.className = "journal-checks";
  node("summary", "Journal technical checks", details);
  node("p", "Check a saved export against dated publisher guidance. Scientific verification and full submission readiness remain separate.", details).className = "muted";
  const field = (label, tag, id) => {
    const wrapper = node("label", label, details);
    const input = node(tag, undefined, wrapper); input.id = id;
    return input;
  };
  const profile = field("Journal and submission stage", "select", "journal-profile");
  const policy = node("p", "Choose a profile to see its scope and source date.", details);
  policy.className = "muted";
  const file = field("Export to inspect", "select", "journal-file");
  const width = field("Optional author target width (mm)", "input", "journal-width");
  width.type = "number"; width.min = "0.000001"; width.step = "any";
  node("p", "Width targets are your explicit choice, with a 0.5 mm tolerance. Standard journal widths can be guidance rather than mandatory sizes.", details).className = "muted";
  const button = node("button", "Check this export", details);
  button.id = "journal-check"; button.type = "button";
  button.disabled = true; file.disabled = true;
  const status = node("p", "Render or choose a saved export first.", details);
  status.id = "journal-status"; status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const findings = node("div", undefined, details); findings.id = "journal-findings";
  const correction = node("button", "Review adding a PDF export", details);
  correction.id = "journal-review-pdf"; correction.type = "button"; correction.hidden = true;
  const correctionNote = node("p", "", details); correctionNote.className = "muted";
  let profiles = [], source = null, version = 0, pending = false, download = null;
  let lastIdentity = null;
  const selectedProfile = () => profiles.find(item => item.id === profile.value);
  const live = () => { const key = current(); return source && typeof key === "string" && source.key === key; };
  const validWidth = () => !width.value || (width.validity.valid && Number.isFinite(Number(width.value)) && Number(width.value) > 0);
  const number = value => Number(value.toPrecision(6)).toString();
  function measured(check) {
    const value = check.actual;
    if (value && typeof value === "object" && Number.isFinite(value.width_in) && Number.isFinite(value.height_in))
      return `${number(value.width_in * 25.4)} × ${number(value.height_in * 25.4)} mm; ${value.pages} page(s)`;
    if (check.code === "requested_width" && typeof value === "number") return number(value) + " mm";
    if (check.code === "raster_resolution" && Array.isArray(value)) return value.map(number).join(" × ") + " DPI";
    if (check.code === "pdf_text_minimum" && value)
      return `${value.characters_measured} measured characters; minimum ${value.minimum_pt === null ? "unknown" : number(value.minimum_pt) + " pt"}; ${value.characters_below_threshold} below threshold`;
    if (value === null) return "Not established";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "number") return number(value);
    return typeof value === "string" ? value : JSON.stringify(value);
  }
  function enabled() {
    file.disabled = !live();
    button.disabled = pending || !live() || !selectedProfile() || !file.value || !validWidth();
  }
  function discard(message = "Check again for this selection.") {
    version++; pending = false;
    if (download) URL.revokeObjectURL(download);
    download = null;
    findings.replaceChildren();
    correction.hidden = true; correctionNote.textContent = "";
    status.textContent = message; delete status.dataset.state;
    enabled();
  }
  function showPolicy() {
    policy.replaceChildren();
    const item = selectedProfile();
    if (!item) { policy.textContent = "Choose a profile to see its scope and source date."; return; }
    node("span", `${item.stage}. Policy checked ${item.checked_utc_date} UTC; review window ${item.review_after_days} days. `, policy);
    const link = node("a", "Official guidance", policy);
    link.href = item.source_url; link.target = "_blank"; link.rel = "noopener noreferrer";
    node("span", ` ${item.source_access}.`, policy);
  }
  profile.onchange = () => { showPolicy(); discard(); };
  file.onchange = () => discard();
  width.oninput = () => discard(validWidth() ? undefined : "Enter a finite positive width in millimetres.");
  button.onclick = async () => {
    if (button.disabled) return;
    discard("Inspecting recorded export bytes…");
    const captured = version, snapshot = source, identity = current();
    const selected = snapshot.files[Number(file.value) - 1];
    pending = true; enabled();
    try {
      const response = await api("/api/journal-check", {
        ...selected.payload, profile: profile.value,
        ...(width.value ? { target_width_mm: Number(width.value) } : {}),
      });
      if (captured !== version || identity !== current() || source !== snapshot) return;
      if (response.context?.current_generation === false)
        throw Error("A newer render exists. Render and check the current export again.");
      const report = response.report;
      if (report?.kind !== "graphunslopify.journal-check" || !Array.isArray(report.checks))
        throw Error("Journal evidence could not be read.");
      const labels = { passed: "Supported technical checks passed", failed: "Technical checks failed", incomplete: "Technical evidence incomplete" };
      status.textContent = labels[report.status] || "Technical result unavailable";
      status.dataset.state = report.status;
      node("p", response.context.scope, findings).className = "muted";
      node("p", `Inspected SHA256: ${report.source.sha256}`, findings).className = "journal-digest";
      node("p", `Policy SHA256: ${report.profile_sha256}; checked as of ${report.as_of} UTC.`, findings).className = "journal-digest";
      const list = node("ul", undefined, findings);
      for (const check of report.checks) {
        const row = node("li", undefined, list);
        node("strong", `${check.status.toUpperCase()} · ${check.code.replaceAll("_", " ")}`, row);
        node("p", check.message, row);
        node("p", `Observed: ${measured(check)}. Requirement: ${JSON.stringify(check.requirement)}.`, row).className = "muted";
      }
      node("h4", "Manual review still required", findings);
      const manual = node("ul", undefined, findings);
      for (const gap of report.manual_review) node("li", gap, manual);
      node("p", "Scientific verification was not performed by this check. Full submission readiness is unknown.", findings).className = "muted";
      const formatFailure = report.checks.find(check => check.code === "file_format" && check.status === "failed");
      if (formatFailure && report.profile.id === "nature-final-graphs") {
        const pdf = snapshot.files.findIndex(item => item.name.endsWith(".pdf"));
        if (pdf >= 0) {
          const choose = node("button", "Choose the saved PDF for checking", findings); choose.type = "button";
          choose.onclick = () => { file.value = String(pdf + 1); discard("PDF selected; check its actual bytes before accepting technical results."); };
        } else if (reviewPdf) {
          correction.hidden = false;
          correctionNote.textContent = "Review the format change before applying. A new render or saved paper audit is required before checking the PDF.";
        }
      }
      download = URL.createObjectURL(new Blob([JSON.stringify(response, null, 2) + "\n"], { type: "application/json" }));
      const link = node("a", "Download this journal report", findings);
      link.href = download; link.download = "journal-check.json"; link.className = "download";
    } catch (problem) {
      if (captured !== version || identity !== current()) return;
      status.textContent = problem.message; status.dataset.state = "incomplete";
    } finally {
      if (captured === version) { pending = false; enabled(); }
    }
  };
  correction.onclick = async () => {
    if (!live()) return;
    const identity = current(), captured = version; correction.disabled = true;
    try { await reviewPdf(() => captured === version && identity === current() && live()); }
    catch (problem) { if (identity === current()) correctionNote.textContent = problem.message; }
    finally { correction.disabled = false; }
  };
  function update() {
    const identity = current();
    if (identity !== lastIdentity) { lastIdentity = identity; discard("Editor selection changed; check its saved export again."); }
    enabled();
  }
  return {
    configure(items) {
      profiles = items || []; profile.replaceChildren(new Option("Choose journal profile", ""));
      for (const item of profiles) profile.add(new Option(item.name, item.id));
      showPolicy(); discard();
    },
    mount(snapshot) {
      source = snapshot; file.replaceChildren(new Option("Choose saved export", ""));
      snapshot.files.forEach((item, index) => file.add(new Option(item.name, String(index + 1))));
      if (snapshot.files.length) file.value = "1";
      lastIdentity = current(); discard("Choose a profile, then check this saved export.");
    },
    clear() { source = null; file.replaceChildren(); discard("Render or choose a saved export first."); },
    update,
  };
}
