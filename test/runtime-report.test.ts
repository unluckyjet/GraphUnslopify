import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();
const base = { kind: "line", x: { field: "epoch", label: "Epoch" },
  y: { field: "score", label: "Score" }, group: "model", aggregation: "mean", legend: { show: false } };
const claim = { kind: "beats_everywhere", subject: "ours", reference: "base" };
const good = "epoch,score,model\n1,1,base\n1,2,base\n1,4,ours\n1,5,ours\n2,2,base\n2,3,base\n2,5,ours\n2,6,ours\n";
type Report = { schema_version: number; ok: boolean; status: string; exit_code: number;
  policy: { passed: boolean }; spec_hash: string; spec: Record<string, unknown>;
  inspection: { checked: boolean; available: boolean };
  data: { counts: { read: number; sample_sizes: number[] } };
  claims: { panel: number; verdict: string; detail: string; metric: string }[];
  panels: { index: number; name: string }[];
  significance: { status: string; raw_p: number; adjusted_p: number; family_size: number }[];
  findings: { code: string }[]; outputs: { path: string; bytes: number; sha256: string }[];
  skipped_outputs: { format: string }[]; untested: string[]; alt_text: string };

function run(csv = good, options: Record<string, unknown> = {},
  flags = ["--strict", "--json"], setup = "") {
  const dir = mkdtempSync(join(tmpdir(), "gu-report-"));
  const result = translate({ ...base, ...options,
    data: options.data ?? { path: "results.csv" },
    output: { stem: "figure", formats: ["png"], dpi: 100, ...(options.output as object ?? {}) } });
  assert.equal(result.status, "translated");
  if (result.status !== "translated") throw Error("not translated");
  writeFileSync(join(dir, "results.csv"), csv);
  writeFileSync(join(dir, "figure.py"), result.code);
  writeFileSync(join(dir, "driver.py"), `import figure\n${setup}\nraise SystemExit(figure.run_cli())\n`);
  const completed = spawnSync(python!, ["driver.py", ...flags], { cwd: dir, encoding: "utf8" });
  assert.equal(completed.error, undefined);
  const destination = flags.includes("--report") ? flags[flags.indexOf("--report") + 1]! : "figure.report.json";
  const report: Report = JSON.parse(readFileSync(join(dir, destination), "utf8"));
  if (flags.includes("--json")) assert.deepEqual(JSON.parse(completed.stdout), report);
  return { ...completed, report, dir };
}

test("a real render produces machine JSON, exact counts and verifiable output hashes", { skip: !python }, () => {
  const { status, report, dir, stderr } = run(good, { claims: [claim], uncertainty: { kind: "sem" } });
  assert.equal(status, 0, stderr);
  assert.equal(report.schema_version, 1);
  assert.equal(report.status, "passed");
  assert.equal(report.ok, true);
  assert.equal(report.inspection.checked, true);
  assert.equal(report.data.counts.read, 8);
  assert.deepEqual(report.data.counts.sample_sizes, [2, 2, 2, 2]);
  assert.equal(report.claims[0]!.verdict, "holds");
  assert.match(report.alt_text, /N = 2 per point/);
  assert.equal(report.outputs.length, 1);
  for (const output of report.outputs) {
    const bytes = readFileSync(join(dir, output.path));
    assert.equal(output.bytes, bytes.length);
    assert.equal(output.sha256, createHash("sha256").update(bytes).digest("hex"));
  }
});

test("failed claims exit 2 in strict mode but remain inspectable in legacy mode", { skip: !python }, () => {
  const options = { claims: [{ ...claim, subject: "base", reference: "ours" }] };
  const strict = run(good, options);
  assert.equal(strict.status, 2);
  assert.equal(strict.report.status, "failed");
  assert.equal(strict.report.claims[0]!.verdict, "fails");
  const legacy = run(good, options, []);
  assert.equal(legacy.status, 0);
  assert.equal(legacy.report.ok, false);
  assert.equal(legacy.report.policy.passed, true);
  assert.match(legacy.stdout, /FAILS/);
});

test("missing reference data is UNTESTED and fails strict mode", { skip: !python }, () => {
  const result = run("epoch,score,model\n1,4,ours\n2,5,ours\n", { claims: [claim] });
  assert.equal(result.status, 2);
  assert.equal(result.report.status, "incomplete");
  assert.equal(result.report.claims[0]!.verdict, "untested");
  assert.ok(!result.report.alt_text.includes("Ours is above"));
});

test("incomplete x coverage cannot pass by dropping the inconvenient points", { skip: !python }, () => {
  const result = run("epoch,score,model\n1,4,ours\n2,0,ours\n1,1,base\n", { claims: [claim] });
  assert.equal(result.report.claims[0]!.verdict, "untested");
  assert.match(result.report.claims[0]!.detail, /incomplete x coverage/);
  assert.equal(result.status, 2);
});

test("one point cannot establish a trend", { skip: !python }, () => {
  const result = run("epoch,score,model\n1,4,ours\n", {
    claims: [{ kind: "monotone_increasing", subject: "ours" }] });
  assert.equal(result.report.claims[0]!.verdict, "untested");
  assert.match(result.report.claims[0]!.detail, /at least two/);
  assert.equal(result.status, 2);
});

test("claims are checked per facet instead of against a misleading pooled mean", { skip: !python }, () => {
  const result = run("epoch,score,model,dataset\n1,1,base,A\n1,1,base,A\n1,9,ours,A\n1,9,ours,A\n1,4,base,B\n1,4,base,B\n1,3,ours,B\n1,3,ours,B\n",
    { claims: [claim], facet: { by: "dataset" } });
  assert.equal(result.status, 2);
  assert.deepEqual(result.report.panels.map(p => p.name), ["A", "B"]);
  assert.deepEqual(result.report.claims.map(c => c.verdict), ["holds", "fails"]);
  assert.match(result.report.alt_text, /Panel A:/);
  assert.match(result.report.alt_text, /Panel B:/);
});

test("repeated metrics get separate claim verdicts", { skip: !python }, () => {
  const result = run("epoch,score,loss,model\n1,1,2,base\n2,2,3,base\n1,5,0,ours\n2,6,1,ours\n",
    { claims: [claim], repeat: { fields: ["score", "loss"] } });
  assert.equal(result.status, 2);
  assert.deepEqual(result.report.claims.map(c => [c.metric, c.verdict]), [["score", "holds"], ["loss", "fails"]]);
});

test("unavailable inspection is incomplete, never a silent strict pass", { skip: !python }, () => {
  const result = run(good, {}, undefined, [
    "import builtins", "original = builtins.__import__", "def blocked(name, *args, **kwargs):",
    "    if name == 'graphunslopify': raise ImportError('controlled missing checker')",
    "    return original(name, *args, **kwargs)", "builtins.__import__ = blocked",
  ].join("\n"));
  assert.equal(result.status, 2);
  assert.equal(result.report.status, "incomplete");
  assert.equal(result.report.inspection.available, false);
  assert.ok(result.report.findings.some(f => f.code === "inspection_unavailable"));
});

const inspector = (severity: string) => ["import graphunslopify",
  "original_inspection = graphunslopify.inspect_figure",
  "def controlled(*args, **kwargs):",
  "    report = original_inspection(*args, **kwargs)",
  `    report.add('${severity}', 'controlled', 'test finding')`,
  "    return report",
  "graphunslopify.inspect_figure = controlled"].join("\n");

test("inspection errors block strict mode; warning policy is explicitly optional", { skip: !python }, () => {
  assert.equal(run(good, {}, undefined, inspector("error")).status, 2);
  assert.equal(run(good, {}, undefined, inspector("warning")).status, 0);
  const warning = run(good, {}, ["--json", "--fail-on-warning"], inspector("warning"));
  assert.equal(warning.status, 2);
  assert.equal(warning.report.exit_code, 2);
  assert.equal(warning.report.policy.passed, false);
});

test("runtime failures still write a report and exit 1", { skip: !python }, () => {
  const result = run(good, { data: { path: "missing.csv" } });
  assert.equal(result.status, 1);
  assert.equal(result.report.status, "failed");
  assert.ok(result.report.findings.some(f => f.code === "runtime_error"));
  assert.deepEqual(result.report.outputs, []);
});

test("unavailable uncertainty and skipped tests are explicit required checks", { skip: !python }, () => {
  const missing = run("epoch,score,model\n1,1,a\n2,2,a\n", { uncertainty: { kind: "sem" } });
  assert.equal(missing.status, 2);
  assert.ok(missing.report.untested.some(x => x.includes("uncertainty")));
  const comparison = run("epoch,score\na,1\nb,2\n", { kind: "bar", group: undefined,
    significance: { method: "bootstrap", pairs: [["a", "b"]] } });
  assert.equal(comparison.status, 2);
  assert.equal(comparison.report.significance[0]!.status, "untested");
});

test("corrected significance records preserve raw and adjusted p values", { skip: !python }, () => {
  const csv = "epoch,score\n" + ["a", "b", "c"].flatMap((name, i) =>
    [0, 1, 2, 3].map(n => `${name},${n + (i === 1 ? 4 : 0)}`)).join("\n") + "\n";
  const result = run(csv, { kind: "bar", group: undefined,
    significance: { method: "bootstrap", pairs: [["a", "b"], ["a", "c"]] } });
  assert.equal(result.report.significance.length, 2);
  const pair = result.report.significance[0]!;
  assert.equal(pair.family_size, 2);
  assert.ok(Math.abs(pair.raw_p - 2 / 70) < 1e-12);
  assert.ok(Math.abs(pair.adjusted_p - 4 / 70) < 1e-12);
});

test("table rendering runs inspection and records each written format", { skip: !python }, () => {
  const result = run(good, { kind: "table", uncertainty: { kind: "sem" }, claims: [claim] },
    ["--json", "--report", "reports/table.json"]);
  assert.equal(result.report.inspection.checked, true);
  assert.equal(result.report.claims[0]!.verdict, "holds");
  assert.deepEqual(result.report.outputs.map(x => x.path).sort(), ["figure.md", "figure.png", "figure.tex"]);
});

test("requested but unsupported output is reported as skipped", { skip: !python }, () => {
  const result = run(good, { kind: "box", output: { interactive: true } });
  assert.equal(result.status, 2);
  assert.equal(result.report.status, "failed");
  assert.ok(result.report.skipped_outputs.some(x => x.format === "html"));
});

test("the Python CLI forwards strict and JSON policies to the actual generated program", { skip: !python }, () => {
  const result = run(good, { claims: [{ ...claim, subject: "base", reference: "ours" }] }, undefined,
    "import sys\nfrom graphunslopify.cli import main as cli\nfigure.run_cli = lambda: cli(['check', 'figure.py', *sys.argv[1:]])");
  assert.equal(result.status, 2);
  assert.equal(result.report.claims[0]!.verdict, "fails");
  assert.equal(result.report.policy.passed, false);
});

test("Figure.render strict failures carry their structured runtime evidence", { skip: !python }, () => {
  const result = run(good, { claims: [{ ...claim, subject: "base", reference: "ours" }] }, undefined, [
    "import contextlib, json, sys", "from pathlib import Path", "from graphunslopify import Figure, SpecError",
    "def through_builder():",
    "    item = Figure.line('results.csv').named('figure')",
    "    item.translate = lambda api=None: {'findings': [], 'code': Path('figure.py').read_text()}",
    "    with contextlib.redirect_stdout(sys.stderr):",
    "        try:", "            item.render(cwd='.', strict=True)",
    "        except SpecError as problem:", "            report = problem.report",
    "        else:", "            raise AssertionError('strict rendering unexpectedly passed')",
    "    assert report is not None, 'missing structured error evidence'",
    "    print(json.dumps(report))", "    return report['exit_code']",
    "figure.run_cli = through_builder",
  ].join("\n"));
  assert.equal(result.status, 2, result.stderr);
  assert.equal(result.report.claims[0]!.verdict, "fails");
});

test("raw duplicate x values cannot be silently averaged to prove a claim", { skip: !python }, () => {
  const result = run("epoch,score,model\n1,0,ours\n1,10,ours\n1,4,base\n", {
    aggregation: "none", claims: [claim] });
  assert.equal(result.report.claims[0]!.verdict, "untested");
  assert.equal(result.status, 2);
});
