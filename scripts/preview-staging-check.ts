/** Actual staged editor with the original scientific checker held, then released. */
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {randomUUID} from "node:crypto";
import {existsSync, readFileSync, renameSync, writeFileSync} from "node:fs";
import {join, resolve} from "node:path";
import {createInterface} from "node:readline";
import {setTimeout as delay} from "node:timers/promises";
import type {Browser, Route} from "playwright";
declare const document: {
  querySelector(selector: string): any;
  querySelectorAll(selector: string): {length: number};
};

export async function checkStaging(browser: Browser, evidence: string,
  env: NodeJS.ProcessEnv, python: string) {
  const control = join(evidence, "controlled-check");
  const server = spawn(python, [resolve("scripts/serve-preview-staging-check.py"),
    "--control-dir", control], {env, stdio:["ignore", "pipe", "pipe"]});
  let stderr = "";
  server.stderr.on("data", chunk => {stderr = (stderr + chunk).slice(-12000);});
  const lines = createInterface({input:server.stdout});
  const page = await browser.newPage({viewport:{width:1500,height:1000}});
  page.setDefaultTimeout(40000);
  const errors: string[] = [], external: string[] = [], workflows: string[] = [];
  const releases: Array<() => void> = [], nonces: string[] = [];
  const renders: any[] = [], observations: Promise<void>[] = [];
  const tickets = new Map<string,string>();
  page.on("pageerror", error => errors.push(error.message));
  let url = "";
  page.on("request", request => {
    if (url && !request.url().startsWith(url) && !request.url().startsWith("data:"))
      external.push(request.url());
    if (request.url().endsWith("/api/render")) {
      const payload = request.postDataJSON();
      if (payload.stage_id) tickets.set(payload.stage_id, payload.spec.title || "");
    }
  });
  page.on("response", response => {
    if (response.url().endsWith("/api/render") && response.status()===200)
      observations.push(response.json().then(body => {renders.push(body);}));
  });
  async function waitFile(path: string) {
    const deadline = Date.now()+35000;
    while (!existsSync(path)) {
      if (Date.now()>deadline) throw Error("Original checker did not reach controlled boundary: "+stderr);
      await delay(10);
    }
  }
  function hold(title: string) {
    const nonce = randomUUID().replaceAll("-", "");
    nonces.push(nonce);
    writeFileSync(join(control,"control.tmp"), JSON.stringify({title,nonce}));
    renameSync(join(control,"control.tmp"),join(control,"control.json"));
    return {entered:()=>waitFile(join(control,nonce+".entered")),
      release:()=>writeFileSync(join(control,nonce+".release"),"")};
  }
  async function render(spec: object) {
    await page.locator("#advanced").evaluate(node=>node.setAttribute("open",""));
    await page.locator("#spec").fill(JSON.stringify(spec));
    await page.locator("#render").click();
  }
  async function final(state = "passed") {
    await page.locator(`#status[data-state="${state}"]`).waitFor();
    await page.waitForFunction(() => {
      const p=document.querySelector('#preview');
      return p.dataset.phase==='final' && !p.hidden && p.complete && p.naturalWidth>0;
    });
  }
  async function unverified() {
    await page.locator('#status[data-state="unverified"]').waitFor();
    assert.equal(await page.locator("#preview").getAttribute("data-phase"),"unverified");
    assert.equal(await page.locator("#preview").isVisible(),true);
    assert.equal(await page.locator("#bundle").isDisabled(),true);
    assert.equal(await page.locator("#files a").count(),0);
    assert.equal(await page.locator("#text-targets").isHidden(),true);
    assert.equal(await page.locator("#diagnostic-targets").isHidden(),true);
    assert.equal(await page.locator("#description-box").isHidden(),true);
    assert.equal(await page.locator("#claims").textContent(),"");
  }
  function titleFor(route: Route) {
    const match = new URL(route.request().url()).pathname.match(/^\/stage\/([0-9a-f]+)(?:\/png)?$/);
    return match?.[1] ? tickets.get(match[1]) : undefined;
  }
  try {
    url = await new Promise<string>((accept,reject)=>{
      const timer=setTimeout(()=>reject(Error("Controlled editor startup: "+stderr)),30000);
      lines.on("line",line=>{try {const body=JSON.parse(line);if(body.url){clearTimeout(timer);accept(body.url);}}catch {}});
      server.once("exit",code=>{clearTimeout(timer);reject(Error("Controlled editor exited "+code+": "+stderr));});
    });
    await page.goto(url);
    await page.waitForFunction(() => document.querySelectorAll('#kind option').length===21);
    await page.locator("#demo").click();
    await final();
    await page.locator("#live").uncheck();
    const clean = JSON.parse(readFileSync(resolve("benchmarks/staged/cases/demo-bootstrap/original.json"),"utf8"));
    await page.locator("#data-file").setInputFiles(resolve("benchmarks/rendering/cases/demo-bootstrap/data.csv"));
    await page.waitForFunction(() => document.querySelector('#status').textContent==='Ready to render');

    const first=hold("Stage genuine clean");
    await render({...clean,title:"Stage genuine clean"});
    await first.entered();
    await unverified();
    assert(!renders.some(r=>r.report?.spec.title==="Stage genuine clean"));
    await page.screenshot({path:join(evidence,"staged-unverified.png"),fullPage:true});
    first.release();
    await final();
    assert.equal(await page.locator("#bundle").isEnabled(),true);
    workflows.push("actual unverified GUI image before genuine checker with exports/maps unavailable");

    const negative = JSON.parse(readFileSync(resolve("benchmarks/staged/cases/false-comparison/original.json"),"utf8"));
    await page.locator("#data-file").setInputFiles(resolve("benchmarks/rendering/cases/false-comparison/data.csv"));
    await page.waitForFunction(() => document.querySelector('#status').textContent==='Ready to render');
    const failed=hold("Stage genuine strict failure");
    await render({...negative,title:"Stage genuine strict failure"});
    await failed.entered();await unverified();failed.release();await final("failed");
    await page.screenshot({path:join(evidence,"staged-failed.png"),fullPage:true});
    workflows.push("original false claim remains visible strict failure after unverified preview");

    for (const kind of ["metadata","image"] as const) {
      const title="Stage delayed "+kind, native=hold(title);
      let announce!:()=>void, release!:()=>void;
      const intercepted=new Promise<void>(resolve=>announce=resolve);
      const gate=new Promise<void>(resolve=>release=resolve);
      releases.push(release);
      const pattern=kind==="image" ? "**/stage/*/png?*" : "**/stage/*?*";
      let caught=false;
      await page.route(pattern,async route=>{
        if (caught || titleFor(route)!==title ||
            (kind==="metadata" && new URL(route.request().url()).pathname.endsWith("/png")))
          return route.continue();
        const response=await route.fetch();
        if (kind==="metadata" && (await response.json()).phase!=="unverified")
          return route.fulfill({response});
        caught=true;announce();await gate;
        try {await route.fulfill({response});} catch { /* canceled old progress request */ }
      });
      await render({...clean,title});await native.entered();
      await Promise.race([intercepted,delay(30000, undefined, {ref:false}).then(()=>{throw Error("No delayed "+kind+" response");})]);
      native.release();await final();
      const finalImage=await page.locator("#preview").getAttribute("src");
      release();await page.unrouteAll({behavior:"wait"});await delay(75);
      assert.equal(await page.locator("#preview").getAttribute("src"),finalImage);
      assert.equal(await page.locator("#status").textContent(),"Verified");
      assert.equal(await page.locator("#preview").getAttribute("data-phase"),"final");
      workflows.push("late provisional "+kind+" cannot replace a current final result");
    }

    const old=hold("Stage invalidated while checking");
    await render({...clean,title:"Stage invalidated while checking"});
    await old.entered();await unverified();
    await page.locator("#spec").fill(JSON.stringify({...clean,title:"Current unrendered intent"}));
    assert.equal(await page.locator("#preview").isHidden(),true);
    old.release();
    await page.waitForFunction(() => document.querySelector('#status').textContent==='Ready to render');
    await Promise.all(observations);await delay(75);
    assert.equal(await page.locator("#preview").isHidden(),true);
    assert.equal(await page.locator("#bundle").isDisabled(),true);
    assert.equal(await page.locator("#files a").count(),0);
    workflows.push("authoring while unverified cancels image and rejects late final acceptance with live preview off");

    const unsafe=hold("Stage rejected progress certificate");
    let corrupted=false;
    await page.route("**/stage/*?*",async route=>{
      if(titleFor(route)!=="Stage rejected progress certificate" || new URL(route.request().url()).pathname.endsWith("/png"))
        return route.continue();
      const response=await route.fetch();const body=await response.json();
      if(body.phase!=="unverified")return route.fulfill({response});
      corrupted=true;await route.fulfill({response,json:{...body,verified:true}});
    });
    await render({...clean,title:"Stage rejected progress certificate"});await unsafe.entered();
    const deadline=Date.now()+10000;while(!corrupted){assert(Date.now()<deadline);await delay(10);}
    await delay(50);assert.equal(await page.locator("#preview").isHidden(),true);
    unsafe.release();await final();await page.unrouteAll({behavior:"wait"});
    workflows.push("malformed progress cannot certify an image or suppress original final verification");
    await Promise.all(observations);
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    const strictFailure=renders.find(r=>r.report?.spec.title==="Stage genuine strict failure");
    assert.equal(strictFailure?.exit_code,2);assert.equal(strictFailure?.report.policy.strict,true);
    assert(renders.filter(r=>r.report).every(r=>r.execution.provisional===true && r.execution.instrumented===true));
    return {passed:true,scope:"Controlled genuine original checker holds, not latency evidence",
      workflows,external_requests:external.length,javascript_errors:errors.length,
      executions:renders.filter(r=>r.report).map(r=>({title:r.report.spec.title,
        status:r.report.status,exit_code:r.exit_code,execution:r.execution,
        translation_execution:r.translation_execution}))};
  } catch(error) {
    await page.screenshot({path:join(evidence,"staged-failure.png"),fullPage:true}).catch(()=>{});
    writeFileSync(join(evidence,"staged-failure.json"),JSON.stringify({error:String(error),
      renders,errors,external,stderr},null,2));
    throw Error(String(error)+"\n"+stderr);
  } finally {
    releases.forEach(release=>release());
    for(const nonce of nonces)writeFileSync(join(control,nonce+".release"),"");
    await page.unrouteAll({behavior:"wait"}).catch(()=>{});
    await page.close();lines.close();
    if(server.exitCode===null) {
      const exited=new Promise<void>(resolve=>server.once("exit",()=>resolve()));
      server.kill("SIGINT");
      await Promise.race([exited,delay(15000, undefined, {ref:false}).then(()=>{server.kill();throw Error("Controlled editor did not close");})]);
    }
    const closed=JSON.parse(readFileSync(join(control,"closed.json"),"utf8"));
    assert(closed.native_closed && closed.compiler_closed && closed.temporary_root_removed);
  }
}
