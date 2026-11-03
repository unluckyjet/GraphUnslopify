/** Real local component evidence, original scientific outcomes and packet download. */
import assert from "node:assert/strict";
import {spawn,execFileSync,type ChildProcess} from "node:child_process";
import {createHash} from "node:crypto";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,renameSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type Page} from "playwright";
declare const document:any;
declare const window:any;

const evidence=process.env.GRAPHUNSLOPIFY_SCORECARD_EVIDENCE||mkdtempSync(join(tmpdir(),"gu-scorecard-"));
if(process.env.GRAPHUNSLOPIFY_SCORECARD_EVIDENCE)mkdirSync(evidence);
const paper=join(evidence,"paper with spaces"),python=process.env.PYTHON||"python";
const env={...process.env};
if(process.env.GRAPHUNSLOPIFY_SCORECARD_INSTALLED)delete env.PYTHONPATH;else env.PYTHONPATH=resolve("python");
const setup=`from pathlib import Path
import copy,json,sys
import graphunslopify
from graphunslopify import Figure
from graphunslopify.project import initialize_project,run_project
from graphunslopify.project_inspections import inspect_project_pdf,project_inspections
p=Path(sys.argv[1]);p.mkdir()
rows=['step,score,seed,model']
for step in range(1,4):
 for model,offset in [('a',0),('b',2)]:
  for seed,value in [('one',1),('two',3),('three',5)]:rows.append(f'{step},{step+value+offset},{seed},{model}')
(p/'runs.csv').write_text('\\n'.join(rows)+'\\n')
s={'kind':'line','group':'model','data':{'path':'runs.csv'},'x':{'field':'step','label':'Step'},'y':{'field':'score','label':'Score'},'aggregation':'mean','uncertainty':{'kind':'std','over':'seed'}}
(p/'line.json').write_text(json.dumps(s))
b={**copy.deepcopy(s),'kind':'bar','orientation':'horizontal'}
a={**copy.deepcopy(s),'output':{'stem':'authored','formats':['png']}}
(p/'authored.py').write_text(Figure(a).translate(api='local')['code'])
(p/'graphunslopify.json').write_text(json.dumps({'schema_version':1,'figures':[{'id':'line','spec':'line.json'},{'id':'bars','spec':b},{'id':'authored','script':'authored.py','data':'runs.csv'}]}))
initialize_project(p)
r=run_project(p);assert r['exit_code']==0,(r['errors'],r['policy_errors'])
pdf=p/'external.pdf';pdf.write_bytes(Path(sys.argv[2]).read_bytes())
inspect_project_pdf(p,pdf,identity='external',expected_revision=project_inspections(p)['revision'],pages=[1],dpi=72)
print(json.dumps({'event':r['id'],'package_root':str(Path(graphunslopify.__file__).parent)}))`;
let server:ChildProcess|undefined,browser,page:Page|undefined;
const errors:string[]=[],external:string[]=[];
try {
 const initial=JSON.parse(execFileSync(python,["-c",setup,paper,resolve("examples/baseline/01-training-curve.pdf")],{env,cwd:evidence,encoding:"utf8",timeout:180_000}));
 if(process.env.GRAPHUNSLOPIFY_SCORECARD_INSTALLED)assert(!initial.package_root.startsWith(resolve("python")));
 const data=readFileSync(join(paper,"runs.csv")),definition=readFileSync(join(paper,"line.json"));
 server=spawn(python,["-m","graphunslopify.cli","project-preview",paper,"--port","0"],{env,cwd:evidence,stdio:["ignore","pipe","pipe"]});
 let stderr="";server.stderr!.on("data",c=>{stderr+=c;});
 const lines=createInterface({input:server.stdout!});
 const url=await new Promise<string>((ok,bad)=>{lines.once("line",line=>{try{ok(JSON.parse(line).url);}catch(e){bad(e);}});server!.once("error",bad);server!.once("exit",code=>bad(Error(`Server exited ${code}: ${stderr}`)));});
 const executable=process.env.GRAPHUNSLOPIFY_BROWSER||(existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")?"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":undefined);
 browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});
 page=await browser.newPage({viewport:{width:1450,height:1100}});page.setDefaultTimeout(120_000);
 page.on("pageerror",e=>errors.push(e.message));
 page.on("request",r=>{if(/^https?:/.test(r.url())&&new URL(r.url()).origin!==new URL(url).origin)external.push(r.url());});
 await page.goto(url);
 await page.locator('#review-figure option[value="line"]').waitFor({state:"attached"});
 await page.locator("#review-figure").selectOption("line");
 const token=(await page.locator('meta[name="preview-token"]').getAttribute("content"))!;
 const api=async(path:string)=>{const r=await page!.request.get(url+path,{headers:{"X-Preview-Token":token}});return {status:r.status(),value:await r.json()};};
 const uiState=async(id:string,state:string)=>{await page!.waitForFunction(({id,state})=>document.querySelector(`.component-scorecard [data-component="${id}"]`)?.dataset.availability===state,{id,state});};
 const refresh=async()=>{await page!.locator("#refresh").click();await page!.locator("#review-latest").click();};
 await uiState("programs","available");
 assert.equal(await page.locator(".component-scorecard .scorecard-component").count(),7);
 await uiState("data","available");await uiState("environment","partial");
 const first=(await api("/api/scorecard")).value;
 const row=first.figures.find((r:any)=>r.id==="line"),parts=Object.fromEntries(row.components.map((c:any)=>[c.id,c]));
 assert(parts.programs.evidence.matches_executed_program);assert.equal(row.scientific_status,"passed");
 const historyCount=(await api("/api/state")).value.history.length;
 await page.locator(".component-scorecard").screenshot({path:join(evidence,"desktop-components.png")});
 await page.locator("#review-figure").selectOption("authored");await uiState("data","partial");await uiState("programs","available");
 await page.locator("#review-figure").selectOption("bars");await uiState("definitions","available");
 await page.locator("#review-figure").selectOption("line");await uiState("data","available");
 renameSync(join(paper,"runs.csv"),join(paper,"runs.csv.held"));await refresh();await uiState("data","missing");
 renameSync(join(paper,"runs.csv.held"),join(paper,"runs.csv"));writeFileSync(join(paper,"runs.csv"),Buffer.concat([data,Buffer.from("\n")]));
 await refresh();await uiState("data","partial");
 writeFileSync(join(paper,"runs.csv"),data);await refresh();await uiState("data","available");
 const relocated=JSON.parse(definition.toString());relocated.data.path="relocated.csv";
 writeFileSync(join(paper,"relocated.csv"),data);writeFileSync(join(paper,"line.json"),JSON.stringify(relocated));
 await refresh();await uiState("data","partial");
 const moved=(await api("/api/scorecard")).value.figures.find((r:any)=>r.id==="line").components.find((c:any)=>c.id==="data");
 assert.equal(moved.evidence.matches_recorded_bytes,true);assert.equal(moved.evidence.matches_recorded_locations,false);
 assert(moved.summary.includes("different declared locations"));
 writeFileSync(join(paper,"line.json"),definition);await refresh();await uiState("data","available");
 const relative=parts.programs.evidence.relative_path;assert(!relative.startsWith("/")&&!relative.split("/").includes(".."));
 const program=join(paper,"graphunslopify-project/history",first.selection.event,"audit",relative),originalProgram=readFileSync(program);
 writeFileSync(program,Buffer.concat([originalProgram,Buffer.from("\n# changed saved program\n")]));
 await refresh();await uiState("programs","partial");
 assert.equal((await api("/api/scorecard?expected_revision="+first.evidence_revision)).status,400);
 writeFileSync(program,originalProgram);await refresh();await uiState("programs","available");
 assert.equal((await api("/api/state")).value.history.length,historyCount);
 assert.deepEqual(readFileSync(join(paper,"line.json")),definition);
 // An actual reviewed definition change creates a later version, without rewriting history.
 await page.locator('[data-figure="line"]').click();
 const spec=JSON.parse(definition.toString()),failed={...spec,claims:[{kind:"beats_everywhere",subject:"a",reference:"b"}]};
 if(!await page.locator("#definition-panel").evaluate((el:any)=>el.open))await page.locator("#definition-panel > summary").click();
 await page.locator("#definition").fill(JSON.stringify(failed,null,2));
 const saved=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/definition");await page.locator("#save-definition").click();assert.equal((await saved).status(),200);
 await page.waitForFunction(()=>!document.getElementById("audit").disabled);await page.locator("#audit").click();
 await page.waitForFunction(()=>!document.getElementById("running").hidden);
 await page.waitForFunction(()=>document.getElementById("running").hidden&&document.getElementById("event-summary").textContent.includes("scientific checks:"));
 await page.locator("#review-latest").click();await page.locator("#review-figure").selectOption("line");await uiState("data","available");
 await page.waitForFunction(()=>document.querySelector(".component-scorecard")?.textContent.includes("Recorded scientific outcome: failed"));
 const actual=(await api("/api/scorecard")).value,failedRow=actual.figures.find((r:any)=>r.id==="line");
 assert.equal(failedRow.scientific_status,"failed");assert.equal(failedRow.paper_status,"failed");
 assert(failedRow.components.filter((c:any)=>["data","programs","checks","exports"].includes(c.id)).every((c:any)=>c.state==="available"));
 await page.locator("#review-event").selectOption(initial.event);
 await page.waitForFunction(()=>document.getElementById("review-context").textContent.includes("selected saved run"));
 const historical=(await api("/api/scorecard?event="+initial.event)).value;
 assert.equal(historical.selection.matches_current_revision,false);assert(historical.figures.some((r:any)=>r.id==="line"&&r.scientific_status==="passed"));
 await page.locator("#review-latest").click();await page.locator("#review-figure").selectOption("line");
 await page.waitForFunction(()=>document.querySelector(".component-scorecard")?.textContent.includes("Recorded scientific outcome: failed")&&!document.getElementById("review-export").disabled);
 const download=page.waitForEvent("download");await page.locator("#review-export").click();const packet=join(evidence,"review-packet.zip");await(await download).saveAs(packet);
 const packetProof=JSON.parse(execFileSync(python,["-c",`import json,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
 p=json.loads(z.read('reports/scorecard.json'))
 assert p['availability_scope']=='local_project_at_query' and not p['packet_inclusion']['raw_datasets'] and not p['packet_inclusion']['source_programs']
 assert any(f['id']=='line' and f['scientific_status']=='failed' for f in p['figures'])
 assert not any(n.endswith(('.csv','.py')) for n in z.namelist())
 print(json.dumps({'downloaded':True,'local_scope':True,'raw_inputs_excluded':True,'failed_science_retained':True}))`,packet],{env,cwd:evidence,encoding:"utf8"}));
 assert(packetProof.failed_science_retained);
 await page.locator("#review-figure").selectOption("pdf:external");await uiState("data","missing");await uiState("programs","missing");await uiState("checks","partial");
 assert((await page.locator(".component-scorecard").textContent())!.includes("Recorded scientific outcome: untested"));
 await page.setViewportSize({width:430,height:920});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 await page.locator(".component-scorecard").screenshot({path:join(evidence,"mobile-pdf-components.png")});
 assert.deepEqual(readFileSync(join(paper,"runs.csv")),data);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 const proof={public_component_states:true,actual_program_identity:true,inline_and_authored_scope:true,missing_data_visible:true,changed_data_visible:true,changed_location_distinguished:true,tampered_program_visible:true,restored_program_visible:true,read_queries_preserve_history:true,stale_expected_revision_refused:true,historical_selection_bound:true,failed_science_retained:true,pdf_visual_scope:true,mobile_scope:true,public_packet_download:true,original_data_preserved:true,page_errors:errors,external_requests:external,data_sha256:createHash("sha256").update(data).digest("hex")};
 writeFileSync(join(evidence,"verification.json"),JSON.stringify(proof,null,2));console.log(JSON.stringify({proof,evidence}));
}catch(error){if(page){await page.screenshot({path:join(evidence,"failure.png"),fullPage:true}).catch(()=>{});writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(error),page_errors:errors},null,2));}throw error;}
finally{
 await browser?.close();
 if(server&&server.exitCode===null){
  const closed=new Promise<void>(ok=>server!.once("exit",()=>ok()));server.kill("SIGTERM");
  await Promise.race([closed,new Promise(ok=>setTimeout(ok,10_000))]);
  if(server.exitCode===null){server.kill("SIGKILL");await closed;}
 }
}
