import { test } from "node:test";
import assert from "node:assert/strict";
import { translate } from "../src/translate.ts";

const base = { kind: "line", x: { field: "x", label: "X" }, y: { field: "y", label: "Y" }, output: { interactive: true } };
test("interactive export explicitly refuses analyses it cannot reproduce", () => {
  for (const extra of [ { kind: "box" }, { kind: "table" }, { kind: "ecdf" },
    { kind: "scatter", trendline: "linear" }, { facet: { by: "dataset" } },
    { repeat: { fields: ["a", "b"] } }, { layers: [{ mark: "rule", value: 0 }] },
    { axis_break: { from: 1, to: 2 } }, { y: { field: "y", label: "Y", scale: "symlog" } },
    { kind: "bar", stacked: true }, { reference_lines: [{ axis: "y", value: 0, meaning: "other" }] } ]) {
    const result = translate({ ...base, ...extra });
    assert.ok(result.status === "translated" && !result.ok, JSON.stringify(result));
    assert.ok(result.findings.some(f => f.code === "interactive_not_supported"));
    assert.ok(!result.code.includes("figure.to_html("), "must not emit a misleading fallback");
  }
});
