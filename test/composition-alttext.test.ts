import { test } from "node:test";
import assert from "node:assert/strict";
import { FigureSpec } from "../src/schema.ts";
import { encodingSentence } from "../src/alttext.ts";

const plain = { kind: "line", x: { field: "epoch", label: "Epoch" },
  y: { field: "score", label: "Score" } };

function sentence(extra: Record<string, unknown> = {}) {
  return encodingSentence(FigureSpec.parse({ ...plain, ...extra }));
}

test("a plain figure keeps its exact pre-change encoding sentence", () => {
  assert.equal(sentence(), "Line chart of Score against Epoch.");
  for (const absent of ["cut between", "inset", "layer labelled", "panel per metric"]) {
    assert.ok(!sentence().includes(absent));
  }
});

test("cut-axis descriptions disclose bounds and incomparable distances", () => {
  assert.match(sentence({ axis_break: { axis: "y", from: 30, to: 60 } }),
    /vertical axis is cut between 30 and 60, so distances across the gap are not comparable/);
});

test("insets disclose magnified limits and their corner", () => {
  assert.match(sentence({ inset: { x: [1, 3], y: [20, 40], corner: "lower_right" } }),
    /lower right corner magnifies x from 1 to 3 and y from 20 to 40/);
});

test("layers disclose their mark and label without inventing unlabeled entries", () => {
  const description = sentence({ layers: [{ mark: "scatter", label: "Observed values" }, { mark: "rug" }] });
  assert.match(description, /scatter layer labelled Observed values/);
  assert.ok(!description.includes("rug layer"));
});

test("repeated metrics are listed as distinct panels", () => {
  assert.match(sentence({ repeat: { fields: ["accuracy", "loss"] } }), /One panel per metric: accuracy, loss/);
});
