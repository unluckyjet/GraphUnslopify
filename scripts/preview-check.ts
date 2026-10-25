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
const env = { ...process.env, PYTHONPATH: resolve("python") };
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
  await page.goto(url);
  await page.waitForFunction(
    () => document.querySelectorAll("#kind option").length === 21,
  );
  assert.equal(await page.locator("#recipe option").count(), 26);
  assert.equal(await page.locator("#bundle").isDisabled(), true);
  const edit = async (spec: object | string) =>
    page
      .locator("#spec")
      .fill(typeof spec === "string" ? spec : JSON.stringify(spec, null, 2));
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
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  writeFileSync(
    join(evidence, "checks.json"),
    JSON.stringify(
      {
        passed: true,
        external_requests: external.length,
        javascript_errors: errors.length,
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
