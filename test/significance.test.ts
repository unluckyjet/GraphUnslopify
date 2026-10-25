import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";
import { FigureSpec } from "../src/schema.ts";
import { verify } from "../src/verify.ts";

const python = resolvePlottingPython();

function compare(driver: string, options: { correction?: string; pairs?: string[][] } = {}): unknown {
  const dir = mkdtempSync(join(tmpdir(), "gu-significance-"));
  const result = translate({ kind: "bar", x: { field: "model", label: "Model" },
    y: { field: "score", label: "Score" }, aggregation: "mean",
    significance: { method: "bootstrap", pairs: options.pairs ?? [["base", "ours"]],
      ...(options.correction ? { correction: options.correction } : {}) } });
  assert.equal(result.status, "translated");
  writeFileSync(join(dir, "figure.py"), result.code);
  writeFileSync(join(dir, "driver.py"), "import figure, json\n" + driver);
  return JSON.parse(execFileSync(python!, ["driver.py"], { cwd: dir, encoding: "utf8" }));
}

test("the historical bootstrap significance method matches an exact 70-partition answer", { skip: !python }, () => {
  // Independent enumeration: 32 of 70 group assignments have |mean gap| >= 1.
  const value = compare("print(json.dumps(figure.compare([1,2,3,4], [2,3,4,5])))");
  assert.equal(value, 32 / 70);
});

test("Holm is the default and opting out warns only for multiple comparisons", () => {
  const base = { kind: "bar", x: { field: "method", label: "Method" },
    y: { field: "score", label: "Score" }, aggregation: "mean" };
  for (const correction of [undefined, "none", "holm"]) {
    const parsed = FigureSpec.parse({ ...base,
      significance: { method: "bootstrap", pairs: [["a", "b"], ["a", "c"]],
        ...(correction ? { correction } : {}) } });
    assert.ok(parsed.kind === "bar");
    assert.equal(parsed.significance!.correction, correction ?? "holm");
    const codes = verify(parsed).map(f => f.code);
    assert.equal(codes.includes("uncorrected_multiple_comparisons"), correction === "none");
  }
  const single = FigureSpec.parse({ ...base,
    significance: { method: "bootstrap", pairs: [["a", "b"]], correction: "none" } });
  assert.ok(!verify(single).some(f => f.code === "uncorrected_multiple_comparisons"));
});

test("brackets use adjusted probabilities and print the raw family", { skip: !python }, () => {
  const driver = [
    "import pandas as pd, io, contextlib",
    "class Axes:",
    "    def __init__(self): self.marks = []",
    "    def plot(self, *args, **kwargs): pass",
    "    def text(self, x, y, mark, **kwargs): self.marks.append(mark)",
    "values = iter([0.02, 0.03, 0.04])",
    "figure.compare = lambda left, right: next(values)",
    "frame = pd.DataFrame({'model': ['base','ours','other'], 'score': [1,1,1]})",
    "ax, output = Axes(), io.StringIO()",
    "with contextlib.redirect_stdout(output):",
    "    figure.mark_significance(ax, frame, ['base','ours','other'], [0,1,2])",
    "print(json.dumps({'marks': ax.marks, 'output': output.getvalue()}))",
  ].join("\n");
  const pairs = [["base", "ours"], ["base", "other"], ["ours", "other"]];
  const holm = compare(driver, { pairs }) as { marks: string[]; output: string };
  assert.deepEqual(holm.marks, ["n.s.", "n.s.", "n.s."]);
  assert.match(holm.output, /p = 0.02, holm-adjusted p = 0.06/);
  assert.match(holm.output, /3 comparisons/);
  const raw = compare(driver, { pairs, correction: "none" }) as typeof holm;
  assert.deepEqual(raw.marks, ["*", "*", "*"]);
  assert.match(raw.output, /no correction/);
});

test("a real null figure reports four non-significant comparisons", { skip: !python }, () => {
  const driver = [
    "import io, contextlib",
    "from pathlib import Path",
    "rows = ['model,score'] + [f'{name},{value}' for name in ['a','b','c','d','e'] for value in [1,2,3,4]]",
    "Path('results.csv').write_text('\\n'.join(rows) + '\\n')",
    "figure.FORMATS, figure.DPI = ['png'], 72",
    "output = io.StringIO()",
    "with contextlib.redirect_stdout(output): figure.main()",
    "print(json.dumps(output.getvalue()))",
  ].join("\n");
  const pairs = [["a", "b"], ["a", "c"], ["a", "d"], ["a", "e"]];
  const output = compare(driver, { pairs }) as string;
  assert.equal((output.match(/\(n\.s\., 4 comparisons\)/g) ?? []).length, 4);
  assert.match(output, /p = 1, holm-adjusted p = 1/);
  const raw = compare(driver, { pairs, correction: "none" }) as string;
  assert.equal((raw.match(/p = 1, no correction/g) ?? []).length, 4);
});

test("small separated samples retain the exact nonzero tail probability", { skip: !python }, () => {
  // Only the observed assignment and its reverse out of C(8,4) are as extreme.
  const value = compare("print(json.dumps(figure.compare([1,2,3,4], [5,6,7,8])))");
  assert.equal(value, 2 / 70);
});

test("equal sample means give a p-value of one", { skip: !python }, () => {
  assert.equal(compare("print(json.dumps(figure.compare([1,2,3,4], [1,2,3,4])))"), 1);
});

test("unequal sample sizes use absolute mean-gap tails in either group order", { skip: !python }, () => {
  // Exactly one of C(5,2)=10 assignments has an absolute mean gap of one.
  assert.equal(compare("print(json.dumps(figure.compare([0,0], [1,1,1])))"), 1 / 10);
  assert.equal(compare("print(json.dumps(figure.compare([1,1,1], [0,0])))"), 1 / 10);
});

test("Monte Carlo permutations are reproducible, nonzero, and nondegenerate", { skip: !python }, () => {
  const values = compare([
    "left = list(range(10))",
    "right = [v + 3 for v in left]",
    "print(json.dumps([figure.compare(left, right), figure.compare(left, right)]))",
  ].join("\n")) as number[];
  assert.equal(values[0], values[1]);
  assert.ok(values[0]! > 0.01 && values[0]! < 0.1, JSON.stringify(values));
  assert.equal(compare("print(json.dumps(figure.compare(list(range(10)), list(range(100,110)))))"), 1 / 2001);
});
