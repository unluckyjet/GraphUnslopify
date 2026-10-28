import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();
const base = {
  kind: "table",
  x: { field: "dataset", label: "Dataset" },
  y: { field: "score", label: "Score" },
  group: "model",
  highlight: "best_per_row",
  data: { path: "table.csv" },
  output: { stem: "table", formats: ["png"], dpi: 100, size: "double_column" },
};

function run(options: Record<string, unknown>, csv: string, driver?: string, expectedExit = 0) {
  const dir = mkdtempSync(join(tmpdir(), "gu-table-"));
  const result = translate({ ...base, ...options });
  assert.equal(result.status, "translated");
  assert.ok(result.ok, JSON.stringify(result.findings));
  writeFileSync(join(dir, "table.csv"), csv);
  writeFileSync(join(dir, "figure.py"), result.code);
  if (driver) writeFileSync(join(dir, "driver.py"), driver);
  const completed = spawnSync(python!, [driver ? "driver.py" : "figure.py"], {
    cwd: dir, encoding: "utf8", stdio: "pipe",
  });
  assert.equal(completed.status, expectedExit, completed.stderr || completed.stdout);
  return { stdout: completed.stdout, read: (name: string) => readFileSync(join(dir, name), "utf8") };
}

test("a table without uncertainty retains scalar cells and adds metric context", { skip: !python }, () => {
  const result = run({}, "dataset,score,model\nA,1,base\nA,3,ours\nB,4,base\nB,2,ours\n");
  const expected = readFileSync(new URL("fixtures/table-plain-expected.md", import.meta.url), "utf8");
  assert.equal(result.read("table.md"), expected);
});

test("table intervals appear in markdown and LaTeX and overlap is not called equivalence", { skip: !python }, () => {
  const result = run({ uncertainty: { kind: "range" } },
    "dataset,score,model\nA,2,base\nA,6,base\nA,3,ours\nA,7,ours\n");
  assert.match(result.read("table.md"), /\*\*4\.00 \[2\.00, 6\.00\]\*\*/);
  assert.match(result.read("table.md"), /\*\*5\.00 \[3\.00, 7\.00\]\*\*/);
  assert.match(result.read("table.tex"), /4\.00 \[2\.00, 6\.00\]/);
  assert.match(result.stdout, /intervals overlap; no uniquely separated leader/);
  assert.match(result.stdout, /Overlap does not establish equivalence/);
});

test("a separated table leader is the only highlighted cell", { skip: !python }, () => {
  const result = run({ uncertainty: { kind: "range" } },
    "dataset,score,model\nA,1,base\nA,2,base\nA,5,ours\nA,6,ours\n");
  assert.equal((result.read("table.md").match(/\*\*/g) ?? []).length, 2);
  assert.match(result.read("table.md"), /\*\*5\.50 \[5\.00, 6\.00\]\*\*/);
  assert.match(result.stdout, /ours has an interval separated/);
});

test("column highlighting supports lower-is-better intervals", { skip: !python }, () => {
  const result = run({ group: undefined, highlight: "best_per_column", higher_is_better: false,
    uncertainty: { kind: "range" } }, "dataset,score\nA,1\nA,2\nB,5\nB,6\n");
  assert.match(result.read("table.md"), /\*\*1\.50 \[1\.00, 2\.00\]\*\*/);
  assert.equal((result.read("table.md").match(/\*\*/g) ?? []).length, 2);
});

test("a missing interval never silently certifies a table winner", { skip: !python }, () => {
  const result = run({ uncertainty: { kind: "range" } },
    "dataset,score,model\nA,1,base\nA,5,ours\nA,6,ours\n", undefined, 2);
  assert.match(result.read("table.md"), /1\.00 \[unavailable\]/);
  assert.ok(!result.read("table.md").includes("**"));
  assert.match(result.stdout, /insufficient observations/);
  const report = JSON.parse(result.read("table.report.json"));
  assert.equal(report.status, "incomplete");
  assert.equal(report.policy.strict, true);
});

test("all table uncertainty kinds share the numeric summarizer", { skip: !python }, () => {
  const driver = [
    "import figure, json",
    "table, low, high = figure.build_table(figure.load())",
    'print(json.dumps([float(table.iloc[0, 0]), float(low.iloc[0, 0]), float(high.iloc[0, 0])]))',
  ].join("\n");
  const expected: Record<string, number[]> = {
    range: [4, 2, 6], iqr: [4, 3, 5], sem: [4, 2, 6], ci: [4, 2, 6],
    std: [4, 4 - Math.sqrt(8), 4 + Math.sqrt(8)],
  };
  for (const [kind, values] of Object.entries(expected)) {
    const result = run({ uncertainty: { kind } }, "dataset,score,model\nA,2,base\nA,6,base\n", driver);
    const actual: number[] = JSON.parse(result.stdout);
    actual.forEach((value, i) => assert.ok(Math.abs(value - values[i]!) < 1e-9, `${kind}: ${actual}`));
  }
});

test("rendered interval text fits inside its table cells", { skip: !python }, () => {
  const driver = [
    "import figure",
    "table, low, high = figure.build_table(figure.load())",
    "fig = figure.render_table_image(table, figure.mark_winners(table, low, high), low, high)",
    "from matplotlib.backends.backend_agg import FigureCanvasAgg",
    "FigureCanvasAgg(fig)",
    "fig.canvas.draw()",
    "renderer = fig.canvas.get_renderer()",
    "for cell in next(iter(fig.axes[0].tables)).get_celld().values():",
    "    text = cell.get_text().get_window_extent(renderer)",
    "    box = cell.get_window_extent(renderer)",
    '    assert text.width <= box.width, cell.get_text().get_text()',
    'print("text fits")',
  ].join("\n");
  const result = run({ uncertainty: { kind: "range" } },
    "dataset,score,model\nImageNet,52.111,base\nImageNet,55.222,base\nImageNet,61.333,ours\nImageNet,65.444,ours\n", driver);
  assert.match(result.stdout, /text fits/);
});
