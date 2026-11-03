/** Real MLflow SDK store and HTTP protocol through the actual editor;W&B consent refusals. */
import assert from "node:assert/strict";
import {spawn,type ChildProcess} from "node:child_process";
import {createHash} from "node:crypto";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {createServer} from "node:http";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type Page} from "playwright";
declare const document:any;
const root=resolve("."),evidence=process.env.GRAPHUNSLOPIFY_TRACKER_EVIDENCE||mkdtempSync(join(tmpdir(),"gu-trackers-"));
if(process.env.GRAPHUNSLOPIFY_TRACKER_EVIDENCE)mkdirSync(evidence);
const env={...process.env};if(process.env.GRAPHUNSLOPIFY_TRACKER_INSTALLED)delete env.PYTHONPATH;else env.PYTHONPATH=join(root,"python");
const secret="synthetic-provider-key-never-persist",errors:string[]=[],external:string[]=[],controls:unknown[]=[],calls:{path:string;authorized:boolean}[]=[];
let server:ChildProcess|undefined,browser,page:Page|undefined;
const protocol=createServer(async(req,res)=>{let raw="";for await(const chunk of req)raw+=chunk;const parsed=new URL(req.url!,"http://127.0.0.1");calls.push({path:parsed.pathname,authorized:req.headers.authorization==="Bearer "+secret});let value;
 if(parsed.pathname.endsWith("runs/search"))value={runs:["a","b"].map(id=>({info:{run_id:id,status:"FINISHED"},data:{tags:[{key:"mlflow.runName",value:"HTTP model"}],metrics:[{key:"loss",value:1}]}}))};
 else if(parsed.pathname.endsWith("get-history")){const n=parsed.searchParams.get("run_id")==="a"?0:1;value={metrics:[{key:"loss",step:0,timestamp:1000,value:3+n},{key:"loss",step:1,timestamp:2000,value:1+n}]};}
 else{res.writeHead(404);res.end();return;}
 res.setHeader("Content-Type","application/json");res.end(JSON.stringify(value));});
async function setup(){const code=`from pathlib import Path
import json
from mlflow import MlflowClient
root=Path(${JSON.stringify(evidence)})
client=MlflowClient(tracking_uri='sqlite:///'+str(root/'owned.sqlite'))
exp=client.create_experiment('browser histories',artifact_location=str(root/'artifacts'))
for i in range(2):
 run=client.create_run(exp,tags={'mlflow.runName':'same display name'})
 for step,stamp,value in [(0,900,4+i),(0,1000,3+i),(2,2000,1+i)]:client.log_metric(run.info.run_id,'loss',value,step=step,timestamp=stamp)
 client.set_terminated(run.info.run_id)
(root/'input.json').write_text(json.dumps({'experiment':exp}))
`;
 const child=spawn(process.env.PYTHON||"python",["-c",code],{env,cwd:evidence,stdio:["ignore","pipe","pipe"]});let text="";child.stdout!.on("data",c=>text+=c);child.stderr!.on("data",c=>text+=c);await new Promise<void>((ok,bad)=>{child.once("error",bad);child.once("exit",c=>c===0?ok():bad(Error(text)));});}
async function serve(){server=spawn(process.env.PYTHON||"python",["-m","graphunslopify.cli","preview","--port","0"],{env,cwd:evidence,stdio:["ignore","pipe","pipe"]});let stderr="";server.stderr!.on("data",c=>stderr+=c);const lines=createInterface({input:server.stdout!});return new Promise<string>((ok,bad)=>{lines.once("line",line=>{try{ok(JSON.parse(line).url);}catch(e){bad(e);}});server!.once("error",bad);server!.once("exit",c=>bad(Error(`Editor exited ${c}: ${stderr}`)));});}
async function catalog(){const response=page!.waitForResponse(r=>r.url().endsWith("/api/experiments/catalog"));await page!.locator("#experiment-list").click();const r=await response;assert.equal(r.status(),200);const result=await r.json();assert.equal(result.runs.length,2);await page!.waitForFunction(()=>document.querySelectorAll("#experiment-runs input").length===2);for(const check of await page!.locator("#experiment-runs input").all())await check.check();await page!.locator("#experiment-metric").selectOption("loss");return result;}
async function reviewed(){const response=page!.waitForResponse(r=>r.url().endsWith("/api/experiments/review"));await page!.locator("#experiment-review").click();const r=await response;assert.equal(r.status(),200);await page!.locator("#experiment-proposal").waitFor();const result=await r.json();assert(!JSON.stringify(result).includes(secret));return result;}
async function applied(){await page!.locator("#experiment-reviewed").check();const response=page!.waitForResponse(r=>r.url().endsWith("/api/render"));await page!.locator("#experiment-accept").click();const value=await(await response).json();assert.equal(value.report.status,"passed");await page!.locator('#status[data-state="passed"]').waitFor();return value;}
const sha=(path:string)=>createHash("sha256").update(readFileSync(path)).digest("hex");
try{
 await setup();await new Promise<void>(r=>protocol.listen(0,"127.0.0.1",r));const address=protocol.address() as {port:number},endpoint=`http://127.0.0.1:${address.port}`;
 const executable=process.env.GRAPHUNSLOPIFY_BROWSER||(existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")?"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":undefined);
 browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});page=await browser.newPage({viewport:{width:1500,height:1100}});page.setDefaultTimeout(90_000);
 page.on("pageerror",e=>errors.push(e.message));page.on("request",r=>{if(/^https?:/.test(r.url())&&!/^http:\/\/127\.0\.0\.1:/.test(r.url()))external.push(r.url());});
 await page.goto(await serve());await page.locator('#kind option[value="line"]').waitFor({state:"attached"});await page.locator("#live").uncheck();await page.locator("#experiment-import>summary").click();
 await page.locator("#experiment-provider").selectOption("mlflow");await page.locator("#experiment-source").fill(join(evidence,"owned.sqlite"));await page.locator("#experiment-ids").fill(JSON.parse(readFileSync(join(evidence,"input.json"),"utf8")).experiment);const original=sha(join(evidence,"owned.sqlite"));
 const local=await catalog();assert.equal(new Set(local.runs.map((r:any)=>r.id)).size,2);assert.equal(new Set(local.runs.map((r:any)=>r.name)).size,1);assert(!local.disclosure.network_read);assert(await page.locator("#experiment-review").isDisabled());await page.locator("#experiment-kind").selectOption("scatter");const plan=await reviewed();assert.equal(plan.report.records,6);assert.equal(plan.report.duplicate_steps,2);await applied();assert.equal(sha(join(evidence,"owned.sqlite")),original);controls.push({control:"actual-sdk-local-run-selection-native",records:6,duplicates:2,source_unchanged:true});
 await page.locator("#figure-surface").screenshot({path:join(evidence,"mlflow-native.png")});const download=page.waitForEvent("download");await page.locator("#bundle").click();await(await download).saveAs(join(evidence,"mlflow-source-free.zip"));controls.push({control:"local-provenance-bundle-produced",passed:true});
 await page.locator("#experiment-undo").click();assert((await page.locator("#data-summary").textContent())?.includes("No data"));controls.push({control:"local-undo-restores-prior-context",passed:true});
 await page.locator("#experiment-source").fill(endpoint);await page.locator("#experiment-ids").fill("1");await page.locator("#experiment-key").fill(secret);await page.locator("#experiment-list").click();await page.waitForFunction(()=>document.getElementById("experiment-status")?.textContent.includes("allow its network read"));assert.equal(calls.length,0);controls.push({control:"endpoint-consent-before-network",passed:true});
 await page.locator("#experiment-network").check();const remote=await catalog();assert(!JSON.stringify(remote).includes(secret));await page.locator("#experiment-kind").selectOption("line");const httpPlan=await reviewed();assert.equal(httpPlan.report.records,4);await applied();assert(calls.length>0&&calls.every(c=>c.authorized));controls.push({control:"actual-http-token-pages-native-no-secret-report",records:4,passed:true});
 await page.locator("#experiment-provider").selectOption("wandb");await page.locator("#experiment-source").fill("fixture/histories");await page.locator("#experiment-endpoint").fill(endpoint);await page.locator("#experiment-key").fill("");assert.equal(await page.locator("#experiment-key").getAttribute("type"),"password");await page.locator("#experiment-network").check();const refused=page.waitForResponse(r=>r.url().endsWith("/api/experiments/catalog"));await page.locator("#experiment-list").click();const refusal=await refused;assert.equal(refusal.status(),400);assert.match((await refusal.json()).error,/explicit API key/);controls.push({control:"wandb-explicit-key-no-login-prompt",passed:true});
 await page.setViewportSize({width:430,height:920});await page.locator("#experiment-import").screenshot({path:join(evidence,"mobile-trackers.png")});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));controls.push({control:"mobile-no-horizontal-overflow",passed:true});
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);writeFileSync(join(evidence,"verification.json"),JSON.stringify({controls,errors,external,source_sha256:original,synthetic_http_protocol:true,real_mlflow_sdk:true,wandb_remote_account_tested:false},null,2)+"\n");console.log(JSON.stringify({evidence,controls:controls.length,errors,external}));
}catch(error){writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(error),controls,errors,external},null,2)+"\n");if(page)await page.screenshot({path:join(evidence,"failure.png"),fullPage:true});throw error;}
finally{await browser?.close();server?.kill("SIGTERM");protocol.close();}
