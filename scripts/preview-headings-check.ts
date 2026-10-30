/** Actual wrapped text targets edit canonical wording and preserve source identity. */
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync, writeFileSync} from "node:fs";
import {join} from "node:path";
import type {Page} from "playwright";

declare const document: {querySelector(selector:string):{textContent:string}|null};

export async function checkHeadings(page: Page, evidence: string) {
  const fixture=JSON.parse(readFileSync("docs/workspace/heading-layout/inputs.json","utf8"));
  const original={...fixture.spec,x:{...fixture.spec.x,unit:"ms"},y:{...fixture.spec.y,unit:"points"}};
  const workflows:string[]=[];
  const current=async()=>JSON.parse(await page.locator("#spec").inputValue());
  const verified=async()=>page.locator('#status[data-state="passed"]').waitFor();
  const response=()=>page.waitForResponse(r=>r.url().endsWith("/api/render"));
  const integrity=(result:any)=>{
    assert.equal(result.report.status,"passed",JSON.stringify(result.report.findings));
    assert.equal(result.report.data.sha256_prefix,createHash("sha256").update(fixture.csv).digest("hex").slice(0,16));
    assert.equal(result.report.data.counts.read,8);
    assert.equal(result.report.panels.length,4);
    assert.equal(result.report.spec.x.unit,"ms");assert.equal(result.report.spec.y.unit,"points");
  };
  const select=async(name:RegExp)=>{
    if(await page.locator("#edit-figure-text").getAttribute("aria-pressed")!=="true")await page.locator("#edit-figure-text").click();
    await page.getByRole("button",{name}).first().click();
  };
  const apply=async(wording:string)=>{
    await page.locator("#text-wording").fill(wording);
    await page.locator("#review-text").click();await page.locator("#text-meaning").check();
    const completed=response();await page.locator("#apply-text").click();const result=await(await completed).json();
    await verified();integrity(result);assert.equal(await page.locator("#live").isChecked(),false);return result;
  };
  await page.setViewportSize({width:1500,height:1000});
  await page.locator("#live").uncheck();
  await page.locator("#data-file").setInputFiles({name:"owned-headings.csv",mimeType:"text/csv",buffer:Buffer.from(fixture.csv)});
  await page.waitForFunction(()=>document.querySelector("#data-summary")?.textContent.includes("owned-headings.csv")&&!document.querySelector("#data-summary")?.textContent.startsWith("Reading "));
  await page.locator("#advanced").evaluate(node=>node.setAttribute("open",""));
  await page.locator("#spec").fill(JSON.stringify(original,null,2));
  await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="Ready to render");
  const first=response();await page.locator("#render").click();const initial=await(await first).json();await verified();integrity(initial);
  assert.ok(initial.edit_map.targets.some((t:any)=>t.role==="panel_title"&&t.text.includes("\n")));
  workflows.push("long nested headings and declared units render strictly with all eight original observations");
  await select(/^Edit Panel title: \(a\)/);
  assert.equal(await page.locator("#text-wording").inputValue(),original.facet.labels[0].text);
  assert.deepEqual(await current(),original);
  workflows.push("actual wrapped heading click loads complete canonical wording without panel letters or inserted line breaks");
  const changed=await apply(original.facet.labels[0].text+" with complete sample retention");
  const intent=await current();assert.deepEqual(intent.facet.labels.slice(1),original.facet.labels.slice(1));
  assert.equal(intent.facet.labels[0].value,"A");assert.equal(intent.facet.labels[0].row,"early");
  const heading=changed.edit_map.targets.find((t:any)=>t.role==="panel_title"&&t.source.value==="A"&&t.source.row==="early");
  assert.ok(heading.text.startsWith("(a) "));assert.ok(heading.text.includes("\n"));
  assert.equal(heading.value,intent.facet.labels[0].text);
  workflows.push("reviewed wrapped panel edit forces strict manual rendering and preserves nested keys and automatic letters");
  await page.locator("#undo-controls").click();assert.deepEqual(await current(),original);assert.equal(await page.locator("#bundle").isDisabled(),true);
  workflows.push("native undo restores original long panel wording and invalidates newer outputs");
  const again=response();await page.locator("#render").click();integrity(await(await again).json());await verified();
  await page.setViewportSize({width:390,height:844});
  await select(/^Edit Axis label: Observed response/);
  assert.equal(await page.locator("#text-wording").inputValue(),original.y.label);
  const measured=await apply("Measured response recorded across the original experimental observation period");
  const axis=measured.edit_map.targets.find((t:any)=>t.role==="axis_label"&&t.source==="score");
  assert.deepEqual(axis.path,["y","label"]);assert.ok(axis.text.includes("(points)"));
  assert.equal((await current()).y.unit,"points");
  workflows.push("narrow-screen wrapped axis edit changes canonical wording while preserving units fields and original data");
  await page.locator(".preview").screenshot({path:join(evidence,"headings-narrow.png")});
  await page.locator("#undo-controls").click();assert.deepEqual(await current(),original);
  workflows.push("axis edit native undo restores full original intent including declared units");
  await page.setViewportSize({width:1500,height:1000});
  const proof={passed:true,workflows};writeFileSync(join(evidence,"heading-checks.json"),JSON.stringify(proof,null,2)+"\n");return proof;
}
