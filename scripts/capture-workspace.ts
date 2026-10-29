/** Capture the real editor and measured regions for a source-bound comparison. */
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { chromium } from "playwright";
declare const document: {
  querySelectorAll(selector: string): { length: number };
  querySelector(selector: string): { complete: boolean } | null;
  fonts: { ready: Promise<unknown> };
};

const folder = resolve(process.argv[2] || "/tmp/gu-workspace-capture");
const name = process.argv[3] || "after";
const source = resolve(process.env.GRAPHUNSLOPIFY_CAPTURE_SOURCE || ".");
mkdirSync(folder, { recursive: true });
const env = { ...process.env, PYTHONPATH: join(source, "python") };
const server = spawn(process.env.PYTHON || "python", ["-m", "graphunslopify.cli", "preview", "--port", "0"],
  { env, stdio: ["ignore", "pipe", "pipe"] });
const lines = createInterface({ input: server.stdout });
const timer = setTimeout(() => server.kill("SIGINT"), 30_000);
const url = await new Promise<string>((accept, reject) => {
  lines.once("line", line => { try { accept(JSON.parse(line).url); } catch (error) { reject(error); } });
  server.once("exit", code => reject(Error(`Preview exited ${code}`)));
});
clearTimeout(timer);
const browser = await chromium.launch({ headless: true,
  ...(process.env.GRAPHUNSLOPIFY_BROWSER ? { executablePath: process.env.GRAPHUNSLOPIFY_BROWSER } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
  page.setDefaultTimeout(60_000);
  await page.goto(url);
  await page.waitForFunction(() => document.querySelectorAll('#kind option').length===21);
  await page.locator("#demo").click();
  await page.locator('#status[data-state="passed"]').waitFor();
  await page.waitForFunction(() => document.querySelector('#preview')?.complete);
  await page.evaluate(() => document.fonts.ready);
  const header = (await page.locator("header").boundingBox())!;
  const crop = { x: 0, y: header.y + header.height, width: 1500, height: 850 };
  await page.screenshot({ path: join(folder, `${name}.png`), clip: crop });
  const bounds: Record<string, object> = {};
  for (const [key, selector] of Object.entries({ canvas: ".paper", data: "#columns", upload: ".upload", inspector: ".editor .section-head" })) {
    const b = (await page.locator(selector).boundingBox())!;
    bounds[key] = { x: b.x / 15, y: (b.y - crop.y) / 8.5, w: b.width / 15, h: b.height / 8.5 };
  }
  const cells = page.locator('#columns th:not(:first-child), #columns td:not(:first-child)');
  const boxes = await Promise.all((await cells.all()).map(cell => cell.boundingBox()));
  const visible = boxes.filter((box): box is NonNullable<typeof box> => box !== null);
  if (visible.length) {
    const x = Math.min(...visible.map(b => b.x)), y = Math.min(...visible.map(b => b.y));
    bounds.dataDetails = { x: x / 15, y: (y - crop.y) / 8.5,
      w: (Math.max(...visible.map(b => b.x + b.width)) - x) / 15,
      h: (Math.max(...visible.map(b => b.y + b.height)) - y) / 8.5 };
  }
  const src = (await page.locator("#preview").getAttribute("src"))!;
  const plot = await (await page.request.get(new URL(src, url).href)).body();
  writeFileSync(join(folder, `${name}-figure.png`), plot);
  const digests = Object.fromEntries(["index.html", "app.js", "app.css"].map(file => [file,
    createHash("sha256").update(readFileSync(join(source, "python/graphunslopify/web", file))).digest("hex")]));
  writeFileSync(join(folder, `${name}.json`), JSON.stringify({ viewport: { width: 1500, height: 1100 }, crop, bounds, source_digests: digests }, null, 2) + "\n");
  console.log(`Captured ${name}: ${folder}`);
} finally {
  await browser.close(); lines.close(); server.kill("SIGINT");
}
