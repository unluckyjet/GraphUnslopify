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

test("reference and layer wording cannot change numerical anchors, filters or marks", () => {
  const input = { ...original, reference_lines: [{axis:"y",value:5,meaning:"target",label:"Target"}],
    layers:[{mark:"rule",value:3,label:"Threshold",filter:[{field:"method",op:"eq",value:"base"}]}] };
  const reference = {editable:true,role:"reference_label",path:["reference_lines",0,"label"],source:{axis:"y",value:5}};
  const updated = proposeTextEdit(input,reference,"Goal");
  assert.deepEqual(updated.spec.reference_lines,[{axis:"y",value:5,meaning:"target",label:"Goal"}]);
  assert.deepEqual(input.reference_lines[0]!.label,"Target");
  assert.throws(()=>proposeTextEdit(input,{...reference,source:{axis:"x",value:5}},"Goal"),/changed/);
  const layer = {editable:true,role:"layer_label",path:["layers",0,"label"],source:{layer:0,mark:"rule"}};
  const result = proposeTextEdit(input,layer,"Comparison");
  assert.deepEqual(result.spec.layers,[{...input.layers[0],label:"Comparison"}]);
  assert.throws(()=>proposeTextEdit(input,{...layer,source:{layer:1,mark:"rule"}},"Comparison"),/changed/);
  assert.deepEqual(result.spec.claims,input.claims);
});

test("renderer-default legends can receive display names without adding unrelated settings", () => {
  const {legend: _legend,...minimal}=original;
  const result=proposeTextEdit(minimal,{editable:true,role:"legend_entry",source:"base",path:["legend","labels",0,"text"]},"Control");
  assert.deepEqual(result.spec.legend,{labels:[{series:"base",text:"Control"}]});
  assert.deepEqual(result.spec.y,minimal.y);
  assert.equal(Object.hasOwn(minimal,"legend"),false);
});

test("metric wording edits create source records and keep renderer panel letters separate", () => {
  const input={...original,repeat:{fields:["score","loss"]}};
  const target={editable:true,role:"metric_label",path:["repeat","labels",0,"text"],source:"score",text:"(a) Score",value:"Score"};
  const result=proposeTextEdit(input,target,"Quality");
  assert.equal(result.before,"Score");
  assert.deepEqual(result.spec.repeat,{fields:["score","loss"],labels:[{field:"score",text:"Quality"}]});
  assert.deepEqual(result.spec.y,input.y);
  assert.deepEqual(result.spec.claims,input.claims);
  assert.throws(()=>proposeTextEdit(result.spec,{...target,source:"loss"},"Error"),/source changed/);
  assert.throws(()=>proposeTextEdit(input,{...target,source:"ghost"},"Error"),/source changed/);
});

test("facet display keys preserve separate literal row and column values", () => {
  const input={...original,facet:{by:"condition",rows:"phase"}};
  const target={editable:true,role:"panel_title",path:["facet","labels",0,"text"],source:{value:"__proto__",row:"A / B"},value:"A / B / __proto__",text:"(a) A / B / __proto__"};
  const result=proposeTextEdit(input,target,"Control");
  assert.deepEqual(result.spec.facet.labels,[{value:"__proto__",row:"A / B",text:"Control"}]);
  assert.equal(result.before,"A / B / __proto__");
  assert.deepEqual(result.spec.data,input.data);
  assert.throws(()=>proposeTextEdit(result.spec,{...target,source:{value:"__proto__",row:"A"}},"Other"),/source changed/);
  assert.throws(()=>proposeTextEdit(input,{...target,source:{value:"__proto__"}},"Other"),/source changed/);
});
