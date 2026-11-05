/** Actual native/paper reviewer controls with public data and controlled HTTP. */
import assert from "node:assert/strict";
import {spawn,spawnSync,type ChildProcess} from "node:child_process";
import {createHash} from "node:crypto";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type BrowserContext,type Page} from "playwright";
declare const document:any;
declare const window:any;

const root=resolve("."), evidence=process.env.GRAPHUNSLOPIFY_REVIEWER_EVIDENCE||mkdtempSync(join(tmpdir(),"gu-reviewer-browser-"));
if(process.env.GRAPHUNSLOPIFY_REVIEWER_EVIDENCE)mkdirSync(evidence);
const scratch=join(evidence,"scratch");mkdirSync(scratch);
const env:NodeJS.ProcessEnv={...process.env,TMPDIR:scratch};
if(process.env.GRAPHUNSLOPIFY_REVIEWER_INSTALLED)delete env.PYTHONPATH;else env.PYTHONPATH=join(root,"python");
if(process.env.GRAPHUNSLOPIFY_REVIEWER_OFFLINE_HOOKS)env.PYTHONPATH=process.env.GRAPHUNSLOPIFY_REVIEWER_OFFLINE_HOOKS;
if(process.env.GRAPHUNSLOPIFY_REVIEWER_CHILD_NODE_OPTIONS)env.NODE_OPTIONS=process.env.GRAPHUNSLOPIFY_REVIEWER_CHILD_NODE_OPTIONS;
const python=process.env.PYTHON||"python", controls:any[]=[],errors:string[]=[],external:string[]=[],resources:any[]=[];
const projectJobs:any[]=[];
const record=controls.push.bind(controls);
controls.push=(...items:any[])=>{const count=record(...items);writeFileSync(join(evidence,"progress.json"),JSON.stringify({controls,recorded_utc:new Date().toISOString()},null,2)+"\n");return count;};
const sha=(raw:Buffer)=>createHash("sha256").update(raw).digest("hex");
function deadline<T>(promise:Promise<T>,label:string,ms=90000):Promise<T>{
 let timeout:ReturnType<typeof setTimeout>;
 const expired=new Promise<T>((_,reject)=>timeout=setTimeout(()=>reject(Error(label+" timed out")),ms));
 return Promise.race([promise,expired]).finally(()=>clearTimeout(timeout));
}
let processHandle:ChildProcess|undefined, processExit:Promise<number|null>|undefined, browser:BrowserContext|undefined, activePage:Page|undefined;
let stderr="";
const waiting:Array<{resolve:(value:any)=>void,reject:(error:Error)=>void}>=[];
let fixture:any;
async function serve(){
 processHandle=spawn(python,[join(root,"scripts/serve-reviewer-check.py"),"--out",join(evidence,"fixture")],{env,cwd:evidence,stdio:["pipe","pipe","pipe"]});
 processHandle.stderr!.on("data",chunk=>stderr=(stderr+chunk).slice(-24000));
 processExit=new Promise(ok=>processHandle!.once("close",ok));
 const lines=createInterface({input:processHandle.stdout!});
 lines.on("line",line=>{try{const value=JSON.parse(line),next=waiting.shift();if(!next)throw Error("Unexpected fixture response");next.resolve(value);}catch(error){const problem=Error(String(error));while(waiting.length)waiting.shift()!.reject(problem);}});
 processHandle.once("exit",code=>{const problem=Error(`Reviewer fixture exited ${code}: ${stderr}`);while(waiting.length)waiting.shift()!.reject(problem);});
 processHandle.once("error",problem=>{while(waiting.length)waiting.shift()!.reject(problem);});
 return new Promise<any>((resolve,reject)=>waiting.push({resolve,reject}));
}
function rpc(operation:string,extra:any={}){return deadline(new Promise<any>((resolve,reject)=>{waiting.push({resolve,reject});processHandle!.stdin!.write(JSON.stringify({operation,...extra})+"\n");}),"Owned fixture "+operation);}
async function snapshot(){return rpc("snapshot");}
async function waitForCalls(count:number){
 const end=Date.now()+15000;
 while(Date.now()<end){const state=await snapshot();if(state.calls.length>=count)return state;await new Promise(r=>setTimeout(r,50));}
 throw Error("Controlled provider did not observe the expected explicit request");
}
function observe(page:Page){
 page.setDefaultTimeout(90000);
 page.on("pageerror",e=>errors.push(e.message));
 page.on("request",r=>{if(/^https?:/.test(r.url())&&!/^http:\/\/127\.0\.0\.1:/.test(r.url()))external.push(r.url());});
 page.on("response",r=>{if(r.status()>=400&&["script","stylesheet","image"].includes(r.request().resourceType()))resources.push({path:new URL(r.url()).pathname,status:r.status()});});
 page.on("response",r=>{
  const path=new URL(r.url()).pathname;if(!["/api/state","/api/job","/api/pdf-upload"].includes(path))return;
  void r.json().then(value=>{
   const job=value.job??(value.kind==="inspection"?value:null);
   projectJobs.push({at:new Date().toISOString(),path,status:r.status(),error:value.error,history_integrity:value.history_integrity,
    job:job?{phase:job.phase,kind:job.kind,error:job.error,result:job.result}:undefined,
    inspections:value.inspections?.map((row:any)=>({id:row.id,event:row.event,evidence_state:row.evidence_state,errors:row.errors}))});
   if(projectJobs.length>64)projectJobs.shift();
   writeFileSync(join(evidence,"project-jobs.json"),JSON.stringify(projectJobs,null,2)+"\n");
  }).catch(()=>{});
 });
 page.on("requestfailed",r=>{if(["script","stylesheet"].includes(r.resourceType()))resources.push({path:new URL(r.url()).pathname,error:r.failure()?.errorText});});
}
async function configure(page:Page,protocol="responses"){
 if(!await page.locator("#figure-reviewer").evaluate((e:any)=>e.open))await page.locator("#figure-reviewer>summary").click();
 if(!await page.locator("#reviewer-settings").evaluate((e:any)=>e.open))await page.locator("#reviewer-settings>summary").click();
 await page.locator("#reviewer-protocol").selectOption(protocol);
 await page.locator("#reviewer-endpoint").fill(fixture.provider);
 await page.locator("#reviewer-model").fill("controlled-browser-review");
 await page.locator("#reviewer-key").fill("REVIEWER_TEST_KEY");
 const saved=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/reviewer/provider"&&r.request().method()==="POST");
 await page.locator("#reviewer-save-provider").click();assert.equal((await saved).status(),200);
 await page.waitForFunction(()=>document.querySelector("#reviewer-provider-note").textContent.includes("Configured:"));
 assert.equal(await page.locator("#reviewer-key").inputValue(),"");
}
async function disclose(page:Page){
 await page.waitForFunction(()=>!document.querySelector("#reviewer-disclose").disabled);
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/reviewer/disclose");
 await page.locator("#reviewer-disclose").click();const reply=await response;
 assert.equal(reply.status(),200,await reply.text());const value=await reply.json();
 await page.waitForFunction(()=>!document.querySelector("#reviewer-consent").disabled);
 assert(await page.locator("#reviewer-start").isDisabled());
 assert.equal(await page.locator("#reviewer-consent").isChecked(),false);
 const body=await page.locator("#reviewer-request-body").textContent();assert.equal(body,value.request_body);
 assert.equal(Buffer.byteLength(body!,"utf8"),value.request_bytes);assert.equal(sha(Buffer.from(body!,"utf8")),value.request_sha256);
 return value;
}
async function run(page:Page){
 await send(page);
 await page.locator('#figure-reviewer[data-phase="completed"]').waitFor();
 assert(await page.locator("#reviewer-advice").isVisible());assert.equal(await page.locator("#reviewer-advice img").count(),0);
 assert((await page.locator("#reviewer-advice").textContent())!.includes("<img"));
 assert.equal(await page.evaluate(()=>window.REVIEW_HTML_EXECUTED),undefined);
}
async function send(page:Page){
 await page.locator("#reviewer-consent").check();
 const [reply]=await Promise.all([
  page.waitForResponse(r=>new URL(r.url()).pathname==="/api/reviewer/start"),
  page.locator("#reviewer-start").click(),
 ]);
 assert.equal(reply.status(),202);
}
async function settled(page:Page){await page.evaluate(()=>new Promise(ok=>window.requestAnimationFrame(()=>window.requestAnimationFrame(ok))));}
async function waitInactive(which:"native"|"paper"){
 const end=Date.now()+15000;
 while(Date.now()<end){const state=await snapshot();if(!state[which+"_active_review"])return state;await new Promise(ok=>setTimeout(ok,50));}
 throw Error("Owned reviewer worker remained active after cancellation");
}
// Delay real server responses; do not synthesize evidence, verdicts or replies.
async function holdResponse(page:Page,action:string,accept:(value:any)=>boolean=()=>true){
 let announce!:(value:any)=>void,release!:()=>void,complete!:()=>void;
 const captured=new Promise<any>(ok=>announce=ok), gate=new Promise<void>(ok=>release=ok),done=new Promise<void>(ok=>complete=ok);
 let held=false;
 const pattern="**/api/"+action;
 const handler=async(route:any)=>{
  const response=await route.fetch();const value=await response.json();
  if(!held&&accept(value)){held=true;announce(value);await gate;await route.fulfill({response});complete();}
  else await route.fulfill({response});
 };
 await page.route(pattern,handler);
 return {captured:deadline(captured,"Real response capture for "+action),release:async()=>{release();await deadline(done,"Real response release for "+action);await page.unroute(pattern,handler);await settled(page);}};
}
async function download(page:Page,which:string,name:string){
 const event=page.waitForEvent("download");await page.locator("#reviewer-download-"+which).click();
 const path=join(evidence,name);await(await event).saveAs(path);return path;
}
async function render(page:Page){
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/render");await page.locator("#render").click();
 const reply=await response;assert.equal(reply.status(),200);const value=await reply.json();
 writeFileSync(join(evidence,"native-render-response.json"),JSON.stringify(value,null,2)+"\n");
 assert.equal(value.exit_code,2);assert(value.review?.available,JSON.stringify(value.review));assert.equal(value.report.data.counts.prepared,333);
 assert(value.report.claims.some((c:any)=>c.verdict==="fails"));
 await page.locator('#status[data-state="failed"]').waitFor();
 await page.waitForFunction(()=>document.querySelectorAll("#reviewer-figures input").length===1);
 return value;
}
async function preserveNativeFiles(page:Page,value:any){
 const links=await page.locator("#files a").evaluateAll((nodes:any[])=>nodes.map(e=>e.href));
 const png=value.report.outputs.find((f:any)=>f.format==="png");assert(png);
 const wanted=[{name:png.path.split(/[\\/]/).at(-1),hash:png.sha256,out:"native-figure.png"},{name:value.spec.output.stem+".py",hash:value.report.script.sha256,out:"native-program.py"}];
 const saved:any[]=[];
 for(const file of wanted){
  const href=links.find((url:string)=>decodeURIComponent(new URL(url).pathname.split("/").at(-1)!)===file.name);assert(href,"Original producer artifact is absent from the owned file links");
  assert.equal(new URL(href).origin,new URL(page.url()).origin);
  const response=await page.request.get(href);assert.equal(response.status(),200);const raw=await response.body();assert.equal(sha(raw),file.hash);
  writeFileSync(join(evidence,file.out),raw);saved.push({path:file.out,bytes:raw.length,sha256:sha(raw)});
 }
 return saved;
}
try{
 fixture=await serve();
 const originalState=await snapshot();
 const executable=process.env.GRAPHUNSLOPIFY_BROWSER||(existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")?"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":undefined);
 browser=await chromium.launchPersistentContext(join(scratch,"browser-profile"),{headless:true,viewport:{width:1600,height:1100},...(executable?{executablePath:executable}:{})});
 const page=await browser.newPage();activePage=page;observe(page);await page.goto(fixture.native);
 await page.locator('#kind option[value="line"]').waitFor({state:"attached"});await page.locator("#live").uncheck();
 if(!await page.locator("#advanced").evaluate((e:any)=>e.open))await page.locator("#advanced>summary").click();
 const uploaded=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/upload");await page.locator("#data-file").setInputFiles(fixture.public_source);assert.equal((await uploaded).status(),200);
 await page.waitForFunction(()=>document.querySelector("#data-summary").textContent.includes("344 rows"));
 await page.locator("#spec").fill(JSON.stringify(fixture.native_spec));const native=await render(page);
 writeFileSync(join(evidence,"native-final.json"),JSON.stringify(native,null,2)+"\n");
 const nativeArtifacts=await preserveNativeFiles(page,native);
 await configure(page);assert.equal((await snapshot()).calls.length,0);
 await page.locator("#reviewer-question").fill("Review Δ ≥ 0 and the deliberately failed comparison.");
 const first=await disclose(page);assert.equal(first.source_kind,"editor-render");assert(first.deterministic_evidence.recorded_failures.length);
 const specBefore=await page.locator("#spec").inputValue();const nativeRequest=await download(page,"request","native-request.json");
 const ephemeral=JSON.parse(readFileSync(nativeRequest,"utf8"));assert.equal(ephemeral.kind,"editor-figure-review-request");assert.equal(ephemeral.replayable,false);
 assert(!("request_body" in ephemeral.disclosure));assert(!readFileSync(nativeRequest,"utf8").includes("REVIEWER_TEST_KEY"));
 controls.push({control:"native-actual-failed-figure-exact-disclosure-and-ephemeral-download",passed:true,request_sha256:first.request_sha256});
 await run(page);const after=await waitForCalls(1);assert.equal(after.calls.length,1);assert.equal(after.calls[0].sha256,first.request_sha256);assert.equal(after.calls[0].bytes,first.request_bytes);
 assert.equal(await page.locator("#spec").inputValue(),specBefore);assert.equal(await page.locator("#status").getAttribute("data-state"),"failed");
 await download(page,"result","native-result.json");await page.locator("#figure-reviewer").screenshot({path:join(evidence,"native-reviewer.png")});
 controls.push({control:"native-consented-exact-wire-literal-advice-and-unchanged-science",passed:true});
 const paper=await browser.newPage();activePage=paper;observe(paper);paper.on("dialog",dialog=>void dialog.accept());const initialInfo=await holdResponse(paper,"info");await paper.goto(fixture.paper);await initialInfo.captured;
 await paper.locator("#review-latest").click();await settled(paper);assert.deepEqual(errors,[]);await initialInfo.release();
 controls.push({control:"review-latest-before-project-initialization-remains-safe",passed:true});
 await paper.locator('#review-figure option[value="mass"]').waitFor({state:"attached"});await paper.locator("#review-figure").selectOption("mass");
 await configure(paper,"chat");await paper.locator("#reviewer-question").fill("Review the saved failed comparison; author label Δ.");
 const paperDisclosure=await disclose(paper);assert.equal(paperDisclosure.source_kind,"paper-project");assert(paperDisclosure.deterministic_evidence.recorded_failures.length);
 const paperRequest=await download(paper,"request","paper-request.json");const replay=await rpc("restore-paper-request",{path:paperRequest});assert(replay.restored);assert.equal(replay.request_sha256,paperDisclosure.request_sha256);
 await run(paper);await download(paper,"result","paper-result.json");assert.equal((await snapshot()).calls.length,2);
 assert(await paper.locator("#save-definition").isDisabled());await paper.locator("#figure-reviewer").screenshot({path:join(evidence,"paper-reviewer.png")});
 controls.push({control:"paper-chat-protocol-current-evidence-and-raw-CLI-restorable-download",passed:true});
 // Same-evidence background refresh must retain completed advice and consent.
 const background=await paper.waitForResponse(r=>new URL(r.url()).pathname==="/api/review");assert.equal(background.status(),200);await background.finished();
 await paper.evaluate(()=>new Promise(ok=>window.requestAnimationFrame(()=>window.requestAnimationFrame(ok))));
 assert.equal(await paper.locator("#figure-reviewer").getAttribute("data-phase"),"completed");assert(await paper.locator("#reviewer-advice").isVisible());assert.equal((await snapshot()).calls.length,2);
 controls.push({control:"unchanged-actual-background-revalidation-retains-current-advice",passed:true});
 // Request-only edits clear advice/consent without changing saved scientific intent.
 await paper.locator("#reviewer-question").fill("A different reviewer question");assert(await paper.locator("#reviewer-advice").isHidden());assert(await paper.locator("#save-definition").isDisabled());
 await disclose(paper);assert(await paper.locator("#reviewer-start").isDisabled());
 if(!await paper.locator("#definition-panel").evaluate((e:any)=>e.open))await paper.locator("#definition-panel>summary").click();
 const definition=await paper.locator("#definition").inputValue();await paper.locator("#definition").fill("{");
 assert(await paper.locator("#reviewer-disclose").isDisabled());assert(await paper.locator("#reviewer-disclosure").isHidden());
 await paper.locator("#reload-definition").click();await paper.waitForFunction((text:string)=>document.querySelector("#definition").value===text,definition);
 controls.push({control:"review-question-does-not-dirty-definitions-and-invalid-source-clears-consent",passed:true});
 const savedEvents=await paper.locator("#review-event option").evaluateAll((options:any[])=>options.map(o=>({value:o.value,label:o.textContent})));
 const historical=savedEvents.find((o:any)=>o.value&&o.label.includes("passed"));assert(historical);
 await paper.locator("#review-event").selectOption(historical.value);const historyDisclosure=await disclose(paper);
 assert.equal(historyDisclosure.deterministic_evidence.selection.explicit_history_selection,true);
 assert.equal(historyDisclosure.deterministic_evidence.figures[0].execution_status,"passed");await run(paper);
 controls.push({control:"explicit-historical-passed-evidence-remains-distinct-from-current-failed-inputs",passed:true});
 await paper.locator("#reviewer-settings>summary").click();await paper.locator("#reviewer-model").fill("changed-provider-intent");
 assert(await paper.locator("#reviewer-disclose").isDisabled());assert(await paper.locator("#reviewer-advice").isHidden());assert(await paper.locator("#save-definition").isDisabled());
 await configure(paper,"chat");controls.push({control:"provider-form-edits-clear-consent-without-dirtying-scientific-definitions",passed:true});
 await paper.locator("#review-latest").click();await paper.locator("#pdf-file").setInputFiles(fixture.pdf);await paper.locator("#pdf-id").fill("visual");await paper.locator("#pdf-pages").fill("1,2");
 const pdfUpload=paper.waitForResponse(r=>new URL(r.url()).pathname==="/api/pdf-upload");
 await paper.locator("#pdf-upload").click();const acceptedPDF=await pdfUpload;assert.equal(acceptedPDF.status(),202);
 await paper.locator('#review-figure option[value="pdf:visual"]').waitFor({state:"attached"});await paper.locator("#review-figure").selectOption("pdf:visual");
 const pdfDisclosure=await disclose(paper);assert.equal(pdfDisclosure.deterministic_evidence.figures[0].source_type,"pdf");
 assert(JSON.stringify(pdfDisclosure.deterministic_evidence.figures[0].groups.claims).includes("untested"));assert.equal(pdfDisclosure.deterministic_evidence.images_supplied,false);await run(paper);
 controls.push({control:"actual-source-free-PDF-review-keeps-numerical-claims-untested",passed:true});
 await paper.locator("#review-page").selectOption("2");assert(await paper.locator("#reviewer-advice").isHidden());assert(await paper.locator("#reviewer-disclosure").isHidden());const secondPage=await disclose(paper);
 controls.push({control:"actual-PDF-page-change-requires-fresh-disclosure-and-consent",passed:true});
 const pagePoll=await paper.waitForResponse(r=>new URL(r.url()).pathname==="/api/state");assert.equal(pagePoll.status(),200);await pagePoll.finished();await settled(paper);
 assert.equal(await paper.locator("#figure-reviewer").getAttribute("data-phase"),"disclosed");assert((await paper.locator("#reviewer-request-digest").textContent())!.includes(secondPage.request_sha256));assert.equal(await paper.locator("#reviewer-consent").isChecked(),false);
 controls.push({control:"unchanged-real-state-poll-after-PDF-page-choice-preserves-disclosure",passed:true});
 await paper.locator("#review-latest").click();const latestDisclosure=await disclose(paper);
 const latestPoll=await paper.waitForResponse(r=>new URL(r.url()).pathname==="/api/state");assert.equal(latestPoll.status(),200);await latestPoll.finished();await settled(paper);
 assert.equal(await paper.locator("#figure-reviewer").getAttribute("data-phase"),"disclosed");assert((await paper.locator("#reviewer-request-digest").textContent())!.includes(latestDisclosure.request_sha256));assert.equal(await paper.locator("#reviewer-consent").isChecked(),false);
 controls.push({control:"unchanged-real-state-poll-after-review-latest-preserves-disclosure",passed:true});
 await paper.locator("#review-latest").click();await paper.locator('#figure-list [data-review-key="mass"]').click();
 const add=paper.locator("details").filter({has:paper.locator("#new-id")}).first();if(!await add.evaluate((e:any)=>e.open))await add.locator("summary").click();
 await paper.locator("#new-id").fill("unrun");await paper.locator("#duplicate").click();await paper.locator('#review-figure option[value="unrun"]').waitFor({state:"attached"});await paper.locator("#review-figure").selectOption("unrun");
 const unrun=await disclose(paper);assert.equal(unrun.deterministic_evidence.figures[0].evidence_state,"unavailable");assert.equal(unrun.deterministic_evidence.figures[0].execution_status,"not_available");await run(paper);
 controls.push({control:"new-figure-without-saved-results-does-not-borrow-another-figures-pass",passed:true});
 for(const choice of await paper.locator("#reviewer-figures input").all())await choice.uncheck();
 for(const key of ["mass","scatter","pdf:visual"])await paper.locator(`#reviewer-figures input[value="${key}"]`).check();
 const multi=await disclose(paper);assert.deepEqual(new Set(multi.deterministic_evidence.figures.map((f:any)=>f.key)),new Set(["mass","scatter","pdf:visual"]));await run(paper);
 controls.push({control:"actual-multiple-native-and-PDF-figure-selection",passed:true});
 for(const choice of await paper.locator("#reviewer-figures input").all())await choice.uncheck();
 assert(await paper.locator("#reviewer-disclose").isDisabled());assert(await paper.locator("#reviewer-advice").isHidden());
 await paper.locator('#reviewer-figures input[value="mass"]').check();
 controls.push({control:"empty-figure-selection-clears-old-advice-and-refuses-disclosure",passed:true});
 const cancelBarrier=await holdResponse(paper,"reviewer/cancel");let prematureDisclosures=0;
 const disclosureSent=(request:any)=>{if(new URL(request.url()).pathname==="/api/reviewer/disclose")prematureDisclosures++;};paper.on("request",disclosureSent);
 await paper.locator("#reviewer-disclose").click();await cancelBarrier.captured;await settled(paper);
 assert.equal(prematureDisclosures,0);const afterBarrier=paper.waitForResponse(r=>new URL(r.url()).pathname==="/api/reviewer/disclose");await cancelBarrier.release();
 assert.equal((await afterBarrier).status(),200);await paper.waitForFunction(()=>!document.querySelector("#reviewer-consent").disabled);paper.off("request",disclosureSent);
 controls.push({control:"new-disclosure-waits-for-its-own-cancellation-barrier",passed:true});
 let requestsAfterRejectedCancel=0;paper.on("request",disclosureSent);
 const rejectCancellation=async(route:any)=>{requestsAfterRejectedCancel++;await route.abort("failed");};
 await paper.route("**/api/reviewer/cancel",rejectCancellation);prematureDisclosures=0;await paper.locator("#reviewer-disclose").click();
 await paper.locator('#figure-reviewer[data-phase="failed"]').waitFor();assert(requestsAfterRejectedCancel>=1);assert.equal(prematureDisclosures,0);
 await paper.unroute("**/api/reviewer/cancel",rejectCancellation);paper.off("request",disclosureSent);
 controls.push({control:"unacknowledged-cancellation-refuses-new-disclosure-without-retry",passed:true});
 for(const mode of ["invalid","error"]){
  await rpc("mode",{mode});const count=(await snapshot()).calls.length;
  await disclose(paper);await send(paper);await paper.locator('#figure-reviewer[data-phase="failed"]').waitFor();
  assert(await paper.locator("#reviewer-advice").isHidden());assert(await paper.locator("#reviewer-download-result").isDisabled());
  assert(!(await paper.locator("#reviewer-status").textContent())!.includes("INVALID_PRIVATE_PROVIDER_REPLY"));
  assert.equal((await snapshot()).calls.length,count+1);await settled(paper);
  controls.push({control:"provider-"+mode+"-clears-old-success-without-private-output-or-auto-retry",passed:true});
 }
 await rpc("mode",{mode:"held"});const beforeCancel=(await snapshot()).calls.length;
 const cancelDisclosure=await disclose(paper);await send(paper);await waitForCalls(beforeCancel+1);
 await paper.locator("#reviewer-cancel").click();const cancelled=await waitInactive("paper");
 assert(cancelled.paper_sessions.some((r:any)=>r.id===cancelDisclosure.review_id&&r.cancelled&&r.phase==="cancelled"&&!r.worker_alive));await rpc("release");await settled(paper);
 assert.equal(await paper.locator("#figure-reviewer").getAttribute("data-phase"),"idle");assert(await paper.locator("#reviewer-advice").isHidden());
 assert.equal((await snapshot()).calls.length,beforeCancel+1);controls.push({control:"explicit-cancel-reaps-owned-request-and-late-provider-output-stays-hidden",passed:true});
 await rpc("mode",{mode:"valid"});
 const lateDisclosure=await holdResponse(paper,"reviewer/disclose");await paper.locator("#reviewer-disclose").click();await lateDisclosure.captured;
 await paper.locator("#reviewer-question").fill("A new question while the real disclosure is in transit");await lateDisclosure.release();
 assert(await paper.locator("#reviewer-disclosure").isHidden());assert(await paper.locator("#reviewer-start").isDisabled());
 controls.push({control:"late-real-disclosure-cannot-restore-consent-after-question-edit",passed:true});
 await disclose(paper);const lateStatus=await holdResponse(paper,"reviewer/status",value=>value.phase==="completed");await send(paper);await lateStatus.captured;
 await paper.locator("#reviewer-question").fill("Changed after a completed server result but before its browser response");await lateStatus.release();
 assert(await paper.locator("#reviewer-advice").isHidden());assert(await paper.locator("#reviewer-download-result").isDisabled());
 controls.push({control:"late-real-completed-result-cannot-revive-stale-advice",passed:true});
 await disclose(paper);let staleDownloads=0;const countDownload=()=>{staleDownloads++;};paper.on("download",countDownload);
 const lateDownload=await holdResponse(paper,"reviewer/download");await paper.locator("#reviewer-download-request").click();await lateDownload.captured;
 await paper.locator("#reviewer-question").fill("Changed before the real raw request download arrived");await lateDownload.release();
 assert.equal(staleDownloads,0);paper.off("download",countDownload);controls.push({control:"late-real-raw-download-is-discarded-after-context-change",passed:true});
 await paper.locator("#reviewer-settings>summary").click();await paper.locator("#reviewer-model").fill("provider-save-in-flight");
 const lateProvider=await holdResponse(paper,"reviewer/provider");await paper.locator("#reviewer-save-provider").click();await lateProvider.captured;
 await paper.locator("#reviewer-model").fill("newer-unsaved-provider-intent");await lateProvider.release();
 assert.equal(await paper.locator("#reviewer-model").inputValue(),"newer-unsaved-provider-intent");assert(await paper.locator("#reviewer-disclose").isDisabled());
 await configure(paper,"chat");controls.push({control:"late-provider-save-cannot-overwrite-newer-provider-form-intent",passed:true});
 const changedSourceDisclosure=await disclose(paper);
 await paper.locator("#reviewer-consent").check();
 const heldProjectPoll=await holdResponse(paper,"state");
 await heldProjectPoll.captured;
 const beforeSourceChange=(await snapshot()).calls.length;
 try {
  // Keep the real project poll pending so the request reaches server preflight.
  await rpc("damage-paper-source");
  await send(paper);
  await paper.locator('#figure-reviewer[data-phase="failed"]').waitFor();
  const refusedSource=await waitInactive("paper");
  assert.equal(refusedSource.calls.length,beforeSourceChange);
  assert(refusedSource.paper_sessions.some((r:any)=>r.id===changedSourceDisclosure.review_id
    &&["failed","cancelled","stale"].includes(r.phase)&&!r.result_present&&!r.worker_alive));
  assert(await paper.locator("#reviewer-advice").isHidden());
 } finally {
  await rpc("restore-paper-source");
  await heldProjectPoll.release();
 }
 controls.push({control:"actual-paper-source-change-after-consent-refuses-provider-call",passed:true});
 const refreshedDisclosure=await disclose(paper);
 await paper.locator("#reviewer-consent").check();
 const beforeRefresh=(await snapshot()).calls.length;
 let staleStarts=0;
 const countStart=(request:{url():string})=>{
  if(new URL(request.url()).pathname==="/api/reviewer/start")staleStarts++;
 };
 paper.on("request",countStart);
 try {
  const [cancelled]=await Promise.all([
   paper.waitForResponse(r=>new URL(r.url()).pathname==="/api/reviewer/cancel"),
   rpc("damage-paper-source"),
   paper.waitForFunction(()=>document.querySelector("#reviewer-start").disabled
     &&!document.querySelector("#reviewer-consent").checked
     &&document.querySelector("#reviewer-disclosure").hidden),
  ]);
  assert.equal(cancelled.status(),200);
  const refreshed=await waitInactive("paper");
  assert.equal(staleStarts,0);
  assert.equal(refreshed.calls.length,beforeRefresh);
  assert(refreshed.paper_sessions.some((r:any)=>r.id===refreshedDisclosure.review_id
    &&r.phase==="cancelled"&&r.cancelled&&!r.result_present&&!r.worker_alive));
  assert(await paper.locator("#reviewer-advice").isHidden());
 } finally {
  paper.off("request",countStart);
  await rpc("restore-paper-source");
 }
 controls.push({control:"actual-paper-refresh-revokes-consent-before-dispatch",passed:true});
 // Rechecking unchanged native intent must revoke old consent before validation returns.
 activePage=page;await disclose(page);const heldValidation=await holdResponse(page,"validate");
 await page.locator("#render").click();await heldValidation.captured;
 assert(await page.locator("#reviewer-disclose").isDisabled());assert(await page.locator("#reviewer-disclosure").isHidden());
 const rechecked=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/render");await heldValidation.release();assert.equal((await rechecked).status(),200);
 await page.locator('#status[data-state="failed"]').waitFor();await disclose(page);
 controls.push({control:"same-generation-new-check-clears-review-before-real-validation-response",passed:true});
 const stagedSpec={...fixture.native_spec,title:"Reviewer staged checks pending"};await rpc("hold-native-check",{title:stagedSpec.title});await page.locator("#spec").fill(JSON.stringify(stagedSpec));
 const stagedResponse=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/render");await page.locator("#render").click();
 await page.locator('#preview[data-phase="unverified"]').waitFor();assert((await snapshot()).stage_entered);assert(await page.locator("#reviewer-disclose").isDisabled());assert(await page.locator("#reviewer-advice").isHidden());
 await page.locator("#figure-surface").screenshot({path:join(evidence,"native-provisional.png")});await rpc("release-native-check");const staged=await(await stagedResponse).json();assert.equal(staged.exit_code,2);
 await page.locator('#status[data-state="failed"]').waitFor();await disclose(page);
 controls.push({control:"actual-provisional-image-cannot-supply-completed-review-evidence",passed:true});
 const beforeExportChange=(await snapshot()).calls.length;await rpc("damage-native-export",{run_id:staged.run_id});await send(page);
 await page.locator('#figure-reviewer[data-phase="failed"]').waitFor();assert.equal((await snapshot()).calls.length,beforeExportChange);assert(await page.locator("#reviewer-download-result").isDisabled());
 controls.push({control:"actual-native-export-change-after-disclosure-refuses-provider-call",passed:true});
 await page.locator("#spec").fill("{");assert(await page.locator("#reviewer-disclose").isDisabled());assert(await page.locator("#reviewer-disclosure").isHidden());
 controls.push({control:"invalid-native-raw-JSON-clears-old-review-binding",passed:true});
 const emptySpec={...fixture.native_spec,filter:[{field:"body_mass_g",op:"gt",value:1000000000}]};
 await page.locator("#spec").fill(JSON.stringify(emptySpec));const emptyResponse=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/render");await page.locator("#render").click();
 const empty=await(await emptyResponse).json();assert.equal(empty.exit_code,1);assert.equal(empty.report.status,"failed");assert.deepEqual(empty.report.outputs,[]);assert(empty.review.available);
 await page.locator('#status[data-state="failed"]').waitFor();const emptyDisclosure=await disclose(page);
 assert.equal(emptyDisclosure.deterministic_evidence.figures[0].execution_status,"failed");assert.equal(emptyDisclosure.deterministic_evidence.figures[0].groups.reproduction.saved_exports_verified,false);
 await run(page);writeFileSync(join(evidence,"native-runtime-failure.json"),JSON.stringify(empty,null,2)+"\n");
 controls.push({control:"actual-empty-data-runtime-failure-remains-reviewable-without-invented-exports",passed:true});
 for(const [name,view] of [["native",page],["paper",paper]] as const){
  activePage=view;await view.setViewportSize({width:430,height:940});const box=await view.locator("#figure-reviewer").boundingBox();assert(box&&box.width>250&&box.x>=0&&box.x+box.width<=431);
  await view.locator("#figure-reviewer").screenshot({path:join(evidence,name+"-reviewer-mobile.png")});
 }
 controls.push({control:"both-actual-reviewer-panels-fit-430px-mobile-viewports",passed:true});
 const fresh=await browser.newPage();activePage=fresh;observe(fresh);await fresh.goto(fixture.fresh);await fresh.locator('#review-figure option[value="unrun-01"]').waitFor({state:"attached"});await configure(fresh,"chat");
 await fresh.waitForFunction(()=>document.querySelectorAll("#reviewer-figures input").length===22);
 const choices=await fresh.locator("#reviewer-figures input").all();for(const [index,choice] of choices.entries()){if(index<20)await choice.check();else await choice.uncheck();}
 const twenty=await disclose(fresh);assert.equal(twenty.deterministic_evidence.figures.length,20);assert(twenty.deterministic_evidence.figures.every((f:any)=>f.evidence_state==="not_run"&&f.execution_status==="not_available"));await run(fresh);
 controls.push({control:"twenty-actual-never-audited-figures-remain-not-run-in-model-evidence",passed:true});
 await choices[20]!.check();assert(await fresh.locator("#reviewer-disclose").isDisabled());assert(await fresh.locator("#reviewer-advice").isHidden());assert(await fresh.locator("#reviewer-disclosure").isHidden());
 controls.push({control:"twenty-one-real-figure-selection-refuses-new-disclosure",passed:true});
 activePage=page;await rpc("mode",{mode:"held"});const beforeClose=(await snapshot()).calls.length;
 const closingDisclosure=await disclose(page);await send(page);await waitForCalls(beforeClose+1);await page.goto("about:blank");const closed=await waitInactive("native");
 assert(closed.native_sessions.some((r:any)=>r.id===closingDisclosure.review_id&&r.cancelled&&r.phase==="cancelled"&&!r.worker_alive));await rpc("release");
 assert.equal((await snapshot()).calls.length,beforeClose+1);controls.push({control:"actual-pagehide-cancels-owned-review-without-retry",passed:true});
 const state=await snapshot();assert(state.public_source_unchanged);assert(state.calls.every((c:any)=>!c.key_in_body&&c.authorization_present));
 assert.deepEqual(state.paper_definitions,originalState.paper_definitions);assert.equal(state.paper_source_sha256,originalState.paper_source_sha256);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(resources,[]);
 const revision=spawnSync("git",["-c","gc.auto=0","-c","maintenance.auto=false","rev-parse","HEAD"],{cwd:root,encoding:"utf8"});assert.equal(revision.status,0,revision.stderr);if(process.env.GITHUB_SHA)assert.equal(revision.stdout.trim(),process.env.GITHUB_SHA);
 assert(fixture.runtime&&Object.keys(fixture.runtime.files).length>=107);assert(state.runtime_unchanged);
 if(process.env.GRAPHUNSLOPIFY_REVIEWER_INSTALLED)assert(fixture.runtime.package_root.includes("site-packages"));
 else assert.equal(resolve(fixture.runtime.package_root),join(root,"python/graphunslopify"));
 writeFileSync(join(evidence,"verification.json"),JSON.stringify({status:"browser-controls-passed",controls,requests:state.calls,errors,external,resource_errors:resources,source_revision:revision.stdout.trim(),runtime:fixture.runtime,native_artifacts:nativeArtifacts,driver_sha256:sha(readFileSync(join(root,"scripts/reviewer-check.ts"))),fixture_sha256:sha(readFileSync(join(root,"scripts/serve-reviewer-check.py"))),public_source_sha256:fixture.public_source_sha256,public_source_unchanged:true,scientific_definitions_unchanged:true,scope:"Actual native/paper browser controls and controlled HTTP;not inference or full97 acceptance",remaining:"provisional/source-change/configured-inference/current-minimum-installed/full-gate acceptance"},null,2)+"\n");
 console.log(JSON.stringify({evidence,controls:controls.length,scope:"actual reviewer browser controls;full97 acceptance remains open"}));
}catch(error){
 const ui=activePage?await activePage.evaluate(()=>({phase:document.querySelector("#figure-reviewer")?.dataset.phase,status:document.querySelector("#reviewer-status")?.textContent,native_status:document.querySelector("#status")?.textContent,native_state:document.querySelector("#status")?.dataset.state,project_error:document.querySelector("#error")?.textContent,project_notice:document.querySelector("#notice")?.textContent,project_running:document.querySelector("#running")?.textContent,figure_choices:document.querySelectorAll("#reviewer-figures input").length})).catch(()=>null):null;
 writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(error),controls,errors,external,resource_errors:resources,runtime:fixture?.runtime,ui,stderr},null,2)+"\n");
 if(activePage)await activePage.screenshot({path:join(evidence,"failure.png"),fullPage:true});throw error;
}finally{
 let browserClosed=!browser, fixtureClosed=!processHandle;
 try{await browser?.close();browserClosed=true;}
 finally{
  try{
   if(processHandle?.pid&&processHandle.exitCode===null){try{await rpc("stop");}finally{processHandle.stdin!.end();fixtureClosed=(await processExit)===0;}}
   else if(processHandle)fixtureClosed=(await processExit)===0;
  }finally{if(browserClosed&&fixtureClosed)rmSync(scratch,{recursive:true,force:true});}
 }
}
