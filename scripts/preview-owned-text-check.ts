/** Real wrapped child targets and table form edits preserve canonical intent. */
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {Page} from "playwright";

declare const document:{querySelector(selector:string):{textContent:string}|null};

export async function checkOwnedText(page:Page,evidence:string){
  const fixture=JSON.parse(readFileSync("docs/workspace/owned-text-layout/inputs.json","utf8"));
  const workflows:string[]=[];
  const current=async()=>JSON.parse(await page.locator("#spec").inputValue());
  const response=()=>page.waitForResponse(r=>r.url().endsWith("/api/render"));
  const verified=async()=>page.locator('#status[data-state="passed"]').waitFor();
  const run=async()=>{const done=response();await page.locator("#render").click();return(await done).json();};
  const load=async(name:string,source:any)=>{
    await page.locator("#live").uncheck();
    await page.locator("#data-file").setInputFiles({name,mimeType:"text/csv",buffer:Buffer.from(source.csv)});
    await page.waitForFunction(filename=>document.querySelector("#data-summary")?.textContent.includes(filename)&&!document.querySelector("#data-summary")?.textContent.startsWith("Reading "),name);
    await page.locator("#advanced").evaluate(node=>node.setAttribute("open",""));
    await page.locator("#spec").fill(JSON.stringify(source.spec,null,2));
    await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="Ready to render");
    const result=await run();assert.equal(result.report.status,"passed",JSON.stringify(result.report.findings));await verified();return result;
  };
  const select=async()=>{
    if(await page.locator("#edit-figure-text").getAttribute("aria-pressed")!=="true")await page.locator("#edit-figure-text").click();
    await page.getByRole("button",{name:/^Edit Series name: Reference treatment/}).first().click();
  };
  const edit=async(text:string)=>{
    await page.locator("#text-wording").fill(text);await page.locator("#review-text").click();await page.locator("#text-meaning").check();
    const done=response();await page.locator("#apply-text").click();return(await done).json();
  };
  await page.setViewportSize({width:1500,height:1000});
  const source=fixture.sparkline;
  const initial=await load("original-child-headings.csv",source);
  assert.equal(initial.edit_map.targets.filter((t:any)=>t.role==="legend_entry").length,3);
  const before=await current();const original=source.spec.series_order[1];
  await select();assert.equal(await page.locator("#text-wording").inputValue(),original);
  const wording=original+" with original source identity retained";const changed=await edit(wording);await verified();
  assert.equal(changed.report.status,"passed",JSON.stringify(changed.report.findings));
  assert.equal(changed.report.data.sha256_prefix,createHash("sha256").update(source.csv).digest("hex").slice(0,16));
  assert.equal(changed.report.data.counts.read,6);assert.deepEqual(changed.report.spec.series_order,source.spec.series_order);
  const intent=await current();assert.deepEqual(intent.legend.labels,[{series:original,text:wording}]);
  assert.ok(changed.edit_map.targets.filter((t:any)=>t.role==="legend_entry"&&t.source===original).every((t:any)=>t.text.split(/\s+/).join(" ")===wording));
  workflows.push("actual wrapped child title click, reviewed manual edit and strict render retain complete original names, source IDs and all six observations");
  await page.locator(".preview").screenshot({path:join(evidence,"wrapped-child-headings.png")});
  await page.locator("#undo-controls").click();assert.deepEqual(await current(),before);assert.equal(await page.locator("#bundle").isDisabled(),true);
  assert.equal((await run()).report.status,"passed");await verified();
  workflows.push("native child-name undo restores original canonical words and invalidates newer outputs before strict recovery");
  await select();const failed=await edit("OriginalSourceIdentifier".repeat(25));
  await page.locator('#status[data-state="failed"]').waitFor();assert.equal(failed.report.status,"failed");
  assert.ok(failed.report.findings.some((f:any)=>f.code==="text_too_small"));assert.equal(await page.locator("#bundle").isDisabled(),false);
  await page.locator("#undo-controls").click();assert.deepEqual(await current(),before);assert.equal((await run()).report.status,"passed");await verified();
  workflows.push("unbreakable child name remains a strict failure with review downloads and native undo/manual recovery");
  for(const table of fixture.tables){
    await page.setViewportSize({width:390,height:900});
    const rendered=await load(`${table.name}-complete-context.csv`,table);
    assert.equal(rendered.report.data.sha256_prefix,createHash("sha256").update(table.csv).digest("hex").slice(0,16));
    const baseline=await current();const title=baseline.title+" with all original observations retained";
    await page.getByLabel(/^Figure title/).fill(title);await page.getByLabel(/^Figure title/).press("Tab");
    await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="Ready to render");
    const updated=await run();await verified();assert.equal(updated.report.status,"passed",JSON.stringify(updated.report.findings));
    assert.equal(updated.report.spec.title,title);assert.equal(updated.report.spec.y.label,baseline.y.label);assert.equal(updated.report.spec.y.unit,"fraction");
    assert.equal(updated.report.data.sha256_prefix,rendered.report.data.sha256_prefix);assert.equal(await page.locator("#live").isChecked(),false);
    await page.locator(".preview").screenshot({path:join(evidence,`${table.name}-complete-context.png`)});
    workflows.push(`${table.name} full context native rendering and narrow-screen title form edit retain original data, units and current strict verification`);
  }
  await page.setViewportSize({width:1500,height:1000});
  const proof={passed:true,workflows};writeFileSync(join(evidence,"owned-text-checks.json"),JSON.stringify(proof,null,2)+"\n");return proof;
}
