export function createPresentationPreview(root, api) {
  const get = id => root.querySelector("#" + id);
  const status = get("presentation-status"), content = get("presentation-content");
  const select = get("presentation-layout"), metrics = get("presentation-measurements");
  const image = get("presentation-image"), sheet = root.querySelector(".presentation-sheet");
  let selected, result, generation = 0;
  const number = value => value.toFixed(1);

  function place() {
    const layout = result.layouts[select.value];
    const [pageWidth, pageHeight] = layout.page_mm;
    const [left, top, width, height] = layout.placed_mm;
    sheet.dataset.layout = select.value;
    sheet.style.setProperty("--page-ratio", pageWidth + " / " + pageHeight);
    for (const [key, value, dimension] of [
      ["x", left, pageWidth], ["y", top, pageHeight],
      ["width", width, pageWidth], ["height", height, pageHeight],
    ]) {
      sheet.style.setProperty("--image-" + key, value * 100 / dimension + "%");
    }
    const slide = select.value === "slide";
    get("presentation-heading").textContent = slide ? "Research presentation" : "Research manuscript";
    get("presentation-subheading").textContent = slide ? "Results · widescreen slide" : "Results · sample page context";
    const messages = ["Figure placement " + number(width) + " × " + number(height) + " mm."];
    if (layout.height_limited) messages.push("Reduced to fit the available height.");
    if (layout.minimum_text_pt !== null) {
      const scope = result.text.status === "partial" ? "in measured PDF text" : "in extractable PDF text";
      messages.push("Smallest measured text " + number(layout.minimum_text_pt) + " pt " + scope + ".");
    } else {
      messages.push("Physical text size is unavailable for this export.");
    }
    if (layout.raster_dpi) messages.push("Effective raster resolution " + layout.raster_dpi.map(number).join(" × ") + " DPI.");
    metrics.textContent = messages.join(" ");
  }

  async function load() {
    if (!selected || !root.open) return;
    const version = ++generation;
    status.textContent = "Preparing the saved figure…";
    try {
      const next = await api("/api/presentation?" + new URLSearchParams(selected));
      if (version !== generation) return;
      image.src = next.image;
      await image.decode();
      if (version !== generation) return;
      result = next;
      const previous = select.value;
      select.replaceChildren(...Object.entries(result.layouts).map(([key, layout]) => new Option(layout.label, key)));
      if (Object.hasOwn(result.layouts, previous)) select.value = previous;
      place();
      status.textContent = "Saved " + result.export.format.toUpperCase() + " · audit " + result.event +
        " · exit " + result.exit_code + ".";
      content.hidden = false;
    } catch (problem) {
      if (version === generation) status.textContent = problem.message;
    }
  }

  select.onchange = place;
  root.ontoggle = () => { if (root.open && !result) load(); };
  return {
    mount(next) {
      selected = next;
      result = undefined;
      generation++;
      content.hidden = true;
      root.hidden = !next;
      image.removeAttribute("src");
      if (next && root.open) load();
    },
  };
}
