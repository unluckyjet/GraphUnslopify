/** Actual saved-audit browser report, native controls and passive SVG isolation. */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const python = process.env.PYTHON || "python";
const evidence = mkdtempSync(join(tmpdir(), "gu-comparison-check-"));
const fixture = JSON.parse(execFileSync(python, ["scripts/check-visual-comparison.py", "--work-dir", join(evidence,"fixture")], {
  env: {...process.env, PYTHONPATH:resolve("python")}, encoding:"utf8", timeout:120_000,
}));
const macChrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executable=process.env.GRAPHUNSLOPIFY_BROWSER || (existsSync(macChrome) ? macChrome : undefined);
const browser=await chromium.launch({headless:true,...(executable ? {executablePath:executable}:{})});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors:string[]=[],external:string[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("request",r=>{if(!r.url().startsWith("file:")&&!r.url().startsWith("data:")) external.push(r.url());});
  page.on("dialog",async dialog=>{errors.push("Unexpected dialog: "+dialog.message());await dialog.dismiss();});
  await page.goto(pathToFileURL(fixture.html).href);
  await page.locator(".pair img").first().waitFor();
  assert.match(await page.locator(".verdicts").innerText(),/After validation: failed \(exit 2\)/);
  assert.match(await page.locator(".metrics").innerText(),/visible pixels changed/);
  assert.equal(await page.locator(".pair img").count(),2);
  await page.screenshot({path:join(evidence,"desktop.png"),fullPage:true});
  await page.locator("details").filter({hasText:"Blend before and after"}).locator("summary").click();
  const slider=page.locator("[data-blend]");
  await slider.focus(); await page.keyboard.press("Home");
  assert.match((await page.locator(".upper").getAttribute("style"))||"",/opacity: 0/);
  await page.keyboard.press("End");
  assert.match((await page.locator(".upper").getAttribute("style"))||"",/opacity: 1/);
  await page.setViewportSize({width:390,height:844});
  await page.goto(pathToFileURL(fixture.html).href);
  await page.waitForFunction("Array.from(document.querySelectorAll('.pair img')).every(image => image.complete && image.naturalWidth > 0)");
  assert.equal(await page.locator("h1").count(),1);
  const overflow=await page.evaluate("document.documentElement.scrollWidth > window.innerWidth");
  assert.equal(overflow,false);
  await page.screenshot({path:join(evidence,"mobile.png"),fullPage:true});
  await page.goto(pathToFileURL(fixture.svg_html).href);
  const loaded=await page.locator(".pair img").evaluateAll(images=>images.every((image:any)=>image.complete&&image.naturalWidth>0));
  if(!loaded) await page.waitForFunction("Array.from(document.querySelectorAll('.pair img')).every(image => image.complete && image.naturalWidth > 0)");
  assert.equal(await page.evaluate("window.__svg_ran === undefined"),true);
  assert.equal(await page.locator("img[onerror]").count(),0);
  assert.match(await page.locator("body").innerText(),/SVG.*no server-side pixel score/);
  assert.deepEqual(external,[]);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:join(evidence,"passive-svg.png"),fullPage:true});
  console.log(JSON.stringify({status:"passed",evidence,fixture,external_requests:external.length,browser_errors:errors.length}));
} finally { await browser.close(); }
