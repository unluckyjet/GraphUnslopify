/** Select actual rendered cells in the local editor and verify their evidence. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { Page, Response } from "playwright";

declare const document: {
  querySelector(selector: string): { complete: boolean; textContent: string; dataset: { runId?: string } } | null;
};

export async function checkObservations(page: Page, evidence: string) {
  const fixture = resolve("examples/published-papers/data/iris-long.csv");
  const rawSource = readFileSync(fixture);
  const hash = (raw: Buffer) => createHash("sha256").update(raw).digest("hex");
  const spec = {
    kind: "heatmap",
    x: { field: "measurement", label: "Measurement" },
    y: { field: "species", label: "Species" },
    value: "value",
    value_label: "Mean (cm)",
    aggregation: "mean",
    annotate_cells: true,
    filter: [{ field: "measurement", op: "ne", value: "sepal width" }],
    output: { stem: "iris-observations", formats: ["png"], dpi: 300, size: "double_column" },
  };
  const watch = (route: string) => page.waitForResponse(
    response => new URL(response.url()).pathname === route && response.request().method() === "POST",
  );
  const click = async (id: string, route: string) => {
    const [response] = await Promise.all([watch(route), page.locator("#" + id).click()]);
    if (!response.ok()) assert.fail(await response.text());
    return response;
  };
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.locator("#live").uncheck();
  const [upload] = await Promise.all([
    watch("/api/upload"), page.locator("#data-file").setInputFiles(fixture),
  ]);
  assert.ok(upload.ok());
  await page.waitForFunction(() => document.querySelector("#data-summary")?.textContent.startsWith("iris-long.csv"));
  await page.locator("#advanced").evaluate(node => node.setAttribute("open", ""));
  await page.locator("#spec").fill(JSON.stringify(spec));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  const render = async (id: string) => {
    const response = await click(id, "/api/render");
    const result = await response.json();
    assert.equal(result.exit_code, 0, JSON.stringify(result.report.findings));
    await page.waitForFunction(run => {
      const image = document.querySelector("#preview");
      return image !== null && image.dataset.runId === run && image.complete;
    }, result.run_id);
    return result;
  };
  const ordinary = await render("render");
  assert.equal(ordinary.observations, undefined);
  assert.equal(ordinary.report.observation_selection, undefined);
  const traced = await render("trace-observations");
  const reference = traced.report.observation_selection;
  const binding = traced.observations;
  const panel = page.locator("#observation-explorer");
  const image = page.locator("#preview");
  await panel.waitFor();
  assert.ok(binding.available);
  assert.deepEqual(binding.grids, [{ rows: 3, columns: 3 }]);
  const source = await image.getAttribute("src");
  const prefix = "data:image/png;base64,";
  assert.ok(source && source.startsWith(prefix));
  assert.equal(hash(Buffer.from(source.slice(prefix.length), "base64")), binding.image.sha256);

  const [download] = await Promise.all([
    page.waitForEvent("download"), page.locator("#observation-graph").click(),
  ]);
  const downloaded = await download.path();
  assert.ok(downloaded);
  const rawGraph = readFileSync(downloaded);
  assert.equal(hash(rawGraph), reference.sha256);
  assert.ok(traced.files.every((file: {name: string}) => file.name !== reference.path));
  const graph = JSON.parse(rawGraph.toString());
  assert.equal(graph.source.snapshot_sha256, hash(rawSource));
  const placement = graph.nodes.find((node: {id: string}) => node.id === reference.matrix_geometry_node_id);
  const [grid] = placement.metadata.grids;
  const x = (grid.x_edges[0] + grid.x_edges[1]) / 2;
  const y = (grid.y_edges[0] + grid.y_edges[1]) / 2;
  const route = "/api/observations/query";
  const selected = (await (await click("observation-pick", route)).json()).selection;
  const node = selected.node;
  assert.equal(node.operation, "matrix_cell");
  const expected = rawSource.toString().trim().split(/\r?\n/).slice(1).flatMap((line, index) => {
    const [measurement, value, species] = line.split(",");
    return measurement === node.metadata.column_label && species === node.metadata.row_label
      ? [{ index, value: Number(value) }] : [];
  });
  assert.equal(expected.length, 50);
  assert.deepEqual(selected.contributing_records.items, expected.map(row => row.index));
  const mean = expected.reduce((sum, row) => sum + row.value, 0) / expected.length;
  assert.ok(Math.abs(node.value - mean) < 1e-12);

  const sizes: number[] = [];
  for (const width of [1500, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const box = await image.boundingBox();
    assert.ok(box);
    sizes.push(box.width);
    const position = { x: x * box.width / binding.image.width, y: y * box.height / binding.image.height };
    const [response] = await Promise.all([watch(route), image.click({ position })]);
    assert.equal((await response.json()).selection.node.id, node.id);
  }
  assert.notEqual(sizes[0], sizes[1]);
  const filters = (await (await click("observation-filters", route)).json()).selection;
  assert.equal(filters.contributing_records.total, 450);
  assert.equal(filters.excluded_records.total, 150);
  const next = (await (await click("observation-next", route)).json()).selection;
  assert.deepEqual(next.excluded_records.items, Array.from({ length: 50 }, (_, i) => 4 * (50 + i) + 1));
  await click("observation-program", "/api/observations/download");
  const program = page.locator("#observation-code");
  await program.waitFor();
  assert.equal(hash(Buffer.from(await program.textContent() || "")), traced.report.script.sha256);

  let release = () => {};
  let observe = (_status: number) => {};
  let refuse = (_error: unknown) => {};
  const held = new Promise<number>((resolve, reject) => { observe = resolve; refuse = reject; });
  const resume = new Promise<void>(done => { release = done; });
  await page.route("**" + route, async intercepted => {
    try {
      const response = await intercepted.fetch();
      observe(response.status());
      await resume;
      await intercepted.fulfill({ response });
    } catch (error) {
      refuse(error);
      throw error;
    }
  }, { times: 1 });
  const late = watch(route);
  try {
    await page.locator("#observation-pick").click();
    assert.equal(await held, 200);
    await page.locator("#spec").fill(JSON.stringify({ ...spec, title: "Edited while inspecting" }));
    await panel.waitFor({ state: "hidden" });
  } finally {
    release();
  }
  await late;
  assert.equal(await page.locator("#observation-details").textContent(), "");
  await page.setViewportSize({ width: 1500, height: 1000 });
  assert.equal(hash(readFileSync(fixture)), hash(rawSource));
  const intervals = await checkLineIntervals(page, watch, click);
  const summaryCharts = await checkSummaryChartIntervals(page, watch, click);
  const rawLine = await checkRawLine(page, watch, click);
  const proof = {
    passed: true,
    intervals,
    summary_charts: summaryCharts,
    raw_line: rawLine,
    workflows: [
      "opt-in trace with private graph download and exact generated Python",
      "same independently recomputed Iris cell via keyboard, desktop and narrow view",
      "scoped exclusions with paging and no late browser response after edit",
      "the same public 90% interval from keyboard, stems and caps on desktop and narrow view",
      "a filled band span links both computed endpoints and an endpoint click selects its actual interval",
      "the same public PNG offers calculated line vertices and stroke connections independently of the uncertainty band",
      "the public smoothed curve and its unsmoothed overlay have independent keyboard and pixel targets",
      "grouped horizontal bar intervals follow reindexed categories and forest caps retain their own rows",
      "bar bodies and forest center dots select their estimates independently of intervals by keyboard and PNG position",
      "a bar without intervals opens the estimate picker directly",
      "an unaggregated line preserves quoted-record positions through temporal sorting and refuses coincident pixel selection",
    ],
    cell: { id: node.id, estimate: mean, contributing: expected.length, display_widths: sizes },
    sha256: { source: hash(rawSource), image: binding.image.sha256, graph: reference.sha256 },
  };
  writeFileSync(join(evidence, "observation-explorer.json"), JSON.stringify(proof, null, 2) + "\n");
  return proof;
}

async function checkLineIntervals(
  page: Page,
  watch: (route: string) => Promise<Response>,
  click: (id: string, route: string) => Promise<Response>,
) {
  const fixture = resolve("benchmarks/papers/sources/penguins.csv");
  const raw = readFileSync(fixture);
  const digest = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");
  const [uploaded] = await Promise.all([
    watch("/api/upload"), page.locator("#data-file").setInputFiles(fixture),
  ]);
  assert.ok(uploaded.ok());
  await page.waitForFunction(() => document.querySelector("#data-summary")?.textContent.startsWith("penguins.csv"));
  const spec = {
    kind: "line",
    x: { field: "year", label: "Year" },
    y: { field: "body_mass_g", label: "Body mass (g)" },
    filter: [{ field: "species", op: "eq", value: "Adelie" }, { field: "sex", op: "eq", value: "male" }],
    aggregation: "mean", marker: true,
    uncertainty: { kind: "ci", level: 0.9, display: "bar" },
    output: { stem: "public-ci", formats: ["png"], dpi: 300, size: "double_column" },
  };
  await page.locator("#spec").fill(JSON.stringify(spec));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  const rendered = await (await click("trace-observations", "/api/render")).json();
  assert.equal(rendered.report.status, "passed", JSON.stringify(rendered.report.findings));
  assert.equal(rendered.observations.intervals, 3);
  await page.locator("#observation-interval-picker").waitFor();
  assert.ok(await page.locator("#observation-cell-picker").isHidden());
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.locator("#observation-graph").click(),
  ]);
  const saved = await download.path();
  assert.ok(saved);
  const graphBytes = readFileSync(saved);
  const reference = rendered.report.observation_selection;
  assert.equal(digest(graphBytes), reference.sha256);
  const graph = JSON.parse(graphBytes.toString());
  assert.equal(graph.source.snapshot_sha256, digest(raw));
  const root = graph.nodes.find((node: { id: string }) => node.id === reference.summary_interval_geometry_node_id);
  const query = "/api/observations/query";
  const keyboard = (await (await click("observation-pick-interval", query)).json()).selection;
  assert.equal(keyboard.node.id, root.inputs[0]);
  assert.equal(keyboard.node.metadata.estimator, "ci");
  const year = keyboard.node.metadata.keys.year;
  const rows = raw.toString().trim().split(/\r?\n/).slice(1).flatMap((text, index) => {
    const fields = text.split(",");
    return fields[0] === "Adelie" && fields[6] === "male" && fields[7] === year ? [index] : [];
  });
  assert.deepEqual(keyboard.contributing_records.items, rows);

  const image = page.locator("#preview");
  const widths: number[] = [];
  for (const width of [1500, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const box = await image.boundingBox();
    assert.ok(box);
    widths.push(box.width);
    for (const role of ["stem", "cap"]) {
      const stroke = root.metadata.strokes.find((item: { node_id: string; role: string }) =>
        item.node_id === keyboard.node.id && item.role === role);
      const x = (stroke.endpoints[0][0] + stroke.endpoints[1][0]) / 2;
      const y = (stroke.endpoints[0][1] + stroke.endpoints[1][1]) / 2;
      const position: { x: number; y: number } = {
        x: x * box.width / rendered.observations.image.width,
        y: y * box.height / rendered.observations.image.height,
      };
      const [response] = await Promise.all([watch(query), image.click({ position })]);
      assert.equal((await response.json()).selection?.node.id, keyboard.node.id);
    }
  }
  assert.notEqual(widths[0], widths[1]);
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.locator("#spec").fill(JSON.stringify({ ...spec, uncertainty: { ...spec.uncertainty, display: "band" } }));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  const band = await (await click("trace-observations", "/api/render")).json();
  assert.equal(band.report.status, "passed", JSON.stringify(band.report.findings));
  assert.ok(band.observations.band);
  assert.equal(band.observations.intervals, 3);
  const [bandDownload] = await Promise.all([
    page.waitForEvent("download"), page.locator("#observation-graph").click(),
  ]);
  const bandPath = await bandDownload.path();
  assert.ok(bandPath);
  const bandBytes = readFileSync(bandPath);
  const bandRef = band.report.observation_selection;
  assert.equal(digest(bandBytes), bandRef.sha256);
  const bandGraph = JSON.parse(bandBytes.toString());
  assert.equal(bandGraph.source.snapshot_sha256, digest(raw));
  const bandRoot = bandGraph.nodes.find((node: { id: string }) => node.id === bandRef.summary_interval_geometry_node_id);
  assert.equal(bandRoot.metadata.bands.length, 2);
  const [strip] = bandRoot.metadata.bands;
  const bandYears = strip.interval_ids.map((identity: string) =>
    bandGraph.nodes.find((node: { id: string }) => node.id === identity).metadata.keys.year);
  assert.deepEqual(bandYears, ["2007", "2008"]);
  const bandRows = raw.toString().trim().split(/\r?\n/).slice(1).flatMap((line, index) => {
    const columns = line.split(",");
    return columns[0] === "Adelie" && columns[6] === "male" && bandYears.includes(columns[7] ?? "") ? [index] : [];
  });
  const [low, high, nextLow, nextHigh] = strip.endpoints;
  const interior: [number, number] = [(low[0] + nextLow[0]) / 2,
    (low[1] + high[1] + nextLow[1] + nextHigh[1]) / 4];
  const endpoint: [number, number] = [low[0], (low[1] + high[1]) / 2];
  for (const width of [1500, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const box = await image.boundingBox();
    assert.ok(box);
    for (const [point, target] of [[interior, strip.node_id], [endpoint, strip.interval_ids[0]]] as const) {
      const position: { x: number; y: number } = {
        x: point[0] * box.width / band.observations.image.width,
        y: point[1] * box.height / band.observations.image.height,
      };
      const [response] = await Promise.all([watch(query), image.click({ position })]);
      const selected = (await response.json()).selection;
      assert.equal(selected.node.id, target);
      if (target === strip.node_id) {
        assert.equal(selected.node.operation, "summary_band_span");
        assert.equal(selected.node.value, null);
        assert.deepEqual(selected.inputs.items.map((item: { id: string }) => item.id), strip.interval_ids);
        assert.deepEqual(selected.contributing_records.items, bandRows);
        await page.getByText(/The renderer joins the two calculated bounds/).waitFor();
      }
    }
  }
  const curve = bandGraph.nodes.find((node: { id: string }) => node.id === bandRef.summary_estimate_geometry_node_id);
  assert.deepEqual(curve.metadata.image, bandRoot.metadata.image);
  assert.equal(band.observations.estimates, 5);
  const [vertex] = curve.metadata.estimates;
  const segment = curve.metadata.estimates.find((mark: { kind: string }) => mark.kind === "segment");
  assert.equal(vertex.kind, "dot");
  assert.equal(vertex.node_id, segment.endpoint_ids[0]);
  const firstYear = bandGraph.nodes.find((node: { id: string }) => node.id === vertex.node_id).metadata.keys.year;
  assert.equal(firstYear, "2007");
  const masses = raw.toString().trim().split(/\r?\n/).slice(1).flatMap((line, index) => {
    const fields = line.split(",");
    return fields[0] === "Adelie" && fields[6] === "male" && fields[7] === firstYear
      ? [{ index, grams: Number(fields[5]) }] : [];
  });
  const mean = masses.reduce((total, row) => total + row.grams, 0) / masses.length;
  await page.locator("#observation-summary-mode").selectOption("estimate");
  const estimate = (await (await click("observation-pick-estimate", query)).json()).selection;
  assert.equal(estimate.node.id, vertex.node_id);
  assert.equal(estimate.node.value, mean);
  assert.deepEqual(estimate.contributing_records.items, masses.map(row => row.index));
  const segmentPoint: [number, number] = [
    (segment.endpoints[0][0] + segment.endpoints[1][0]) / 2,
    (segment.endpoints[0][1] + segment.endpoints[1][1]) / 2,
  ];
  for (const width of [390, 1500]) {
    await page.setViewportSize({ width, height: 1000 });
    const box = await image.boundingBox();
    assert.ok(box);
    const targets: [[number, number], string][] = [[vertex.center, vertex.node_id], [segmentPoint, segment.node_id]];
    for (const [point, identity] of targets) {
      const position: { x: number; y: number } = {
        x: point[0] * box.width / band.observations.image.width,
        y: point[1] * box.height / band.observations.image.height,
      };
      const [response] = await Promise.all([watch(query), image.click({ position })]);
      const selected = (await response.json()).selection;
      assert.equal(selected.node.id, identity);
      if (identity === segment.node_id) {
        assert.equal(selected.node.operation, "summary_line_span");
        assert.equal(selected.node.value, null);
        assert.deepEqual(selected.inputs.items.map((item: { id: string }) => item.id), segment.endpoint_ids);
        assert.deepEqual(selected.contributing_records.items, bandRows);
        await page.getByText(/The stroke connects two plotted values/).waitFor();
      }
    }
  }
  await page.locator("#spec").fill(JSON.stringify({
    ...spec,
    uncertainty: undefined,
    smooth: { kind: "rolling", window: 3, show_raw: true },
    output: { ...spec.output, stem: "smoothed" },
  }));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  const smoothRender = await (await click("trace-observations", "/api/render")).json();
  assert.equal(smoothRender.report.status, "passed", JSON.stringify(smoothRender.report.findings));
  assert.equal(smoothRender.observations.intervals, 0);
  assert.deepEqual(smoothRender.observations.estimate_curves, { smoothed: 5, raw: 5 });
  await page.locator("#observation-estimate-curve-label").waitFor();
  const rolePicker = page.locator("#observation-estimate-curve");
  assert.equal(await rolePicker.inputValue(), "smoothed");
  const [smoothDownload] = await Promise.all([
    page.waitForEvent("download"), page.locator("#observation-graph").click(),
  ]);
  const smoothPath = await smoothDownload.path();
  assert.ok(smoothPath);
  const smoothBytes = readFileSync(smoothPath);
  const smoothRef = smoothRender.report.observation_selection;
  assert.equal(digest(smoothBytes), smoothRef.sha256);
  const smoothGraph = JSON.parse(smoothBytes.toString());
  const smoothGeometry = smoothGraph.nodes.find((node: { id: string }) => node.id === smoothRef.summary_estimate_geometry_node_id);
  const nextMasses = raw.toString().trim().split(/\r?\n/).slice(1).flatMap(line => {
    const fields = line.split(",");
    return fields[0] === "Adelie" && fields[6] === "male" && fields[7] === "2008" ? [Number(fields[5])] : [];
  });
  const nextMean = nextMasses.reduce((total, value) => total + value, 0) / nextMasses.length;
  const expectedSmooth = (mean + nextMean) / 2;
  const expectedRoles = [
    { role: "smoothed", operation: "summary_smoothed_estimate", value: expectedSmooth, records: bandRows },
    { role: "raw", operation: "summary_estimate", value: mean, records: masses.map(row => row.index) },
  ];
  for (const expected of expectedRoles) {
    await rolePicker.selectOption(expected.role);
    const chosen = (await (await click("observation-pick-estimate", query)).json()).selection;
    const mark = smoothGeometry.metadata.estimates.find((item: { curve: string }) => item.curve === expected.role);
    assert.equal(chosen.node.id, mark.node_id);
    assert.equal(chosen.node.operation, expected.operation);
    assert.equal(chosen.node.value, expected.value);
    assert.deepEqual(chosen.contributing_records.items, expected.records);
    if (expected.role === "smoothed") {
      assert.equal(chosen.node.metadata.window, 3);
      assert.equal(chosen.node.metadata.estimator, "centered_rolling_mean");
    }
    for (const width of [1500, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      const box = await image.boundingBox();
      assert.ok(box);
      const position = {
        x: mark.center[0] * box.width / smoothRender.observations.image.width,
        y: mark.center[1] * box.height / smoothRender.observations.image.height,
      };
      const [response] = await Promise.all([watch(query), image.click({ position })]);
      assert.equal((await response.json()).selection?.node.id, chosen.node.id);
    }
  }
  await page.setViewportSize({ width: 1500, height: 1000 });
  assert.equal(digest(readFileSync(fixture)), digest(raw));
  return { year, bounds: keyboard.node.value, contributors: rows.length, display_widths: widths,
    band: { endpoint_years: bandYears, contributors: bandRows.length, linked_calculations: 2 },
    estimate: { year: firstYear, mean, contributors: masses.length, connection_contributors: bandRows.length },
    smoothing: { smoothed: expectedSmooth, raw: mean, smoothed_records: bandRows.length, raw_records: masses.length } };
}

async function checkSummaryChartIntervals(
  page: Page,
  watch: (route: string) => Promise<Response>,
  click: (id: string, route: string) => Promise<Response>,
) {
  const source = Buffer.from(
    "category,method,score\nb,ours,6\na,other,10\nc,ours,20\nb,ours,8\n"
    + "a,other,14\nc,ours,24\nc,other,30\nc,other,32\n",
  );
  const [uploaded] = await Promise.all([
    watch("/api/upload"),
    page.locator("#data-file").setInputFiles({ name: "summary-methods.csv", mimeType: "text/csv", buffer: source }),
  ]);
  assert.ok(uploaded.ok());
  await page.waitForFunction(() => document.querySelector("#data-summary")?.textContent.startsWith("summary-methods.csv"));
  const specifications = [
    { kind: "bar", group: "method", orientation: "horizontal", interval_count: 4 },
    { kind: "forest", interval_count: 3 },
  ];
  const proved = [];
  for (const { interval_count, ...specification } of specifications) {
    await page.locator("#spec").fill(JSON.stringify({
      ...specification,
      x: { field: "category", label: "Condition" },
      y: { field: "score", label: "Score" },
      category_order: ["c", "a", "b"],
      aggregation: "mean",
      uncertainty: { kind: "range", display: "bar" },
      output: { stem: specification.kind + "-intervals", formats: ["png"], dpi: 300, size: "double_column" },
    }));
    await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
    const result = await (await click("trace-observations", "/api/render")).json();
    assert.equal(result.report.status, "passed", JSON.stringify(result.report.findings));
    assert.equal(result.observations.intervals, interval_count);
    await page.locator("#observation-interval-picker").waitFor();
    const [download] = await Promise.all([
      page.waitForEvent("download"), page.locator("#observation-graph").click(),
    ]);
    const saved = await download.path();
    assert.ok(saved);
    const bytes = readFileSync(saved);
    const reference = result.report.observation_selection;
    assert.equal(createHash("sha256").update(bytes).digest("hex"), reference.sha256);
    const graph = JSON.parse(bytes.toString());
    assert.equal(graph.source.snapshot_sha256, createHash("sha256").update(source).digest("hex"));
    const root = graph.nodes.find((entry: { id: string }) => entry.id === reference.summary_interval_geometry_node_id);
    const query = "/api/observations/query";
    const selected = (await (await click("observation-pick-interval", query)).json()).selection;
    assert.equal(selected.node.id, root.inputs[0]);
    const { category, method } = selected.node.metadata.keys;
    const rows = source.toString().trim().split("\n").slice(1).flatMap((row, index) => {
      const [name, family, score] = row.split(",");
      return name === category && (method === undefined || family === method) ? [{ index, score: Number(score) }] : [];
    });
    assert.deepEqual(selected.contributing_records.items, rows.map(row => row.index));
    const scores = rows.map(row => row.score);
    assert.deepEqual(selected.node.value, [Math.min(...scores), Math.max(...scores)]);
    await page.setViewportSize({ width: 390, height: 1000 });
    const image = page.locator("#preview");
    const box = await image.boundingBox();
    assert.ok(box);
    for (const role of ["cap", "stem"]) {
      const stroke = root.metadata.strokes.find((entry: { node_id: string; role: string }) =>
        entry.node_id === selected.node.id && entry.role === role);
      const x = (stroke.endpoints[0][0] + stroke.endpoints[1][0]) / 2;
      const y = (stroke.endpoints[0][1] + stroke.endpoints[1][1]) / 2;
      const position: { x: number; y: number } = {
        x: x * box.width / result.observations.image.width,
        y: y * box.height / result.observations.image.height,
      };
      const [response] = await Promise.all([watch(query), image.click({ position })]);
      assert.equal((await response.json()).selection?.node.id, selected.node.id);
    }
    assert.equal(result.observations.estimates, interval_count);
    const estimateRoot = graph.nodes.find((entry: { id: string }) => entry.id === reference.summary_estimate_geometry_node_id);
    assert.deepEqual(estimateRoot.metadata.image, root.metadata.image);
    await page.locator("#observation-summary-mode").selectOption("estimate");
    const estimate = (await (await click("observation-pick-estimate", query)).json()).selection;
    assert.equal(estimate.node.id, estimateRoot.inputs[0]);
    assert.equal(estimate.node.operation, "summary_estimate");
    const estimateKeys = estimate.node.metadata.keys;
    const contributing = source.toString().trim().split("\n").slice(1).flatMap((line, index) => {
      const [name, family, score] = line.split(",");
      return name === estimateKeys.category && (estimateKeys.method === undefined || family === estimateKeys.method)
        ? [{ index, score: Number(score) }] : [];
    });
    assert.deepEqual(estimate.contributing_records.items, contributing.map(row => row.index));
    assert.equal(estimate.node.value, contributing.reduce((total, row) => total + row.score, 0) / contributing.length);
    const mark = estimateRoot.metadata.estimates[0];
    assert.equal(mark.node_id, estimate.node.id);
    assert.equal(mark.kind, specification.kind === "bar" ? "bar" : "dot");
    const [x, y] = mark.kind === "dot" ? mark.center
      : [(mark.bounds[0] + mark.bounds[2]) / 2, (mark.bounds[1] + mark.bounds[3]) / 2];
    for (const width of [390, 1500]) {
      await page.setViewportSize({ width, height: 1000 });
      const estimateBox = await image.boundingBox();
      assert.ok(estimateBox);
      const position = {
        x: x * estimateBox.width / result.observations.image.width,
        y: y * estimateBox.height / result.observations.image.height,
      };
      const [response] = await Promise.all([watch(query), image.click({ position })]);
      const picked = (await response.json()).selection;
      assert.equal(picked?.node.id, estimate.node.id);
      assert.notEqual(picked.node.id, selected.node.id);
    }
    proved.push({
      kind: specification.kind, interval_count,
      picked: { category, method, bounds: selected.node.value, records: rows.length },
      estimate: { keys: estimateKeys, value: estimate.node.value, records: contributing.length },
    });
  }
  await page.locator("#spec").fill(JSON.stringify({
    kind: "bar",
    x: { field: "category", label: "Condition" },
    y: { field: "score", label: "Total score" },
    aggregation: "sum",
    output: { stem: "totals", formats: ["png"], dpi: 300, size: "double_column" },
  }));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  const totals = await (await click("trace-observations", "/api/render")).json();
  assert.equal(totals.report.status, "passed", JSON.stringify(totals.report.findings));
  assert.equal(totals.observations.intervals, 0);
  assert.equal(totals.observations.estimates, 3);
  await page.locator("#observation-estimate-picker").waitFor();
  assert.ok(await page.locator("#observation-summary-mode-label").isHidden());
  const selected = (await (await click("observation-pick-estimate", "/api/observations/query")).json()).selection;
  const category = selected.node.metadata.keys.category;
  const records = source.toString().trim().split("\n").slice(1).flatMap((line, index) => {
    const [name, , score] = line.split(",");
    return name === category ? [{ index, score: Number(score) }] : [];
  });
  assert.deepEqual(selected.contributing_records.items, records.map(record => record.index));
  assert.equal(selected.node.value, records.reduce((total, record) => total + record.score, 0));
  proved.push({ kind: "bar without intervals", estimate: { keys: selected.node.metadata.keys, value: selected.node.value, records: records.length } });
  return proved;
}


async function checkRawLine(
  page: Page,
  watch: (route: string) => Promise<Response>,
  click: (id: string, route: string) => Promise<Response>,
) {
  const raw = Buffer.from(
    'day,y,notes,selected\n2026-01-03,40,"two\nlines",yes\n2026-01-01,10,first,yes\n'
    + "2026-01-02,20,one,yes\n2026-01-02,20,two,yes\n2026-01-04,99,no,no\n",
  );
  const [uploaded] = await Promise.all([
    watch("/api/upload"),
    page.locator("#data-file").setInputFiles({ name: "raw-observations.csv", mimeType: "text/csv", buffer: raw }),
  ]);
  assert.ok(uploaded.ok());
  await page.waitForFunction(() => document.querySelector("#data-summary")?.textContent.startsWith("raw-observations.csv"));
  await page.locator("#spec").fill(JSON.stringify({
    kind: "line",
    x: { field: "day", label: "Date", temporal: true },
    y: { field: "y", label: "Response" },
    marker: true,
    filter: [{ field: "selected", op: "eq", value: "yes" }],
    output: { stem: "raw-positions", formats: ["png"], dpi: 300, size: "double_column" },
  }));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  const result = await (await click("trace-observations", "/api/render")).json();
  assert.ok(result.observations.available, JSON.stringify(result.observations));
  assert.equal(result.observations.intervals, 0);
  await page.locator("#observation-estimate-picker").waitFor();
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.locator("#observation-graph").click(),
  ]);
  const path = await download.path();
  assert.ok(path);
  const bytes = readFileSync(path);
  const reference = result.report.observation_selection;
  assert.equal(createHash("sha256").update(bytes).digest("hex"), reference.sha256);
  const graph = JSON.parse(bytes.toString());
  assert.equal(graph.source.snapshot_sha256, createHash("sha256").update(raw).digest("hex"));
  const root = graph.nodes.find((node: { id: string }) => node.id === reference.summary_estimate_geometry_node_id);
  const query = "/api/observations/query";
  const ordinals: number[] = [];
  for (const number of [1, 2, 3, 4]) {
    await page.locator("#observation-estimate-index").fill(String(number));
    const found = (await (await click("observation-pick-estimate", query)).json()).selection;
    assert.equal(found.node.operation, "line_observation");
    assert.equal(found.node.id, root.metadata.estimates[number - 1].node_id);
    assert.equal(found.contributing_records.items.length, 1);
    ordinals.push(found.contributing_records.items[0]);
  }
  assert.equal(ordinals[0], 1);
  assert.equal(ordinals[3], 0);
  assert.deepEqual(ordinals.slice(1, 3).sort(), [2, 3]);
  assert.deepEqual(root.metadata.estimates[1].center, root.metadata.estimates[2].center);
  const image = page.locator("#preview");
  await page.setViewportSize({ width: 390, height: 1000 });
  const box = await image.boundingBox();
  assert.ok(box);
  for (const index of [1, 3]) {
    const mark = root.metadata.estimates[index];
    const position: { x: number; y: number } = {
      x: mark.center[0] * box.width / result.observations.image.width,
      y: mark.center[1] * box.height / result.observations.image.height,
    };
    const [response] = await Promise.all([watch(query), image.click({ position })]);
    if (index === 1) {
      assert.equal(response.status(), 400);
      await page.getByText(/More than one observation estimate/).waitFor();
    } else {
      const found = (await response.json()).selection;
      assert.equal(found.node.id, mark.node_id);
      assert.deepEqual(found.contributing_records.items, [0]);
    }
  }
  await page.setViewportSize({ width: 1500, height: 1000 });
  const filtered = (await (await click("observation-filters", query)).json()).selection;
  assert.deepEqual(filtered.excluded_records.items, [4]);
  return { plotted_records: ordinals, excluded_record: 4, overlap_refused: true };
}
