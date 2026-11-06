/** Real preparation-only requests in both workspaces, including a stale reply. */
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Page } from "playwright";

const python = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED
  ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const evidence = mkdtempSync(join(tmpdir(), "gu-cleaning-check-"));
const workers: ReturnType<typeof spawn>[] = [];
const errors: string[] = [], external: string[] = [], workflows: string[] = [];
const route = "/api/cleaning-preview";

function cli(...args: string[]) {
  const result = spawnSync(python, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 60_000 });
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

async function serve(...args: string[]): Promise<string> {
  const child = spawn(python, ["-m", "graphunslopify.cli", ...args, "--port", "0"], {
    env, stdio: ["ignore", "pipe", "pipe"],
  });
  workers.push(child);
  const reader = createInterface({ input: child.stdout });
  let stderr = "";
  child.stderr.on("data", part => { stderr += part; });
  const timer = setTimeout(() => child.kill(), 30_000);
  try {
    return await new Promise((accept, reject) => {
      reader.once("line", line => {
        try { accept(JSON.parse(line).url); } catch (error) { reject(error); }
      });
      child.once("exit", code => reject(Error("Local workspace exited " + code + ": " + stderr)));
    });
  } finally {
    clearTimeout(timer);
    reader.close();
  }
}

function watch(page: Page, url: string) {
  const forbidden: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (!request.url().startsWith(url) && !/^(blob:|data:)/.test(request.url())) external.push(request.url());
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && ["/api/run", "/api/render", "/api/definition"].includes(path)) {
      forbidden.push(path);
    }
  });
  return forbidden;
}

async function prepare(page: Page) {
  const ready = page.waitForResponse(response => response.url().endsWith(route));
  await page.locator("#cleaning-run").press("Enter");
  const response = await ready;
  assert.equal(response.status(), 200, await response.text());
  return response.json();
}

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch(existsSync(chrome) ? { executablePath: chrome } : {});
try {
  const url = await serve("preview");
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const renders = watch(page, url);
  await page.goto(url);
  await page.locator("#live").uncheck();
  await page.locator("#cleaning-preview > summary").click();
  assert.equal(await page.locator("#cleaning-run").isDisabled(), true);
  const data = Buffer.from("x,y,keep\n1,1.2,1\n2,broken,1\n3,,1\n4,inf,1\n5,7,0\n");
  await page.locator("#data-file").setInputFiles({ name: "mixed.csv", mimeType: "text/csv", buffer: data });
  await page.locator("#data-summary").filter({ hasText: "5 rows" }).waitFor();
  await page.locator("#advanced").evaluate(node => node.setAttribute("open", ""));
  const spec = {
    kind: "line", x: { field: "x", label: "Step" }, y: { field: "y", label: "Response" },
    aggregation: "mean", filter: [{ field: "keep", op: "eq", value: 1 }],
  };
  const original = JSON.stringify(spec);
  await page.locator("#spec").fill(original);
  const report = await prepare(page);
  assert.equal(report.status, "prepared");
  await page.locator("#cleaning-results").getByText(/4 after filters/).waitFor();
  const display = await page.locator("#cleaning-results").innerText();
  assert.match(display, /y \(.*\) · 1 missing/);
  assert.match(display, /1 became missing, 1 infinite/);
  assert.match(display, /invalid numeric measurement · y · records 2/);
  assert.match(display, /filter predicate false · filter 1 · records 5/);
  assert.equal(await page.locator("#spec").inputValue(), original);
  await page.locator("#cleaning-preview").screenshot({ path: join(evidence, "editor-mobile.png") });
  assert.deepEqual(renders, []);
  workflows.push("keyboard preview reports parsed missing values, conversions and precise exclusions without a render or draft edit");

  let arrive!: () => void, release!: () => void;
  const arrived = new Promise<void>(accept => { arrive = accept; });
  const held = new Promise<void>(accept => { release = accept; });
  await page.route("**" + route, async intercepted => {
    const response = await intercepted.fetch();
    arrive();
    await held;
    await intercepted.fulfill({ response });
  });
  const pending = prepare(page);
  try {
    await arrived;
    await page.locator("#spec").fill(JSON.stringify({ ...spec, title: "New draft" }));
    assert.equal(await page.locator("#cleaning-results").textContent(), "");
  } finally {
    release();
  }
  await pending;
  await page.unroute("**" + route);
  assert.equal(await page.locator("#cleaning-results").textContent(), "");
  assert.deepEqual(renders, []);
  workflows.push("a held real preparation reply cannot attach to a changed draft");

  const paper = join(evidence, "paper");
  cli("demo", paper, "--json");
  cli("audit-init", paper);
  cli("project-init", paper);
  const paperUrl = await serve("project-preview", paper);
  const project = await browser.newPage();
  const paperWrites = watch(project, paperUrl);
  await project.goto(paperUrl);
  await project.locator("#selected-title").and(project.getByText("figure", { exact: true })).waitFor();
  await project.locator("#cleaning-preview > summary").click();
  await project.locator("#cleaning-run:enabled").waitFor();
  const source = join(paper, "figure.json");
  const before = readFileSync(source);
  const paperReport = await prepare(project);
  assert.equal(paperReport.status, "prepared");
  await project.locator("#cleaning-results").getByText(/parsed records/).waitFor();
  await project.locator("#definition-panel > summary").click();
  await project.locator("#definition").fill(JSON.stringify({ ...JSON.parse(before.toString()), title: "Unsaved draft" }));
  assert.equal(await project.locator("#cleaning-run").isDisabled(), true);
  assert.equal(await project.locator("#cleaning-results").textContent(), "");
  assert.deepEqual(readFileSync(source), before);
  assert.deepEqual(paperWrites, []);
  workflows.push("paper preview reads the saved definition and clears when an unsaved draft takes ownership");
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  const result = { status: "passed", workflows, editor: report, paper: paperReport, evidence };
  writeFileSync(join(evidence, "verification.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} catch (error) {
  console.error(JSON.stringify({ status: "failed", evidence, error: String(error) }));
  throw error;
} finally {
  await browser.close();
  for (const worker of workers) worker.kill();
}
