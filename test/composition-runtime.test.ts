import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();
const base = { kind: "line", x: { field: "epoch", label: "Epoch" },
  y: { field: "score", label: "Score" }, group: "model", aggregation: "mean", legend: { show: false } };
const rows = ["epoch,score,loss,model,seed,dataset,split"];
for (const [r, split] of ["val", "test"].entries()) for (const [c, dataset] of ["A", "B"].entries()) {
  for (const [m, model] of ["a", "b"].entries()) for (const epoch of [1, 2]) for (const seed of [0, 1])
    rows.push(`${epoch},${r * 100 + c * 10 + m * 2 + epoch + seed},${1 / (epoch + 1)},${model},${seed},${dataset},${split}`);
}
const csv = rows.join("\n") + "\n";
function run(data: string, options: Record<string, unknown> = {}) {
  const dir = mkdtempSync(join(tmpdir(), "gu-compose-contract-"));
  const result = translate({ ...base, ...options, output: { stem: "figure", formats: ["png"], dpi: 100, size: "double_column" } });
  assert.ok(result.status === "translated" && result.ok, JSON.stringify(result));
  writeFileSync(join(dir, "figure.py"), result.code);
  writeFileSync(join(dir, "results.csv"), data);
  writeFileSync(join(dir, "driver.py"), [
    "import figure as m, json", "original = m.check", "def capture(fig):",
    "    axes = [a for a in fig.axes if a.get_visible()]", "    first = axes[0]",
    "    measured = {'shape': [first.get_subplotspec().get_gridspec().nrows, first.get_subplotspec().get_gridspec().ncols],",
    "        'x_shared': len(axes)>1 and first.get_shared_x_axes().joined(first, axes[1]),",
    "        'y_shared': len(axes)>1 and first.get_shared_y_axes().joined(first, axes[1]),",
    "        'line_counts': [len(a.lines) for a in axes],",
    "        'first_values': [float(a.lines[0].get_ydata()[0]) if a.lines else None for a in axes],",
    "        'collections': [len(c.get_offsets()) for a in axes for c in a.collections]}",
    "    with open('geometry.json', 'w') as h: json.dump(measured,h)", "    return original(fig)",
    "m.check = capture", "raise SystemExit(m.run_cli(['--strict','--json']))",
  ].join("\n"));
  const completed = spawnSync(python!, ["driver.py"], { cwd: dir, encoding: "utf8" });
  const report = JSON.parse(completed.stdout);
  let geometry;
  try { geometry = JSON.parse(readFileSync(join(dir, "geometry.json"), "utf8")); } catch { geometry = null; }
  return { ...completed, report, geometry };
}

test("nested facets draw the full row/column grid and keep repeat counts separate", { skip: !python }, () => {
  const result = run(csv, { facet: { by: "dataset", rows: "split", columns: 2 }, uncertainty: { kind: "sem", over: "seed" } });
  assert.equal(result.status, 0, JSON.stringify(result.report.findings));
  assert.deepEqual(result.geometry.shape, [2, 2]);
  assert.deepEqual(result.geometry.first_values, [1.5, 11.5, 101.5, 111.5]);
  assert.deepEqual(result.report.panels.map((p: { name: string }) => p.name), ["val / A", "val / B", "test / A", "test / B"]);
  assert.equal(result.report.data.counts.sample_sizes.length, 16);
  assert.ok(result.report.data.counts.sample_sizes.every((n: number) => n === 2));
});

test("an absent grid cell stays in place and is explicitly incomplete", { skip: !python }, () => {
  const result = run(rows.filter(r => !r.endsWith(",B,test")).join("\n") + "\n", { facet: { by: "dataset", rows: "split" } });
  assert.equal(result.status, 2);
  assert.deepEqual(result.geometry.shape, [2, 2]);
  assert.equal(result.geometry.first_values[3], null);
  assert.equal(result.report.status, "incomplete");
  assert.match(result.report.alt_text, /Panel test \/ B: No data/);
});

test("repeat uses its declared sharing flags rather than absent facet defaults", { skip: !python }, () => {
  const data = rows.filter(r => r.endsWith(",A,val") || r.startsWith("epoch,")).join("\n") + "\n";
  for (const [x, y] of [[true, false], [false, true]]) {
    const result = run(data, { repeat: { fields: ["score", "loss"], share_x: x, share_y: y } });
    assert.equal(result.geometry.x_shared, x);
    assert.equal(result.geometry.y_shared, y);
  }
});

test("wide columns become distinct series with valid raw-column references and recoverable specs", { skip: !python }, () => {
  const spec = { group: undefined, y: { field: "value", label: "Score" },
    series_from_columns: { fields: ["a", "b"] }, series_order: ["a", "b"],
    data: { path: "results.csv", columns: ["epoch", "seed", "a", "b"] },
    uncertainty: { kind: "sem", over: "seed" }, claims: [{ kind: "beats_everywhere", subject: "b", reference: "a" }] };
  const result = run("epoch,seed,a,b\n1,0,1,5\n1,1,2,6\n2,0,2,6\n2,1,3,7\n", spec);
  assert.equal(result.status, 0, JSON.stringify(result.report.findings));
  assert.equal(result.report.claims[0].verdict, "holds");
  assert.deepEqual(result.geometry.line_counts, [2]);
  assert.equal(result.report.spec.group, undefined);
  assert.equal(translate(result.report.spec).status, "translated");
  const roundtrip = translate(result.report.spec);
  assert.ok(roundtrip.status === "translated" && roundtrip.ok);
  assert.deepEqual(result.report.data.counts.sample_sizes, [2, 2, 2, 2]);
});

test("sequential layer filters use the current subset without index re-alignment warnings", { skip: !python }, () => {
  const data = rows.filter(r => r.endsWith(",A,val") || r.startsWith("epoch,")).join("\n") + "\n";
  const result = run(data, { layers: [{ mark: "scatter", filter: [{ field: "model", op: "eq", value: "a" }, { field: "epoch", op: "gte", value: 2 }] }] });
  assert.deepEqual(result.geometry.collections, [2]);
  assert.ok(!result.stderr.includes("reindexed"));
});

test("unsupported or contradictory compositions produce actionable static errors", () => {
  const cases: [Record<string, unknown>, string][] = [
    [{ kind: "table", axis_break: { from: 1, to: 2 } }, "table_composition_unsupported"],
    [{ axis_break: { axis: "x", from: 1, to: 2 } }, "x_break_unsupported"],
    [{ axis_break: { from: 2, to: 1 } }, "invalid_axis_break"],
    [{ facet: { by: "dataset" }, axis_break: { from: 1, to: 2 } }, "axis_break_composition_unsupported"],
    [{ facet: { by: "dataset" }, repeat: { fields: ["score", "loss"] } }, "facet_repeat_conflict"],
    [{ facet: { by: "dataset", rows: "dataset" } }, "facet_keys_identical"],
    [{ repeat: { fields: ["score", "score"] } }, "unsupported_repeat"],
    [{ layers: [{ mark: "band" }] }, "incomplete_layer"],
    [{ layers: [{ mark: "rule" }] }, "incomplete_layer"],
    [{ series_from_columns: { fields: ["a", "b"] }, group: undefined }, "invalid_series_reshape"],
  ];
  for (const [extra, code] of cases) {
    const result = translate({ ...base, ...extra });
    assert.ok(result.status === "translated" && !result.ok);
    assert.ok(result.findings.some(f => f.code === code), code);
  }
});

test("field references validate row keys, repeated metrics and layer fields before execution", () => {
  for (const extra of [{ facet: { by: "dataset", rows: "absent" } }, { repeat: { fields: ["score", "absent"] } },
    { layers: [{ mark: "band", y: "score", y2: "absent" }] }]) {
    const result = translate({ ...base, data: { columns: ["epoch", "score", "model", "dataset"] }, ...extra });
    assert.ok(result.status === "translated" && result.findings.some(f => f.code === "unknown_field"));
  }
});
