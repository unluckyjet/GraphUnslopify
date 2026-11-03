/** Actual local histories through browser review,strict native rendering and undo. */
import assert from "node:assert/strict";
import {spawn,type ChildProcess} from "node:child_process";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync,appendFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type Page} from "playwright";
declare const document:any;
const root=resolve("."),evidence=process.env.GRAPHUNSLOPIFY_EXPERIMENT_EVIDENCE||mkdtempSync(join(tmpdir(),"gu-experiments-"));
if(process.env.GRAPHUNSLOPIFY_EXPERIMENT_EVIDENCE)mkdirSync(evidence);
const env={...process.env};if(process.env.GRAPHUNSLOPIFY_EXPERIMENT_INSTALLED)delete env.PYTHONPATH;else env.PYTHONPATH=join(root,"python");
const csv=join(evidence,"csv-runs"),tb=join(evidence,"tensorboard-runs");mkdirSync(csv);mkdirSync(tb);
writeFileSync(join(csv,"a.csv"),"step,loss\n0,3\n1,2\n2,1\n");writeFileSync(join(csv,"b.csv"),"step,loss\n0,4\n1,3\n2,2\n");
let server:ChildProcess|undefined,browser,page:Page|undefined;
const errors:string[]=[],external:string[]=[],receipts:unknown[]=[];
async function serve(){server=spawn(process.env.PYTHON||"python",["-m","graphunslopify.cli","preview","--port","0"],{cwd:evidence,env,stdio:["ignore","pipe","pipe"]});
 let stderr="";server.stderr!.on("data",c=>{stderr+=c;});const lines=createInterface({input:server.stdout!});
 return new Promise<string>((ok,bad)=>{lines.once("line",line=>{try{ok(JSON.parse(line).url);}catch(e){bad(e);}});server!.once("error",bad);server!.once("exit",code=>bad(Error(`Server exited ${code}: ${stderr}`)));});}
async function setupTensorboard(){const program=`from pathlib import Path
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from tensorboard.compat.proto.event_pb2 import Event,SessionLog
from tensorboard.compat.proto.summary_pb2 import Summary
root=Path(${JSON.stringify(tb)})
for name,delta in [('a',0),('b',1)]:
 writer=EventFileWriter(str(root/name))
 for step,value in enumerate([3,2,1]):writer.add_event(Event(step=step,wall_time=100+step,summary=Summary(value=[Summary.Value(tag='loss',simple_value=value+delta)])))
 writer.add_event(Event(step=1,wall_time=110,session_log=SessionLog(status=SessionLog.START)))
 writer.add_event(Event(step=1,wall_time=111,summary=Summary(value=[Summary.Value(tag='loss',simple_value=99+delta)])))
 writer.close()
`;
 const child=spawn(process.env.PYTHON||"python",["-c",program],{env,stdio:["ignore","pipe","pipe"]});let output="";child.stdout!.on("data",c=>output+=c);child.stderr!.on("data",c=>output+=c);await new Promise<void>((ok,bad)=>{child.once("error",bad);child.once("exit",c=>c===0?ok():bad(Error(output)));});}
async function list(provider:string,source:string){await page!.locator("#experiment-provider").selectOption(provider);await page!.locator("#experiment-source").fill(source);const response=page!.waitForResponse(r=>r.url().endsWith("/api/experiments/catalog"));await page!.locator("#experiment-list").click();const result=await response;assert.equal(result.status(),200);const catalog=await result.json();await page!.waitForFunction(()=>document.querySelectorAll("#experiment-runs input").length===2);for(const box of await page!.locator("#experiment-runs input").all())await box.check();await page!.locator("#experiment-metric").selectOption("loss");return catalog;}
async function review(){const response=page!.waitForResponse(r=>r.url().endsWith("/api/experiments/review"));await page!.locator("#experiment-review").click();const result=await response;assert.equal(result.status(),200);await page!.locator("#experiment-proposal").waitFor();return result.json();}
async function accept(){await page!.locator("#experiment-reviewed").check();const rendered=page!.waitForResponse(r=>r.url().endsWith("/api/render"));await page!.locator("#experiment-accept").click();const response=await rendered;assert.equal(response.status(),200);const value=await response.json();await page!.locator('#status[data-state="passed"]').waitFor();await page!.locator('#preview[data-phase="final"]').waitFor();return value;}
try{
 await setupTensorboard();const executable=process.env.GRAPHUNSLOPIFY_BROWSER||(existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")?"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":undefined);
 browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});page=await browser.newPage({viewport:{width:1500,height:1100}});page.setDefaultTimeout(60_000);
 page.on("pageerror",e=>errors.push(e.message));page.on("request",r=>{if(/^https?:/.test(r.url())&&!/^http:\/\/127\.0\.0\.1:/.test(r.url()))external.push(r.url());});
 await page.goto(await serve());await page.locator('#kind option[value="line"]').waitFor({state:"attached"});await page.locator("#live").uncheck();await page.locator("#advanced>summary").click();const original=await page.locator("#spec").inputValue();await page.locator("#experiment-import>summary").click();
 const first=await list("csv",csv);assert.equal(first.runs.length,2);assert((await page.locator("#data-summary").textContent())?.includes("No data"));
 const proposal=await review();assert.equal(proposal.report.records,6);assert.equal(proposal.verified,false);assert.equal(proposal.applied,false);assert(await page.locator("#experiment-accept").isDisabled());
 const csvRender=await accept();assert.equal(csvRender.report.status,"passed");assert.equal(csvRender.report.spec.group,"run");assert.equal(csvRender.report.spec.aggregation,"none");
 receipts.push({control:"csv-native",snapshot:first.snapshot,rows:proposal.report.records,status:csvRender.report.status});
 await page.locator("#figure-surface").screenshot({path:join(evidence,"csv-native.png")});
 const download=page.waitForEvent("download");await page.locator("#bundle").click();await (await download).saveAs(join(evidence,"source-free-bundle.zip"));
 await page.locator("#experiment-undo").click();assert((await page.locator("#data-summary").textContent())?.includes("No data"));assert.equal(await page.locator("#spec").inputValue(),original);receipts.push({control:"restore-prior-empty-context",passed:true});
 await review();appendFileSync(join(csv,"a.csv"),"3,0\n");await page.locator("#experiment-reviewed").check();const stale=page.waitForResponse(r=>r.url().endsWith("/api/experiments/accept"));await page.locator("#experiment-accept").click();const refused=await stale;assert.equal(refused.status(),400);assert.match((await refused.json()).error,/changed/);assert((await page.locator("#data-summary").textContent())?.includes("No data"));receipts.push({control:"changed-source-refused",passed:true});
 await list("csv",csv);await review();await page.locator("#spec").fill("{");assert(await page.locator("#experiment-proposal").isHidden());assert(await page.locator("#experiment-review").isDisabled());await page.locator("#spec").fill(original);receipts.push({control:"invalid-json-clears-stale-review-without-error",passed:true});
 let release:()=>void=()=>{},started:()=>void=()=>{};const held=new Promise<void>(r=>{release=r;}),entered=new Promise<void>(r=>{started=r;});
 await page.route("**/api/experiments/review",async route=>{const response=await route.fetch();started();await held;await route.fulfill({response});});
 await page.locator("#experiment-review").click();await entered;await page.locator("#spec").fill(JSON.stringify({...JSON.parse(original),title:"Newer edit"}));release();await page.waitForResponse(r=>r.url().endsWith("/api/experiments/review"));await page.unroute("**/api/experiments/review");await page.locator("#experiment-review").waitFor({state:"visible"});assert(await page.locator("#experiment-proposal").isHidden());receipts.push({control:"late-review-cannot-overwrite-newer-edit",passed:true});
 appendFileSync(join(csv,"a.csv"),"4,\n");await list("csv",csv);const excluded=await review();assert.equal(excluded.report.excluded_records,1);await page.locator("#experiment-reviewed").check();assert(await page.locator("#experiment-accept").isDisabled());await page.locator("#experiment-exclusions").check();assert(await page.locator("#experiment-accept").isEnabled());const excludedRender=await accept();assert.equal(excludedRender.report.status,"passed");const priorCSV=await page.locator("#spec").inputValue();receipts.push({control:"exclusions-require-author-choice",passed:true,validRows:7});
 const tbCatalog=await list("tensorboard",tb);assert.equal(tbCatalog.runs.length,2);assert(await page.locator("#experiment-review").isDisabled());assert.match((await page.locator("#experiment-status").textContent())!,/duplicate steps/);await page.locator("#experiment-kind").selectOption("scatter");const tbProposal=await review();assert.equal(tbProposal.report.records,8);assert.equal(tbProposal.report.duplicate_steps,2);const tbRender=await accept();assert.equal(tbRender.report.status,"passed");assert.equal(tbRender.report.spec.kind,"scatter");receipts.push({control:"tensorboard-restart-raw-records-native",rows:8,duplicates:2,status:tbRender.report.status});
 await page.locator("#figure-surface").screenshot({path:join(evidence,"tensorboard-native.png")});
 const appliedTB=await page.locator("#spec").inputValue();await page.locator("#spec").fill(JSON.stringify({...JSON.parse(appliedTB),title:"Later author edit"}));assert(await page.locator("#experiment-undo").isDisabled());await page.locator("#spec").fill(appliedTB);assert(await page.locator("#experiment-undo").isEnabled());receipts.push({control:"undo-preserves-later-author-edits",passed:true});
 const restoredResponse=page.waitForResponse(r=>r.url().endsWith("/api/render"));await page.locator("#experiment-undo").click();const restored=await(await restoredResponse).json();assert.equal(restored.report.status,"passed");assert.equal(await page.locator("#spec").inputValue(),priorCSV);assert.match((await page.locator("#data-summary").textContent())!,/7 rows/);receipts.push({control:"undo-restores-prior-owned-dataset-and-native-checks",passed:true});
 await page.setViewportSize({width:430,height:920});await page.locator("#experiment-import").screenshot({path:join(evidence,"mobile-import.png")});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));receipts.push({control:"mobile-no-horizontal-overflow",passed:true});
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 writeFileSync(join(evidence,"verification.json"),JSON.stringify({controls:receipts,errors,external,csvSpec:csvRender.report.spec,tensorboardSpec:tbRender.report.spec,sourceCSV:readFileSync(join(csv,"b.csv"),"utf8")},null,2)+"\n");
 console.log(JSON.stringify({evidence,controls:receipts.length,errors,external}));
}catch(error){writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(error),controls:receipts,errors,external},null,2)+"\n");if(page)await page.screenshot({path:join(evidence,"failure.png"),fullPage:true});throw error;}
finally{await browser?.close();server?.kill("SIGTERM");}
