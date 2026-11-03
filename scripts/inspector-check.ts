/** Actual native geometry, scoped controls, undo and current-evidence fences. */
import assert from "node:assert/strict";
import {spawn,type ChildProcess} from "node:child_process";
import {existsSync,mkdirSync,mkdtempSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {createInterface} from "node:readline";
import {chromium,type Page} from "playwright";
declare const document:any;
const root=resolve("."),evidence=process.env.GRAPHUNSLOPIFY_INSPECTOR_EVIDENCE||mkdtempSync(join(tmpdir(),"gu-inspector-check-"));
if(process.env.GRAPHUNSLOPIFY_INSPECTOR_EVIDENCE)mkdirSync(evidence);
const env={...process.env};if(process.env.GRAPHUNSLOPIFY_INSPECTOR_INSTALLED)delete env.PYTHONPATH;else env.PYTHONPATH=join(root,"python");
let server:ChildProcess|undefined,browser,page:Page|undefined;
const errors:string[]=[],external:string[]=[],receipts:unknown[]=[];
async function serve(){server=spawn(process.env.PYTHON||"python",["-m","graphunslopify.cli","preview","--port","0"],{cwd:evidence,env,stdio:["ignore","pipe","pipe"]});
 let stderr="";server.stderr!.on("data",c=>{stderr+=c;});const lines=createInterface({input:server.stdout!});
 return new Promise<string>((ok,bad)=>{lines.once("line",line=>{try{ok(JSON.parse(line).url);}catch(e){bad(e);}});server!.once("error",bad);server!.once("exit",code=>bad(Error(`Server exited ${code}: ${stderr}`)));});}
async function render(){const pending=page!.waitForResponse(r=>r.url().endsWith("/api/render"));await page!.locator("#render").click();const response=await pending;assert.equal(response.status(),200);const result=await response.json();await page!.locator('#preview[data-phase="final"]').waitFor();await page!.locator("#preview").evaluate((image:any)=>image.decode());return result;}
async function choose(text:string){const options=await page!.locator("#inspector-element option").all();for(const option of options)if((await option.textContent())?.startsWith(text)){await page!.locator("#inspector-element").selectOption((await option.getAttribute("value"))!);return;}throw Error("Missing element "+text);}
try{
 const executable=process.env.GRAPHUNSLOPIFY_BROWSER||(existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")?"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":undefined);
 browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});page=await browser.newPage({viewport:{width:1500,height:1100}});page.setDefaultTimeout(60_000);
 page.on("pageerror",e=>errors.push(e.message));page.on("request",r=>{if(/^https?:/.test(r.url())&&!/^http:\/\/127\.0\.0\.1:/.test(r.url()))external.push(r.url());});
 await page.goto(await serve());await page.locator("#demo").click();await page.locator('#preview[data-phase="final"]').waitFor();await page.locator("#live").uncheck();
 await page.locator("#advanced>summary").click();const original=JSON.parse(await page.locator("#spec").inputValue());const before=await render();assert.equal(before.report.status,"passed");
 const raw=await page.locator("#spec").inputValue(),status=await page.locator("#status").textContent();
 await page.locator("#inspect-element").click();assert(await page.locator("#control-output-dpi").isVisible());assert(!await page.locator("#control-x-label").isVisible());await page.getByRole("button",{name:/^Inspect Horizontal axis/}).first().click();
 assert(await page.locator("#control-x-label").isVisible());assert(!await page.locator("#control-y-label").isVisible());assert(!await page.locator("#control-output-dpi").isVisible());
 assert.equal(await page.locator("#spec").inputValue(),raw);assert.equal(await page.locator("#status").textContent(),status);
 await page.locator("#control-x-label").fill("Observed epoch");assert(await page.locator("#inspector-targets").isHidden());const changed=await render();assert.equal(changed.report.status,"passed");assert.equal(changed.report.spec.x.label,"Observed epoch");
 const expected=structuredClone(before.report.spec);expected.x.label="Observed epoch";assert.deepEqual(changed.report.spec,expected);
 await page.locator("#undo-controls").click();const undone=await render();assert.equal(undone.report.status,"passed");assert.deepEqual(undone.report.spec,before.report.spec);
 if(await page.locator("#element-inspector").isHidden())await page.locator("#inspect-element").click();
 const interval=page.getByRole("button",{name:/^Inspect Uncertainty/}).first();await interval.focus();await interval.press("Enter");
 assert(await page.locator("#control-uncertainty-kind").isVisible());assert(!await page.locator("#control-x-label").isVisible());
 await page.screenshot({path:join(evidence,"interval-desktop.png"),fullPage:true});
 await page.setViewportSize({width:430,height:900});await choose("Horizontal axis");assert(await page.locator("#control-x-scale").isVisible());
 await page.screenshot({path:join(evidence,"axis-mobile.png"),fullPage:true});
 await page.locator("#inspector-all").click();assert(await page.locator("#control-x-label").isVisible());assert(await page.locator("#control-y-label").isVisible());
 // Existing text editing and the new inspector use separate interaction modes.
 await page.locator("#inspect-element").click();await page.locator("#edit-figure-text").click();assert(await page.locator("#element-inspector").isHidden());assert.equal(await page.locator("#inspect-element").getAttribute("aria-pressed"),"false");
 await page.locator("#edit-figure-text").click();
 const horizontal=structuredClone(original);horizontal.kind="bar";horizontal.orientation="horizontal";horizontal.uncertainty.display="bar";horizontal.output.formats=["png"];
 await page.locator("#spec").fill(JSON.stringify(horizontal));const bar=await render();assert.equal(bar.report.status,"passed");await page.locator("#inspect-element").click();await choose("Horizontal axis");
 assert(await page.locator("#control-y-label").isVisible());assert(!await page.locator("#control-x-label").isVisible());
 await choose("Whole figure");await page.locator("#preview").scrollIntoViewIfNeeded();
 const region=bar.edit_map.elements.targets.find((t:any)=>t.role==="uncertainty");assert(region);const segment=region.shapes[0].points;const point:[number,number]=[(segment[0][0]+segment[1][0])/2,(segment[0][1]+segment[1][1])/2];const box=(await page.locator("#preview").boundingBox())!;
 const click={x:box.x+point[0]*box.width/bar.edit_map.image.width,y:box.y+point[1]*box.height/bar.edit_map.image.height};
 await page.evaluate(()=>{(globalThis as any).pointerTrace=[];for(const kind of ["mousedown","mouseup","click","input","change"])document.addEventListener(kind,(event:any)=>(globalThis as any).pointerTrace.push({kind,target:event.target?.tagName,selected:document.getElementById("inspector-element").value,x:event.clientX,y:event.clientY}),true);});
 const hit=await page.evaluate(({x,y})=>({tag:document.elementFromPoint(x,y)?.outerHTML.slice(0,800),x,y}),click);writeFileSync(join(evidence,"pointer.json"),JSON.stringify({hit,box,point,region},null,2));
 await page.mouse.click(click.x,click.y);
 try {await page.locator("#control-uncertainty-kind").waitFor({state:"visible",timeout:10_000});}
 catch(error){const trace=await page.evaluate(()=>({events:(globalThis as any).pointerTrace,selected:document.getElementById("inspector-element").value,context:document.getElementById("inspector-context").textContent,status:document.getElementById("status").textContent,error:document.getElementById("control-error").textContent}));writeFileSync(join(evidence,"pointer-failure.json"),JSON.stringify(trace,null,2));throw error;}
 await page.screenshot({path:join(evidence,"horizontal-bar-interval.png"),fullPage:true});
 await page.locator("#inspector-all").click();
 // A forged map cannot borrow acceptance from the real PNG/report.
 await page.route("**/api/render",async route=>{const response=await route.fetch();const packet=await response.json();packet.edit_map.image.sha256="0".repeat(64);await route.fulfill({response,json:packet});});
 await render();assert(await page.locator("#inspect-element").isDisabled());await page.unroute("**/api/render");await render();assert(!await page.locator("#inspect-element").isDisabled());
 await page.route("**/api/render",async route=>{const response=await route.fetch();const packet=await response.json();packet.edit_map.image.width=1;await route.fulfill({response,json:packet});});
 await render();assert(await page.locator("#inspect-element").isDisabled());await page.unroute("**/api/render");await render();
 // Renderer-owned paths still need canonical source agreement.
 await page.route("**/api/render",async route=>{const response=await route.fetch();const packet=await response.json();packet.edit_map.elements.targets=packet.edit_map.elements.targets.filter((t:any)=>t.role!=="uncertainty");for(const target of packet.edit_map.elements.targets)if(target.role==="axis")target.source="unrelated source";await route.fulfill({response,json:packet});});
 await render();await page.locator("#inspect-element").click();assert.equal(await page.locator("#inspector-element option").count(),1);await page.unroute("**/api/render");
 receipts.push({actual_axis_pointer:true,interval_keyboard:true,horizontal_bar_binding:true,errorbar_pointer:true,whole_figure_controls:true,text_mode_separation:true,mobile_scope:true,selection_preserves_spec_and_status:true,real_native_edit_and_undo:true,stale_image_hash_refused:true,wrong_image_dimensions_refused:true,unmapped_source_refused:true,science_preserved:true,original_kind:original.kind});
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);writeFileSync(join(evidence,"verification.json"),JSON.stringify({receipts,page_errors:errors,external_requests:external},null,2));console.log(JSON.stringify({receipts,page_errors:errors,external_requests:external,evidence}));
}catch(error){if(page){await page.screenshot({path:join(evidence,"failure.png"),fullPage:true}).catch(()=>{});writeFileSync(join(evidence,"failure.json"),JSON.stringify({error:String(error),page_errors:errors},null,2));}throw error;}
finally{await browser?.close();server?.kill();}
