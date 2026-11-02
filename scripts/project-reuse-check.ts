/** Real selective paper audits, retained execution ancestry, mixed inputs and guarded UI. */
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, relative } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Page } from "playwright";
declare const document: { querySelector(selector: string): { textContent: string; hidden: boolean; disabled: boolean } | null; documentElement: { scrollWidth: number }; activeElement: { id: string; tagName: string } | null; hasFocus(): boolean };
declare const window: { innerWidth: number };
const python = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const evidence = mkdtempSync(join(tmpdir(), "gu-paper-reuse-check-")), paper = join(evidence, "paper ü with spaces");
const hash = (value: Uint8Array) => createHash("sha256").update(value).digest("hex");
const cli = (...args: string[]) => { const p = spawnSync(python, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 180_000, maxBuffer: 20 * 1024 * 1024 });assert.ok(p.status === 0 || p.status === 2, p.stderr);return JSON.parse(p.stdout); };
function inventory(root: string): Record<string, string> {
  const result: Record<string, string> = {};
  function walk(folder: string) { for (const entry of readdirSync(folder, { withFileTypes: true })) { const path = join(folder, entry.name);if (entry.isDirectory()) walk(path);else if (entry.isFile()) result[relative(root, path)] = hash(readFileSync(path)); } }
  walk(root);return result;
}
cli("demo", paper, "--json");
const original = JSON.parse(readFileSync(join(paper, "figure.json"), "utf8"));
const data = readFileSync(join(paper, "results.csv"));writeFileSync(join(paper, "second-data.csv"), data);
const second = structuredClone(original);second.kind = "table";second.title = "Second figure";second.data.path = "second-data.csv";second.output.stem = "second";second.output.formats = ["png", "pdf"];second.uncertainty.display = "bar";second.highlight = "best_per_row";
writeFileSync(join(paper, "second.json"), JSON.stringify(second));
const lines = readFileSync(join(paper, "figure.py"), "utf8").split(/(?<=\n)/);
let insertion = 0;lines.forEach((line, i) => { if (line.startsWith("from __future__")) insertion = i + 1; });
// A real slow authored fixture makes job-ownership races observable. These are
// functional workflows, not performance measurements.
lines.splice(insertion, 0, "_paper_reuse_counter = __import__('pathlib').Path(__file__).with_name('executions.txt')\n_paper_reuse_counter.write_text((_paper_reuse_counter.read_text() if _paper_reuse_counter.exists() else '') + 'x')\n__import__('time').sleep(2)\n");
writeFileSync(join(paper, "authored.py"), lines.join(""));const authoredHash = hash(readFileSync(join(paper, "authored.py")));
cli("audit-init", paper);
const manifestFile = join(paper, "graphunslopify.json"), manifest = JSON.parse(readFileSync(manifestFile, "utf8"));
manifest.figures.push({ id: "authored", script: "authored.py", data: "results.csv" });writeFileSync(manifestFile, JSON.stringify(manifest));
cli("project-init", paper);
const initial = cli("project-run", paper, "--no-baseline");assert.equal(initial.exit_code, 0);assert.deepEqual(initial.audit.execution_counts, { executed: 3, reused: 0, not_run: 0 });
const firstHistory = inventory(initial.directory);
const inspections = cli("project-inspections", paper);
assert.equal(cli("project-inspect-pdf", paper, "--id", "foreign", "--pdf", resolve("python/tests/fixtures/project-review-pages.pdf"), "--pages", "1", "--dpi", "72", "--expected-revision", inspections.revision).exit_code, 2);
const server = spawn(python, ["-m", "graphunslopify.cli", "project-preview", paper, "--port", "0"], { env, stdio: ["ignore", "pipe", "pipe"] });
let stderr = "";server.stderr.on("data", chunk => { stderr += chunk; });
const reader = createInterface({ input: server.stdout }), timer = setTimeout(() => server.kill(), 30_000);
const url = await new Promise<string>((accept, reject) => { reader.once("line", line => { try { accept(JSON.parse(line).url); } catch (e) { reject(e); } });server.once("exit", code => reject(Error("Workspace exited " + code + ": " + stderr))); });clearTimeout(timer);
let browser, page: Page | undefined;
const workflows: string[] = [], errors: string[] = [], external: string[] = [], runs: unknown[] = [];
try {
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  browser = await chromium.launch({ headless: true, ...(existsSync(mac) ? { executablePath: mac } : {}) });
  page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });const active = page;active.setDefaultTimeout(120_000);
  active.on("pageerror", error => errors.push(error.message));active.on("request", request => { if (!request.url().startsWith(url) && !request.url().startsWith("data:") && !request.url().startsWith("blob:")) external.push(request.url()); });
  await active.goto(url);await active.waitForFunction(() => document.querySelector("#notice")?.textContent.startsWith("Ready."));
  const token = await active.locator('meta[name="preview-token"]').getAttribute("content");assert.ok(token);
  const api = async (path: string) => { const r = await active.request.get(url + path, { headers: { "X-Preview-Token": token } });assert.equal(r.status(), 200, await r.text());return r.json(); };
  let releasePoll: (() => Promise<void>) | undefined;
  const holdPoll = async () => {
    let ready!: () => void, release!: () => void, done!: () => void;
    const arrived = new Promise<void>(r => { ready = r; }), held = new Promise<void>(r => { release = r; }), delivered = new Promise<void>(r => { done = r; });
    let first = true;
    await active.route("**/api/state", async route => { if (!first) { await route.continue();return; } first = false;const response = await route.fetch();ready();await held;await route.fulfill({ response });done(); });
    await arrived;
    return async () => { release();await delivered;await active.unrouteAll({ behavior: "wait" }); };
  };
  let testedRefresh = false;
  const refreshChanged = async () => {
    if (!testedRefresh) {
      let ready!: () => void, release!: () => void;
      const arrived = new Promise<void>(r => { ready = r; }), held = new Promise<void>(r => { release = r; });
      await active.route("**/api/state", async route => { const response = await route.fetch();ready();await held;await route.fulfill({ response }); });
      try { await active.locator("#refresh").click();await arrived;assert.equal(await active.locator("#regenerate").isDisabled(), true);await active.waitForTimeout(3300);assert.equal(await active.locator("#regenerate").isDisabled(), true); }
      finally { release();await active.unrouteAll({ behavior: "wait" }); }
      testedRefresh = true;workflows.push("a real held manual refresh stays locked across background polling");
    } else await active.locator("#refresh").click();
    await active.waitForFunction(() => document.querySelector("#project-status")?.textContent.includes("Audit needed"));
    await active.waitForFunction(() => document.querySelector("#regenerate")?.disabled === false);
  };
  const run = async (executed: number, reused: number, keyboard = false, expectedExit = 0) => {
    if (keyboard) {
      await active.waitForFunction(() => document.querySelector("#regenerate")?.disabled === false);
      // Keep the native key action attached to its target instead of a separate
      // page-wide press after a focus call. No job response is simulated.
      await active.locator("#regenerate").press("Enter");
    } else await active.locator("#regenerate").click();
    await active.waitForFunction(() => document.querySelector("#running")?.hidden === false);
    if (releasePoll) {
      await releasePoll();releasePoll = undefined;await active.waitForTimeout(100);
      const job = await api("/api/job");assert.equal(job.phase, "running", "the genuine authored worker must still be active");
      assert.equal(await active.locator("#regenerate").isDisabled(), true, "an older real poll cannot unlock a new audit");
      workflows.push("an older real state reply cannot supersede a newly started genuine audit");
    }
    assert.equal(await active.locator("#regenerate").isDisabled(), true);
    await active.waitForFunction(() => document.querySelector("#running")?.hidden === true && document.querySelector("#event-summary")?.textContent.includes("reused"));
    const state = await api("/api/state");assert.equal(state.job.phase, "complete", JSON.stringify(state.job));assert.equal(state.job.error, null);const id = state.job.result.id;
    const result = JSON.parse(readFileSync(join(paper, "graphunslopify-project/history", id, "result.json"), "utf8"));
    assert.equal(result.exit_code, expectedExit, JSON.stringify({ errors: result.errors, comparison: result.audit.visual_comparison }));assert.deepEqual(result.audit.execution_counts, { executed, reused, not_run: 0 });
    runs.push({ id, exit_code: result.exit_code, counts: result.audit.execution_counts, figures: result.audit.figures.map((f: { id: string; execution: unknown }) => ({ id: f.id, execution: f.execution })) });
    assert.equal(readFileSync(join(paper, "executions.txt"), "utf8").length, runs.length + 1);
    return { ...result, directory: join(paper, "graphunslopify-project/history", id) };
  };
  const saveDefinition = async (value: unknown) => {
    await active.locator("#definition-panel").evaluate(node => node.setAttribute("open", ""));
    await active.locator("#definition").fill(JSON.stringify(value));
    assert.equal(await active.locator("#regenerate").isDisabled(), true);
    await active.locator("#save-definition").click();
    await active.waitForFunction(() => document.querySelector("#regenerate")?.disabled === false);
  };
  assert.equal((await api("/api/state")).figures.length, 3);assert.equal((await api("/api/state")).inspections.length, 1);
  workflows.push("existing mixed paper opens with two native specs, an authored program and a real source-free PDF");
  releasePoll = await holdPoll();
  let result = await run(1, 2);
  assert.ok(result.audit.figures.filter((f: { execution: { mode: string } }) => f.execution.mode === "reused").every((f: { execution: { origin_event: string } }) => f.execution.origin_event === initial.id));
  workflows.push("actual unchanged native figures reuse accepted reports while the authored program executes again");
  await active.locator("#history-figure").selectOption("second");
  await active.waitForFunction(() => document.querySelector("#checks")?.textContent.includes("not executed again"));
  await active.screenshot({ path: join(evidence, "desktop.png"), fullPage: true });
  await active.setViewportSize({ width: 390, height: 1000 });await active.screenshot({ path: join(evidence, "mobile.png"), fullPage: true });
  assert.equal(await active.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  workflows.push("actual desktop and narrow mobile views disclose copied execution ancestry without overflow");
  await run(1, 2, true);await active.setViewportSize({ width: 1440, height: 1100 });
  workflows.push("keyboard regeneration preserves counts and reruns unknown authored dependencies");
  await saveDefinition({ ...original, title: "Current wording after a real edit" });
  result = await run(2, 1);assert.equal(result.audit.figures.find((f: { id: string }) => f.id === "figure").report.spec.title, "Current wording after a real edit");
  workflows.push("saved canonical title edit executes the affected native figure and reuses the independent one");
  await saveDefinition(original);await run(2, 1);
  workflows.push("restoring an older definition still compares with the newest native run");
  writeFileSync(join(paper, "second-data.csv"), Buffer.concat([data, Buffer.from("\n")]));
  await refreshChanged();
  await run(2, 1);
  workflows.push("actual independent data-byte change reruns only its native dependent plus the authored program");
  writeFileSync(join(paper, "second-data.csv"), data);
  await refreshChanged();
  result = await run(2, 1);
  workflows.push("restored original data is verified through a fresh dependent execution");
  const figure = result.audit.figures.find((f: { id: string }) => f.id === "figure"), png = figure.outputs.find((f: { format: string }) => f.format === "png");
  const output = join(result.directory, "audit", png.path);writeFileSync(output, Buffer.concat([readFileSync(output), Buffer.from("\nchanged")]));
  await refreshChanged();
  result = await run(2, 1, false, 2);
  assert.equal(result.audit.visual_comparison.preview_status, "partial");
  workflows.push("a damaged saved export is regenerated while its unverifiable baseline still correctly rejects paper acceptance");
  await active.locator("#baseline").evaluate(node => node.closest("details")?.setAttribute("open", ""));
  await active.locator("#baseline").selectOption("");
  await run(3, 0);
  workflows.push("explicit No baseline recovery reruns every figure after the latest failed run and retains the original failure");
  assert.deepEqual(inventory(initial.directory), firstHistory);
  assert.equal(hash(readFileSync(join(paper, "results.csv"))), hash(data));assert.equal(hash(readFileSync(join(paper, "second-data.csv"))), hash(data));
  assert.deepEqual(JSON.parse(readFileSync(join(paper, "figure.json"), "utf8")), original);assert.equal(hash(readFileSync(join(paper, "authored.py"))), authoredHash);
  assert.deepEqual(errors, []);assert.deepEqual(external, []);assert.equal(cli("project-history", paper).integrity, "verified");
  workflows.push("original data, source values, authored program bytes and first history survive all real runs");
  const paths = Object.keys(inventory(evidence));assert.deepEqual(paths.filter(path => /[":<>|*?\r\n]/.test(path)), []);
  const report = { status: "passed", workflows, runs, authored_executions: runs.length + 1, original_data_and_first_history_preserved: true, original_definition_values_restored: true, page_errors: errors, external_requests: external, artifact_paths_portable: true, evidence };
  writeFileSync(join(evidence, "verification.json"), JSON.stringify(report, null, 2));console.log(JSON.stringify(report));
} catch (problem) {
  const view = await page?.evaluate(() => ({
    activeElementId: document.activeElement?.id,
    activeElementTag: document.activeElement?.tagName,
    documentFocused: document.hasFocus(),
    regenerateDisabled: document.querySelector("#regenerate")?.disabled,
    runningHidden: document.querySelector("#running")?.hidden,
    notice: document.querySelector("#notice")?.textContent,
    error: document.querySelector("#error")?.textContent,
    summary: document.querySelector("#event-summary")?.textContent,
  })).catch(error => ({ captureError: String(error) }));
  writeFileSync(join(evidence, "failure-state.json"), JSON.stringify({ error: String(problem), view, workflows, runs, page_errors: errors, external_requests: external, server_stderr: stderr }, null, 2));
  await page?.screenshot({ path: join(evidence, "failure.png"), fullPage: true }).catch(() => {});
  console.error(JSON.stringify({ evidence, error: String(problem) }));throw problem;
}
finally { await browser?.close();server.kill();reader.close(); }

