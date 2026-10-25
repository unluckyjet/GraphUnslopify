import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();
const base = { kind: "line", x: { field: "epoch", label: "Epoch" },
  y: { field: "score", label: "Score" }, group: "model", aggregation: "mean" };
const duplicates = "epoch,score,model,seed\n" + Array(10).fill("1,0,a,0").join("\n") + "\n1,10,a,1\n";

type Measurement = { mean: number; low: number | null; high: number | null;
  counts: { sample_sizes: number[]; unit_observations?: number; missing_unit_ids?: number };
  output: string; input_rows: number };

function measure(csv: string, options: Record<string, unknown> = {}): Measurement {
  const dir = mkdtempSync(join(tmpdir(), "gu-units-"));
  const result = translate({ ...base, uncertainty: { kind: "sem", over: "seed" }, ...options });
  assert.ok(result.status === "translated");
  assert.ok(result.ok, JSON.stringify(result.findings));
  writeFileSync(join(dir, "results.csv"), csv);
  writeFileSync(join(dir, "figure.py"), result.code);
  writeFileSync(join(dir, "driver.py"), [
    "import figure, json, numpy as np, io, contextlib",
    "frame = figure.prepare(figure.load())",
    "output = io.StringIO()",
    "with contextlib.redirect_stdout(output): figure.report_counts(frame)",
    "row = figure.summarise(frame).iloc[0]",
    "def nullable(value): return float(value) if np.isfinite(value) else None",
    "print(json.dumps({'mean': float(row['score']), 'low': nullable(row['_low']), 'high': nullable(row['_high']),",
    " 'counts': figure.ROW_COUNTS, 'output': output.getvalue(), 'input_rows': len(figure.summary_input(frame, 'score'))}))",
  ].join("\n"));
  return JSON.parse(execFileSync(python!, ["driver.py"], { cwd: dir, encoding: "utf8", stdio: "pipe" }));
}

test("each named unit has equal weight across all five interval kinds", { skip: !python }, () => {
  const expected: Record<string, number[]> = { sem: [0, 10], range: [0, 10], iqr: [2.5, 7.5],
    ci: [0, 10], std: [5 - Math.sqrt(50), 5 + Math.sqrt(50)] };
  for (const [kind, bounds] of Object.entries(expected)) {
    const result = measure(duplicates, { uncertainty: { kind, over: "seed" } });
    assert.equal(result.mean, 5, kind);
    assert.ok(Math.abs(result.low! - bounds[0]!) < 1e-9, kind);
    assert.ok(Math.abs(result.high! - bounds[1]!) < 1e-9, kind);
    assert.deepEqual(result.counts.sample_sizes, [2]);
    assert.equal(result.counts.unit_observations, 2);
    assert.match(result.output, /n = 2 per point \(unit IDs: seed\)/);
  }
});

test("technical repeats from a single unit never invent an interval", { skip: !python }, () => {
  const result = measure("epoch,score,model,seed\n1,1,a,0\n1,2,a,0\n1,3,a,0\n");
  assert.equal(result.mean, 2);
  assert.equal(result.low, null);
  assert.equal(result.high, null);
  assert.deepEqual(result.counts.sample_sizes, [1]);
});

test("median summaries take the median within each unit before comparing units", { skip: !python }, () => {
  const result = measure("epoch,score,model,seed\n1,0,a,0\n1,0,a,0\n1,0,a,0\n1,10,a,0\n1,8,a,1\n",
    { aggregation: "median", uncertainty: { kind: "iqr", over: "seed" } });
  assert.equal(result.mean, 4);
  assert.equal(result.low, 2);
  assert.equal(result.high, 6);
});

test("absent unit identifiers are disclosed and excluded from unit statistics", { skip: !python }, () => {
  const result = measure("epoch,score,model,seed\n1,100,a,\n1,0,a,0\n1,10,a,1\n");
  assert.equal(result.mean, 5);
  assert.equal(result.counts.missing_unit_ids, 1);
  assert.equal(result.counts.unit_observations, 2);
  assert.match(result.output, /1 rows have no seed identifier/);
});

test("omitting a unit identifier retains the explicit row-level assumption", { skip: !python }, () => {
  const result = measure(duplicates, { uncertainty: { kind: "sem" } });
  assert.ok(Math.abs(result.mean - 10 / 11) < 1e-9);
  assert.deepEqual(result.counts.sample_sizes, [11]);
});

test("non-finite measurements cannot contaminate numeric summaries", { skip: !python }, () => {
  const result = measure("epoch,score,model\n1,inf,a\n1,1,a\n1,3,a\n", { uncertainty: { kind: "sem" } });
  assert.equal(result.mean, 2);
  assert.equal(result.low, 1);
  assert.equal(result.high, 3);
  assert.deepEqual(result.counts.sample_sizes, [2]);
});

test("unit identifiers stay separate across panels", { skip: !python }, () => {
  const result = measure("epoch,score,model,seed,dataset\n1,0,a,0,A\n1,10,a,1,A\n1,100,a,0,B\n1,110,a,1,B\n",
    { facet: { by: "dataset" } });
  assert.equal(result.input_rows, 4);
  assert.deepEqual(result.counts.sample_sizes, [2, 2]);
});

test("significance tests receive the same unit summaries as the plotted intervals", { skip: !python }, () => {
  const dir = mkdtempSync(join(tmpdir(), "gu-unit-test-"));
  const result = translate({ ...base, kind: "bar", group: undefined,
    x: { field: "model", label: "Model" }, uncertainty: { kind: "sem", over: "seed", display: "bar" },
    significance: { method: "bootstrap", pairs: [["base", "ours"]] },
    output: { formats: ["png"], dpi: 100 } });
  assert.ok(result.status === "translated" && result.ok);
  writeFileSync(join(dir, "figure.py"), result.code);
  writeFileSync(join(dir, "results.csv"), duplicates.replaceAll(",a,", ",base,") + "1,3,ours,0\n1,7,ours,1\n");
  writeFileSync(join(dir, "driver.py"), [
    "import figure, json, io, contextlib",
    "calls = []",
    "def compare(left, right):",
    "    calls.append([len(left), len(right), float(left.mean()), float(right.mean())])",
    "    return 1.0",
    "figure.compare = compare",
    "with contextlib.redirect_stdout(io.StringIO()): figure.main()",
    "print(json.dumps(calls))",
  ].join("\n"));
  const calls = JSON.parse(execFileSync(python!, ["driver.py"], { cwd: dir, encoding: "utf8", stdio: "pipe" }));
  assert.deepEqual(calls, [[2, 2, 5, 5]]);
});

test("missing or entirely absent unit identifiers stop the calculation clearly", { skip: !python }, () => {
  assert.throws(() => measure("epoch,score,model,seed\n1,1,a,\n1,2,a,\n"), /no usable replicate identifiers/);
  assert.throws(() => measure("epoch,score,model\n1,1,a\n1,2,a\n"), /replicate identifier column seed is missing/);
});

test("a replicate key cannot be a grouping key and intervals require mean or median", () => {
  for (const over of ["epoch", "model"]) {
    const result = translate({ ...base, uncertainty: { kind: "sem", over } });
    assert.ok(result.status === "translated");
    assert.ok(result.findings.some(f => f.code === "replicate_matches_grouping_key"));
  }
  for (const aggregation of ["sum", "count"]) {
    const result = translate({ ...base, kind: "bar", aggregation, uncertainty: { kind: "sem" } });
    assert.ok(result.status === "translated");
    assert.ok(result.findings.some(f => f.code === "uncertainty_aggregation_unsupported"));
  }
});
