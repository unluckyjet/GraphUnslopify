import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { verify } from "../src/verify.ts";
import { FigureSpec } from "../src/schema.ts";
import { z } from "zod";
import { resolvePython } from "../scripts/python.ts";

const line = {
  kind: "line",
  x: { field: "epoch", label: "Training epoch" },
  y: { field: "accuracy", label: "Test accuracy", unit: "%" },
  group: "model",
};

function translated(spec: unknown) {
  const result = translate(spec);
  assert.equal(result.status, "translated");
  return result;
}

function codes(spec: unknown): string[] {
  return verify(FigureSpec.parse(spec)).map((f) => f.code);
}

test("a minimal line spec produces a script and no complaints", () => {
  const result = translated(line);
  assert.equal(result.ok, true);
  assert.deepEqual(result.findings, []);
  assert.equal(result.filename, "figure.py");
  assert.match(result.code, /ax\.plot\(/);
  assert.match(result.code, /Test accuracy \(%\)/);
});

test("an unknown chart kind is rejected", () => {
  const result = translate({ ...line, kind: "sankey" });
  assert.equal(result.status, "invalid_spec");
});

test("a missing axis label is rejected with a path", () => {
  const result = translate({ ...line, y: { field: "accuracy" } });
  assert.equal(result.status, "invalid_spec");
  assert.ok(result.issues.some((i) => i.path === "y.label"));
});

test("a JSON-encoded spec is parsed rather than rejected", () => {
  assert.equal(translate(JSON.stringify(line)).status, "translated");
});

test("defaults fill in without being stated", () => {
  const spec = FigureSpec.parse(line);
  assert.equal(spec.output.dpi, 600);
  assert.equal(spec.style.preset, "paper");
  assert.equal(spec.data.path, "results.csv");
  assert.equal(spec.legend.show, true);
});

test("a log axis reaching zero is an error", () => {
  const found = codes({ ...line, y: { ...line.y, scale: "log", limits: [0, 100] } });
  assert.ok(found.includes("log_scale_nonpositive_limit"));
});

test("inverted limits are an error", () => {
  assert.ok(codes({ ...line, x: { ...line.x, limits: [10, 1] } }).includes("axis_limits_inverted"));
});

test("a field absent from data.columns is an error", () => {
  const found = codes({ ...line, data: { columns: ["epoch", "accuracy"] } });
  assert.ok(found.includes("unknown_field"));
});

test("emphasis without a group is an error", () => {
  const { group, ...ungrouped } = line;
  const found = codes({ ...ungrouped, emphasis: { series: "ours" } });
  assert.ok(found.includes("emphasis_without_group"));
});

test("emphasis naming a series outside series_order is an error", () => {
  const found = codes({ ...line, series_order: ["a", "b"], emphasis: { series: "c" } });
  assert.ok(found.includes("emphasis_series_unknown"));
});

test("a bar baselined at zero on a log axis is an error", () => {
  const found = codes({
    ...line,
    kind: "bar",
    aggregation: "mean",
    y: { ...line.y, scale: "log" },
  });
  assert.ok(found.includes("log_bar_baseline"));
});

test("an unaggregated bar chart warns about overplotting", () => {
  assert.ok(codes({ ...line, kind: "bar" }).includes("unaggregated_bar"));
});

test("a legend with nothing to list warns", () => {
  const { group, ...ungrouped } = line;
  assert.ok(codes(ungrouped).includes("legend_without_group"));
});

test("errors set ok false but still return a script", () => {
  const result = translated({ ...line, x: { ...line.x, limits: [10, 1] } });
  assert.equal(result.ok, false);
  assert.ok(result.code.length > 0);
});

test("an unaggregated line chart carries a runtime duplicate check", () => {
  const result = translated(line);
  assert.match(result.code, /def warn_duplicates/);
  assert.match(result.code, /warn_duplicates\(df\)/);
});

test("an aggregated line chart groups instead of warning", () => {
  const result = translated({ ...line, aggregation: "mean" });
  assert.ok(!result.code.includes("warn_duplicates"));
  assert.match(result.code, /groupby\(keys, as_index=False, sort=False, observed=True\)\[Y_FIELD\]/);
  assert.match(result.code, /summary = grouped\.mean\(\)/);
});

test("recessive series keep their own colour instead of collapsing to one grey", () => {
  const result = translated({
    ...line,
    series_order: ["a", "b", "c", "d"],
    emphasis: { series: "d" },
  });
  assert.match(result.code, /RECEDED_ALPHA = 0\.4/);
  assert.match(result.code, /"colour": colour, "width": [\d.]+, "alpha": RECEDED_ALPHA/);
  assert.ok(!result.code.includes("MUTED"));
  assert.match(result.code, /alpha=style\["alpha"\]/);
});

test("aggregation keeps the file's category order", () => {
  const result = translated({ ...line, kind: "bar", aggregation: "mean" });
  assert.match(result.code, /groupby\(keys, as_index=False, sort=False, observed=True\)/);
});

test("a horizontal bar reads top to bottom", () => {
  const horizontal = translated({
    ...line,
    kind: "bar",
    aggregation: "mean",
    orientation: "horizontal",
  });
  assert.match(horizontal.code, /ax\.invert_yaxis\(\)/);

  const vertical = translated({ ...line, kind: "bar", aggregation: "mean" });
  assert.ok(!vertical.code.includes("invert_yaxis"));
});

test("a second visual channel appears once colour stops being enough", () => {
  const few = translated({ ...line, series_order: ["a", "b"] });
  const many = translated({ ...line, series_order: ["a", "b", "c", "d", "e", "f"] });

  assert.match(few.code, /SECOND_CHANNEL_THRESHOLD = 1/);
  assert.match(few.code, /LINE_STYLES = \["-", "--", "-\.", ":"\]/);
  for (const code of [few.code, many.code]) {
    assert.match(code, /if total <= SECOND_CHANNEL_THRESHOLD:/);
    assert.match(code, /channel = LINE_STYLES\[index % len\(LINE_STYLES\)\]/);
    assert.match(code, /linestyle=style\["linestyle"\]/);
  }
});

test("bars reach for hatching rather than line styles", () => {
  const result = translated({ ...line, kind: "bar", aggregation: "mean" });
  assert.match(result.code, /HATCHES = /);
  assert.match(result.code, /hatch=style\["hatch"\]/);
  assert.match(result.code, /edgecolor="white"/);
  assert.ok(!result.code.includes("LINE_STYLES"));
});

test("scatter reaches for markers rather than line styles", () => {
  const result = translated({ ...line, kind: "scatter" });
  assert.match(result.code, /MARKERS = /);
  assert.match(result.code, /marker=style\["marker"\]/);
  assert.ok(!result.code.includes("LINE_STYLES"));
});

test("the script carries its own provenance", () => {
  const result = translated(line);
  assert.match(result.code, /tool version \d+\.\d+\.\d+, spec sha256:[0-9a-f]{16}/);
  assert.match(result.code, /SPEC_HASH = "[0-9a-f]{16}"/);
  assert.match(result.code, /SPEC_JSON = /);
  assert.match(result.code, /DISCLOSURE = \(/);
  assert.match(result.code, /metadata=meta/);
  assert.match(result.code, /DATA_HASH = /);
});

test("the spec hash changes with the spec and not otherwise", () => {
  const hashOf = (spec: unknown) => translated(spec).code.match(/SPEC_HASH = "([0-9a-f]+)"/)?.[1];
  assert.equal(hashOf(line), hashOf(line));
  assert.notEqual(hashOf(line), hashOf({ ...line, title: "different" }));
});

test("the render-time checker is called but never required", () => {
  const result = translated(line);
  assert.match(result.code, /from graphunslopify import inspect_figure/);
  assert.match(result.code, /except ImportError:/);
  assert.match(result.code, /skipping figure checks/);
  assert.match(result.code, /TARGET_WIDTH_IN = 3\.4/);
  assert.match(result.code, /target_width_in=TARGET_WIDTH_IN/);
  assert.match(result.code, /check\(fig\)/);
});

test("a double column figure tells the checker its real target width", () => {
  const result = translated({ ...line, output: { size: "double_column" } });
  assert.match(result.code, /TARGET_WIDTH_IN = 7/);
});

test("the emphasised series stays solid while the rest are dashed", () => {
  const result = translated({
    ...line,
    series_order: ["a", "b", "c", "d"],
    emphasis: { series: "d" },
  });
  assert.ok(result.code.includes("if name == EMPHASIS:"));
  assert.ok(result.code.includes('channel = "-"'));
  assert.ok(result.code.includes("LINE_STYLES[index % len(LINE_STYLES)]"));
});

test("output is deterministic", () => {
  assert.equal(translated(line).code, translated(line).code);
});

test("no styling knob reaches the schema an agent sees", () => {
  const schema = JSON.stringify(z.toJSONSchema(FigureSpec, { io: "input" }));
  for (const banned of ["linewidth", "markersize", "figsize", "fontsize"]) {
    assert.ok(!schema.includes(banned), `${banned} must stay out of the spec`);
  }
});

test("a categorical bar axis gets no scale or limit calls", () => {
  const result = translated({
    ...line,
    kind: "bar",
    aggregation: "mean",
    x: { ...line.x, limits: [0, 5] },
  });
  assert.ok(!result.code.includes("set_xscale"));
  assert.ok(!result.code.includes("set_xlim("));
  assert.match(result.code, /set_xticklabels/);
});

// Signed zero-inclusive ranges are checked on real artists in test_signed_bars.py.
test("a horizontal bar puts each label on the axis that actually shows it", () => {
  const result = translated({
    ...line,
    kind: "bar",
    aggregation: "mean",
    orientation: "horizontal",
  });
  assert.match(result.code, /ax\.set_ylabel\("Training epoch"\)/);
  assert.match(result.code, /ax\.set_xlabel\("Test accuracy \(%\)"\)/);
  assert.match(result.code, /ax\.set_yticklabels/);
});

test("a vertical bar keeps labels on their own axes", () => {
  const result = translated({ ...line, kind: "bar", aggregation: "mean" });
  assert.match(result.code, /ax\.set_xlabel\("Training epoch"\)/);
  assert.match(result.code, /ax\.set_ylabel\("Test accuracy \(%\)"\)/);
});

test("a horizontal bar sends the value limit to the axis that draws it", () => {
  const result = translated({
    ...line,
    kind: "bar",
    aggregation: "mean",
    orientation: "horizontal",
    y: { ...line.y, limits: [0, 100] },
  });
  assert.match(result.code, /ax\.set_xlim\(0, 100\)/);
  assert.ok(!result.code.includes("set_ylim(0, 100)"));
});

const SAMPLES: [string, unknown][] = [
  ["line grouped", line],
  ["line plain", { ...line, group: undefined, marker: true }],
  ["scatter trendline", { ...line, kind: "scatter", trendline: "linear" }],
  ["scatter plain", { ...line, kind: "scatter", group: undefined }],
  ["bar grouped", { ...line, kind: "bar", aggregation: "mean" }],
  ["bar horizontal", { ...line, kind: "bar", aggregation: "sum", orientation: "horizontal" }],
  ["emphasis", { ...line, series_order: ["base", "ours"], emphasis: { series: "ours" } }],
  ["compact log", { ...line, style: { preset: "paper_compact" }, y: { ...line.y, scale: "log" } }],
];

test("every emitted script is valid Python", (t) => {
  const python = resolvePython();
  if (!python) {
    t.skip("no Python interpreter found");
    return;
  }

  const dir = mkdtempSync(join(tmpdir(), "gu-codegen-"));
  for (const [name, spec] of SAMPLES) {
    const result = translated(spec);
    const file = join(dir, `${name.replace(/\s+/g, "_")}.py`);
    writeFileSync(file, result.code);
    execFileSync(python, ["-c", `compile(open(r'''${file}''').read(), 'x', 'exec')`], {
      stdio: "pipe",
    });
  }
});
