import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();
const base = { kind: "line", x: { field: "epoch", label: "Epoch" },
  y: { field: "score", label: "Score" }, group: "model", aggregation: "mean", legend: { show: false } };

function run(csv: string, options: Record<string, unknown> = {}) {
  const dir = mkdtempSync(join(tmpdir(), "gu-accounting-"));
  const result = translate({ ...base, ...options, data: { path: "results.csv" },
    output: { stem: "figure", formats: ["png"], dpi: 100 } });
  assert.ok(result.status === "translated", JSON.stringify(result));
  assert.ok(result.ok, JSON.stringify(result.findings));
  writeFileSync(join(dir, "results.csv"), csv);
  writeFileSync(join(dir, "figure.py"), result.code);
  const output = execFileSync(python!, ["figure.py"], { cwd: dir, encoding: "utf8", stdio: "pipe" });
  const alt = execFileSync(python!, ["-c", "from PIL import Image; print(Image.open('figure.png').info.get('Comment', ''))"],
    { cwd: dir, encoding: "utf8" }).trim();
  return { output, alt };
}

test("uniform sample counts are printed and embedded in PNG alt text", { skip: !python }, () => {
  const result = run("epoch,score,model\n1,1,a\n1,3,a\n2,2,a\n2,4,a\n");
  assert.match(result.output, /4 rows read/);
  assert.match(result.output, /n = 2 per point/);
  assert.match(result.alt, /N = 2 per point/);
});

test("unaggregated figures have row counts and no summary sample-size assertion", { skip: !python }, () => {
  const result = run("epoch,score,model\n1,1,a\n2,2,a\n", { aggregation: "none" });
  assert.match(result.output, /2 rows read/);
  assert.ok(!/[nN] = |[nN] ranges/.test(result.output));
  assert.ok(!/[nN] = |[nN] ranges/.test(result.alt));
});

test("filter and missing-value accounting preserve exact row counts", { skip: !python }, () => {
  const rows = ["epoch,score,model"];
  for (let epoch = 1; epoch <= 10; epoch++) {
    rows.push(`${epoch},${epoch === 2 || epoch === 3 ? "" : epoch},a`, `${epoch},${epoch + 1},a`);
  }
  const result = run(rows.join("\n") + "\n", { filter: [{ field: "epoch", op: "lte", value: 8 }] });
  assert.match(result.output, /20 rows read/);
  assert.match(result.output, /16 rows after filter \(epoch lte 8\)/);
  assert.match(result.output, /14 rows with a finite score \(2 non-finite\)/);
  assert.match(result.output, /n ranges from 1 to 2 across 8 points/);
  assert.match(result.output, /warning: sample sizes differ/);
});

test("faceted counts describe plotted groups instead of pooling panels", { skip: !python }, () => {
  const rows = ["epoch,score,model,dataset"];
  for (const dataset of ["A", "B"]) {
    for (const epoch of [1, 2]) rows.push(`${epoch},1,a,${dataset}`, `${epoch},3,a,${dataset}`);
  }
  const result = run(rows.join("\n") + "\n", { facet: { by: "dataset" } });
  assert.match(result.output, /n = 2 per point/);
  assert.ok(!result.output.includes("n = 4 per point"));
});

test("repeated metrics count the observations available for each metric", { skip: !python }, () => {
  const result = run("epoch,score,loss,model\n1,1,2,a\n1,3,,a\n2,2,4,a\n2,4,6,a\n",
    { repeat: { fields: ["score", "loss"] } });
  assert.match(result.output, /n ranges from 1 to 2 across 4 points/);
});

test("skipped significance pairs name their insufficient observations", { skip: !python }, () => {
  const result = run("model,score\nbase,1\nours,2\nours,3\n", { kind: "bar", group: undefined,
    x: { field: "model", label: "Model" }, significance: { method: "bootstrap", pairs: [["base", "ours"]] } });
  assert.match(result.output, /base vs ours skipped: fewer than two finite observations \(n=1, 2\)/);
});

test("three real gallery inputs report the physical CSV row count and correct summary scope", { skip: !python }, () => {
  for (const name of ["01-training-curve", "03-single-run", "09-uncertainty-band"]) {
    const spec = JSON.parse(readFileSync(new URL(`../examples/specs/${name}.json`, import.meta.url), "utf8"));
    const path = fileURLToPath(new URL(`../examples/${spec.data.path}`, import.meta.url));
    const csv = readFileSync(path, "utf8");
    const result = run(csv, { ...spec, group: spec.group });
    assert.ok(result.output.includes(`${csv.trim().split(/\r?\n/).length - 1} rows read`), name);
    if (name === "03-single-run") {
      assert.ok(!/[nN] = |[nN] ranges/.test(result.alt));
      assert.match(result.output, /30 rows after filter/);
    } else assert.match(result.alt, /N = 3 per point/);
  }
});
