/** Real prospective planning in the local figure and paper workspaces. */
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Page } from "playwright";

const python = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED
  ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const evidence = mkdtempSync(join(tmpdir(), "gu-power-check-"));
const owners: ReturnType<typeof spawn>[] = [];
const errors: string[] = [], external: string[] = [], writes: string[] = [], workflows: string[] = [];
const route = "/api/statistical-power";

function cli(...args: string[]) {
  return execFileSync(python, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 60_000 });
}

async function serve(...args: string[]): Promise<string> {
  const child = spawn(python, ["-m", "graphunslopify.cli", ...args, "--port", "0"], { env, stdio: ["ignore", "pipe", "pipe"] });
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

async function open(page: Page, url: string) {
  const origin = new URL(url).origin;
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (!/^(blob:|data:)/.test(request.url()) && new URL(request.url()).origin !== origin) external.push(request.url());
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && ["/api/upload", "/api/render", "/api/run", "/api/definition", "/api/entry", "/api/shared-apply", "/api/selection-apply"].includes(path)) {
      writes.push(path);
    }
  });
  await page.goto(url);
  await page.locator("#statistical-power > summary").click();
  return page.locator("#statistical-power");
}

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch(existsSync(chrome) ? { executablePath: chrome } : {});
try {
  const chart = await browser.newPage({ viewport: { width: 390, height: 900 } });
  const chartPower = await open(chart, await serve("preview"));
  await chartPower.getByLabel("Study design").selectOption("paired");
  await chartPower.getByLabel("Difference units").selectOption("raw");
  await chartPower.getByLabel("Test alternative").selectOption("greater");
  await chartPower.getByLabel("Planned independent complete pairs").fill("24");
  await chartPower.getByLabel("Planning SD of within-pair differences").fill("0.25");
  await chartPower.getByLabel("Significance level (alpha)").fill("0.05");
  await chartPower.getByLabel("Planned difference in outcome units").fill("0.08");
  const button = chartPower.getByRole("button", { name: "Calculate planning power" });
  await button.click();
  assert.equal(await chartPower.getByRole("heading", { name: /Estimated power/ }).count(), 0);
  await chartPower.getByRole("checkbox").check();
  const pairedResponse = chart.waitForResponse(response => response.url().endsWith(route));
  await button.press("Enter");
  const paired = await (await pairedResponse).json();
  assert.ok(Math.abs(paired.result.power - 0.4508691) < 5e-8);
  assert.equal(paired.assumptions_verified, false);
  await chartPower.getByRole("heading", { name: /45\.087%/ }).waitFor();
  await chartPower.screenshot({ path: join(evidence, "paired-mobile.png") });
  workflows.push("chart planner requires assumptions and calculates published paired power without chart input");

  const paper = join(evidence, "paper");
  cli("demo", paper, "--json");
  cli("audit-init", paper);
  cli("project-init", paper);
  const filenames = ["figure.json", "results.csv", "graphunslopify-project/project.json"];
  const before = filenames.map(name => readFileSync(join(paper, name)));
  const project = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const panel = await open(project, await serve("project-preview", paper));
  await panel.getByLabel("Study design").selectOption("welch");
  await panel.getByLabel("Calculate").selectOption("detectable_effect");
  await panel.getByLabel("Test alternative").selectOption("two_sided");
  await panel.getByLabel("Planned independent units in group A").fill("8");
  await panel.getByLabel("Planned independent units in group B").fill("16");
  await panel.getByLabel("Planning SD in group A").fill("0.3333333333333333");
  await panel.getByLabel("Planning SD in group B").fill("1");
  await panel.getByLabel("Significance level (alpha)").fill("0.05");
  await panel.getByLabel("Target power (0 to 1)").fill("0.8");
  await panel.getByRole("checkbox").check();
  const projectButton = panel.getByRole("button", { name: "Calculate planning power" });
  const welchResponse = project.waitForResponse(response => response.url().endsWith(route));
  await projectButton.click();
  const welch = await (await welchResponse).json();
  assert.ok(Math.abs(welch.result.power - 0.8) < 1e-8);
  assert.ok(Math.abs(welch.result.difference - 0.8150316) < 1e-6);
  assert.ok(welch.result.null_rejection_probability < 0.05);
  await panel.getByText(/Detectable difference 0\.815032/).waitFor();
  await panel.screenshot({ path: join(evidence, "welch-desktop.png") });
  workflows.push("paper planner solves a Welch detectable difference and reports its model-specific zero-effect rejection");

  let arrived!: () => void, release!: () => void;
  const responseArrived = new Promise<void>(accept => { arrived = accept; });
  const held = new Promise<void>(accept => { release = accept; });
  await project.route("**" + route, async intercepted => {
    const response = await intercepted.fetch();
    arrived();
    await held;
    await intercepted.fulfill({ response });
  });
  const completed = project.waitForResponse(response => response.url().endsWith(route));
  try {
    await projectButton.click();
    await responseArrived;
    await panel.getByLabel("Target power (0 to 1)").fill("0.85");
  } finally { release(); }
  await (await completed).finished();
  assert.equal(await panel.getByRole("heading", { name: /Estimated power/ }).count(), 0);
  await project.unroute("**" + route);
  assert.deepEqual(filenames.map(name => readFileSync(join(paper, name))), before);
  assert.deepEqual([errors, external, writes], [[], [], []]);
  workflows.push("an old real result cannot reappear after planning inputs change and files stay intact");
  const proof = { status: "passed", workflows, paired, welch, errors, external, writes };
  writeFileSync(join(evidence, "verification.json"), JSON.stringify(proof, null, 2) + "\n");
  console.log(JSON.stringify({ ...proof, evidence }));
} finally {
  await browser.close();
  for (const child of owners) child.kill();
}
