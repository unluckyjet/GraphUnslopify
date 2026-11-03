/** Actual paper geometry, original-definition edits, reuse and owner refusals. */
import assert from "node:assert/strict";
import {spawn,execFileSync,type ChildProcess} from "node:child_process";
import {createHash} from "node:crypto";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type Page} from "playwright";
declare const document:any;
declare const window:any;
const evidence=process.env.GRAPHUNSLOPIFY_PAPER_INSPECTOR_EVIDENCE||mkdtempSync(join(tmpdir(),"gu-paper-inspector-"));
if(process.env.GRAPHUNSLOPIFY_PAPER_INSPECTOR_EVIDENCE)mkdirSync(evidence);
const paper=join(evidence,"paper with spaces"),python=process.env.PYTHON||"python";
const env={...process.env};if(process.env.GRAPHUNSLOPIFY_PAPER_INSPECTOR_INSTALLED)delete env.PYTHONPATH;else env.PYTHONPATH=resolve("python");
const setup=`from pathlib import Path
import copy,json,sys
import graphunslopify
from graphunslopify import Figure
from graphunslopify.project import initialize_project,run_project
p=Path(sys.argv[1]);p.mkdir()
rows=['step,score,seed,model']
for step in range(1,4):
 for model,offset in [('a',0),('b',2)]:
  for seed,value in [('one',1),('two',3),('three',5)]:rows.append(f'{step},{step+value+offset},{seed},{model}')
(p/'runs.csv').write_text('\\n'.join(rows)+'\\n')
s={'kind':'line','group':'model','data':{'path':'runs.csv'},'x':{'field':'step','label':'Step'},'y':{'field':'score','label':'Score'},'aggregation':'mean','uncertainty':{'kind':'std','over':'seed'}}
(p/'line.json').write_text(json.dumps(s))
b={**copy.deepcopy(s),'kind':'bar','orientation':'horizontal','output':{'stem':'bars','formats':['png','pdf']}}
a={**copy.deepcopy(s),'output':{'stem':'authored','formats':['png','pdf']}}
(p/'authored.py').write_text(Figure(a).translate(api='local')['code'])
(p/'graphunslopify.json').write_text(json.dumps({'schema_version':1,'figures':[{'id':'line','spec':'line.json'},{'id':'bars','spec':b},{'id':'authored','script':'authored.py','data':'runs.csv'}]}))
initialize_project(p)
r=run_project(p,baseline=None)
assert r['exit_code']==0,(r['errors'],r['policy_errors'])
print(json.dumps({'event':r['id'],'counts':r['audit']['execution_counts'],'package_root':str(Path(graphunslopify.__file__).parent)}))`;
let server:ChildProcess|undefined,browser,page:Page|undefined;
const errors:string[]=[],external:string[]=[];
try {
 const initial=JSON.parse(execFileSync(python,["-c",setup,paper],{env,cwd:evidence,encoding:"utf8",timeout:180_000}));
 if(process.env.GRAPHUNSLOPIFY_PAPER_INSPECTOR_INSTALLED)assert(!initial.package_root.startsWith(resolve("python")));
 const original=JSON.parse(readFileSync(join(paper,"line.json"),"utf8")),data=readFileSync(join(paper,"runs.csv"));
 server=spawn(python,["-m","graphunslopify.cli","project-preview",paper,"--port","0"],{env,cwd:evidence,stdio:["ignore","pipe","pipe"]});
 let stderr="";server.stderr!.on("data",c=>{stderr+=c;});const lines=createInterface({input:server.stdout!});
 const url=await new Promise<string>((ok,bad)=>{lines.once("line",line=>{try{ok(JSON.parse(line).url);}catch(e){bad(e);}});server!.once("error",bad);server!.once("exit",code=>bad(Error(`Server exited ${code}: ${stderr}`)));});
 const executable=process.env.GRAPHUNSLOPIFY_BROWSER||(existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")?"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":undefined);
 browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});page=await browser.newPage({viewport:{width:1450,height:1100}});page.setDefaultTimeout(120_000);
 page.on("pageerror",e=>errors.push(e.message));page.on("request",r=>{if(/^https?:/.test(r.url())&&new URL(r.url()).origin!==new URL(url).origin)external.push(r.url());});
 await page.goto(url);await page.waitForFunction(()=>!document.getElementById("inspect-element").disabled);
 const token=(await page.locator('meta[name="preview-token"]').getAttribute("content"))!;
 const api=async(path:string,body?:unknown)=>{const response=body===undefined?await page!.request.get(url+path,{headers:{"X-Preview-Token":token}}):await page!.request.post(url+path,{headers:{"X-Preview-Token":token},data:body});return {status:response.status(),value:await response.json()};};
 const definition=async()=>JSON.parse(await page!.locator("#definition").inputValue());
 const ready=async()=>{await page!.waitForFunction(()=>!document.getElementById("inspect-element").disabled);await page!.locator("#preview").evaluate((img:any)=>img.decode());};
 const summary=await page.locator("#event-summary").textContent();
 await page.locator("#inspect-element").click();assert.equal(await page.locator("#paper-inspector-host #preview").count(),1);
 await page.getByRole("button",{name:/^Inspect Horizontal axis/}).click();assert(await page.locator("#control-x-label").isVisible());assert(await page.locator("#control-y-label").isHidden());
 await page.getByRole("button",{name:/^Inspect Uncertainty/}).first().focus();await page.keyboard.press("Enter");assert(await page.locator("#control-uncertainty-kind").isVisible());assert(await page.locator("#control-x-label").isHidden());
 assert.deepEqual(await definition(),original);assert.equal(await page.locator("#event-summary").textContent(),summary);
 await page.screenshot({path:join(evidence,"desktop-interval.png"),fullPage:true});
 await page.locator("#definition-inspector-layout").screenshot({path:join(evidence,"desktop-selected-settings.png")});
 await page.locator("#inspector-element").selectOption("0");assert(await page.locator("#control-title").isVisible());
 await page.getByRole("button",{name:/^Inspect Horizontal axis/}).click();
 await page.locator("#control-x-label").fill("Revised step");await page.locator("#control-x-label").blur();
 await page.waitForFunction(()=>JSON.parse(document.getElementById("definition").value).x.label==="Revised step");assert(await page.locator("#inspect-element").isDisabled());assert(await page.locator("#preview").isHidden());
 await page.locator("#undo-controls").click();assert.deepEqual(await definition(),original);
 await page.locator("#control-x-label").fill("Revised step");await page.locator("#control-x-label").blur();
 const saved=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/definition");await page.locator("#save-definition").click();assert.equal((await saved).status(),200);
 await page.waitForFunction(()=>!document.getElementById("audit").disabled);await page.locator("#audit").click();
 await page.waitForFunction(()=>!document.getElementById("running").hidden);await page.waitForFunction(()=>document.getElementById("running").hidden&&document.getElementById("event-summary").textContent.includes("scientific checks:"));await ready();
 let state=(await api("/api/state")).value,latest=state.job.result.id;assert.equal(state.job.result.status,"passed");
 const after=JSON.parse(readFileSync(join(paper,"line.json"),"utf8"));assert.deepEqual(after,{...original,x:{...original.x,label:"Revised step"}});
 await page.locator("#regenerate").click();await page.waitForFunction(()=>!document.getElementById("running").hidden);await page.waitForFunction(()=>document.getElementById("running").hidden&&document.getElementById("event-summary").textContent.includes("scientific checks:"));await ready();
 state=(await api("/api/state")).value;latest=state.job.result.id;assert.equal(state.job.result.status,"passed");
 const reused=(await api("/api/event?id="+latest)).value;assert.deepEqual(reused.result.audit.execution_counts,{executed:1,reused:2,not_run:0});
 await page.locator("#history").selectOption(initial.event);await page.waitForFunction(()=>document.getElementById("inspect-element").disabled);assert.deepEqual(await definition(),after);
 assert.equal((await api("/api/element-map",{event:initial.event,figure:"line",expected_revision:state.revision})).status,400);
 await page.locator("#history").selectOption(latest);await ready();
 await page.locator("#history-figure").selectOption("bars");await page.waitForFunction(()=>document.getElementById("inspect-element").disabled);
 await page.locator('[data-figure="bars"]').click();await ready();await page.locator("#inspect-element").click();
 await page.getByRole("button",{name:/^Inspect Horizontal axis/}).click();assert(await page.locator("#control-y-label").isVisible());assert(await page.locator("#control-x-label").isHidden());
 const packet=(await api("/api/element-map",{event:latest,figure:"bars",expected_revision:state.revision})).value;
 const interval=packet.edit_map.elements.targets.find((t:any)=>t.role==="uncertainty"),points=interval.shapes[0].points;
 const point:[number,number]=[(points[0][0]+points[1][0])/2,(points[0][1]+points[1][1])/2],box=(await page.locator("#preview").boundingBox())!;
 await page.mouse.click(box.x+point[0]*box.width/packet.edit_map.image.width,box.y+point[1]*box.height/packet.edit_map.image.height);assert(await page.locator("#control-uncertainty-kind").isVisible());
 await page.setViewportSize({width:430,height:920});assert(await page.locator("#control-uncertainty-over").isVisible());assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));await page.screenshot({path:join(evidence,"mobile-interval.png"),fullPage:true});
 await page.locator("#inspector-all").click();await page.setViewportSize({width:1450,height:1100});
 await page.locator("#history-figure").selectOption("line");await page.locator('[data-figure="line"]').click();await ready();
 for(const wrong of ["sha256","width"]) {
  await page.route("**/api/element-map",async route=>{const response=await route.fetch(),p=await response.json();p.edit_map.image[wrong]=wrong==="width"?1:"0".repeat(64);await route.fulfill({response,json:p});});
  const reply=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/element-map"&&r.status()===200);
  await page.locator("#history-figure").selectOption("line");await reply;await page.waitForFunction(()=>!document.getElementById("preview").hidden&&document.getElementById("preview").complete&&document.getElementById("preview").naturalWidth>0);await page.locator("#preview").evaluate((img:any)=>img.decode());assert(await page.locator("#inspect-element").isDisabled());
  await page.unroute("**/api/element-map");await page.locator("#history-figure").selectOption("line");await ready();
 }
 let held=false,release:(()=>void)|undefined;
 await page.route("**/api/element-map",async route=>{const response=await route.fetch();held=true;await new Promise<void>(done=>{release=done;});await route.fulfill({response});});
 await page.locator("#history-figure").selectOption("line");
 for(let i=0;i<200&&!held;i++)await new Promise(done=>setTimeout(done,25));assert(held&&release);
 await page.locator('[data-figure="bars"]').click();const late=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/element-map");release();await late;
 await page.waitForFunction(()=>document.getElementById("selected-title").textContent==="bars"&&document.getElementById("inspect-element").disabled);assert.equal((await definition()).kind,"bar");await page.unroute("**/api/element-map");
 await page.locator("#history-figure").selectOption("authored");await page.locator('[data-figure="authored"]').click();await page.waitForFunction(()=>document.getElementById("selected-title").textContent==="authored");assert(await page.locator("#inspect-element").isDisabled());assert(await page.locator("#definition").getAttribute("readonly")!==null);
 await page.locator("#history-figure").selectOption("line");await page.locator('[data-figure="line"]').click();await ready();
 const failedIntent={...after,claims:[{kind:"beats_everywhere",subject:"a",reference:"b"}]};
 if(!await page.locator("#definition-panel").evaluate((el:any)=>el.open))await page.locator("#definition-panel > summary").click();
 await page.locator("#definition").fill(JSON.stringify(failedIntent,null,2));const savedFailure=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/definition");await page.locator("#save-definition").click();assert.equal((await savedFailure).status(),200);
 await page.waitForFunction(()=>!document.getElementById("audit").disabled);await page.locator("#audit").click();await page.waitForFunction(()=>!document.getElementById("running").hidden);await page.waitForFunction(()=>document.getElementById("running").hidden&&document.getElementById("event-summary").textContent.includes("scientific checks:"));await ready();
 assert.equal((await api("/api/state")).value.job.result.status,"failed");const failedSummary=await page.locator("#event-summary").textContent();await page.locator("#inspect-element").click();await page.getByRole("button",{name:/^Inspect Horizontal axis/}).click();assert.equal(await page.locator("#event-summary").textContent(),failedSummary);assert.deepEqual((await definition()).claims,failedIntent.claims);await page.screenshot({path:join(evidence,"failed-science-remains-failed.png"),fullPage:true});
 assert.deepEqual(readFileSync(join(paper,"runs.csv")),data);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 const proof={current_native_png:true,axis_pointer:true,interval_keyboard:true,whole_figure:true,selection_preserves_intent_and_status:true,owned_form_and_image:true,real_edit_undo_save_and_audit:true,selective_reuse_maps:true,historical_revision_refused:true,wrong_definition_refused:true,late_reply_refused:true,inline_horizontal_bar_binding:true,errorbar_pointer:true,mobile_scope:true,wrong_png_hash_refused:true,wrong_dimensions_refused:true,authored_read_only:true,failed_science_remains_failed:true,data_sha256:createHash("sha256").update(data).digest("hex"),page_errors:errors,external_requests:external};writeFileSync(join(evidence,"verification.json"),JSON.stringify(proof,null,2));console.log(JSON.stringify({proof,evidence}));
} catch(error) {
 if(page){await page.screenshot({path:join(evidence,"failure.png"),fullPage:true}).catch(()=>{});writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(error),page_errors:errors},null,2));}
 throw error;
} finally {await browser?.close();server?.kill();}
