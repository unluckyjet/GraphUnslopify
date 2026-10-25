/**
 * Renders every composition feature against real matplotlib.
 *
 * Layering, repeat, a cut axis, an inset and a table each touch a different
 * part of main(), and a spec that validates but does not run is worse than none
 * because an agent will trust it.
 *
 *   node scripts/compose-check.ts [python]
 */

import { execFileSync } from "node:child_process";
import { readFileSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { failureDetail } from "./exec-failure.ts";
import { resolvePython } from "./python.ts";

const python = process.argv[2] ?? resolvePython();
if (!python) {
  console.log("no Python interpreter found; set PYTHON or pass one as the first argument");
  process.exit(1);
}
const dir = mkdtempSync(join(tmpdir(), "gu-compose-"));

let seed = 31;
const next = () => ((seed = (seed * 1103515245 + 12345) % 2147483648), seed / 2147483648);

const rows = ["model,dataset,split,seed,epoch,accuracy,loss,latency_ms"];
for (const model of ["baseline", "ours"]) {
  for (const dataset of ["CIFAR", "ImageNet"]) {
    for (const split of ["val", "test"]) {
      for (let s = 0; s < 3; s += 1) {
        for (let epoch = 1; epoch <= 20; epoch += 1) {
          const ceiling = model === "ours" ? 84 : 72;
          const accuracy = ceiling * (1 - Math.exp(-epoch / 6)) + (next() - 0.5) * 2;
          const loss = 2.2 * Math.exp(-epoch / 7) + 0.2 + (next() - 0.5) * 0.05;
          rows.push(
            `${model},${dataset},${split},${s},${epoch},${accuracy.toFixed(3)},${loss.toFixed(4)},${(12 + next() * 8).toFixed(2)}`,
          );
        }
      }
    }
  }
}
// A gap in the middle, which is what an axis break is for.
for (const model of ["baseline", "ours"]) {
  rows.push(`${model},Bimodal,test,0,1,${model === "ours" ? 95 : 8},0.5,10`);
}
writeFileSync(join(dir, "results.csv"), rows.join("\n") + "\n");

const DATA = { path: "results.csv" };
const X = { field: "epoch", label: "Training epoch" };
const Y = { field: "accuracy", label: "Test accuracy", unit: "%" };

const CASES: [string, Record<string, unknown>][] = [
  [
    "layers",
    {
      kind: "line",
      x: X,
      y: Y,
      group: "model",
      aggregation: "mean",
      layers: [
        { mark: "scatter", label: "observations" },
        { mark: "rug" },
        { mark: "rule", value: 80, label: "target" },
      ],
      data: DATA,
    },
  ],
  [
    "repeat",
    {
      kind: "line",
      x: X,
      y: Y,
      group: "model",
      aggregation: "mean",
      repeat: { fields: ["accuracy", "loss", "latency_ms"], columns: 3 },
      output: { size: "double_column" },
      data: DATA,
    },
  ],
  [
    "inset",
    {
      kind: "line",
      x: X,
      y: Y,
      group: "model",
      aggregation: "mean",
      inset: { x: [14, 20], y: [65, 85], corner: "lower_right" },
      data: DATA,
    },
  ],
  [
    "axis_break",
    {
      kind: "line",
      x: X,
      y: Y,
      group: "model",
      aggregation: "mean",
      axis_break: { axis: "y", from: 30, to: 60 },
      data: DATA,
    },
  ],
  [
    "nested_facet",
    {
      kind: "line",
      x: X,
      y: Y,
      group: "model",
      aggregation: "mean",
      facet: { by: "dataset", rows: "split", columns: 3 },
      output: { size: "double_column" },
      data: DATA,
    },
  ],
  [
    "table",
    {
      kind: "table",
      x: { field: "dataset", label: "Dataset" },
      y: Y,
      group: "model",
      aggregation: "mean",
      highlight: "best_per_row",
      uncertainty: { kind: "ci", over: "seed" },
      precision: 2,
      data: DATA,
    },
  ],
  [
    "table_plain",
    {
      kind: "table",
      x: { field: "model", label: "Model" },
      y: { field: "latency_ms", label: "Latency", unit: "ms" },
      aggregation: "mean",
      higher_is_better: false,
      highlight: "best_per_column",
      data: DATA,
    },
  ],
];

let failures = 0;
console.log(`python: ${python}\nworkdir: ${dir}\n`);

for (const [name, spec] of CASES) {
  const withOutput = {
    ...spec,
    output: { ...(spec.output as object | undefined), stem: name, formats: ["png"], dpi: 150 },
  };
  const result = translate(withOutput);
  if (result.status !== "translated") {
    console.log(`FAIL  ${name}  rejected: ${JSON.stringify(result.issues).slice(0, 200)}`);
    failures += 1;
    continue;
  }

  const file = join(dir, `${name}.py`);
  writeFileSync(file, result.code);
  try {
    const stdout = execFileSync(python, [file], { cwd: dir, stdio: "pipe", encoding: "utf8" });
    if (name === "nested_facet") {
      const report = JSON.parse(readFileSync(join(dir, `${name}.report.json`), "utf8"));
      if (report.panels.length !== 6 || !report.untested.some((item: string) => item.includes("val / Bimodal"))) {
        throw new Error("nested facet must preserve the full 2x3 grid and disclose its empty cell");
      }
    }
    const disclosure: Record<string, string> = {
      axis_break: "distances across the gap are not comparable",
      inset: "corner magnifies",
      layers: "layer labelled observations",
      repeat: "One panel per metric: accuracy, loss, latency_ms",
    };
    const expected = disclosure[name];
    if (expected) {
      const alt = stdout.split(/\r?\n/).find(line => line.startsWith("alt text:")) ?? "";
      if (!alt.includes(expected)) throw new Error(`alt text missing: ${expected}`);
      console.log(`      ${alt}`);
    }
    if (name === "axis_break") {
      if (!stdout.includes("figure checks:")) throw new Error("axis-break inspection did not run");
      if (stdout.includes("panels_disagree_on_y")) throw new Error("axis break misidentified as mismatched panels");
    }
    const produced = readdirSync(dir);
    const ok = produced.includes(`${name}.png`);
    const extras = [`${name}.md`, `${name}.tex`].filter((f) => produced.includes(f));
    console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extras.length ? `  also wrote ${extras.join(", ")}` : ""}`);
    if (!ok) failures += 1;
  } catch (error) {
    console.log(`FAIL  ${name}  ${failureDetail(error, 3)}`);
    failures += 1;
  }
}

console.log(failures === 0 ? `\nall ${CASES.length} composition cases rendered` : `\n${failures} failed`);
process.exitCode = failures === 0 ? 0 : 1;
