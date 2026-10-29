/** Real browser/editor contract, including stale responses and exported reproduction. */
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { setTimeout as delay } from "node:timers/promises";
import { chromium } from "playwright";

// Module-local browser globals; importing lib.dom changes unrelated Node stream types.
declare const document: {
  querySelectorAll(selector: string): { length: number };
  querySelector(selector: string): {
    textContent: string;
    hidden: boolean;
    complete: boolean;
    naturalWidth: number;
  } | null;
  documentElement: { scrollWidth: number };
};
declare const window: { innerWidth: number };

const python = process.env.PYTHON || "python";
const evidence = mkdtempSync(join(tmpdir(), "gu-preview-check-"));
const env: NodeJS.ProcessEnv = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED
  ? { ...process.env }
  : { ...process.env, PYTHONPATH: resolve("python") };
// The driver must fetch a loopback response to hold it. Product processes keep
// their independent translator-network hook in installed offline verification.
if (process.env.GRAPHUNSLOPIFY_PREVIEW_NODE_OPTIONS)
  env.NODE_OPTIONS = process.env.GRAPHUNSLOPIFY_PREVIEW_NODE_OPTIONS;
const server = spawn(
  python,
  ["-m", "graphunslopify.cli", "preview", "--port", "0"],
  { env, stdio: ["ignore", "pipe", "pipe"] },
);
let stderr = "";
server.stderr.on("data", (chunk) => {
  stderr += chunk;
});
const lines = createInterface({ input: server.stdout });
const startTimeout = setTimeout(() => server.kill(), 30_000);
const url = await new Promise<string>((accept, reject) => {
  lines.once("line", (line) => {
    try {
      accept(JSON.parse(line).url);
    } catch (error) {
      reject(error);
    }
  });
  server.once("exit", (code) =>
    reject(Error(`Editor exited ${code}: ${stderr}`)),
  );
});
clearTimeout(startTimeout);
let browser;
try {
  const macChrome =
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  const executable =
    process.env.GRAPHUNSLOPIFY_BROWSER ||
    (existsSync(macChrome) ? macChrome : undefined);
  browser = await chromium.launch({
    headless: true,
    ...(executable ? { executablePath: executable } : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1500, height: 1000 },
    acceptDownloads: true,
  });
  page.setDefaultTimeout(120_000);
  const errors: string[] = [],
    external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith(url) && !request.url().startsWith("data:"))
      external.push(request.url());
  });
  const infoResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/info"),
  );
  await page.goto(url);
  const info = await (await infoResponse).json();
  await page.waitForFunction(
    () => document.querySelectorAll("#kind option").length === 21,
  );
  assert.equal(await page.locator("#recipe option").count(), 26);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  // Legacy display is derived guidance; literal messages never become markup.
  const legacy = await page.evaluate<{text: string; scripts: number; unknown: string}>(`(async () => {
    const {describeFinding} = await import('/diagnostics.js');
    const token = document.querySelector('meta[name="preview-token"]').content;
    const info = await (await fetch('/api/info', {headers: {'X-Preview-Token':token}})).json();
    const node = document.createElement('div');
    describeFinding(node, {code:'truncated_bar_axis', message:'<script>bad()</script>'}, info.diagnostics);
    const unknown = document.createElement('div');
    describeFinding(unknown, {code:'__proto__', message:'External finding'}, info.diagnostics);
    return {text:node.textContent, scripts:node.querySelectorAll('script').length, unknown:unknown.textContent};
  })()`);
  assert.match(legacy.text, /<script>bad\(\)<\/script>[\s\S]*Why it matters:[\s\S]*Recommended correction:/);
  assert.equal(legacy.scripts, 0);
  assert.match(legacy.unknown, /not been classified/);
  const edit = async (spec: object | string) => {
    await page
      .locator("#advanced")
      .evaluate((node) => node.setAttribute("open", ""));
    return page
      .locator("#spec")
      .fill(typeof spec === "string" ? spec : JSON.stringify(spec, null, 2));
  };
  const spec = async () => JSON.parse(await page.locator("#spec").inputValue());
  const verified = async () => {
    await page.locator('#status[data-state="passed"]').waitFor();
    await page.waitForFunction(() => {
      const image = document.querySelector("#preview");
      return (
        image && !image.hidden && image.complete && image.naturalWidth > 10
      );
    });
    assert.equal(await page.locator("#bundle").isDisabled(), false);
  };
  await page.getByRole("button", { name: "Try sample data" }).click();
  await verified();
  assert.match(await page.locator("#counts").innerText(), /24 rows read/);
  const demo = await spec();
  assert.equal(
    await page.getByRole("textbox", { name: "X unit", exact: true }).count(),
    1,
  );
  await page.screenshot({
    path: join(evidence, "controls-default-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .locator(".editor")
    .screenshot({ path: join(evidence, "controls-default-mobile.png") });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  await page.setViewportSize({ width: 1500, height: 1000 });
  // Common research settings and a complete claim edit need no raw JSON.
  assert.equal(await page.locator("#advanced").getAttribute("open"), null);
  await page.locator("#live").uncheck();
  const control = async (id: string, value: string) => {
    const input = page.locator("#control-" + id);
    await input.evaluate((node) => {
      let parent = node.parentElement;
      while (parent) {
        if (parent.tagName === "DETAILS") parent.setAttribute("open", "");
        parent = parent.parentElement;
      }
    });
    if ((await input.evaluate((node) => node.tagName)) === "SELECT")
      await input.selectOption(value);
    else {
      await input.fill(value);
      await input.press("Tab");
    }
  };
  const caption =
    "Literal <script> _&% control caption\nSecond line stays literal.";
  await control("title", "Controls-only figure");
  await control("y-label", "Validation score");
  await control("y-unit", "points");
  await control("caption", caption);
  await control("output-size", "double_column");
  await control("output-dpi", "300");
  await control("uncertainty-kind", "ci");
  await control("uncertainty-over", "seed");
  await control("uncertainty-level", "0.95");
  await page.locator("#control-format-svg").uncheck();
  assert.equal(await page.locator("#advanced").getAttribute("open"), null);
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.locator("#render").click();
  await verified();
  assert.equal((await spec()).caption, caption);
  assert.deepEqual((await spec()).output.formats, ["png", "pdf"]);
  const controlsDownload = page.waitForEvent("download");
  await page.locator("#include-data").check();
  await page.locator("#bundle").click();
  await (
    await controlsDownload
  ).saveAs(join(evidence, "controls-with-data.zip"));
  await page.locator("#include-data").uncheck();
  // Invalid/unfinished numeric drafts never become valid defaults or resurrect exports.
  let renderRequests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/render")) renderRequests++;
  });
  await control("output-dpi", "71");
  assert.equal((await spec()).output.dpi, 300);
  assert.match(await page.locator("#control-error").innerText(), /Raster DPI/);
  await control("title", "Draft is preserved");
  assert.equal((await spec()).title, "Controls-only figure");
  const beforeInvalid = renderRequests;
  await page.locator("#render").click();
  assert.equal(renderRequests, beforeInvalid);
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await control("output-dpi", "300");
  assert.equal((await spec()).title, "Draft is preserved");
  const dpi = page.locator("#control-output-dpi");
  await dpi.fill("");
  await dpi.pressSequentially("1e");
  await dpi.press("Tab");
  assert.equal(await dpi.inputValue(), "");
  assert.match(
    await page.locator("#control-error").innerText(),
    /valid number/,
  );
  assert.equal((await spec()).output.dpi, 300);
  await control("output-dpi", "300");
  await page.locator("#undo-controls").click();
  assert.equal((await spec()).title, "Controls-only figure");
  await control("aggregation", "median");
  await control("uncertainty-kind", "sem");
  await page.locator("#render").click();
  await page.locator('[data-code="median_sem_unsupported"]').waitFor();
  assert.match(await page.locator('[data-code="median_sem_unsupported"]').innerText(), /Why it matters:[\s\S]*Recommended correction:/);
  assert.equal(await page.locator("#preview").isHidden(), true);
  await control("aggregation", "mean");
  await control("uncertainty-kind", "ci");
  await control("claims-0-subject", "base");
  await control("claims-0-reference", "ours");
  await page.locator("#render").click();
  await page.locator('#status[data-state="failed"]').waitFor();
  assert.match(await page.locator("#claims").innerText(), /FAILS/);
  assert.match(await page.locator("#claims").innerText(), /Why it matters:[\s\S]*Recommended correction:/);
  await control("claims-0-subject", "ours");
  await control("claims-0-reference", "base");
  await page.locator("#add-claim").click();
  assert.deepEqual((await spec()).claims[1], {});
  await control("claims-1-kind", "monotone_increasing");
  await control("claims-1-subject", "ours");
  await page.locator("#render").click();
  await verified();
  assert.equal(await page.locator("#claims .claim").count(), 2);
  await page
    .getByRole("button", { name: "Remove claim 2", exact: true })
    .click();
  assert.equal((await spec()).claims.length, 1);
  // Advanced authored fields survive unrelated native controls and undo.
  const advanced = {
    ...demo,
    y: { ...demo.y, label: "Authored score label", unit: "points" },
    filter: [{ field: "model", op: "in", value: ["base", "ours"] }],
    legend: { ...demo.legend, title: "Authored legend", style: "box" },
    smooth: { kind: "rolling", window: 2, show_raw: true },
  };
  await edit(advanced);
  await control("title", "Preserve advanced settings");
  await page.locator("#y-field").selectOption("score");
  for (const key of ["filter", "smooth", "legend", "y"])
    assert.deepEqual(
      (await spec())[key],
      advanced[key as keyof typeof advanced],
    );
  await control("caption", "Another authored caption from controls");
  await page.locator("#undo-controls").click();
  assert.equal((await spec()).caption, undefined);
  assert.deepEqual((await spec()).filter, advanced.filter);
  // Every kind's required primitive/category settings come from the actual schema.
  const controlledKinds = [];
  for (const branch of info.schema.oneOf) {
    const kind = branch.properties.kind.const;
    await page.locator("#kind").selectOption(kind);
    for (const key of branch.required) {
      const node = branch.properties[key];
      if (key === "kind" || (node.type === "object" && key !== "uncertainty"))
        continue;
      if (node.type === "array" && node.items?.type !== "string") continue;
      assert.equal(
        await page
          .locator(
            "#control-" + (key === "uncertainty" ? "uncertainty-kind" : key),
          )
          .count(),
        1,
        `${kind}.${key}`,
      );
    }
    if (kind === "waterfall") {
      await control("start", "0");
      assert.equal((await spec()).start, 0);
      await control("start", "");
      assert.equal((await spec()).start, 0);
      assert.match(
        await page.locator("#control-error").innerText(),
        /Starting total/,
      );
      await control("start", "2");
      await control("category_order", " stage, one\ntwo ");
      assert.deepEqual((await spec()).category_order, [" stage, one", "two "]);
    }
    controlledKinds.push(kind);
  }
  assert.equal(controlledKinds.length, 21);
  await page.screenshot({
    path: join(evidence, "kind-controls.png"),
    fullPage: true,
  });
  await edit(demo);
  await page.locator("#live").check();
  await verified();
  await page.locator("#control-title").fill("Live control title");
  await page.waitForFunction(
    () => document.querySelector("#status")?.textContent === "Verified",
  );
  await verified();
  assert.equal((await spec()).title, "Live control title");
  assert.equal(await page.locator("#control-title:focus").count(), 1);
  await edit(demo);
  await verified();
  // Existing successful output disappears immediately when input is invalidated.
  await edit({ ...demo, y: { ...demo.y, temporal: true } });
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.locator('[data-code="temporal_y_axis"] button').waitFor();
  await page.screenshot({
    path: join(evidence, "selected-fix.png"),
    fullPage: true,
  });
  await page.locator('[data-code="temporal_y_axis"] button').click();
  await verified();
  assert.equal((await spec()).y.temporal, false);
  // Runtime false claims remain visible, including their panel/metric scope.
  await edit({
    ...demo,
    claims: [{ kind: "beats_everywhere", subject: "base", reference: "ours" }],
  });
  await page.locator('#status[data-state="failed"]').waitFor();
  assert.match(await page.locator("#claims").innerText(), /FAILS.*panel 1/);
  assert.equal(await page.locator("#preview").isVisible(), true);
  await page.screenshot({
    path: join(evidence, "failed-claim.png"),
    fullPage: true,
  });
  await edit("{");
  await page.waitForFunction(
    () => document.querySelector("#status")?.textContent === "Fix JSON",
  );
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#files a").count(), 0);
  assert.notEqual(
    await page.locator("#settings").getAttribute("disabled"),
    null,
  );
  assert.equal(await page.locator("#control-title").isDisabled(), true);
  assert.equal(await page.locator("#spec").inputValue(), "{");
  await edit({ ...demo, x: { field: "missing_column", label: "Missing" } });
  await page.locator('[data-code="unknown_field"]').waitFor();
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  // A slow older render must never replace a newer successful result.
  let held = false;
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let announce: () => void = () => {};
  const intercepted = new Promise<void>((resolve) => {
    announce = resolve;
  });
  await page.route("**/api/render", async (route) => {
    if (!held && route.request().postDataJSON().spec.title === "Old revision") {
      held = true;
      const response = await route.fetch();
      announce();
      await gate;
      await route.fulfill({ response });
    } else await route.continue();
  });
  await edit({ ...demo, title: "Old revision" });
  await Promise.race([
    intercepted,
    delay(120_000, undefined, { ref: false }).then(() => {
      throw Error("Older render was not intercepted");
    }),
  ]);
  assert.equal(await page.locator("#preview").isHidden(), true);
  await edit({ ...demo, title: "Current revision" });
  await verified();
  const currentSource = await page.locator("#preview").getAttribute("src");
  release();
  await page.unrouteAll({ behavior: "wait" });
  assert.equal((await spec()).title, "Current revision");
  assert.equal(
    await page.locator("#preview").getAttribute("src"),
    currentSource,
  );
  // Actual local file picker, then an explicitly authored spec against that file.
  const csv = join(evidence, "experiment.csv");
  const rows = ["epoch,score,loss,model,seed"];
  for (let epoch = 1; epoch <= 3; epoch++)
    for (const [model, gain] of [
      ["base", 0],
      ["ours", 2],
    ] as const)
      for (let seed = 0; seed < 4; seed++)
        rows.push(
          `${epoch},${50 + epoch + seed + gain},${100 - (50 + epoch + seed + gain)},${model},${seed}`,
        );
  writeFileSync(csv, rows.join("\n") + "\n");
  const uploadReady = page.waitForRequest((request) =>
    request.url().endsWith("/api/validate"),
  );
  await page.locator("#data-file").setInputFiles(csv);
  await page.waitForFunction(() =>
    document
      .querySelector("#data-summary")
      ?.textContent?.startsWith("experiment.csv"),
  );
  // Wait for the upload/suggestion transition before the explicit author edit.
  await uploadReady;
  await edit({
    ...demo,
    repeat: { fields: ["score", "loss"], columns: 2 },
    output: { stem: "panels", size: "double_column", formats: ["png"] },
  });
  await page.locator('#status[data-state="failed"]').waitFor();
  assert.equal(await page.locator("#claims .claim").count(), 2);
  assert.match(
    await page.locator("#claims").innerText(),
    /HOLDS.*score.*panel 1/,
  );
  assert.match(
    await page.locator("#claims").innerText(),
    /FAILS.*loss.*panel 2/,
  );
  await page.screenshot({
    path: join(evidence, "per-panel-claims.png"),
    fullPage: true,
  });
  await page.locator("#live").uncheck();
  await edit({
    ...demo,
    title: "Exported experiment",
    output: { stem: "experiment", formats: ["svg", "pdf"] },
  });
  await page.waitForFunction(
    () => document.querySelector("#status")?.textContent === "Ready to render",
  );
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.locator("#render").click();
  await verified();
  assert.deepEqual((await spec()).output.formats, ["svg", "pdf", "png"]);
  await page.screenshot({
    path: join(evidence, "desktop.png"),
    fullPage: true,
  });
  const download = async (name: string) => {
    const pending = page.waitForEvent("download");
    await page.locator("#bundle").click();
    await (await pending).saveAs(join(evidence, name));
  };
  await download("without-data.zip");
  await page.locator("#include-data").check();
  await download("with-data.zip");
  execFileSync(
    python,
    [
      "-c",
      `
import json, pathlib, subprocess, sys, zipfile
from graphunslopify.audit import _outputs, _validate_report
root=pathlib.Path(sys.argv[1])
with zipfile.ZipFile(root/'controls-with-data.zip') as archive:
    controlled=root/'controls-reproduced';archive.extractall(controlled)
controlled=controlled.resolve()
form_report=json.loads((controlled/'figure.report.json').read_text())
assert form_report['status']=='passed'
assert form_report['spec']['title']=='Controls-only figure'
assert form_report['spec']['y']['label']=='Validation score' and form_report['spec']['y']['unit']=='points'
assert form_report['spec']['caption']=="Literal <script> _&% control caption\\nSecond line stays literal."
assert form_report['spec']['output']['size']=='double_column' and form_report['spec']['output']['dpi']==300
assert form_report['spec']['output']['formats']==['png','pdf']
assert form_report['spec']['uncertainty']['over']=='seed'
_validate_report(form_report);assert len(_outputs(form_report,controlled,controlled))==2
done=subprocess.run([sys.executable,'figure.py','--strict','--json'],cwd=controlled,capture_output=True,text=True)
assert done.returncode==0,done.stderr
assert json.loads(done.stdout)['spec_hash']==form_report['spec_hash']
with zipfile.ZipFile(root/'without-data.zip') as archive:
    assert not any(n.endswith(('.csv','.parquet')) or n=='data.json' for n in archive.namelist())
with zipfile.ZipFile(root/'with-data.zip') as archive:
    assert 'data.csv' in archive.namelist()
    assert all(pathlib.PurePosixPath(n).name==n for n in archive.namelist())
    target=root/'reproduced';archive.extractall(target)
target=target.resolve()
spec=json.loads((target/'experiment.figure.json').read_text())
report=json.loads((target/'experiment.report.json').read_text())
assert spec==report['spec']
assert spec['data']['path']=='data.csv'
_validate_report(report);assert len(_outputs(report,target,target))==3
assert (target/'experiment.pdf').read_bytes().startswith(b'%PDF')
result=subprocess.run([sys.executable,'experiment.py','--strict','--json','--report','roundtrip.json'],cwd=target,text=True,capture_output=True)
assert result.returncode==0,result.stderr
again=json.loads(result.stdout);assert again['spec_hash']==report['spec_hash']
assert again['data']['sha256_prefix']==report['data']['sha256_prefix']
_validate_report(again);_outputs(again,target,target)
print('Exported Python rerendered outside checkout; spec, report, data, output digests and provenance verified')
`,
      evidence,
    ],
    { env, stdio: "inherit" },
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: join(evidence, "mobile.png"), fullPage: true });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  await page.locator("#live").check();
  await edit({
    ...demo,
    filter: [{ field: "model", op: "eq", value: "not-present" }],
  });
  await page.locator('#status[data-state="failed"]').waitFor();
  assert.match(
    await page.locator("#findings").innerText(),
    /every row was filtered out/,
  );
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.screenshot({
    path: join(evidence, "runtime-error.png"),
    fullPage: true,
  });
  // A real multi-sheet workbook must not silently choose an experiment.
  await page.setViewportSize({width: 1500, height: 1000});
  await page.locator("#live").uncheck();
  await page.locator("#data-file").setInputFiles(resolve("python/tests/fixtures/worksheet-experiments.xlsx"));
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Choose a worksheet");
  assert.equal(await page.locator("#worksheet").inputValue(), "");
  assert.equal(await page.locator("#include-data-label").innerText(), "Include entire workbook (all worksheets) in ZIP");
  assert.equal(await page.locator("#include-data").isChecked(), false);
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.locator("#render").click();
  assert.equal(await page.locator("#status").innerText(), "Choose a worksheet");
  await page.locator("#worksheet").selectOption("Measured results");
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  assert.equal((await spec()).data.sheet, "Measured results");
  await page.locator("#kind").selectOption("bar");
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  await control("title", "Native worksheet figure");
  await control("y-unit", "points");
  await page.locator("#render").click();
  await verified();
  const nativeSpec = await spec();
  assert.equal(nativeSpec.data.format, "excel");
  assert.equal(nativeSpec.data.sheet, "Measured results");
  await page.locator("#include-data").uncheck();
  await download("workbook-without-data.zip");
  await page.locator("#include-data").check();
  await download("workbook-with-data.zip");
  await page.screenshot({path: join(evidence, "workbook-desktop.png"), fullPage: true});
  await page.locator("#worksheet").selectOption("Control experiment");
  assert.equal(await page.locator("#preview").isHidden(), true);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  assert.equal((await spec()).title, "Native worksheet figure");
  assert.equal((await spec()).data.sheet, "Control experiment");
  const controlledResponse = page.waitForResponse(response => response.url().endsWith("/api/render"));
  await page.locator("#render").click();
  const controlledRun = await (await controlledResponse).json();
  await verified();
  assert.equal(controlledRun.report.spec.data.sheet, "Control experiment");
  await page.locator("#worksheet").selectOption("Measured results");
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  let releaseSheet!: () => void, sawSheet!: () => void, deliveredSheet!: () => void;
  const heldSheet = new Promise<void>(resolve => releaseSheet = resolve);
  const sheetSeen = new Promise<void>(resolve => sawSheet = resolve);
  const sheetDelivered = new Promise<void>(resolve => deliveredSheet = resolve);
  let heldWorksheetOnce = false;
  await page.route("**/api/select-sheet", async route => {
    if (!heldWorksheetOnce && route.request().postDataJSON().sheet === "Control experiment") {
      heldWorksheetOnce = true;
      const response = await route.fetch();
      sawSheet();
      await heldSheet;
      await route.fulfill({response});
      deliveredSheet();
    } else await route.continue();
  });
  await page.locator("#worksheet").selectOption("Control experiment");
  const sheetDeadline = async (promise: Promise<void>, label: string) => {
    const abort = new AbortController();
    try {
      await Promise.race([promise, delay(30_000, undefined, {signal: abort.signal})
        .then(() => { throw Error(label); })]);
    } finally { abort.abort(); }
  };
  await sheetDeadline(sheetSeen, "Worksheet request was not intercepted");
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  await page.locator("#worksheet").selectOption("Measured results");
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  releaseSheet();
  await sheetDeadline(sheetDelivered, "Held worksheet response was not delivered");
  await delay(150);
  await page.unroute("**/api/select-sheet");
  assert.equal((await spec()).data.sheet, "Measured results");
  assert.equal((await spec()).title, "Native worksheet figure");
  assert.equal(await page.locator("#worksheet").inputValue(), "Measured results");
  assert.match(await page.locator("#data-summary").innerText(), /Measured results.*3 rows/);
  assert.equal(await page.locator("#preview").isHidden(), true);
  await page.locator("#render").click();
  await verified();
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: join(evidence, "workbook-mobile.png"), fullPage: true});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
  execFileSync(python, ["-c", `
import importlib.util, json, pathlib, subprocess, sys, zipfile
from graphunslopify.audit import _validate_report
root=pathlib.Path(sys.argv[1]); original=pathlib.Path(sys.argv[2]).read_bytes()
with zipfile.ZipFile(root/'workbook-without-data.zip') as z:
    assert 'data.xlsx' not in z.namelist()
with zipfile.ZipFile(root/'workbook-with-data.zip') as z:
    assert z.read('data.xlsx')==original
    target=root/'workbook-reproduced';z.extractall(target)
target=target.resolve()
specs=list(target.glob('*.figure.json'));assert len(specs)==1
spec=json.loads(specs[0].read_text());stem=spec['output']['stem']
report=json.loads((target/(stem+'.report.json')).read_text());_validate_report(report)
assert spec==report['spec'] and spec['data']['sheet']=='Measured results'
assert spec['title']=='Native worksheet figure' and spec['y']['unit']=='points'
done=subprocess.run([sys.executable,stem+'.py','--strict','--json'],cwd=target,capture_output=True,text=True)
assert done.returncode==0,done.stderr
assert json.loads(done.stdout)['spec_hash']==report['spec_hash']
probe="""import importlib.util,matplotlib.pyplot as plt
s=importlib.util.spec_from_file_location('workbook',(STEM+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
f=m.prepare(m.load());assert f['subject'].tolist()==['001','NA','010']
fig,ax=plt.subplots();m.draw_panel(ax,f)
assert dict(zip([t.get_text() for t in ax.get_xticklabels()],[p.get_height() for p in ax.patches]))=={'001':7,'NA':11,'010':13}
plt.close(fig)
""".replace('STEM',repr(stem))
checked=subprocess.run([sys.executable,'-c',probe],cwd=target,capture_output=True,text=True)
assert checked.returncode==0,checked.stderr
assert (target/'data.xlsx').read_bytes()==original
print('Browser-selected workbook reproduced with actual7/11/13 marks and001/NA/010 identifiers')
`, evidence, resolve("python/tests/fixtures/worksheet-experiments.xlsx")], {env, stdio: "inherit"});
  await page.getByRole("button", {name: "Try sample data"}).click();
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Ready to render");
  assert.equal(await page.locator("#worksheet-box").isHidden(), true);
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  writeFileSync(
    join(evidence, "checks.json"),
    JSON.stringify(
      {
        passed: true,
        external_requests: external.length,
        javascript_errors: errors.length,
        controlled_kinds: controlledKinds,
        workflows: [
          "data picker",
          "spec editing",
          "offered fix",
          "static rejection",
          "false runtime claim",
          "per-panel mixed verdicts",
          "manual rendering",
          "runtime error invalidates outputs",
          "stale response",
          "PNG preview",
          "ZIP consent",
          "reproduced exports",
          "mobile layout",
          "schema-driven required controls for all21 kinds",
          "controls-only figure and reproduced bundle",
          "typed numeric draft refusal and batch recovery",
          "unsupported median SEM rejection",
          "native claim add edit remove and strict failure",
          "advanced settings custom labels and undo preserved",
          "invalid JSON disables form controls",
          "live native text input preserves focus",
          "native workbook staging and explicit worksheet selection",
          "worksheet switching preserves settings and invalidates evidence",
          "stale worksheet selection cannot replace current data",
          "native workbook ZIP consent and actual-artist reproduction",
          "native workbook desktop mobile and CSV sample recovery",
        ],
      },
      null,
      2,
    ),
  );
  console.log(`Local editor browser checks passed. Evidence: ${evidence}`);
} catch (error) {
  const page = browser?.contexts()[0]?.pages()[0];
  await page
    ?.screenshot({ path: join(evidence, "failure.png"), fullPage: true })
    .catch(() => {});
  console.error(`Editor evidence: ${evidence}\n${stderr}`);
  throw error;
} finally {
  await browser?.close();
  lines.close();
  server.kill("SIGINT");
}
