import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();

function compare(driver: string): unknown {
  const dir = mkdtempSync(join(tmpdir(), "gu-significance-"));
  const result = translate({ kind: "bar", x: { field: "model", label: "Model" },
    y: { field: "score", label: "Score" }, aggregation: "mean",
    significance: { method: "bootstrap", pairs: [["base", "ours"]] } });
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
