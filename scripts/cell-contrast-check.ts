/** Check real offline browser text against the heatmap's rendered PNG cells. */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";
import { translate } from "../src/translate.ts";
import { resolvePython } from "./python.ts";

const python = resolvePython();
if (!python) throw Error("Set PYTHON to an interpreter with the interactive extra");
const destination = mkdtempSync(join(tmpdir(), "gu-cell-contrast-"));
const sweep = Array.from({ length: 16 }, (_, r) => Array.from({ length: 16 }, (_, c) => r * 16 + c));
const cases = [
  { name: "sequential", values: [[1, 2], [3, 4]], diverging: false },
  { name: "sequential-sweep", values: sweep, diverging: false },
  { name: "diverging-sweep", values: sweep.map(row => row.map(v => v - 128)), diverging: true },
  { name: "constant-zero", values: [[0, 0], [0, 0]], diverging: true },
  { name: "missing", values: [[1, null], [null, 4]], diverging: false },
];
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executable = process.env.GRAPHUNSLOPIFY_BROWSER || (existsSync(chrome) ? chrome : undefined);
const browser = await chromium.launch({ headless: true, ...(executable ? { executablePath: executable } : {}) });
const evidence: unknown[] = [];
try {
  const page = await browser.newPage({ viewport: { width: 1500, height: 1200 } });
  const requests: string[] = [];
  await page.route(/^https?:/, route => { requests.push(route.request().url()); return route.abort(); });
  for (const item of cases) {
    const folder = join(destination, item.name);
    mkdirSync(folder);
    const columns = item.values[0]!.map((_, c) => c === 0 ? "01" : String(c));
    const rows = item.values.map((_, r) => `r${r}`);
    const csv = ["column,row,value", ...item.values.flatMap((row, r) => row.map((v, c) => `${columns[c]},${rows[r]},${v ?? ""}`))].join("\n");
    writeFileSync(join(folder, "data.csv"), csv);
    const result = translate({
      kind: "heatmap", x: { field: "column", label: "Column" }, y: { field: "row", label: "Row" },
      value: "value", value_label: "Value", annotate_cells: true, diverging: item.diverging,
      data: { path: join(folder, "data.csv") }, legend: { show: false },
      output: { stem: join(folder, "figure"), formats: ["png", "svg"], interactive: true, size: "double_column", dpi: 150 },
    });
    assert(result.status === "translated" && result.ok);
    writeFileSync(join(folder, "figure.py"), result.code);
    const runtime = JSON.parse(execFileSync(python, [join(folder, "figure.py"), "--strict", "--json"], { cwd: folder, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
    assert.equal(runtime.status, "passed");
    await page.goto(pathToFileURL(join(folder, "figure.html")).href);
    await page.waitForSelector(".annotation-text");
    const observed: { x: string[]; y: string[]; z: (number | null)[][]; labels: { text: string; colour: string; background: number[]; row: number; column: number }[] } = await page.evaluate(`(async () => {
      const image = document.querySelector('.hm image');
      const bitmap = new Image(); bitmap.src = image.getAttribute('href') || image.getAttribute('xlink:href');
      await bitmap.decode();
      const canvas = document.createElement('canvas'); canvas.width = bitmap.naturalWidth; canvas.height = bitmap.naturalHeight;
      const ctx = canvas.getContext('2d'); ctx.drawImage(bitmap, 0, 0);
      const box = image.getBoundingClientRect();
      const labels = Array.from(document.querySelectorAll('.annotation-text'), text => {
        const label = text.getBoundingClientRect();
        const column = Math.floor(((label.left + label.right) / 2 - box.left) / box.width * canvas.width);
        const row = Math.floor(((label.top + label.bottom) / 2 - box.top) / box.height * canvas.height);
        return {text:text.textContent, colour:getComputedStyle(text).fill, row, column,
                background:Array.from(ctx.getImageData(column,row,1,1).data)};
      });
      const trace = document.querySelector('.js-plotly-plot')._fullData[0];
      return {x:trace.x, y:trace.y, z:trace.z, labels};
    })()`);
    assert.deepEqual(observed.x, columns);
    assert.deepEqual(observed.y, rows);
    assert.deepEqual(observed.z, item.values);
    assert.equal(observed.labels.length, item.values.flat().filter(v => v !== null).length);
    const ratios: number[] = [];
    for (const label of observed.labels) {
      const expected = item.values[label.row]?.[label.column];
      assert(expected !== undefined && expected !== null, "Annotation must occupy a measured cell");
      assert.equal(Number(label.text), expected);
      assert.equal(label.background[3], 255);
      const foreground = label.colour.match(/[\d.]+/g)!.slice(0, 3).map(Number);
      const luminance = (rgb: number[]) => rgb.slice(0, 3).map(v => v / 255)
        .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i]!, 0);
      const [low, high] = [luminance(foreground), luminance(label.background)].sort((a, b) => a - b);
      const ratio = (high! + 0.05) / (low! + 0.05);
      assert(ratio >= 4.5, `${item.name}: ${label.text} has contrast ${ratio}`);
      ratios.push(ratio);
    }
    assert.equal(requests.length, 0, "HTML must run with no external connections");
    await page.screenshot({ path: join(folder, "browser.png") });
    const report = { name: item.name, labels: ratios.length, minimumContrast: Math.min(...ratios), runtime: runtime.status };
    evidence.push(report);
    console.log(JSON.stringify(report));
  }
  writeFileSync(join(destination, "evidence.json"), JSON.stringify(evidence, null, 2));
  console.log(`Offline cell contrast evidence: ${destination}`);
} finally {
  await browser.close();
}
