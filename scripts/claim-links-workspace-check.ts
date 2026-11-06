/** Real paper, exact text, native audit verdicts and checked history navigation. */
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Page } from "playwright";
declare const document: { documentElement: { scrollWidth: number } };
declare const window: { innerWidth: number };

const interpreter = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED
  ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const root = mkdtempSync(join(tmpdir(), "gu-claim-links-workspace-check-"));
const route = "/api/claim-links";
const text = "Arm A has a higher mean than Arm B at every recorded visit.";
const manuscript = "Results\n" + text + "\n";
const source = "visit,arm,value\n1,A,8\n1,A,6\n1,B,3\n1,B,5\n2,A,10\n2,A,8\n2,B,5\n2,B,7\n";
const changed = source.replace("2,A,10\n2,A,8", "2,A,2\n2,A,4");
const definition = JSON.stringify({
  kind: "line", title: "Two arms over time", aggregation: "mean", marker: true, group: "arm",
  data: { path: "input.csv", format: "csv" },
  x: { field: "visit", label: "Visit" }, y: { field: "value", label: "Response" },
  caption: text, claims: [{ kind: "beats_everywhere", subject: "A", reference: "B" }],
  output: { stem: "response", dpi: 144, formats: ["png"] },
});
const ledger = join(root, "graphunslopify-project", "claim-links.json");
const sha = (data: string | Buffer) => createHash("sha256").update(data).digest("hex");
function cli(...args: string[]) {
  return execFileSync(interpreter, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 90_000 });
}
function audited(expected: number) {
  let output;
  try { output = cli("project-run", root); assert.equal(expected, 0); }
  catch (error) {
    const failed = error as { status?: number, stdout?: string };
    assert.equal(failed.status, expected);
    output = failed.stdout;
  }
  assert.ok(output);
  return JSON.parse(output);
}
const workflows: string[] = [], errors: string[] = [], external: string[] = [];
writeFileSync(join(root, "input.csv"), source);
writeFileSync(join(root, "paper.tex"), manuscript);
writeFileSync(join(root, "response.figure.json"), definition);
writeFileSync(join(root, "graphunslopify.json"), JSON.stringify({
  schema_version: 1, figures: [{ id: "response", spec: "response.figure.json" }],
}));
cli("project-init", root);
const before = audited(0);
const owner = spawn(interpreter, ["-m", "graphunslopify.cli", "project-preview", root, "--port", "0"],
  { env, stdio: ["ignore", "pipe", "pipe"] });
const reader = createInterface({ input: owner.stdout });
let stderr = "";
owner.stderr.on("data", data => { stderr += data; });
const timeout = setTimeout(() => owner.kill(), 30_000);
const serving = new Promise<string>((accept, reject) => {
  reader.once("line", line => {
    try { accept(JSON.parse(line).url); } catch (error) { reject(error); }
  });
  owner.once("exit", code => reject(Error("Paper workspace exited " + code + ": " + stderr)));
});
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch(existsSync(chrome) ? { executablePath: chrome } : {});
try {
  const url = await serving;
  clearTimeout(timeout);
  reader.close();
  const page: Page = await browser.newPage({ viewport: { width: 1280, height: 950 } });
  const origin = new URL(url).origin;
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (!/^(blob:|data:)/.test(request.url()) && new URL(request.url()).origin !== origin) external.push(request.url());
  });
  await page.goto(url);
  const panel = page.locator("#claim-links");
  const list = panel.getByRole("region", { name: "Saved claim links" });
  const approval = panel.getByRole("region", { name: "Claim link review" });
  const check = panel.getByLabel("Recorded figure check");
  const reload = panel.getByRole("button", { name: "Refresh claim links" });
  await panel.locator("summary").click();
  await list.getByText("No saved claim links.").waitFor();
  assert.equal((await page.request.get(new URL(route, url).href)).status(), 403);
  await check.selectOption({ index: 1 });
  await panel.getByLabel("Manuscript path relative to paper folder").fill("paper.tex");
  await panel.getByLabel("Exact excerpt").fill(text);

  const reviewButton = panel.getByRole("button", { name: "Review claim link" });
  const save = approval.getByRole("button", { name: "Save confirmed claim link" });
  const consent = approval.getByRole("checkbox");
  const review = async () => {
    const pending = page.waitForResponse(response => response.url().endsWith(route) &&
      response.request().method() === "POST");
    await reviewButton.click();
    const reply = await pending;
    assert.equal(reply.status(), 200, await reply.text());
    await save.waitFor();
    assert.equal(await save.isDisabled(), true);
    return { body: reply.request().postDataJSON(), response: await reply.json() };
  };
  const first = await review();
  assert.equal(first.response.evidence.event, before.id);
  assert.equal(first.response.location.first_line, 2);
  assert.equal(existsSync(ledger), false);
  const token = await page.locator('meta[name="preview-token"]').getAttribute("content");
  const unconfirmed = await page.request.post(new URL(route, url).href, {
    headers: { "X-Preview-Token": token || "" },
    data: { ...first.body, action: "save", review_sha256: first.response.review_sha256 },
  });
  assert.equal(unconfirmed.status(), 400, await unconfirmed.text());
  assert.equal(existsSync(ledger), false);
  workflows.push("loopback authorization and explicit confirmation guard the ledger");

  writeFileSync(join(root, "paper.tex"), "Introduction\n" + manuscript);
  await consent.check();
  await save.click();
  await panel.getByRole("status").getByText(/changed since review/i).waitFor();
  assert.equal(existsSync(ledger), false);
  await review();
  await consent.check();
  await save.click();
  await list.getByRole("heading", { name: "Supported by the recorded check" }).waitFor();
  await list.getByText(/paper.tex · line 3/).waitFor();
  workflows.push("a changed manuscript rejects the prior review and binds the newly confirmed line");

  await panel.getByLabel("Text source").selectOption("caption");
  const caption = await review();
  assert.equal(caption.response.location.first_line, 1);
  await consent.check();
  await save.click();
  await list.getByText(/Figure caption · line 1/).waitFor();
  await list.getByText(/paper.tex · line 3/).waitFor();
  assert.equal(JSON.parse(readFileSync(ledger, "utf8")).links.length, 2);
  workflows.push("manuscript and caption links coexist with their exact locations");

  writeFileSync(join(root, "input.csv"), changed);
  await reload.click();
  await list.getByRole("heading", { name: "Stale figure evidence" }).last().waitFor();
  assert.equal(await list.getByRole("button", { name: "Open linked figure audit" }).count(), 0);
  const after = audited(2);
  await page.locator("#refresh").click();
  const finalRequest = page.waitForResponse(response => response.url().endsWith(route) &&
    response.request().method() === "GET" && response.ok());
  await reload.click();
  const final = await (await finalRequest).json();
  await list.getByRole("heading", { name: "Contradiction" }).last().waitFor();
  assert.equal(final.audit, after.id);
  assert.deepEqual(final.links.map((link: { status: string }) => link.status), ["contradiction", "contradiction"]);
  for (const link of final.links) {
    assert.equal(link.evidence.data_sha256, sha(changed));
    assert.equal(link.check_result.verdict, "fails");
    assert.equal(link.reviewed_run, before.id);
  }
  const output = after.audit.figures[0].outputs.find((item: { format: string }) => item.format === "png");
  const png = readFileSync(join(root, "graphunslopify-project", "history", after.id, "audit", output.path));
  assert.equal(sha(png), output.sha256);
  assert.deepEqual(final.links.map((link: { evidence: { exports: { sha256: string }[] } }) =>
    link.evidence.exports[0]?.sha256), [sha(png), sha(png)]);
  writeFileSync(join(root, "contradictory-native.png"), png);
  writeFileSync(join(root, "contradictory-links.json"), JSON.stringify(final, null, 2));
  await list.getByRole("button", { name: "Open linked figure audit" }).first().click();
  await page.locator("#checks").getByText(/Scientific result: failed/).waitFor();
  assert.equal(await page.locator("#history").inputValue(), after.id);
  assert.equal(await page.locator("#history-figure").inputValue(), "response");
  workflows.push("a fresh native audit identifies contradictions and opens their exact failed figure evidence");

  await page.setViewportSize({ width: 390, height: 900 });
  await panel.screenshot({ path: join(root, "claim-links-mobile.png") });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await list.getByRole("button", { name: "Remove this claim link" }).last().click();
  await panel.getByRole("status").getByText(/^1 saved/).waitFor();
  assert.equal(JSON.parse(readFileSync(ledger, "utf8")).links.length, 1);
  assert.equal(readFileSync(join(root, "paper.tex"), "utf8"), "Introduction\n" + manuscript);
  assert.equal(readFileSync(join(root, "response.figure.json"), "utf8"), definition);
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  workflows.push("mobile status and guarded removal preserve the manuscript and figure definition");
  const proof = { status: "passed", workflows, data_sha256: sha(changed), native_png_sha256: sha(png),
    initial_event: before.id, contradictory_event: after.id, errors, external };
  writeFileSync(join(root, "verification.json"), JSON.stringify(proof, null, 2));
  console.log(JSON.stringify({ ...proof, evidence: root }));
} finally {
  clearTimeout(timeout);
  reader.close();
  await browser.close();
  owner.kill();
}
