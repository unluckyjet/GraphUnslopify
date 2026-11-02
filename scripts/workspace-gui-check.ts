/** Seven public-data tasks through actual controls, with original downloads and failures. */
import assert from "node:assert/strict";
import {spawn,spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import {existsSync,mkdirSync,readFileSync,writeFileSync} from "node:fs";
import {basename,join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type Page} from "playwright";

declare const document:{documentElement:{scrollWidth:number}};
declare const window:{innerWidth:number};

const outputIndex=process.argv.indexOf("--out");
assert.ok(outputIndex>=0&&process.argv[outputIndex+1],"--out NEW_DIRECTORY is required");
const output=resolve(process.argv[outputIndex+1]!);
mkdirSync(output,{recursive:false});
const executionIndex=process.argv.indexOf("--execution-context");
const executionArgs=executionIndex<0?[]:["--execution-context",resolve(process.argv[executionIndex+1]!)];
const installed=process.argv.includes("--installed"),python=process.env.PYTHON||"python";
const protocol=JSON.parse(readFileSync("benchmarks/workspace/protocol.json","utf8"));
const env={...process.env};if(installed)delete env.PYTHONPATH;else env.PYTHONPATH=resolve("python");
const child=spawn(python,["benchmarks/workspace/gui_server.py","--out",join(output,"server"),...(installed?["--installed"]:[]),...executionArgs],{env,stdio:["pipe","pipe","pipe"]});
let stderr="";child.stderr.on("data",chunk=>{stderr+=chunk;});
const exited=new Promise<number|null>(accept=>child.once("exit",accept));
const lines=createInterface({input:child.stdout});
const startup=await new Promise<any>((accept,reject)=>{
  let ready=false;
  const failed=(error:Error)=>{
    if(ready)return;ready=true;clearTimeout(timer);
    writeFileSync(join(output,"server-stderr.log"),stderr);
    writeFileSync(join(output,"browser-results.json"),JSON.stringify({profile:installed?"fresh-wheel":"source-current",startup_error:error.stack,rows:protocol.gui.tasks.map((task:string)=>({task,attempted:false,outcome:"not_run",error:error.message,formal_comparison_performed:false})),formal_comparison_performed:false},null,2)+"\n");
    child.stdin.end();reject(error);
  };
  const timer=setTimeout(()=>{child.kill();failed(Error("GUI server startup deadline expired before any browser request"));},45_000);
  lines.once("line",line=>{try{const value=JSON.parse(line);ready=true;clearTimeout(timer);accept(value);}catch(error){failed(error instanceof Error?error:Error(String(error)));}});
  child.once("error",failed);child.once("exit",code=>failed(Error(`GUI server exited ${code}: ${stderr}`)));
});
const execution=startup.execution_context;assert.ok(execution&&typeof execution.formal_comparison_performed==="boolean");
const hash=(raw:Uint8Array)=>createHash("sha256").update(raw).digest("hex");
const rows:any[]=[],pageErrors:string[]=[],external:string[]=[];
let browser:Awaited<ReturnType<typeof chromium.launch>>|undefined;
let row:any;
const record=(action:string,control:string,value?:unknown)=>row.actions.push({action,control,...(value===undefined?{}:{value})});
const spec=(name:string)=>JSON.parse(readFileSync(`benchmarks/workspace/figures/${name}.json`,"utf8"));
const current=(page:Page)=>page.locator("#spec").inputValue().then(JSON.parse);
async function section(page:Page,name:string){
  const details=page.locator("#settings > details").filter({has:page.getByText(name,{exact:true})});
  if(await details.getAttribute("open")===null){record("click","settings summary",name);await details.locator(":scope > summary").click();}
}
async function fill(page:Page,id:string,value:string){record("fill",id,value);await page.locator("#"+id).fill(value);await page.locator("#"+id).press("Tab");}
async function select(page:Page,id:string,value:string){record("select",id,value);await page.locator("#"+id).selectOption(value);}
async function upload(page:Page,path:string){
  record("file input","data-file",{name:basename(path),sha256:hash(readFileSync(path))});
  const response=page.waitForResponse(r=>r.url().endsWith("/api/suggest"));
  await page.locator("#data-file").setInputFiles(path);await(await response).finished();
  await page.locator("#data-summary").filter({hasText:basename(path)}).waitFor();
}
async function settings(page:Page,desired:any){
  await select(page,"kind",desired.kind);await select(page,"x-field",desired.x.field);await select(page,"y-field",desired.y.field);await select(page,"group",desired.group||"");
  await section(page,"Labels and units");await fill(page,"control-title",desired.title);
  for(const axis of ["x","y"]){await fill(page,`control-${axis}-label`,desired[axis].label);await fill(page,`control-${axis}-unit`,desired[axis].unit||"");}
  await section(page,"Axis scales and limits");for(const axis of ["x","y"])await select(page,`control-${axis}-scale`,desired[axis].scale||"linear");
  if(await page.locator("#control-uncertainty-kind").count()){
    await section(page,"Summaries and uncertainty");
    await select(page,"control-uncertainty-kind",desired.uncertainty?.kind||"");
    if(desired.aggregation)await select(page,"control-aggregation",desired.aggregation);
    if(desired.uncertainty?.display)await select(page,"control-uncertainty-display",desired.uncertainty.display);
  }
  await section(page,"Legend and paper style");await select(page,"control-legend-position",desired.legend.position);
  await fill(page,"control-series_order",desired.series_order?.join("\n")||"");
  await section(page,"Manuscript and exports");await select(page,"control-output-size",desired.output.size);await fill(page,"control-output-dpi",String(desired.output.dpi));await fill(page,"control-output-stem",desired.output.stem);
  for(const format of ["svg","pdf"]){record("checkbox","control-format-"+format,true);await page.locator("#control-format-"+format).check();}
  if(desired.claims){
    await section(page,"Claims to check");
    for(const [index,claim] of desired.claims.entries()){
      record("click","add-claim");await page.locator("#add-claim").click();await select(page,`control-claims-${index}-kind`,claim.kind);
      await fill(page,`control-claims-${index}-subject`,claim.subject);await fill(page,`control-claims-${index}-reference`,claim.reference);
    }
  }
}
async function configure(page:Page,name:string){
  const desired=spec(name),data=resolve("benchmarks/workspace/figures",desired.data.path);
  await upload(page,data);
  // A public recipe replaces recommendation-specific scientific intent through the UI.
  await select(page,"recipe","scaling_law");await settings(page,desired);return {desired,data};
}
async function render(page:Page,desired:any,data:string,phase:string,button="render"){
  record("click",button);const pending=page.waitForResponse(r=>r.url().endsWith("/api/render"));await page.locator("#"+button).click();
  const response=await pending,answer=await response.json();await response.finished();
  row.responses.push({phase,http_status:response.status(),answer,expected:structuredClone(desired),data_source:data});
  assert.ok(answer.run_id&&answer.report,JSON.stringify(answer.translation||answer));
  await page.locator('#status[data-state="passed"],#status[data-state="failed"]').waitFor();
  return answer;
}
async function downloadBundle(page:Page,name:string){
  const pending=page.waitForEvent("download");record("click","bundle");await page.locator("#bundle").click();const download=await pending,path=join(output,name+".zip");await download.saveAs(path);row.downloads.push({kind:"bundle",path,run_id:row.responses.at(-1).answer.run_id,sha256:hash(readFileSync(path))});
}
async function reuseOpen(page:Page){if(await page.locator("#reuse-panel").getAttribute("open")===null){record("click","reuse summary");await page.locator("#reuse-panel > summary").click();}}
async function proposal(page:Page,button:string){const pending=page.waitForResponse(r=>r.url().endsWith("/api/reuse/proposal"));record("click",button);await page.locator("#"+button).click();const response=await pending,value=await response.json();await response.finished();row.proposals.push(value);await page.locator("#reuse-review").waitFor();return value;}
try{
  const mac="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  browser=await chromium.launch({headless:true,...(existsSync(mac)?{executablePath:mac}:{})});
  for(const [index,task] of protocol.gui.tasks.entries()){
    row={task,profile:installed?"fresh-wheel":"source-current",attempted:true,outcome:"not_run",actions:[],responses:[],proposals:[],downloads:[],required_json_edits:[],module_network_failures:[],error:null,formal_comparison_performed:execution.formal_comparison_performed,execution_context:execution};rows.push(row);
    const page=await browser.newPage({viewport:index%2?{width:390,height:844}:{width:1440,height:1000},acceptDownloads:true});page.setDefaultTimeout(60_000);
    const taskRow=row;
    page.on("pageerror",error=>pageErrors.push(error.message));page.on("request",request=>{if(!/^(http:\/\/127\.0\.0\.1:|blob:|data:)/.test(request.url()))external.push(request.url());});
    page.on("requestfailed",request=>{const path=new URL(request.url()).pathname;if(/\.(js|css)$|^\/api\/info$/.test(path))taskRow.module_network_failures.push({path,error:request.failure()});});
    page.on("response",response=>{const path=new URL(response.url()).pathname;if(response.status()>=400&&/\.(js|css)$|^\/api\/info$/.test(path))taskRow.module_network_failures.push({path,status:response.status()});});
    try{
      await page.goto(startup.url);await page.locator("#reuse-preset option").nth(2).waitFor({state:"attached"});record("checkbox","live",false);await page.locator("#live").uncheck();
      if(index<4){
        const name=task.replace(/-first$/,""),{desired,data}=await configure(page,name);
        if(desired.filter&&!((await current(page)).filter))row.required_json_edits.push("filter: public controls do not expose the frozen redundant sex filter");
        await render(page,desired,data,"first");await downloadBundle(page,`task-${index}`);
      }else if(index===4){
        const {desired,data}=await configure(page,"iris-scatter");await render(page,desired,data,"setup");
        for(const [role,path,wording] of [["Title",["title"],"Iris petals, original observations"],["Axis label",["y","label"],"Petal width, descriptive"]] as const){
          if(await page.locator("#edit-figure-text").getAttribute("aria-pressed")!=="true"){record("click","edit-figure-text");await page.locator("#edit-figure-text").click();}
          const target=role==="Title"?page.getByRole("button",{name:/^Edit Title:/}).first():page.getByRole("button",{name:/^Edit Axis label: Petal width/}).first();record("click","owned text target",role);await target.click();await fill(page,"text-wording",wording);record("click","review-text");await page.locator("#review-text").click();record("keyboard Space","text-meaning",true);assert.equal(await page.locator("#text-meaning").isChecked(),false);await page.locator("#text-meaning").focus();await page.locator("#text-meaning").press("Space");
          if(path.length===1)desired.title=wording;else desired.y.label=wording;await render(page,desired,data,"direct-"+role,"apply-text");
        }
        await downloadBundle(page,`task-${index}`);
      }else if(index===5){
        const {desired,data}=await configure(page,"iris-scatter");await render(page,desired,data,"setup");await reuseOpen(page);
        const presets=[{id:"paper-single",size:"single_column",dpi:600,formats:["png","svg","pdf"]},{id:"paper-double",size:"double_column",dpi:600,formats:["png","svg","pdf"]},{id:"review-png",size:"single_column",dpi:144,formats:["png"]}];
        for(const preset of presets){
          await select(page,"reuse-preset",preset.id);await proposal(page,"reuse-preset-review");record("keyboard Space","reuse-reviewed",true);assert.equal(await page.locator("#reuse-reviewed").isChecked(),false);await page.locator("#reuse-reviewed").focus();await page.locator("#reuse-reviewed").press("Space");desired.output={...desired.output,size:preset.size,dpi:preset.dpi,formats:preset.formats};
          if(preset.id!=="review-png")desired.style={preset:"paper",venue:"none"};else{desired.output.interactive=false;desired.output.latex=false;}
          await render(page,desired,data,preset.id,"reuse-apply");await downloadBundle(page,`task-${index}-${preset.id}`);
        }
      }else{
        const {desired,data}=await configure(page,"iris-scatter");await render(page,desired,data,"setup");await reuseOpen(page);await fill(page,"reuse-name","Iris public-data design");
        const pending=page.waitForEvent("download");record("click","reuse-save");await page.locator("#reuse-save").click();const download=await pending,path=join(output,"iris.gu-template.json");await download.saveAs(path);row.downloads.push({kind:"template",path,sha256:hash(readFileSync(path))});
        const target=spec("iris-scatter-mm"),targetData=resolve("benchmarks/workspace/figures",target.data.path);await upload(page,targetData);
        const imported=page.waitForResponse(r=>r.url().endsWith("/api/reuse/proposal"));record("file input","reuse-file",{name:basename(path),sha256:hash(readFileSync(path))});await page.locator("#reuse-file").setInputFiles(path);row.proposals.push(await(await imported).json());
        for(const [field,mapped] of Object.entries({petal_length:"petal_length_mm",petal_width:"petal_width_mm"})){record("select","Map template field "+field,mapped);await page.getByLabel("Map template field "+field,{exact:true}).selectOption(mapped);}
        await proposal(page,"reuse-template-review");record("checkbox","reuse-reviewed",true);await page.locator("#reuse-reviewed").check();await render(page,target,targetData,"mapped-before-unit-correction","reuse-apply");
        await section(page,"Labels and units");await fill(page,"control-x-unit","mm");await fill(page,"control-y-unit","mm");await render(page,target,targetData,"corrected-units");await downloadBundle(page,`task-${index}`);
      }
      row.outcome="completed";
    }catch(error){row.outcome="controls_failed";row.error=error instanceof Error?error.stack:String(error);}
    finally{
      row.final_spec_read_only=await current(page).catch(()=>null);row.viewports=[];
      for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
        await page.setViewportSize(viewport);const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);row.viewports.push({...viewport,no_horizontal_overflow:noOverflow});
        await page.screenshot({path:join(output,`task-${index}-${viewport.width}.png`),fullPage:true}).catch(error=>{row.screenshot_error=String(error);});
      }
      await page.close();
      writeFileSync(join(output,"progress.json"),JSON.stringify({rows,page_errors:pageErrors,external_requests:external},null,2)+"\n");console.log(JSON.stringify({task,outcome:row.outcome,error:row.error?.split("\n")[0]}));
    }
  }
}finally{
  await browser?.close();child.stdin.end(JSON.stringify({operation:"close"})+"\n");
  const status=await exited;writeFileSync(join(output,"server-stderr.log"),stderr);
  const result={profile:installed?"fresh-wheel":"source-current",startup,rows,page_errors:pageErrors,external_requests:external,server_exit_code:status,scope:"Seven actual typed-control tasks; explicit execution mode, no JSON mutation, mocks or human authoring claim",formal_comparison_performed:execution.formal_comparison_performed,execution_context:execution};writeFileSync(join(output,"browser-results.json"),JSON.stringify(result,null,2)+"\n");
  const verified=spawnSync(python,["scripts/check-workspace-gui.py","--browser-results",join(output,"browser-results.json"),"--out",join(output,"conformance.json"),...executionArgs],{env,encoding:"utf8"});
  process.stdout.write(verified.stdout||"");process.stderr.write(verified.stderr||"");process.exitCode=verified.status??1;
}
