/** Actual diagnostic selection, image ownership, responsive bounds and explicit repair. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import { chromium, type Page } from "playwright";

type Rect = {x:number;y:number;width:number;height:number};
type BrowserNode = {textContent:string;hidden:boolean;complete:boolean;naturalWidth:number;currentSrc:string;getBoundingClientRect():Rect};
declare const document: {querySelector(selector:string):BrowserNode|null;querySelectorAll(selector:string):ArrayLike<BrowserNode>;documentElement:{scrollWidth:number}};
declare const window:{innerWidth:number};

export async function checkDiagnostics(page: Page, evidence: string) {
  const workflows:string[]=[];
  let renderPosts=0;
  const counted=(request:{url():string})=>{if(request.url().endsWith("/api/render"))renderPosts++;};
  page.on("request",counted);
  const spec=async()=>JSON.parse(await page.locator("#spec").inputValue());
  const edit=async(value:object)=>{
    await page.locator("#advanced").evaluate(node=>node.setAttribute("open",""));
    await page.locator("#spec").fill(JSON.stringify(value,null,2));
    await page.waitForFunction(()=>["Ready to render","Fix specification"].includes(document.querySelector("#status")?.textContent||""));
  };
  const upload=async(name:string,csv:string)=>{
    await page.locator("#data-file").setInputFiles({name,mimeType:"text/csv",buffer:Buffer.from(csv)});
    await page.waitForFunction(name=>document.querySelector("#data-summary")?.textContent.includes(name)&&!document.querySelector("#data-summary")?.textContent.startsWith("Reading "),name);
  };
  const rendered=async(value:object)=>{
    await edit(value);
    const response=page.waitForResponse(r=>r.url().endsWith("/api/render"));
    await page.locator("#render").click();const result=await(await response).json();
    await page.waitForFunction(run=>{const image=document.querySelector("#preview");return image&&!image.hidden&&image.complete&&image.naturalWidth>10&&image.currentSrc.includes(`/artifact/${run}/`);},result.run_id);
    return result;
  };
  const clipped={kind:"bar",title:"Observed range",x:{field:"category",label:"Category"},y:{field:"value",label:"Value",limits:[0,5]},aggregation:"mean",uncertainty:{kind:"range"},legend:{show:false},output:{stem:"diagnostics",formats:["png","svg","pdf"]}};
  try {
    await page.locator("#model-drafts").evaluate(node=>node.removeAttribute("open"));
    await page.locator("#live").uncheck();
    await upload("diagnostic-values.csv","category,value\nA,1\nA,2\nA,9\n");
    const result=await rendered(clipped);
    assert.equal(result.report.status,"failed");assert.equal(result.exit_code,2);
    const index=result.report.findings.findIndex((f:{code:string})=>f.code==="bar_interval_clipped");assert.ok(index>=0);
    assert.ok(result.diagnostic_map.targets.some((t:{finding_index:number})=>t.finding_index===index));
    const original=await spec(),requests=renderPosts,bundleDisabled=await page.locator("#bundle").isDisabled();
    await page.locator("#show-diagnostics").click();
    const marker=page.getByRole("button",{name:"Show finding: bar interval clipped",exact:true}).first();
    await marker.click();
    assert.match(await page.locator("#diagnostic-description").innerText(),/Why it matters:[\s\S]*Recommended correction:/);
    assert.match(await page.locator("#diagnostic-description").innerText(),/true endpoints/);
    assert.deepEqual(await spec(),original);assert.equal(renderPosts,requests);
    assert.equal(await page.locator("#bundle").isDisabled(),bundleDisabled);
    assert.equal(await page.locator("#status").getAttribute("data-state"),"failed");
    workflows.push("actual clipped interval selection preserves intent render count strict failure and review-artifact availability");
    await marker.focus();await marker.press("Enter");
    const focusState=await page.locator("#diagnostic-description").evaluate(node=>({focused:node===node.ownerDocument.activeElement,active:node.ownerDocument.activeElement?.id,tag:node.ownerDocument.activeElement?.tagName}));
    assert.equal(focusState.focused,true,JSON.stringify(focusState));
    await page.locator("#diagnostic-description").press("Escape");
    assert.equal(await page.locator("#diagnostic-review").isHidden(),true);
    await page.locator('#findings .finding[data-code="bar_interval_clipped"] .finding-location').click();
    workflows.push("keyboard and finding-card locate actions select the actual runtime finding");

    const geometry=[];
    for(const [name,width,height] of [["desktop",1500,1000],["narrow",390,844],["wide",1800,900],["short",1280,540]] as const){
      await page.setViewportSize({width,height});
      await page.locator("#figure-surface").scrollIntoViewIfNeeded();
      const measured=await page.evaluate(()=>({image:document.querySelector("#preview")!.getBoundingClientRect(),targets:Array.from(document.querySelectorAll("#diagnostic-targets button")).map(node=>node.getBoundingClientRect()),overflow:document.documentElement.scrollWidth>window.innerWidth}));
      assert.equal(measured.overflow,false);assert.equal(measured.targets.length,result.diagnostic_map.targets.length);
      for(let i=0;i<measured.targets.length;i++){
        const actual=measured.targets[i]!,bounds=result.diagnostic_map.targets[i].bounds,image=measured.image,source=result.diagnostic_map.image;
        const expected=[image.x+bounds[0]/source.width*image.width,image.y+bounds[1]/source.height*image.height,bounds[2]/source.width*image.width,bounds[3]/source.height*image.height];
        for(const [j,key] of ["x","y","width","height"].entries())assert.ok(Math.abs(actual[key as keyof Rect]-expected[j]!)<=1,`${name} ${key}: ${actual[key as keyof Rect]} vs ${expected[j]}`);
      }
      geometry.push({viewport:name,...measured});
      await page.locator(".preview").screenshot({path:join(evidence,`diagnostics-${name}.png`)});
      if(name==="narrow"){
        await marker.click();await marker.focus();await marker.press("Enter");
        assert.equal(await page.locator("#diagnostic-review").isVisible(),true);
        assert.deepEqual(await spec(),original);
        workflows.push("narrow viewport diagnostic click and keyboard selection preserve canonical intent");
      }
    }
    workflows.push("measured diagnostic rectangles align with actual PNG at desktop narrow wide and short-height viewports");
    await page.setViewportSize({width:1500,height:1000});
    const unknown=result.diagnostic_map.unlocated[0];assert.ok(unknown);
    await page.locator("#diagnostic-finding").selectOption(String(unknown.finding_index));
    assert.match(await page.locator("#diagnostic-location").innerText(),/Location unavailable/);
    assert.equal(await page.locator("#diagnostic-targets .selected").count(),0);
    workflows.push("unlocated actual findings remain explicit without invented highlighted regions");

    await page.locator("#edit-figure-text").click();assert.equal(await page.locator("#diagnostic-targets").isHidden(),true);
    await page.getByRole("button",{name:"Edit Title: Observed range",exact:true}).click();
    await page.locator("#text-wording").fill("Unapplied wording");
    await page.locator("#show-diagnostics").click();assert.equal(await page.locator("#text-targets").isHidden(),true);
    await page.locator("#edit-figure-text").click();assert.equal(await page.locator("#text-wording").inputValue(),"Unapplied wording");
    assert.deepEqual(await spec(),original);
    workflows.push("switching text and diagnostic modes preserves unapplied wording and canonical intent");

    for(const mutation of ["version","image_hash","finding_index","bounds"]){
      await page.route("**/api/render",async route=>{
        const response=await route.fetch(),body=await response.json();
        if(mutation==="version")body.diagnostic_map.schema_version=999;
        if(mutation==="image_hash")body.diagnostic_map.image.sha256="0".repeat(64);
        if(mutation==="finding_index")body.diagnostic_map.targets[0].finding_index=999999;
        if(mutation==="bounds")body.diagnostic_map.targets[0].bounds[0]=-10;
        await route.fulfill({response,json:body});
      });
      try{
        const changed=await rendered({...clipped,title:`Refusal ${mutation}`});
        assert.equal(changed.report.status,"failed");
        await page.locator("#show-diagnostics").click();
        assert.equal(await page.locator("#diagnostic-targets button").count(),0);
        await page.locator("#diagnostic-finding").selectOption(String(index));
        assert.match(await page.locator("#diagnostic-location").innerText(),/Location unavailable/);
        assert.equal(await page.locator("#status").getAttribute("data-state"),"failed");
      }finally{await page.unroute("**/api/render");}
      workflows.push(`browser refuses ${mutation} diagnostic metadata without fake targets or false scientific acceptance`);
    }

    await rendered(clipped);await page.locator("#show-diagnostics").click();
    await page.getByRole("button",{name:"Show finding: bar interval clipped",exact:true}).first().click();
    await edit({...clipped,title:"Current edited intent"});
    assert.equal(await page.locator("#show-diagnostics").isDisabled(),true);
    assert.equal(await page.locator("#diagnostic-targets button").count(),0);
    workflows.push("canonical edits clear diagnostic review and old image targets immediately");

    let releaseHeld!:()=>void,signalHeld!:()=>void;
    const held=new Promise<void>(done=>signalHeld=done),released=new Promise<void>(done=>releaseHeld=done);
    await page.route("**/api/render",async route=>{const response=await route.fetch();signalHeld();await released;await route.fulfill({response});});
    try{
      await edit({...clipped,title:"Held old intent"});
      const oldResponse=page.waitForResponse(r=>r.url().endsWith("/api/render"));
      await page.locator("#render").click();await held;
      await page.locator("#spec").fill(JSON.stringify({...clipped,title:"New current intent"},null,2));
      releaseHeld();await oldResponse;
      await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="Ready to render");
      assert.equal((await spec()).title,"New current intent");
      assert.equal(await page.locator("#diagnostic-targets button").count(),0);
      assert.equal(await page.locator("#show-diagnostics").isDisabled(),true);
    }finally{releaseHeld();await page.unroute("**/api/render");}
    workflows.push("held completed old render cannot revive diagnostic targets after a newer canonical edit");

    for(const mode of ["literal","truncated"]){
      await page.route("**/api/render",async route=>{
        const response=await route.fetch(),body=await response.json();
        const i=body.report.findings.findIndex((item:{code:string})=>item.code==="bar_interval_clipped");
        if(mode==="literal")body.report.findings[i].message="<img src=x onerror=alert(1)> literal finding";
        else body.diagnostic_map.truncated=true;
        await route.fulfill({response,json:body});
      });
      try{
        await rendered({...clipped,title:`Controlled ${mode}`});await page.locator("#show-diagnostics").click();
        await page.getByRole("button",{name:"Show finding: bar interval clipped",exact:true}).first().click();
        if(mode==="literal"){
          assert.match(await page.locator("#diagnostic-description").innerText(),/<img src=x onerror=alert\(1\)> literal finding/);
          assert.equal(await page.locator("#diagnostic-description img, #diagnostic-description script").count(),0);
        }else assert.match(await page.locator("#diagnostic-location").innerText(),/additional locations could not be captured/);
      }finally{await page.unroute("**/api/render");}
      workflows.push(mode==="literal"?"literal diagnostic wording remains text without active markup":"partial location capture stays explicit alongside measured regions");
    }
    await upload("diagnostic-replacement.csv","category,value\nA,2\nA,3\nA,4\n");
    assert.equal(await page.locator("#diagnostic-targets button").count(),0);
    assert.equal(await page.locator("#show-diagnostics").isDisabled(),true);
    workflows.push("dataset replacement clears selected diagnostic locations before another render");

    const dates="date,value\n2024-01-01,1\n2024-01-02,2\n2024-01-03,3\n";
    await upload("diagnostic-dates.csv",dates);
    const temporal={kind:"line",title:"Observed dates",x:{field:"date",label:"Date",temporal:true,scale:"log"},y:{field:"value",label:"Value"},legend:{show:false},output:{formats:["png"]}};
    await edit(temporal);await page.locator("#render").click();
    await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="Fix specification");
    const repaired=page.waitForResponse(r=>r.url().endsWith("/api/render"));
    await page.locator('#findings .finding[data-code="temporal_log_axis"]').getByRole("button",{name:"Apply fix",exact:true}).click();
    const fixed=await(await repaired).json();
    writeFileSync(join(evidence,"diagnostic-fix-runtime-report.json"),JSON.stringify(fixed.report,null,2)+"\n");
    assert.equal(fixed.report.status,"passed",JSON.stringify(fixed.report.findings));
    assert.ok(!fixed.report.findings.some((item:{code:string})=>item.code==="tick_labels_collide"));
    assert.equal(fixed.report.data.sha256_prefix,createHash("sha256").update(dates).digest("hex").slice(0,16));
    assert.equal(fixed.report.data.counts.read,3);
    await page.locator('#status[data-state="passed"]').waitFor();
    assert.equal(await page.locator("#live").isChecked(),false);
    assert.equal((await spec()).x.scale,"linear");assert.equal((await spec()).x.temporal,true);
    assert.equal(await page.locator("#undo-controls").isDisabled(),false);
    await page.locator("#undo-controls").click();
    assert.equal((await spec()).x.scale,"log");assert.equal(await page.locator("#bundle").isDisabled(),true);
    workflows.push("three-day temporal repair fits actual date labels retains original observations and joins native undo");

    const years="date,value\n2020-01-01,1\n2024-01-01,2\n2028-01-01,3\n";
    await upload("diagnostic-years.csv",years);
    await edit({...temporal,output:{formats:["png"],size:"double_column"}});
    const acceptedRepair=page.waitForResponse(r=>r.url().endsWith("/api/render"));
    await page.locator('#findings .finding[data-code="temporal_log_axis"]').getByRole("button",{name:"Apply fix",exact:true}).click();
    const accepted=await(await acceptedRepair).json();
    assert.equal(accepted.report.status,"passed",JSON.stringify(accepted.report.findings));
    assert.equal(accepted.report.data.sha256_prefix,createHash("sha256").update(years).digest("hex").slice(0,16));
    assert.equal(accepted.report.data.counts.read,3);
    await page.locator('#status[data-state="passed"]').waitFor();
    assert.equal(await page.locator("#live").isChecked(),false);
    assert.equal((await spec()).x.scale,"linear");
    await page.locator("#undo-controls").click();
    assert.equal((await spec()).x.scale,"log");assert.equal(await page.locator("#bundle").isDisabled(),true);
    workflows.push("valid explicit temporal repair renders verified in manual mode and native undo restores authored intent");

    const hiddenDomain="date,value\n2024-01-01,-1\n2024-01-02,2\n2024-01-03,3\n";
    await upload("diagnostic-log-domain.csv",hiddenDomain);
    await edit({...temporal,y:{field:"value",label:"Value",scale:"log"}});
    const negativeRepair=page.waitForResponse(r=>r.url().endsWith("/api/render"));
    await page.locator('#findings .finding[data-code="temporal_log_axis"]').getByRole("button",{name:"Apply fix",exact:true}).click();
    const negative=await(await negativeRepair).json();
    assert.equal(negative.report.status,"failed");assert.equal(negative.exit_code,2);
    assert.ok(negative.report.findings.some((item:{code:string;severity:string})=>item.code==="log_domain_hidden"&&item.severity==="error"));
    assert.equal(negative.report.data.sha256_prefix,createHash("sha256").update(hiddenDomain).digest("hex").slice(0,16));
    assert.equal(negative.report.data.counts.read,3);
    await page.locator('#status[data-state="failed"]').waitFor();
    assert.equal((await spec()).x.scale,"linear");assert.equal((await spec()).y.scale,"log");
    await page.locator("#undo-controls").click();
    assert.equal((await spec()).x.scale,"log");assert.equal(await page.locator("#bundle").isDisabled(),true);
    workflows.push("explicit temporal repair still blocks actual negative observations hidden by an authored log value axis");

    const proof={passed:true,provider:"No model inference used by diagnostic cases",strict_negative_status:result.report.status,original_spec_unchanged_by_selection:true,geometry,workflows};
    writeFileSync(join(evidence,"diagnostic-overlays-checks.json"),JSON.stringify(proof,null,2)+"\n");return proof;
  }finally{page.off("request",counted);}
}

if(import.meta.url===pathToFileURL(process.argv[1]||"").href){
  const evidence=mkdtempSync(join(tmpdir(),"gu-diagnostic-browser-"));
  const env:NodeJS.ProcessEnv=process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED?{...process.env}:{...process.env,PYTHONPATH:resolve("python")};
  if(process.env.GRAPHUNSLOPIFY_PREVIEW_NODE_OPTIONS)env.NODE_OPTIONS=process.env.GRAPHUNSLOPIFY_PREVIEW_NODE_OPTIONS;
  const server=spawn(process.env.PYTHON||"python",["-m","graphunslopify.cli","preview","--port","0"],{env,stdio:["ignore","pipe","pipe"]});
  let stderr="";server.stderr.on("data",chunk=>stderr+=chunk);
  const lines=createInterface({input:server.stdout});
  const url=await new Promise<string>((accept,reject)=>{lines.once("line",line=>{try{accept(JSON.parse(line).url);}catch(error){reject(error);}});server.once("exit",code=>reject(Error(`Editor exited ${code}: ${stderr}`)));});
  let browser;
  try{
    const chrome=process.env.GRAPHUNSLOPIFY_BROWSER||"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
    browser=await chromium.launch({headless:true,...(existsSync(chrome)?{executablePath:chrome}:{})});
    const page=await browser.newPage({viewport:{width:1500,height:1000},acceptDownloads:true});page.setDefaultTimeout(120000);
    const errors:string[]=[],external:string[]=[];page.on("pageerror",error=>errors.push(error.message));page.on("request",request=>{if(!request.url().startsWith(url)&&!request.url().startsWith("data:"))external.push(request.url());});
    await page.goto(url);await page.waitForFunction(()=>document.querySelectorAll("#kind option").length===21);
    const proof=await checkDiagnostics(page,evidence);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);console.log(JSON.stringify({...proof,evidence,javascript_errors:errors.length,external_browser_requests:external.length}));
  }finally{await browser?.close();server.kill();}
}
