/** Real mixed/native-free PDF review, page bytes and current/historical browser evidence. */
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, readdirSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, relative } from "node:path";
import { createInterface } from "node:readline";
import { chromium } from "playwright";

declare const document: { querySelector(selector: string): { textContent: string; hidden: boolean; naturalWidth: number; value: string } | null; documentElement: { scrollWidth: number } };
declare const window: { innerWidth: number };
const python = process.env.PYTHON || "python";
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED ? { ...process.env } : { ...process.env, PYTHONPATH: resolve("python") };
const evidence = mkdtempSync(join(tmpdir(), "gu-pdf-paper-check-"));
const fixture = readFileSync("python/tests/fixtures/project-review-pages.pdf");
const other = readFileSync("examples/baseline/02-loss-log.pdf");
const hash = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");
const cli = (...args: string[]) => JSON.parse(execFileSync(python, ["-m", "graphunslopify.cli", ...args], { env, encoding: "utf8", timeout: 180_000 }));
function inventory(root: string): Record<string, string> {
  const result: Record<string, string> = {};
  function walk(folder: string) { for (const item of readdirSync(folder, { withFileTypes: true })) { const path = join(folder, item.name); if (item.isDirectory()) walk(path); else if (item.isFile()) result[relative(root, path)] = hash(readFileSync(path)); } }
  walk(root); return result;
}
const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.GRAPHUNSLOPIFY_BROWSER || (existsSync(mac) ? mac : undefined);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const workflows: string[] = [], errors: string[] = [], external: string[] = [];
const results: object[] = [];
try {
  for (const mode of ["mixed", "review-only"]) {
    const paper = join(evidence, mode + " paper ü with spaces");
    let firstNative = "", nativeBytes: Record<string, string> = {}, data: Buffer | null = null;
    if (mode === "mixed") {
      cli("demo", paper, "--json"); cli("audit-init", paper); cli("project-init", paper);
      firstNative = cli("project-run", paper).id;
      nativeBytes = inventory(join(paper, "graphunslopify-project/history", firstNative));
      data = readFileSync(join(paper, "results.csv"));
    } else { mkdirSync(paper); cli("project-init", paper, "--review-only"); }
    const server = spawn(python, ["-m", "graphunslopify.cli", "project-preview", paper, "--port", "0"], { env, stdio: ["ignore", "pipe", "pipe"] });
    let stderr = ""; server.stderr.on("data", chunk => { stderr += chunk; });
    const lines = createInterface({ input: server.stdout });
    const startup = setTimeout(() => server.kill(), 30_000);
    const url = await new Promise<string>((accept, reject) => { lines.once("line", line => { try { accept(JSON.parse(line).url); } catch (problem) { reject(problem); } }); server.once("exit", code => reject(Error(`Workspace exited ${code}: ${stderr}`))); });
    clearTimeout(startup);
    const page = await browser.newPage({ viewport: { width: 1480, height: 1050 }, acceptDownloads: true });
    page.setDefaultTimeout(90_000);
    page.on("pageerror", problem => errors.push(problem.message));
    page.on("request", request => { if (!request.url().startsWith("data:") && new URL(request.url()).origin !== new URL(url).origin) external.push(request.url()); });
    try {
      await page.goto(url);
      await page.waitForFunction(() => document.querySelector("#notice")?.textContent.startsWith("Ready"));
      const token = await page.locator('meta[name="preview-token"]').getAttribute("content"); assert.ok(token);
      const api = async (path: string) => { const response = await page.request.get(url + path, { headers: { "X-Preview-Token": token } }); assert.equal(response.status(), 200, await response.text()); return response.json(); };
      if (mode === "review-only") {
        assert.equal(await page.locator("#audit").isDisabled(), true);
        assert.equal(await page.locator(".definition-card").isHidden(), true);
        assert.match(await page.locator("#review-status").innerText(), /Add a PDF/);
        assert.equal((await api("/api/state")).figures.length, 0);
        workflows.push("genuine review-only initialization without fake native figures or audit actions");
      }
      await page.locator("#pdf-file").setInputFiles({ name: "Synthetic two-page paper ü.pdf", mimeType: "application/pdf", buffer: fixture });
      await page.locator("#pdf-id").fill("external");
      await page.locator("#pdf-pages").fill("0");
      assert.equal(await page.locator("#pdf-upload").isDisabled(), true);
      await page.locator("#pdf-pages").fill("1,2"); await page.locator("#pdf-dpi").fill("71");
      assert.equal(await page.locator("#pdf-upload").isDisabled(), true);
      workflows.push(mode + " invalid page and DPI intent cannot submit an inspection");
      if (mode === "mixed") {
        await page.locator("#pdf-id").fill("figure");
        assert.equal(await page.locator("#pdf-upload").isDisabled(), true);
        await page.locator("#pdf-id").fill("external");
        workflows.push("PDF source IDs cannot silently replace native figure bindings");
      }
      await page.locator("#pdf-pages").fill("1,2"); await page.locator("#pdf-dpi").fill("144");
      await page.locator("#pdf-upload").click();
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === false);
      assert.equal(await page.locator("#audit").isDisabled(), true);
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === true);
      await page.waitForFunction(() => document.querySelector("#review-figure")?.value === "pdf:external");
      await page.waitForFunction(() => !!document.querySelector("#review-preview")?.naturalWidth && document.querySelector("#review-preview")?.hidden === false);
      let state = await api("/api/state");
      assert.equal(state.job.result.exit_code, 2); assert.equal(state.job.result.status, "incomplete");
      assert.equal(state.inspections[0].origin, "uploaded_local_copy");
      const first = state.inspections[0].event;
      const review = await api("/api/review");
      const pdf = review.figures.find((row: { source_type: string }) => row.source_type === "pdf");
      assert.equal(pdf.inspection.science_status, "untested");
      assert.equal(pdf.matches_latest_accepted_inputs, false);
      assert.equal(await page.locator("[data-review-group]").count(), 4);
      assert.equal(pdf.groups.claims.state, "untested");
      assert.ok((await page.locator('[data-review-group="claims"]').innerText()).includes(pdf.groups.claims.reason));
      assert.equal(await page.locator('[data-review-group="claims"] [data-verdict="untested"]').count(), 1);
      assert.match(await page.locator("#review-status").innerText(), /Numerical claims and original data remain untested/);
      assert.equal(await page.locator("#review-edit").isDisabled(), true);
      assert.equal(await page.locator(".definition-card").isHidden(), true);
      workflows.push(mode + " real upload, strict incomplete2 and four scoped PDF evidence groups");
      assert.equal(await page.locator("#review-page option").count(), 2);
      const one = hash(Buffer.from((await page.locator("#review-preview").getAttribute("src"))!.split(",")[1]!, "base64"));
      await page.locator("#review-page").selectOption("2");
      await page.waitForFunction(() => document.querySelector("#review-preview-note")?.textContent.startsWith("Saved page 2"));
      const two = hash(Buffer.from((await page.locator("#review-preview").getAttribute("src"))!.split(",")[1]!, "base64"));
      assert.notEqual(one, two);
      workflows.push(mode + " actual distinct saved page navigation");
      const downloadPromise = page.waitForEvent("download");
      await page.getByRole("link", { name: "Saved page-2.png", exact: true }).click();
      const downloaded = await downloadPromise; const output = join(evidence, mode + "-page-2.png");
      await downloaded.saveAs(output);
      assert.equal(hash(readFileSync(output)), pdf.inspection.assets.find((asset: { path: string }) => asset.path === "packet/page-2.png").sha256);
      workflows.push(mode + " actual page download matches inventoried bytes");
      await page.locator(".review-card").screenshot({ path: join(evidence, mode + "-desktop.png") });
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
      await page.locator(".review-card").screenshot({ path: join(evidence, mode + "-mobile.png") });
      await page.setViewportSize({ width: 1480, height: 1050 });
      workflows.push(mode + " real desktop and narrow mobile review");
      if (mode === "mixed") {
        assert.equal(state.status, "inputs_match_last_run");
        assert.equal(state.figures.length, 1);
        await page.locator('[data-figure="figure"]').click();
        await page.waitForFunction(() => document.querySelector("#review-figure")?.value === "figure");
        await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.includes("match this accepted saved audit"));
        assert.equal(await page.locator(".definition-card").isHidden(), false);
        await page.locator("#review-edit").click();
        assert.equal(await page.locator("#selected-title").innerText(), "figure");
        assert.equal(await page.locator("#error").isHidden(), true);
        workflows.push("native review edit action forwards its selected figure identity");
        await page.locator('[data-pdf="external"]').click();
        await page.waitForFunction(() => document.querySelector("#review-figure")?.value === "pdf:external");
        workflows.push("mixed navigation preserves current native acceptance and independent unknown PDF science");
      }
      const source = join(paper, pdf.inspection.path);
      writeFileSync(source, other);
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Historical PDF visual evidence"));
      workflows.push(mode + " polling detects changed PDF source and labels saved visual evidence historical");
      await page.locator("#review-page").selectOption("2");
      await page.waitForFunction(() => document.querySelector("#review-preview-note")?.textContent.startsWith("Saved page 2"));
      await page.locator("#review-inspect").click();
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === false, undefined, { timeout: 15_000 });
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === true);
      state = await api("/api/state");
      assert.equal(state.job.result.status, "failed");
      assert.equal(state.job.result.exit_code, 2);
      const failedEvent = await api("/api/event?id=" + state.job.result.id);
      assert.ok(failedEvent.result.errors.some((message: string) => message.includes("one-based pages within this PDF")));
      await page.waitForFunction(() => document.querySelector("#review-groups")?.textContent.includes("one-based pages within this PDF"));
      await page.locator("#pdf-file").setInputFiles({ name: "Updated paper.pdf", mimeType: "application/pdf", buffer: other });
      await page.locator("#pdf-pages").fill("1"); await page.locator("#pdf-id").fill("external");
      await page.locator("#pdf-upload").click();
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === false);
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === true);
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Source-free PDF inspection"));
      workflows.push(mode + " actual reinspection and failed page recovery remain strict incomplete");
      await page.locator("#review-event").selectOption(first);
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Saved historical PDF inspection"));
      assert.equal(await page.locator("#review-figure").inputValue(), "pdf:external");
      workflows.push(mode + " explicit old PDF review never borrows a newer inspection or native acceptance");
      let releaseMetadata!: () => void, heldMetadata!: () => void;
      const metadataHeld = new Promise<void>(accept => { heldMetadata = accept; });
      const metadataGate = new Promise<void>(accept => { releaseMetadata = accept; });
      const savedPattern = "**/api/review?event=" + first;
      await page.route(savedPattern, async route => {
        const response = await page.request.fetch(route.request()); heldMetadata();
        await metadataGate; await route.fulfill({ response });
      });
      try {
        await page.locator("#review-event").selectOption(first); await metadataHeld;
        await page.locator("#review-latest").click();
        await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Source-free PDF inspection"));
        releaseMetadata(); await page.waitForTimeout(150);
        assert.equal(await page.locator("#review-event").inputValue(), "");
        assert.match(await page.locator("#review-status").innerText(), /^Source-free PDF inspection/);
      } finally { releaseMetadata(); await page.unroute(savedPattern); }
      workflows.push(mode + " late real saved-PDF response cannot replace current evidence");
      const latestReview = await api("/api/review");
      const latestPdf = latestReview.figures.find((row: { source_type: string }) => row.source_type === "pdf");
      const latestEvent = latestPdf.inspection.event;
      let releaseImage!: () => void, heldImage!: () => void;
      const imageHeld = new Promise<void>(accept => { heldImage = accept; });
      const imageGate = new Promise<void>(accept => { releaseImage = accept; });
      const assetPattern = "**/api/pdf-asset?**";
      await page.route(assetPattern, async route => {
        const request = new URL(route.request().url());
        if (request.searchParams.get("event") !== first || request.searchParams.get("view") !== "1") { await route.continue(); return; }
        const response = await page.request.fetch(route.request()); heldImage();
        await imageGate; await route.fulfill({ response });
      });
      try {
        await page.locator("#review-event").selectOption(first); await imageHeld;
        await page.locator("#review-latest").click();
        await page.waitForFunction((event: string) => document.querySelector("#review-preview-note")?.textContent.includes(event), latestEvent);
        const ownedImage = await page.locator("#review-preview").getAttribute("src");
        releaseImage(); await page.waitForTimeout(150);
        assert.equal(await page.locator("#review-preview").getAttribute("src"), ownedImage);
        assert.equal(await page.locator("#review-event").inputValue(), "");
      } finally { releaseImage(); await page.unroute(assetPattern); }
      workflows.push(mode + " late real saved page bytes cannot replace a newer selected preview");
      const latestPng = latestPdf.inspection.assets.find((asset: { path: string }) => asset.path.endsWith(".png"));
      const pngPath = join(paper, "graphunslopify-project/history", latestEvent, latestPng.path);
      const originalPng = readFileSync(pngPath);
      writeFileSync(pngPath, Buffer.concat([originalPng, Buffer.from("tampered")]));
      await page.waitForFunction(() => document.querySelector("#review-preview")?.hidden === true);
      await page.waitForFunction(() => document.querySelector('[data-review-group="reproduction"]')?.textContent.includes("unavailable or changed"));
      assert.equal(await page.locator("#review-downloads a").count(), 0);
      assert.equal((await api("/api/state")).history.find((event: { id: string }) => event.id === latestEvent).integrity, true);
      writeFileSync(pngPath, originalPng);
      await page.waitForFunction(() => document.querySelector("#review-preview")?.hidden === false && !!document.querySelector("#review-preview")?.naturalWidth);
      workflows.push(mode + " polling rejects tampered page bytes despite intact receipt and restores only matching bytes");
      const currentSource = join(paper, latestPdf.inspection.path);
      renameSync(currentSource, currentSource + ".missing-by-check");
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Historical PDF visual evidence") && document.querySelector("#review-context")?.textContent.includes("source unavailable"));
      assert.equal(await page.locator("#review-inspect").isDisabled(), true);
      renameSync(currentSource + ".missing-by-check", currentSource);
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Source-free PDF inspection"));
      workflows.push(mode + " missing local source retains historical evidence and disables reinspection until recovery");
      await page.route("**/api/state", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "fixture state transport unavailable" }) }));
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.includes("Could not refresh the project"));
      assert.equal(await page.locator("#review-preview").isHidden(), true);
      assert.equal(await page.locator("#review-downloads a").count(), 0);
      assert.equal(await page.locator("#review-inspect").isDisabled(), true);
      await page.unroute("**/api/state");
      await page.waitForFunction(() => document.querySelector("#review-status")?.textContent.startsWith("Source-free PDF inspection"));
      await page.waitForFunction(() => document.querySelector("#review-preview")?.hidden === false);
      workflows.push(mode + " failed collection transport clears PDF preview/actions until successful recovery");
      await page.locator("#pdf-file").setInputFiles({ name: "<img src=x onerror=alert(1)>.pdf", mimeType: "application/pdf", buffer: other });
      await page.locator("#pdf-id").fill("unsafe"); await page.locator("#pdf-pages").fill("1");
      await page.locator("#pdf-upload").click();
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === false);
      await page.waitForFunction(() => document.querySelector("#running")?.hidden === true);
      await page.waitForFunction(() => document.querySelector("#review-figure")?.value === "pdf:unsafe");
      assert.equal(await page.locator('[data-pdf="unsafe"] img').count(), 0);
      assert.ok((await page.locator('[data-pdf="unsafe"]').innerText()).includes("<img src=x"));
      workflows.push(mode + " source filenames render as text without executable markup or external requests");
      if (data) {
        assert.deepEqual(readFileSync(join(paper, "results.csv")), data);
        assert.deepEqual(inventory(join(paper, "graphunslopify-project/history", firstNative)), nativeBytes);
        assert.equal((await api("/api/state")).history.filter((event: { action: string }) => event.action === "run").length, 1);
      }
      results.push({ mode, paper, first_inspection: first, native_data_and_first_history_unchanged: data ? true : null, final_state: await api("/api/state") });
    } catch (problem) {
      await page.screenshot({ path: join(evidence, mode + "-failure.png"), fullPage: true });
      const token = await page.locator('meta[name="preview-token"]').getAttribute("content");
      const state = await page.request.get(url + "/api/state", { headers: { "X-Preview-Token": token || "" } });
      writeFileSync(join(evidence, mode + "-failure.json"), JSON.stringify({
        error: String(problem), error_text: await page.locator("#error").innerText(),
        status: await page.locator("#review-status").innerText(), state: await state.json(),
      }, null, 2));
      throw problem;
    } finally { await page.close(); server.kill(); lines.close(); }
  }
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  const report = { status: "passed", workflows, results, page_errors: errors, external_requests: external, evidence };
  writeFileSync(join(evidence, "verification.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
