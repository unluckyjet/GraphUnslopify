/** Actual wrapped legend edits keep canonical source identity and local statistics. */
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync, writeFileSync} from "node:fs";
import {join} from "node:path";
import type {Page} from "playwright";

declare const document: {querySelector(selector:string):{textContent:string}|null};

export async function checkOutsideLegends(page:Page,evidence:string){
  const fixture=JSON.parse(readFileSync("docs/workspace/outside-legend-layout/inputs.json","utf8"));
  const workflows:string[]=[];
  const current=async()=>JSON.parse(await page.locator("#spec").inputValue());
  const response=()=>page.waitForResponse(r=>r.url().endsWith("/api/render"));
  const verified=async()=>page.locator('#status[data-state="passed"]').waitFor();
  const select=async()=>{
    if(await page.locator("#edit-figure-text").getAttribute("aria-pressed")!=="true")await page.locator("#edit-figure-text").click();
    await page.getByRole("button",{name:/^Edit Series name: Reference treatment/}).first().click();
  };
  const edit=async(wording:string)=>{
    await page.locator("#text-wording").fill(wording);await page.locator("#review-text").click();await page.locator("#text-meaning").check();
    const done=response();await page.locator("#apply-text").click();return(await done).json();
  };
  for(const kind of ["line","calibration"]){
    const source=fixture.grouped.find((item:any)=>item.kind===kind);
    const spec=structuredClone(source.spec);spec.legend.position="outside_bottom";
    const csv=kind==="calibration"?fixture.calibration_statistics_csv:source.csv;
    const name=`${kind}-complete-legend.csv`;
    await page.setViewportSize({width:kind==="calibration"?390:1500,height:1000});
    await page.locator("#live").uncheck();
    await page.locator("#data-file").setInputFiles({name,mimeType:"text/csv",buffer:Buffer.from(csv)});
    await page.waitForFunction(filename=>document.querySelector("#data-summary")?.textContent.includes(filename)&&!document.querySelector("#data-summary")?.textContent.startsWith("Reading "),name);
    await page.locator("#advanced").evaluate(node=>node.setAttribute("open",""));
    await page.locator("#spec").fill(JSON.stringify(spec,null,2));
    await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="Ready to render");
    const rendered=response();await page.locator("#render").click();const initial=await(await rendered).json();await verified();
    assert.equal(initial.report.status,"passed",JSON.stringify(initial.report.findings));
    const before=await current();const original=spec.series_order[1];
    await select();assert.equal(await page.locator("#text-wording").inputValue(),original);
    const wording=original+" with original identity retained";const changed=await edit(wording);await verified();
    assert.equal(changed.report.status,"passed",JSON.stringify(changed.report.findings));
    assert.equal(changed.report.data.sha256_prefix,createHash("sha256").update(csv).digest("hex").slice(0,16));
    assert.equal(changed.report.data.counts.read,6);assert.deepEqual(changed.report.spec.series_order,spec.series_order);
    assert.equal(await page.locator("#live").isChecked(),false);
    const intent=await current();assert.deepEqual(intent.legend.labels,[{series:original,text:wording}]);
    const entries=changed.edit_map.targets.filter((item:any)=>item.role==="legend_entry"&&item.source===original);
    assert.equal(entries.length,kind==="calibration"?2:1);
    assert.ok(entries.every((item:any)=>item.text.split(/\s+/).join(" ").startsWith(wording)));
    assert.ok(entries.every((item:any)=>JSON.stringify(item.path)===JSON.stringify(["legend","labels",0,"text"])));
    if(kind==="calibration"){
      const displayed=entries.map((item:any)=>item.text.split(/\s+/).join(" "));
      assert.ok(displayed.some((text:string)=>text.endsWith("(ECE 0.1)")));
      assert.ok(displayed.some((text:string)=>text.endsWith("(ECE 0.25)")));
    }
    await page.locator(".preview").screenshot({path:join(evidence,`${kind}-complete-legend.png`)});
    if(kind==="line"){
      await select();const failed=await edit("OriginalIdentifier".repeat(20));
      await page.locator('#status[data-state="failed"]').waitFor();
      assert.equal(failed.report.status,"failed");assert.ok(failed.report.findings.some((item:any)=>item.code==="text_too_small"));
      assert.equal(await page.locator("#bundle").isDisabled(),false);
      await page.locator("#undo-controls").click();assert.deepEqual(await current(),intent);
      const recovered=response();await page.locator("#render").click();assert.equal((await(await recovered).json()).report.status,"passed");await verified();
      workflows.push("unbreakable legend alias remains failed with review downloads; native undo and strict rerender recover original verified data");
    }
    await page.locator("#undo-controls").click();assert.deepEqual(await current(),before);assert.equal(await page.locator("#bundle").isDisabled(),true);
    workflows.push(`${kind} wrapped legend click, reviewed manual alias edit and undo retain complete source IDs, data hashes and panel statistics`);
  }
  await page.setViewportSize({width:1500,height:1000});
  const proof={passed:true,workflows};writeFileSync(join(evidence,"outside-legend-checks.json"),JSON.stringify(proof,null,2)+"\n");return proof;
}
