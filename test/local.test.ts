import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { translate } from "../src/translate.ts";
import { FIGURE_KINDS } from "../src/schema.ts";
import { TOOL_VERSION } from "../src/codegen/theme.ts";

function local(operation: string, payload: unknown = {}) {
  const result = spawnSync(process.execPath, ["python/graphunslopify/_translator.mjs"], {
    input: JSON.stringify({ operation, payload }), encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout).result;
}

test("packaged local translator emits exactly the canonical source and findings", () => {
  const spec = { kind: "line", x: { field: "x", label: "X" }, y: { field: "y", label: "Y" } };
  assert.deepEqual(local("convert", spec), translate(spec));
  assert.deepEqual(local("convert", { kind: "unknown" }), translate({ kind: "unknown" }));
  const info = local("info");
  assert.equal(info.version, TOOL_VERSION);
  assert.deepEqual(info.kinds, FIGURE_KINDS);
});

test("local schema and recipe transport expose actual supported inputs", () => {
  const schema = local("schema");
  assert.equal(schema.oneOf.length, FIGURE_KINDS.length);
  assert.equal(local("recipes").length, 25);
  const recipe = local("recipes", { name: local("recipes")[0].name });
  assert.equal(local("validate", recipe.spec).ok, true);
  assert.equal(typeof local("score", recipe.spec).cost, "number");
  assert.deepEqual(local("repair", { spec: recipe.spec }).spec, local("validate", recipe.spec).resolved);
});

test("suggestions preserve the real input path and format instead of another default file", () => {
  for (const format of ["csv", "json", "parquet"]) {
    const path = `experiments/actual.${format}`;
    const profile = { path, columns: [
      { name: "epoch", role: "ordinal", distinct: 30 },
      { name: "score", role: "measure", distinct: 50 },
    ] };
    const candidates = local("suggest", { profile });
    assert.ok(candidates.length > 0);
    for (const item of candidates) assert.deepEqual(item.spec.data, { path, format });
    assert.deepEqual(local("suggest", { profile: { ...profile, path: "data.jsonl" } }), []);
  }
});

test("Excel candidates retain the selected worksheet across native formats", () => {
  for (const suffix of ["xlsx", "xls", "xlsm"]) {
    const profile = { path: `actual.${suffix}`, sheet: "Selected results", columns: [
      { name: "epoch", role: "ordinal", distinct: 30 },
      { name: "score", role: "measure", distinct: 50, finite: 50 },
    ] };
    const candidates = local("suggest", { profile });
    assert.ok(candidates.length > 0);
    for (const candidate of candidates) assert.deepEqual(candidate.spec.data,
      { path: profile.path, format: "excel", sheet: profile.sheet });
  }
});

test("a known all-nonfinite measurement is not recommended as available data", () => {
  assert.deepEqual(local("suggest", { profile: { path: "unavailable.csv", columns: [
    { name: "epoch", role: "ordinal", distinct: 30 },
    { name: "score", role: "measure", distinct: 2, finite: 0 },
  ] } }), []);
});
