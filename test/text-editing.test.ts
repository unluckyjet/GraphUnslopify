import { test } from "node:test";
import assert from "node:assert/strict";
const { proposeTextEdit } = await import(new URL("../python/graphunslopify/web/text-editing.js", import.meta.url).href);

const original = {
  title: "Observed accuracy", group: "method",
  x: { field: "epoch", label: "Epoch", scale: "log" },
  y: { field: "score", label: "Accuracy", unit: "%", percent: true },
  legend: { title: "Method" }, annotate: [{ at: "last", series: "ours", text: "Final observation" }],
  claims: [{ kind: "higher", subject: "ours", reference: "base" }],
  data: { path: "actual.csv", format: "csv" },
};

test("chart text edits preserve scientific fields, units and source-attached annotations", () => {
  for (const [role, path, source] of [
    ["title", ["title"], null], ["axis_label", ["y", "label"], "score"],
    ["legend_title", ["legend", "title"], null], ["annotation", ["annotate", 0, "text"], { panel: 0, metric: "score" }],
  ]) {
    const snapshot = structuredClone(original);
    const result = proposeTextEdit(original, { role, path, source, editable: true }, "Reviewed <literal> wording");
    assert.deepEqual(original, snapshot);
    assert.deepEqual(result.spec.claims, original.claims);
    assert.deepEqual(result.spec.data, original.data);
    assert.equal(result.spec.group, original.group);
    assert.equal(result.spec.y.unit, "%");
    assert.equal(result.spec.y.percent, true);
    assert.equal(result.spec.x.scale, "log");
    assert.equal(result.spec.annotate[0].at, "last");
    assert.equal(result.spec.annotate[0].series, "ours");
    assert.equal(result.after, "Reviewed <literal> wording");
  }
});

test("prospective legend slots create full records and reject reuse for another source", () => {
  const target = { editable: true, role: "legend_entry", source: "__proto__", path: ["legend", "labels", 0, "text"] };
  const result = proposeTextEdit(original, target, "Control");
  assert.deepEqual(result.spec.legend.labels, [{ series: "__proto__", text: "Control" }]);
  assert.equal(result.before, "__proto__");
  assert.equal(Object.hasOwn(original.legend, "labels"), false);
  assert.throws(() => proposeTextEdit(result.spec, { ...target, source: "ours" }, "Treatment"), /source series changed/);
  const next = proposeTextEdit(result.spec, { ...target, source: "ours", path: ["legend", "labels", 1, "text"] }, "Treatment");
  assert.equal(next.spec.legend.labels.length, 2);
  assert.deepEqual(next.spec.claims, original.claims);
});

test("display editing refuses data, unit, prototype, stale-field and read-only paths", () => {
  for (const target of [
    { role: "axis_label", path: ["y", "unit"], source: "score" },
    { role: "axis_label", path: ["y", "label"], source: "old_score" },
    { role: "axis_label", path: ["__proto__", "label"], source: "score" },
    { role: "annotation", path: ["annotate", -1, "text"] },
    { role: "title", path: ["data", "path"] },
    { role: "derived_axis_label", path: null },
  ]) assert.throws(() => proposeTextEdit(original, { editable: true, ...target }, "New wording"));
  assert.throws(() => proposeTextEdit(original, { editable: false, role: "title", path: ["title"] }, "New wording"));
  assert.equal(({} as Record<string, unknown>).label, undefined);
  assert.throws(() => proposeTextEdit(original, { editable: true, role: "title", path: ["title"] }, " \t "));
});
