import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { DIAGNOSTIC_ADVICE, diagnosticAdvice, explainFinding } from "../src/diagnostics.ts";
import { translate } from "../src/translate.ts";

test("owned compiler and emitted runtime codes must have reviewed guidance", () => {
  const owned = new Set<string>();
  function scan(folder: string) {
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      const path = join(folder, entry.name);
      if (entry.isDirectory()) scan(path);
      else if (entry.name.endsWith(".ts") && entry.name !== "diagnostics.ts") {
        const text = readFileSync(path, "utf8");
        for (const pattern of [
          /\b(?:add|finding)\(\s*["'](?:warning|error)["']\s*,\s*["']([a-z_]+)["']/g,
          /\bcode:\s*["']([a-z_]+)["']/g,
          /diagnostic_text\(\s*["']([a-z_]+)["']/g,
          /finding\([^\n]*?"[a-z_]+" if [^\n]+? else "([a-z_]+)"/g,
        ]) for (const match of text.matchAll(pattern)) owned.add(match[1]!);
      }
    }
  }
  scan("src");
  assert.ok(owned.size >= 110, `unexpectedly incomplete source inventory: ${owned.size}`);
  assert.deepEqual([...owned].filter((code) => !DIAGNOSTIC_ADVICE[code]), []);
  for (const code of owned) {
    assert.ok(diagnosticAdvice(code).consequence.length > 40, code);
    assert.ok(diagnosticAdvice(code).correction.length > 40, code);
  }
});

test("schema problems retain their actual path and explain what must be corrected", () => {
  const result = translate({kind: "line", x: {field: "x", label: "X"}, y: {field: "score"}});
  assert.equal(result.status, "invalid_spec");
  const issue = result.issues.find((item) => item.path === "y.label");
  assert.ok(issue);
  assert.match(issue.consequence, /not been verified/);
  assert.match(issue.correction, /y.label/);
  assert.equal(translate({kind: "line", x: {field: "x", label: "X"}, y: {field: "score", label: "Score"}}).status, "translated");
});

test("context and conservative proposed fixes survive enrichment and unknown codes stay explicit", () => {
  const original = {severity: "warning", code: "truncated_bar_axis", message: "Lower bound 95 for score", fix: {y: {limits: [0, 100]}}};
  const explained = explainFinding(original);
  assert.equal(explained.message, original.message);
  assert.equal(explained.fix, original.fix);
  assert.match(explained.consequence, /ratio|length|difference/);
  assert.match(diagnosticAdvice("external_extension_code").correction, /no automatic|not infer/i);
});
