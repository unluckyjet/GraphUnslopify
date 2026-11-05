/** Select actual rendered cells in the local editor and verify their evidence. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { Page } from "playwright";

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
  const proof = {
    passed: true,
    workflows: [
      "opt-in trace with private graph download and exact generated Python",
      "same independently recomputed Iris cell via keyboard, desktop and narrow view",
      "scoped exclusions with paging and no late browser response after edit",
    ],
    cell: { id: node.id, estimate: mean, contributing: expected.length, display_widths: sizes },
    sha256: { source: hash(rawSource), image: binding.image.sha256, graph: reference.sha256 },
  };
  writeFileSync(join(evidence, "observation-explorer.json"), JSON.stringify(proof, null, 2) + "\n");
  return proof;
}
