/** Actual editor paths for journal evidence, downloads and superseded replies. */
import assert from "node:assert/strict";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Page } from "playwright";

declare function requestAnimationFrame(callback: () => void): number;

const root = resolve(".");
const evidence = process.env.GRAPHUNSLOPIFY_JOURNAL_EVIDENCE || mkdtempSync(join(tmpdir(), "gu-journal-check-"));
if (process.env.GRAPHUNSLOPIFY_JOURNAL_EVIDENCE) mkdirSync(evidence);
const python = process.env.PYTHON || "python";
const env = { ...process.env };
if (process.env.GRAPHUNSLOPIFY_JOURNAL_INSTALLED) delete env.PYTHONPATH;
else env.PYTHONPATH = join(root, "python");
const servers: ChildProcess[] = [];
async function serve(args: string[]) {
  const process = spawn(python, ["-m", "graphunslopify.cli", ...args, "--port", "0"], { cwd: evidence, env, stdio: ["ignore", "pipe", "pipe"] });
  servers.push(process);
  let stderr = ""; process.stderr!.on("data", chunk => { stderr += chunk; });
  const lines = createInterface({ input: process.stdout! });
  const timeout = setTimeout(() => process.kill(), 30_000);
  try {
    return await new Promise<string>((accept, reject) => {
      lines.once("line", line => { try { accept(JSON.parse(line).url); } catch (problem) { reject(problem); } });
      process.once("exit", code => reject(Error(`Editor exited ${code}: ${stderr}`)));
      process.once("error", reject);
    });
  } finally { clearTimeout(timeout); }
}
const failures: string[] = [];
const external: string[] = [];
const receipts: unknown[] = [];
async function check(page: Page, kind: "figure" | "paper") {
  await page.locator(".journal-checks > summary").click();
  await page.locator("#journal-profile").selectOption("nature-final-graphs");
  const options = await page.locator("#journal-file option").all();
  let pdf = "";
  for (const option of options) if ((await option.textContent())?.endsWith(".pdf")) pdf = (await option.getAttribute("value"))!;
  assert(pdf, "Actual PDF export must be available");
  await page.locator("#journal-file").selectOption(pdf);
  const scientific = page.locator(kind === "figure" ? "#status" : "#event-summary");
  const nativeStatus = await scientific.textContent();
  const response = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
  await page.locator("#journal-check").click();
  const received = await response; assert.equal(received.status(), 200);
  const packet = await received.json();
  await page.locator("#journal-findings h4").waitFor();
  assert.match((await page.locator("#journal-findings").textContent())!, /Manual review still required/);
  assert.match((await page.locator(".journal-checks").textContent())!, /Scientific verification was not performed/);
  assert.equal(packet.report.scientific_verification, "not_performed");
  assert.equal(packet.report.submission_ready, null);
  const token = (await page.locator('meta[name="preview-token"]').getAttribute("content"))!;
  const body = received.request().postDataJSON();
  const artifact = kind === "figure"
    ? `/artifact/${body.run_id}/${encodeURIComponent(body.filename)}`
    : `/api/artifact?${new URLSearchParams({ event: body.event, figure: body.figure, index: String(body.index) })}`;
  const bytes = await page.request.get(new URL(artifact, page.url()).href, { headers: { "X-Preview-Token": token } });
  assert.equal(bytes.status(), 200);
  assert.equal(createHash("sha256").update(await bytes.body()).digest("hex"), packet.report.source.sha256);
  const download = page.waitForEvent("download");
  await page.getByText("Download this journal report", { exact: true }).click();
  const saved = join(evidence, kind + "-journal-report.json");
  await (await download).saveAs(saved);
  assert.deepEqual(JSON.parse(readFileSync(saved, "utf8")), packet);
  assert.equal(await scientific.textContent(), nativeStatus);
  await page.screenshot({ path: join(evidence, kind + "-journal-evidence.png"), fullPage: true });

  let held!: () => void, release!: () => void;
  const intercepted = new Promise<void>(accept => { held = accept; });
  const released = new Promise<void>(accept => { release = accept; });
  let first = true;
  await page.route("**/api/journal-check", async route => {
    if (!first) { await route.continue(); return; }
    first = false;
    const actual = await route.fetch(); held(); await released;
    await route.fulfill({ response: actual });
  });
  await page.locator("#journal-check").click(); await intercepted;
  await page.locator("#journal-width").fill("999");
  const newer = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
  await page.locator("#journal-check").click();
  const changed = await (await newer).json();
  await page.locator('#journal-status[data-state="failed"]').waitFor();
  assert(changed.report.checks.some((check: { code: string; status: string }) => check.code === "requested_width" && check.status === "failed"));
  const old = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
  release(); await (await old).finished();
  await page.evaluate(() => new Promise<void>(accept => requestAnimationFrame(() => requestAnimationFrame(accept))));
  assert.equal(await page.locator("#journal-status").textContent(), "Technical checks failed");
  assert.match((await page.locator("#journal-findings").textContent())!, /999/);
  await page.unroute("**/api/journal-check");
  await page.locator("#journal-profile").selectOption("plos-one-main");
  assert.equal(await page.locator("#journal-findings").textContent(), "");
  assert.equal(await scientific.textContent(), nativeStatus);
  await page.screenshot({ path: join(evidence, kind + "-journal-panel.png"), fullPage: true });
  await page.locator("#journal-profile").selectOption("nature-final-graphs");
  await page.locator("#journal-width").fill("");
  if (kind === "figure") await page.locator("#live").uncheck();
  let pending!: () => void, finish!: () => void;
  const waiting = new Promise<void>(accept => { pending = accept; });
  const finished = new Promise<void>(accept => { finish = accept; });
  await page.route("**/api/journal-check", async route => {
    const response = await route.fetch(); pending(); await finished;
    await route.fulfill({ response });
  });
  await page.locator("#journal-check").click(); await waiting;
  const editor = page.locator(kind === "figure" ? "#spec" : "#definition");
  if (!await editor.isVisible()) await page.locator(kind === "figure" ? "#advanced > summary" : "#definition-panel > summary").click();
  const spec = JSON.parse(await editor.inputValue());
  spec.x.label = "Edited while journal evidence was in flight";
  await editor.fill(JSON.stringify(spec, null, 2));
  assert(await page.locator("#journal-check").isDisabled());
  const late = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
  finish(); await (await late).finished();
  await page.evaluate(() => new Promise<void>(accept => requestAnimationFrame(() => requestAnimationFrame(accept))));
  assert.equal(await page.locator("#journal-findings").textContent(), "");
  assert(await page.locator("#journal-check").isDisabled());
  await page.unroute("**/api/journal-check");
  if (kind === "paper") {
    const figures = await page.locator("#history-figure option").all();
    const previous = await page.locator("#history-figure").inputValue();
    const other = await Promise.all(figures.map(option => option.getAttribute("value")));
    const next = other.find(value => value && value !== previous);
    assert(next, "Real paper fixture must contain another recorded figure");
    await page.locator("#history-figure").selectOption(next);
    await page.locator("#exports a").first().waitFor();
    assert(await page.locator("#journal-check").isDisabled(), "Dirty editor cannot become current through history navigation");
  }
  receipts.push({ kind, actual_export_sha256: packet.report.source.sha256, exact_download: true, superseded_reply_rejected: true, editor_change_rejected: true, ...(kind === "paper" ? { dirty_history_rejected: true } : {}), native_status_preserved: true });
}
async function correctPdf(page: Page, kind: "figure" | "paper") {
  const editor = page.locator(kind === "figure" ? "#spec" : "#definition");
  if (kind === "figure") {
    await page.locator("#live").uncheck();
    if (!await editor.isVisible()) await page.locator("#advanced > summary").click();
    const spec = JSON.parse(await editor.inputValue()); spec.output.formats = ["png"];
    await editor.fill(JSON.stringify(spec));
    const rendered = page.waitForResponse(response => response.url().endsWith("/api/render"));
    await page.locator("#render").click(); await rendered;
    await page.locator('#preview[data-phase="final"]').waitFor();
  }
  const before = JSON.parse(await editor.inputValue());
  await page.locator(".journal-checks > summary").click();
  await page.locator("#journal-profile").selectOption("nature-final-graphs");
  if (kind === "paper") {
    const selected = await page.locator("#history-figure").inputValue();
    const choices = await page.locator("#history-figure option").all();
    let other = "";
    for (const option of choices) { const value = await option.getAttribute("value"); if (value && value !== selected) other = value; }
    await page.locator("#history-figure").selectOption(other);
    const mismatch = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
    await page.locator("#journal-check").click(); await mismatch;
    await page.locator("#journal-review-pdf").click();
    await page.getByText("Choose the matching current figure definition before proposing an export change.",{exact:true}).waitFor();
    assert(!await page.locator("#reuse-review").isVisible());
    assert.deepEqual(JSON.parse(await editor.inputValue()),before);
    await page.locator("#history-figure").selectOption(selected);
    await page.locator("#exports a").first().waitFor();
  }
  const response = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
  await page.locator("#journal-check").click();
  const failed = await (await response).json();
  assert(failed.report.checks.some((check: {code: string;status:string}) => check.code === "file_format" && check.status === "failed"));
  let captured!:()=>void,release!:()=>void;
  const held=new Promise<void>(accept=>{captured=accept;}),released=new Promise<void>(accept=>{release=accept;});
  await page.route("**/api/reuse/proposal",async route=>{const real=await route.fetch();captured();await released;await route.fulfill({response:real});});
  const lateProposal=page.waitForResponse(response=>response.url().endsWith("/api/reuse/proposal"));
  const opening=page.locator("#journal-review-pdf").click();await held;
  await page.locator("#journal-width").fill("999");
  release();await(await lateProposal).finished();await opening;
  await page.evaluate(()=>new Promise<void>(accept=>requestAnimationFrame(()=>requestAnimationFrame(accept))));
  assert(!await page.locator("#reuse-review").isVisible(),"Old proposal cannot survive journal target changes");
  await page.unroute("**/api/reuse/proposal");
  await page.locator("#journal-width").fill("");
  const rechecked=page.waitForResponse(response=>response.url().endsWith("/api/journal-check"));
  await page.locator("#journal-check").click();await rechecked;
  const proposalResponse = page.waitForResponse(response => response.url().endsWith("/api/reuse/proposal"));
  await page.locator("#journal-review-pdf").click();
  const proposal = await (await proposalResponse).json();
  assert.deepEqual(proposal.changes.map((change:{path:string})=>change.path),["/output/formats"]);
  assert.equal(proposal.claims_policy,"preserved");
  assert.equal(proposal.execution,"not_run");
  await page.locator("#reuse-review").waitFor();
  assert.match((await page.locator("#reuse-changes").textContent())!, /Export formats/);
  assert(await page.locator("#reuse-apply").isDisabled(), "Author review is required");
  await page.screenshot({path:join(evidence,kind+"-pdf-correction-review.png"),fullPage:true});
  await page.locator("#reuse-reviewed").check();
  const rendered = kind === "figure" ? page.waitForResponse(response => response.url().endsWith("/api/render")) : null;
  rendered?.catch(() => {});
  await page.locator("#reuse-apply").click();
  const after = JSON.parse(await editor.inputValue());
  assert.deepEqual(after.claims, before.claims);
  assert.deepEqual(after.uncertainty, proposal.spec.uncertainty);
  assert.deepEqual(after.output.formats, ["png","pdf"]);
  assert.equal(await page.locator("#journal-findings").textContent(), "");
  if (kind === "figure") {
    await rendered; await page.locator('#preview[data-phase="final"]').waitFor();
    assert(!await page.locator("#undo-controls").isDisabled());
  } else {
    assert(await page.locator("#journal-check").isDisabled());
    await page.locator("#save-definition").click();
    await page.getByText("Saved. Audit the paper to check this version.",{exact:true}).waitFor();
    await page.locator("#regenerate").click();
    await page.locator("#notice").filter({hasText:"Audit finished:"}).waitFor();
    await page.locator("#exports a").filter({hasText:"PDF"}).waitFor();
  }
  const options = await page.locator("#journal-file option").all();
  let pdf = "";
  for (const option of options) if ((await option.textContent())?.endsWith(".pdf")) pdf = (await option.getAttribute("value"))!;
  assert(pdf,"A new real PDF export must exist after applying");
  await page.locator("#journal-file").selectOption(pdf);
  const verified = page.waitForResponse(response => response.url().endsWith("/api/journal-check"));
  await page.locator("#journal-check").click();
  const result = await (await verified).json();
  assert.equal(result.report.source.format,"pdf");
  assert(result.report.checks.some((check:{code:string;status:string})=>check.code==="pdf_text_minimum"&&check.status==="passed"));
  assert.equal(result.report.submission_ready,null);
  assert.notEqual(result.report.source.sha256,failed.report.source.sha256);
  await page.locator("#journal-findings h4").waitFor();
  if (kind === "figure") {
    await page.locator("#undo-controls").click();
    assert.deepEqual(JSON.parse(await editor.inputValue()).output.formats,["png"]);
    assert.equal(await page.locator("#journal-findings").textContent(),"");
  }
  receipts.push({kind,reviewed_pdf_correction:true,real_new_pdf_checked:true,pdf_text_evidence:true,old_evidence_invalidated:true,stale_proposal_rejected:true,...(kind==="paper"?{wrong_figure_rejected:true}:{undo_restored_png:true}),science_fields_preserved:true});
}
let browser, activePage: Page | undefined;
try {
  const executable = process.env.GRAPHUNSLOPIFY_BROWSER || (existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined);
  browser = await chromium.launch({ headless: true, ...(executable ? { executablePath: executable } : {}) });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, acceptDownloads: true });
  activePage = page;
  page.setDefaultTimeout(60_000);
  page.on("pageerror", error => failures.push(error.message));
  page.on("request", request => { if (/^https?:/.test(request.url()) && !/^http:\/\/127\.0\.0\.1:/.test(request.url())) external.push(request.url()); });
  await page.goto(await serve(["preview"]));
  await page.locator("#demo").click();
  await page.locator('#preview[data-phase="final"]').waitFor();
  await correctPdf(page, "figure");
  await page.reload();await page.locator("#demo").click();
  await page.locator('#preview[data-phase="final"]').waitFor();
  await check(page, "figure");
  const paper = join(evidence, "paper"); cpSync(join(root, "examples/paper"), paper, { recursive: true });
  execFileSync(python, ["-c", "import sys;from graphunslopify.project import initialize_project,run_project;initialize_project(sys.argv[1]);r=run_project(sys.argv[1]);assert r['exit_code']==0,r", paper], { cwd: evidence, env });
  await page.goto(await serve(["project-preview", paper]));
  await page.locator("#exports a").first().waitFor();
  await check(page, "paper");
  const correctionPaper=join(evidence,"correction-paper");cpSync(join(root,"examples/paper"),correctionPaper,{recursive:true});
  for(const filename of ["training.figure.json","results.figure.json"]){const source=join(correctionPaper,filename),spec=JSON.parse(readFileSync(source,"utf8"));spec.output.formats=["png"];writeFileSync(source,JSON.stringify(spec));}
  execFileSync(python,["-c","import sys;from graphunslopify.project import initialize_project,run_project;initialize_project(sys.argv[1]);r=run_project(sys.argv[1]);assert r['exit_code']==0,r",correctionPaper],{cwd:evidence,env});
  await page.goto(await serve(["project-preview",correctionPaper]));await page.locator("#exports a").first().waitFor();
  await correctPdf(page,"paper");
  assert.deepEqual(failures, []); assert.deepEqual(external, []);
  const result = { kind: "journal-editor-browser-proof", installed: !!process.env.GRAPHUNSLOPIFY_JOURNAL_INSTALLED, receipts, page_errors: failures, external_requests: external };
  writeFileSync(join(evidence, "verification.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(JSON.stringify({ ...result, evidence }));
} catch (problem) {
  await activePage?.screenshot({path:join(evidence,"failure.png"),fullPage:true}).catch(()=>{});
  writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(problem),page_errors:failures},null,2)+"\n");
  throw problem;
} finally {
  await browser?.close();
  await Promise.all(servers.map(process => new Promise<void>(accept => { if (!process.pid || process.exitCode !== null) accept(); else { process.once("exit", () => accept()); process.kill(); } })));
}
