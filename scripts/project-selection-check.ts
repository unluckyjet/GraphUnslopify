/** Actual mixed-paper shared review, strict outputs, undo and stale/late/failed UI evidence. */
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, relative } from "node:path";
import { createInterface } from "node:readline";
import { chromium, type Page } from "playwright";

declare const document: { querySelector(selector: string): { textContent: string; hidden: boolean; disabled: boolean; checked: boolean; getAttribute(name:string):string|null } | null; documentElement: { scrollWidth: number } };
declare const window: { innerWidth: number };
const python = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const evidence = mkdtempSync(join(tmpdir(), "gu-selection-paper-check-")), paper = join(evidence, "paper ü with spaces");
const hash = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");
const cli = (...args: string[]) => { const r = spawnSync(python, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 180_000, maxBuffer: 20 * 1024 * 1024 }); assert.ok(r.status === 0 || r.status === 2, r.stderr); return JSON.parse(r.stdout); };
function inventory(root: string): Record<string, string> {
  const values: Record<string, string> = {};
  function walk(folder: string) { for (const e of readdirSync(folder, { withFileTypes: true })) { const p = join(folder, e.name); if (e.isDirectory()) walk(p); else if (e.isFile()) values[relative(root, p)] = hash(readFileSync(p)); } }
  walk(root);return values;
}
cli("demo", paper, "--json");
const second = JSON.parse(readFileSync(join(paper, "figure.json"), "utf8"));
second.kind = "table"; second.title = "Second figure";second.output.stem = "second";second.uncertainty.display = "bar";second.output.formats = ["png", "pdf"];second.highlight = "best_per_row";
writeFileSync(join(paper, "second.json"), JSON.stringify(second));cli("audit-init", paper);
const program = readFileSync(join(paper,"figure.py"),"utf8").split(/(?<=\n)/);let insert = 0;program.forEach((line,i) => { if (line.startsWith("from __future__")) insert = i+1; });
program.splice(insert,0,"_counter = __import__('pathlib').Path(__file__).with_name('executions.txt')\n_counter.write_text((_counter.read_text() if _counter.exists() else '') + 'x')\n");writeFileSync(join(paper,"authored.py"),program.join(""));
const manifestPath = join(paper,"graphunslopify.json"), manifest = JSON.parse(readFileSync(manifestPath,"utf8"));manifest.figures.push({id:"authored",script:"authored.py",data:"results.csv"});writeFileSync(manifestPath,JSON.stringify(manifest));
cli("project-init", paper);
const initial = cli("project-run", paper, "--no-baseline");assert.equal(initial.exit_code, 0);
const inspections = cli("project-inspections", paper);
assert.equal(cli("project-inspect-pdf", paper, "--id", "external", "--pdf", resolve("python/tests/fixtures/project-review-pages.pdf"), "--pages", "1", "--dpi", "72", "--expected-revision", inspections.revision).exit_code, 2);
const config = join(paper, "graphunslopify-project/project.json"), originalConfig = readFileSync(config), data = readFileSync(join(paper, "results.csv"));
const originals = Object.fromEntries(["figure.json", "second.json", "authored.py"].map(n => [n, hash(readFileSync(join(paper, n)))]));
const firstHistory = inventory(initial.directory);
const server = spawn(python, ["-m", "graphunslopify.cli", "project-preview", paper, "--port", "0"], { env, stdio: ["ignore", "pipe", "pipe"] });
let stderr = "";server.stderr.on("data", chunk => { stderr += chunk; });
const lines = createInterface({ input: server.stdout });
const timer = setTimeout(() => server.kill(), 30_000);
const url = await new Promise<string>((accept, reject) => { lines.once("line", line => { try { accept(JSON.parse(line).url); } catch (e) { reject(e); } });server.once("exit", code => reject(Error(`Server exited ${code}: ${stderr}`))); });clearTimeout(timer);
const workflows: string[] = [], errors: string[] = [], external: string[] = [];
let browser, currentPage: Page | undefined;
try {
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  browser = await chromium.launch({ ...(existsSync(mac) ? { executablePath: mac } : {}), headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });currentPage = page;page.setDefaultTimeout(60_000);
  page.on("pageerror", e => errors.push(e.message));page.on("request", r => { if (!r.url().startsWith(url) && !r.url().startsWith("data:") && !r.url().startsWith("blob:")) external.push(r.url()); });
  await page.goto(url);
  await page.waitForFunction(() => document.querySelector("#notice")?.textContent.startsWith("Ready."));
  const token = await page.locator('meta[name="preview-token"]').getAttribute("content");assert.ok(token);
  const api = async (path:string, body?:unknown, expected=200) => { const r = await page.request[body === undefined ? "get" : "post"](url+path,{headers:{"X-Preview-Token":token},...(body === undefined ? {} : {data:body})});assert.equal(r.status(),expected,await r.text());return r.json(); };
  const executions = () => readFileSync(join(paper,"executions.txt"),"utf8").length;
  const open = async () => page.locator("#selection-panel").evaluate(n => n.setAttribute("open",""));
  const pick = async (id:string) => page.locator('#selection-figures input[value="'+id+'"]').check();
  const propose = async (button="selection-review") => { const [r] = await Promise.all([page.waitForResponse(r => r.url().endsWith("/api/selection-review") && r.request().method()==="POST"),page.locator("#"+button).click()]);assert.equal(r.status(),200,await r.text());const plan = await r.json();await page.waitForFunction(() => document.querySelector("#selection-apply")?.disabled===false);return plan; };
  const save = async () => { await page.locator("#selection-apply").click();await page.waitForFunction(() => document.querySelector("#notice")?.textContent.startsWith("Saved selected presentation."));await page.waitForFunction(() => document.querySelector("#selection-settings")?.disabled===false);return api("/api/state"); };
  const audit = async (selective=false) => { await page.locator(selective ? "#regenerate" : "#audit").click();await page.waitForFunction(() => document.querySelector("#running")?.hidden===false);await page.waitForFunction(() => document.querySelector("#running")?.hidden===true);const s = await api("/api/state");return api("/api/event?id="+s.job.result.id); };
  await open();assert.equal(executions(),1);assert.equal(await page.locator("#selection-review").isDisabled(),true);
  await pick("figure");await pick("authored");await pick("pdf:external");
  await page.locator('#selection-figures input[value="figure"]').focus();await page.keyboard.press("Space");await page.keyboard.press("Space");
  await page.locator("#selection-dpi").fill("0");assert.equal(await page.locator("#selection-review").isDisabled(),true);
  await page.locator("#selection-dpi").fill("72.5");assert.equal(await page.locator("#selection-review").isDisabled(),true);
  await page.locator("#selection-dpi").fill("144");workflows.push("actual checkbox keyboard selection and invalid numeric drafts cannot silently save defaults");
  const before = await api("/api/state"), firstPlan = await propose();
  assert.deepEqual(firstPlan.affected_ids,["figure"]);assert.deepEqual(firstPlan.excluded.map((r:{id:string})=>r.id).sort(),["authored","pdf:external"]);
  assert.equal(firstPlan.execution,"not_run");assert.equal((await api("/api/state")).history.length,before.history.length);assert.equal(executions(),1);assert.equal(hash(readFileSync(config)),hash(originalConfig));assert.equal(await page.locator("#audit").isDisabled(),true);
  workflows.push("real resolved selected review excludes authored Python and numerical-untested PDFs without writes or program execution");
  await page.locator("#selection-proposal").screenshot({path:join(evidence,"desktop.png")});await page.setViewportSize({width:390,height:1000});await page.locator("#selection-proposal").screenshot({path:join(evidence,"mobile.png")});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);await page.setViewportSize({width:1440,height:1100});
  workflows.push("actual desktop and mobile presentation review remains readable without horizontal overflow");
  let arrived!:()=>void, release!:()=>void;const ready=new Promise<void>(r=>{arrived=r;}),held=new Promise<void>(r=>{release=r;});
  await page.route("**/api/selection-apply",async route=>{const response=await route.fetch();arrived();await held;await route.fulfill({response});});
  await page.locator("#selection-apply").click();await ready;assert.equal(await page.locator("#audit").isDisabled(),true);assert.equal(await page.locator("#shared-json").isDisabled(),true);assert.equal(executions(),1);
  release();await page.waitForFunction(()=>document.querySelector("#selection-settings")?.disabled===false);await page.unroute("**/api/selection-apply");let state=await api("/api/state");const firstID=state.history.find((e:{action:string})=>e.action==="selection").id;
  assert.deepEqual(state.figure_settings,{figure:{output:{dpi:144}}});assert.equal(state.status,"needs_audit");await page.waitForFunction(()=>document.querySelector("#review-status")?.getAttribute("data-state")==="needs-audit");assert.equal(executions(),1);
  workflows.push("a held genuine Apply reply locks other writers and audits while saving only one owned settings event");
  const selective=await audit(true);assert.equal(selective.result.exit_code,0);let rows=Object.fromEntries(selective.result.audit.figures.map((r:{id:string})=>[r.id,r]));assert.equal(rows.figure.execution.mode,"executed");assert.equal(rows.second.execution.mode,"reused");assert.equal(rows.authored.execution.mode,"executed");assert.deepEqual(rows.second.report,initial.audit.figures.find((r:{id:string})=>r.id==="second").report);assert.equal(executions(),2);
  workflows.push("actual selective audit rerenders one selected JSON figure and the authored program while preserving the untouched original report");
  await open();await page.locator("#selection-all").click();assert.equal(await page.locator('#selection-figures input:checked').count(),2);
  const labels = {title:"Reviewed experiment results", "x-label":"Measured step", "y-label":"Observed score",
    "legend-title":"Experiment groups"};
  const policies = {"legend-show":"true", "legend-position":"outside_right", "legend-style":"box",
    size:"double_column", preset:"paper_compact", grid:"true"};
  for (const [id, value] of Object.entries(labels)) await page.locator("#selection-" + id).fill(value);
  for (const [id, value] of Object.entries(policies)) await page.locator("#selection-" + id).selectOption(value);
  await page.locator("#selection-dpi").fill("150");
  const both = await propose();
  assert.deepEqual(both.affected_ids, ["figure","second"]);
  const linePlan = both.figures.find((row: {id:string}) => row.id === "figure");
  const tablePlan = both.figures.find((row: {id:string}) => row.id === "second");
  assert.ok(linePlan.changes.some((change: {path:string}) => change.path === "/legend/title"));
  assert.ok(linePlan.changes.some((change: {path:string}) => change.path === "/x/label"));
  assert.deepEqual(tablePlan.before.legend, tablePlan.after.legend);
  assert.match(await page.locator("#selection-rows").innerText(), /This figure has no series legend/);
  await page.setViewportSize({width:390,height:1000});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth), true);
  await page.locator("#selection-proposal").screenshot({path:join(evidence,"multi-label-mobile.png")});
  await page.setViewportSize({width:1440,height:1100});
  state=await save();const secondID=state.history.find((e:{action:string})=>e.action==="selection").id;
  const full=await audit();assert.equal(full.result.exit_code,0);rows=Object.fromEntries(full.result.audit.figures.map((r:{id:string})=>[r.id,r]));assert.equal(rows.figure.report.spec.output.dpi,150);assert.equal(rows.second.report.spec.output.dpi,150);assert.equal(executions(),3);
  for (const id of ["figure","second"]) {
    const original = initial.audit.figures.find((row: {id:string}) => row.id === id).report;
    const current = rows[id].report;
    assert.deepEqual(current.claims, original.claims);
    assert.equal(current.spec.title, labels.title);
    assert.equal(current.spec.x.label, labels["x-label"]);
    assert.equal(current.spec.y.label, labels["y-label"]);
    assert.deepEqual(current.spec.x, {...original.spec.x,label:labels["x-label"]});
    assert.deepEqual(current.spec.y, {...original.spec.y,label:labels["y-label"]});
    assert.equal(current.spec.output.size, "double_column");
    assert.equal(current.spec.style.preset, "paper_compact");
    assert.equal(current.spec.style.grid, true);
  }
  assert.equal(rows.figure.report.spec.legend.title, labels["legend-title"]);
  assert.equal(rows.figure.report.spec.legend.position, "outside_right");
  assert.equal(rows.second.report.spec.legend.title, undefined);
  for (const id of Object.keys(labels)) await page.locator("#selection-" + id).fill("");
  for (const id of Object.keys(policies)) await page.locator("#selection-" + id).selectOption("");
  workflows.push("real multi-select Apply renders reviewed labels, legend, width and style on selected figures and preserves claims and data bindings");
  const beforeUnavailableSelection = await page.locator('#selection-figures input:checked').count();assert.equal(beforeUnavailableSelection,2);
  const intactManifest = readFileSync(manifestPath), beforeUnavailableConfig = hash(readFileSync(config)), beforeUnavailableHistory = (await api("/api/state")).history.length;
  try {
    writeFileSync(manifestPath,"{");await page.locator("#refresh").click();
    await page.waitForFunction(() => document.querySelector("#project-status")?.textContent === "Project unavailable");
    assert.equal(await page.locator("#selection-reset").isDisabled(),true);assert.equal(await page.locator("#selection-apply").isDisabled(),true);assert.equal(await page.locator("#audit").isDisabled(),true);
  } finally { writeFileSync(manifestPath,intactManifest); }
  await page.locator("#refresh").click();await page.waitForFunction(() => document.querySelector("#selection-settings")?.disabled === false);
  const afterUnavailableSelection = await page.locator('#selection-figures input:checked').count();
  const selectionRecovery = { before:beforeUnavailableSelection, after:afterUnavailableSelection, manifest_restored:hash(readFileSync(manifestPath))===hash(intactManifest), config_unchanged:hash(readFileSync(config))===beforeUnavailableConfig, history_unchanged:(await api("/api/state")).history.length===beforeUnavailableHistory, authored_executions:executions() };
  writeFileSync(join(evidence,"unavailable-selection-control.json"),JSON.stringify(selectionRecovery,null,2));
  assert.equal(afterUnavailableSelection,beforeUnavailableSelection,"A temporary unavailable project must not erase user selection");assert.equal(selectionRecovery.config_unchanged,true);assert.equal(selectionRecovery.history_unchanged,true);assert.equal(executions(),3);
  workflows.push("actual unavailable manifest disables writes and retains selected figures after byte-exact restoration without configuration/history/program changes");
  await open();const reset=await propose("selection-reset");assert.deepEqual(reset.affected_ids,["figure","second"]);state=await save();assert.deepEqual(state.figure_settings,{});const resetID=state.history.find((e:{action:string})=>e.action==="selection").id;
  workflows.push("reviewed reset removes selected overrides and returns to the original definitions and paper defaults");
  for(const id of [resetID,secondID,firstID]){await page.locator("#selection-undo-event").selectOption(id);await propose("selection-undo");await save();}
  assert.equal(hash(readFileSync(config)),hash(originalConfig));assert.equal(executions(),3);
  workflows.push("three explicit reviewed undo steps restore the exact original v1 configuration bytes and retain complete history");
  await page.locator("#selection-none").click();await pick("figure");await page.locator("#selection-dpi").fill("160");
  let oldArrive!:()=>void,oldRelease!:()=>void;const oldReady=new Promise<void>(r=>{oldArrive=r;}),oldHeld=new Promise<void>(r=>{oldRelease=r;});let heldOnce=false;
  await page.route("**/api/selection-review",async route=>{if(heldOnce){await route.continue();return;}heldOnce=true;const response=await route.fetch();oldArrive();await oldHeld;await route.fulfill({response});});
  const olderResponse=page.waitForResponse(r=>r.url().endsWith("/api/selection-review") && r.request().postDataJSON()?.settings?.output?.dpi===160);await page.locator("#selection-review").click();await oldReady;await page.locator("#selection-cancel").click();await page.locator("#selection-dpi").fill("170");const newer=await propose();oldRelease();await (await olderResponse).finished();await page.unroute("**/api/selection-review");assert.equal(newer.figures[0].after.output.dpi,170);assert.ok((await page.locator("#selection-rows").innerText()).includes("170"));await page.locator("#selection-cancel").click();assert.equal(hash(readFileSync(config)),hash(originalConfig));
  workflows.push("cancelled older genuine review replies cannot replace newer selected intent");
  await propose();const oldHistory=(await api("/api/state")).history.length;
  let stateArrive!:()=>void,stateRelease!:()=>void;const stateReady=new Promise<void>(r=>{stateArrive=r;}),stateHeld=new Promise<void>(r=>{stateRelease=r;});let heldState=false;
  await page.route("**/api/state",async route=>{if(heldState){await route.continue();return;}heldState=true;const response=await route.fetch();stateArrive();await stateHeld;await route.fulfill({response});});
  const olderState=page.waitForResponse(r=>r.url().endsWith("/api/state") && r.request().method()==="GET");await stateReady;
  writeFileSync(join(paper,"results.csv"),Buffer.concat([data,Buffer.from("\n")]));await page.locator("#selection-apply").click();await page.waitForFunction(()=>document.querySelector("#error")?.textContent.includes("changed"));assert.equal((await api("/api/state")).history.length,oldHistory);assert.equal(hash(readFileSync(config)),hash(originalConfig));assert.equal(await page.locator("#selection-apply").isDisabled(),true);writeFileSync(join(paper,"results.csv"),data);stateRelease();await (await olderState).finished();await page.unroute("**/api/state");await page.locator("#refresh").click();
  workflows.push("genuine changed source data refuses a previously reviewed Apply before any new event or source write");
  await api("/api/selection-review",{ids:["figure"],settings:{claims:[]},expected_revision:(await api("/api/state")).revision},400);assert.equal(hash(readFileSync(config)),hash(originalConfig));
  workflows.push("the real authenticated API rejects scientific and binding changes through the presentation endpoint");
  const originalFigure=readFileSync(join(paper,"figure.json"));const falseSpec=JSON.parse(originalFigure.toString());falseSpec.claims=[{...falseSpec.claims[0],subject:"base",reference:"ours"}];writeFileSync(join(paper,"figure.json"),JSON.stringify(falseSpec));await page.locator("#refresh").click();await page.waitForFunction(()=>document.querySelector("#selection-review")?.disabled===false);await propose();await save();const rejected=await audit();assert.equal(rejected.result.exit_code,2);assert.equal(rejected.result.audit.figures.find((r:{id:string})=>r.id==="figure").status,"failed");assert.equal(executions(),4);await page.waitForFunction(()=>document.querySelector("#review-context")?.textContent.includes("Whole-paper audit: failed"));
  workflows.push("presentation batch edits never weaken a real false claim: final paper audit still exits strict2");
  writeFileSync(join(paper,"figure.json"),originalFigure);
  assert.equal(hash(readFileSync(join(paper,"results.csv"))),hash(data));assert.deepEqual(Object.fromEntries(Object.keys(originals).map(n=>[n,hash(readFileSync(join(paper,n)))])),originals);assert.deepEqual(inventory(initial.directory),firstHistory);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={status:"passed",workflows,authored_executions:executions(),original_inputs_and_first_history_unchanged:true,page_errors:errors,external_requests:external,evidence};writeFileSync(join(evidence,"verification.json"),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
} catch(problem){
  const view = await currentPage?.evaluate(() => ({
    notice:document.querySelector("#notice")?.textContent,error:document.querySelector("#error")?.textContent,
    project:document.querySelector("#project-status")?.textContent,selection:document.querySelector("#selection-count")?.textContent,
    selected:["figure","second","authored","pdf:external"].map(id => ({id,checked:document.querySelector('#selection-figures input[value="'+id+'"]')?.checked})),
    resetDisabled:document.querySelector("#selection-reset")?.disabled,settingsDisabled:document.querySelector("#selection-settings")?.disabled,
    reviewDisabled:document.querySelector("#selection-review")?.disabled,applyDisabled:document.querySelector("#selection-apply")?.disabled,
    runningHidden:document.querySelector("#running")?.hidden,
  })).catch(error => ({captureError:String(error)}));
  writeFileSync(join(evidence,"failure-state.json"),JSON.stringify({error:String(problem),view,workflows,page_errors:errors,external_requests:external},null,2));
  await currentPage?.screenshot({path:join(evidence,"failure.png"),fullPage:true}).catch(()=>{});console.error(JSON.stringify({evidence,error:String(problem)}));throw problem;
}
finally{await browser?.close();server.kill();lines.close();}
