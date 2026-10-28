import { test } from "node:test";
import assert from "node:assert/strict";
import { translate } from "../src/translate.ts";

const base = { kind: "bar", x: {field: "condition", label: "Condition"},
  y: {field: "score", label: "Score"}, aggregation: "mean",
  uncertainty: {kind: "sem", over: "unit", display: "bar"} };
const paired = {method: "ttest", design: "paired", pair_by: "unit", pairs: [["base", "new"]]};
function codes(options: object, significance = paired): string[] {
  const result = translate({...base, significance, ...options});
  assert.equal(result.status, "translated");
  if (result.status !== "translated") throw Error("invalid fixture");
  return result.findings.filter(f => f.severity === "error").map(f => f.code);
}

test("paired design needs explicit shared summary units and a compatible test", () => {
  assert.deepEqual(codes({}), []);
  assert.ok(codes({uncertainty: undefined}).includes("significance_design_invalid"));
  assert.ok(codes({}, {...paired, pair_by: "other"}).includes("significance_design_invalid"));
  assert.ok(codes({}, {...paired, method: "mannwhitney"}).includes("significance_design_invalid"));
  assert.ok(codes({}, {...paired, design: "independent"}).includes("significance_design_invalid"));
});

test("comparison hypotheses cannot silently test a different displayed estimator or pooled cohort", () => {
  for (const aggregation of ["none", "median", "count", "sum"]) {
    assert.ok(codes({aggregation}).includes("significance_estimator_mismatch"));
  }
  assert.ok(codes({group: "cohort"}).includes("significance_group_unsupported"));
  assert.ok(codes({stacked: true}).includes("significance_group_unsupported"));
});

test("self and reversed comparisons are invalid planned test families", () => {
  assert.ok(codes({}, {...paired, pairs: [["base", "base"]]}).includes("significance_pair_invalid"));
  assert.ok(codes({}, {...paired, pairs: [["base", "new"], ["new", "base"]]}).includes("significance_pair_invalid"));
});

test("pair IDs participate in numeric/lexical role validation and known-column checks", () => {
  assert.ok(codes({data: {path: "data.csv", columns: ["condition", "score"]}}).includes("unknown_field"));
  assert.ok(codes({uncertainty: {kind: "sem", over: "score"}}, {...paired, pair_by: "score"}).includes("unsupported_identity_roles"));
});
