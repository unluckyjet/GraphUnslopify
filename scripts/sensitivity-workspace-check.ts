/** Actual native comparison, author review and stale-input refusal in both editors. */
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Locator, type Page } from "playwright";
declare const document: { documentElement: { scrollWidth: number } };
declare const window: { innerWidth: number };

const interpreter = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED
  ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const evidence = mkdtempSync(join(tmpdir(), "gu-sensitivity-workspace-check-"));
const owners: ReturnType<typeof spawn>[] = [];
const errors: string[] = [], external: string[] = [], writes: string[] = [], workflows: string[] = [];
const route = "/api/sensitivity";
const sha = (value: string | Buffer) => createHash("sha256").update(value).digest("hex");
const raw = Buffer.from("x,arm,y,unit\n1,A,1,u1\n1,A,1,u2\n1,A,16,u3\n1,B,4,u1\n1,B,4,u2\n1,B,4,u3\n2,A,1,u1\n2,A,1,u2\n2,A,22,u3\n2,B,4,u1\n2,B,4,u2\n2,B,4,u3\n");
const spec = {
  kind: "line", title: "Two trial arms", aggregation: "mean", marker: true, group: "arm",
  x: { field: "x", label: "Time point" }, y: { field: "y", label: "Outcome" },
  data: { path: "source.csv", format: "csv" }, output: { dpi: 144, formats: ["png"] },
  claims: [{ kind: "beats_everywhere", subject: "A", reference: "B" }],
};
const name = "Median by arm", justification = "Check influence of an extreme measurement.";

async function serve(...args: string[]): Promise<string> {
  const child = spawn(interpreter, ["-m", "graphunslopify.cli", ...args, "--port", "0"], { env, stdio: ["ignore", "pipe", "pipe"] });
  owners.push(child);
  const lines = createInterface({ input: child.stdout });
  let stderr = "";
  child.stderr.on("data", part => { stderr += part; });
  const timeout = setTimeout(() => child.kill(), 30_000);
  try {
    return await new Promise((accept, reject) => {
      lines.once("line", line => {
        try { accept(JSON.parse(line).url); } catch (error) { reject(error); }
      });
      child.once("exit", code => reject(Error("Local workspace exited " + code + ": " + stderr)));
    });
  } finally {
    clearTimeout(timeout);
    lines.close();
  }
}
function cli(...args: string[]) {
  return execFileSync(interpreter, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 60_000 });
}
async function open(page: Page, url: string) {
  const origin = new URL(url).origin;
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (!/^(blob:|data:)/.test(request.url()) && new URL(request.url()).origin !== origin) external.push(request.url());
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && ["/api/render", "/api/run", "/api/definition", "/api/entry", "/api/shared-apply"].includes(path)) writes.push(path);
  });
  await page.goto(url);
  const panel = page.locator("#sensitivity-workspace");
  await panel.locator("summary").first().click();
  return panel;
}
async function review(page: Page, panel: Locator, fill = true) {
  if (fill) {
    await panel.getByLabel("Alternative name").first().fill(name);
    await panel.getByLabel("Statistical justification").first().fill(justification);
    await panel.getByLabel("Summary estimator").first().selectOption("median");
  }
  const reply = page.waitForResponse(response => response.url().endsWith(route));
  await panel.getByRole("button", { name: "Review alternatives" }).click();
  const response = await reply;
  assert.equal(response.status(), 200, await response.text());
  const report = await response.json();
  assert.equal(report.status, "review_required");
  assert.equal(report.source.sha256, sha(raw));
  assert.equal(report.choices[0].analysis.aggregation, "mean");
  assert.equal(report.choices[1].analysis.aggregation, "median");
  const render = panel.getByRole("button", { name: "Render reviewed comparison" });
  await render.waitFor();
  assert.equal(await render.isDisabled(), true);
  return { report, payload: response.request().postDataJSON(), render };
}
async function run(page: Page, panel: Locator, render: Locator, prefix: string, expectedCohort?: number) {
  await panel.getByRole("checkbox", { name: "I reviewed the statistical choices and assumptions" }).check();
  const reply = page.waitForResponse(response => response.url().endsWith(route));
  await render.click();
  const response = await reply;
  assert.equal(response.status(), 200, await response.text());
  const report = await response.json();
  assert.equal(report.status, "partial");
  assert.equal(report.choices[1].runtime_exit_code, 2);
  assert.deepEqual(report.choices[1].claim_comparison.map((row: {
    before: { verdict: string }, after: { verdict: string }, changed: boolean
  }) => [row.before.verdict, row.after.verdict, row.changed]), [["holds", "fails", true]]);
  const first = report.choices[1].comparison[0];
  assert.equal(first.before.estimate, 6);
  assert.equal(first.after.estimate, 1);
  assert.equal(first.difference, -5);
  if (expectedCohort !== undefined) {
    assert.equal(report.choices[2].counts.after_filter, expectedCohort);
    assert.equal(report.choices[2].comparison.filter((row: { after: unknown }) => row.after === null).length, 2);
  }
  const output = panel.getByRole("region", { name: "Sensitivity comparison results" });
  await output.getByText(/holds → fails/).waitFor();
  for (const [index, choice] of report.choices.entries()) {
    const actual = await output.getByRole("img", { name: choice.label + " native figure" }).getAttribute("src");
    assert.ok(actual && actual.startsWith("data:image/png;base64,"));
    const png = Buffer.from(actual.split(",")[1]!, "base64");
    assert.equal(sha(png), choice.preview.sha256);
    writeFileSync(join(evidence, prefix + "-native-" + index + ".png"), png);
  }
  writeFileSync(join(evidence, prefix + "-native-report.json"),
    JSON.stringify(report, (key, value) => key === "data_url" ? undefined : value, 2));
  return { report, output };
}
async function post(page: Page, payload: unknown, authenticated = true) {
  const token = await page.locator('meta[name="preview-token"]').getAttribute("content");
  return page.request.post(new URL(route, page.url()).href, {
    data: payload, headers: authenticated ? { "X-Preview-Token": token || "" } : {},
  });
}

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch(existsSync(chrome) ? { executablePath: chrome } : {});
try {
  const chart = await browser.newPage({ viewport: { width: 390, height: 900 }, acceptDownloads: true });
  const chartPanel = await open(chart, await serve("preview"));
  await chart.locator("#live").uncheck();
  assert.equal(await chartPanel.getByRole("button", { name: "Review alternatives" }).isDisabled(), true);
  await chart.locator("#data-file").setInputFiles({ name: "source.csv", mimeType: "text/csv", buffer: raw });
  await chart.locator("#data-summary").getByText(/12/).waitFor();
  await chart.locator("#advanced > summary").click();
  const original = JSON.stringify(spec, null, 2);
  await chart.locator("#spec").fill(original);
  const reviewed = await review(chart, chartPanel);
  assert.equal((await post(chart, reviewed.payload, false)).status(), 403);
  for (const payload of [
    { ...reviewed.payload, mode: "render", ticket: reviewed.report.ticket },
    { ...reviewed.payload, mode: "render", ticket: reviewed.report.ticket, reviewed: true,
      alternatives: [{ label: name, justification: "Changed after review", changes: { aggregation: "median" } }] },
  ]) {
    const rejected = await post(chart, payload);
    assert.equal(rejected.status(), 400, await rejected.text());
    assert.match((await rejected.json()).error, /review again/i);
  }
  workflows.push("editor rejects unauthenticated, unconfirmed and modified reviewed requests");
  const single = await run(chart, chartPanel, reviewed.render, "editor");
  assert.equal(await chart.locator("#spec").inputValue(), original);
  assert.equal(await chart.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  const downloadPending = chart.waitForEvent("download");
  await single.output.getByRole("button", { name: "Download comparison report" }).click();
  const download = await downloadPending;
  await download.saveAs(join(evidence, "editor-comparison.json"));
  const saved = readFileSync(join(evidence, "editor-comparison.json"), "utf8");
  assert.equal(JSON.parse(saved).source.sha256, sha(raw));
  assert.ok(!saved.includes("data:image/png"));
  await single.output.screenshot({ path: join(evidence, "editor-mobile.png") });
  workflows.push("mobile editor runs real baseline and median, keeps failed claim evidence, and downloads a report");

  const second = await review(chart, chartPanel, false);
  let arrived!: () => void, release!: () => void;
  const ready = new Promise<void>(accept => { arrived = accept; });
  const held = new Promise<void>(accept => { release = accept; });
  await chart.route("**" + route, async intercepted => {
    const response = await intercepted.fetch();
    arrived();
    await held;
    await intercepted.fulfill({ response });
  });
  const stale = chart.waitForResponse(response => response.url().endsWith(route));
  try {
    await chartPanel.getByRole("checkbox").check();
    await second.render.click();
    await ready;
    await chart.locator("#spec").fill(JSON.stringify({ ...spec, title: "Changed while rendering" }));
  } finally { release(); }
  await (await stale).finished();
  assert.equal(await chartPanel.getByRole("img").count(), 0);
  assert.equal(await chartPanel.getByText(/holds → fails/).count(), 0);
  await chart.unroute("**" + route);
  workflows.push("a real late native response cannot repopulate the edited figure revision");

  const paper = join(evidence, "paper");
  mkdirSync(paper);
  writeFileSync(join(paper, "source.csv"), raw);
  writeFileSync(join(paper, "figure.json"), original);
  cli("audit-init", paper);
  cli("project-init", paper);
  const project = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const panel = await open(project, await serve("project-preview", paper));
  await panel.getByRole("button", { name: "Review alternatives" }).waitFor();
  await panel.getByRole("button", { name: "Add alternative" }).click();
  await panel.getByLabel("Alternative name").nth(1).fill("First time point");
  await panel.getByLabel("Statistical justification").nth(1).fill("Review the planned early endpoint.");
  await panel.getByLabel("Cohort filters").nth(1).selectOption("replace");
  await panel.getByLabel("Replacement filters (JSON array)").nth(1).fill('[{"field":"x","op":"eq","value":1}]');
  const paperReview = await review(project, panel);
  const projectResult = await run(project, panel, paperReview.render, "paper", 6);
  assert.equal(readFileSync(join(paper, "figure.json"), "utf8"), original);
  assert.deepEqual(readFileSync(join(paper, "source.csv")), raw);
  await projectResult.output.screenshot({ path: join(evidence, "paper-desktop.png") });
  workflows.push("paper compares multiple alternatives against the saved project and discloses absent groups");

  const changed = await review(project, panel, false);
  writeFileSync(join(paper, "source.csv"), Buffer.concat([raw, Buffer.from("2,B,4,u4\n")]));
  const refusal = await post(project, { ...changed.payload, mode: "render", reviewed: true, ticket: changed.report.ticket });
  assert.equal(refusal.status(), 400, await refusal.text());
  assert.match((await refusal.json()).error, /project inputs changed/i);
  workflows.push("an on-disk dataset change invalidates the saved project's review");
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  assert.deepEqual(writes, []);
  const summarized = (report: typeof single.report) => report.choices.map((choice: {
    label: string, status: string, preview?: { sha256: string }, counts?: { after_filter: number },
  }) => ({ label: choice.label, status: choice.status, png_sha256: choice.preview?.sha256, after_filter: choice.counts?.after_filter }));
  writeFileSync(join(evidence, "fixture.csv"), raw);
  const proof = { status: "passed", workflows, source_sha256: sha(raw),
    single: summarized(single.report), paper: summarized(projectResult.report),
    failed_claim: single.report.choices[1].claim_comparison[0], errors, external, writes, evidence };
  writeFileSync(join(evidence, "verification.json"), JSON.stringify(proof, null, 2));
  console.log(JSON.stringify(proof));
} finally {
  await browser.close();
  for (const child of owners) child.kill();
}
