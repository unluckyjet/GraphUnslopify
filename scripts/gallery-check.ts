/** Regenerate the published gallery and reject failed or incomplete checks. */
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { translate } from "../src/translate.ts";
import { resolvePython } from "./python.ts";

const python = process.argv[2] ?? resolvePython();
if (!python) throw new Error("No Python interpreter found; set PYTHON");
const workdir = join(import.meta.dirname, "..", "examples");
const destination = mkdtempSync(join(tmpdir(), "gu-gallery-"));
let failures = 0;
const specs = readdirSync(join(workdir, "specs")).filter(f => f.endsWith(".json")).sort();
for (const file of specs) {
  const name = file.slice(0, -5);
  const raw = JSON.parse(readFileSync(join(workdir, "specs", file), "utf8"));
  const stem = join(destination, name);
  const translated = translate({ ...raw, output: { ...raw.output, stem } });
  if (translated.status !== "translated" || !translated.ok) {
    console.log(`FAIL  ${name}  invalid specification`);
    failures++;
    continue;
  }
  const script = `${stem}.py`;
  writeFileSync(script, translated.code);
  const completed = spawnSync(python, [script, "--strict"], { cwd: workdir, encoding: "utf8" });
  try {
    const report = JSON.parse(readFileSync(`${stem}.report.json`, "utf8"));
    if (completed.status !== 0 || !report.ok || !report.inspection.checked || report.status !== "passed") {
      const reasons = report.findings.filter((f: { severity: string }) => f.severity === "error")
        .map((f: { code: string }) => f.code);
      console.log(`FAIL  ${name}  ${report.status}: ${reasons.join(", ") || JSON.stringify(report.untested)}`);
      failures++;
    } else console.log(`PASS  ${name}  inspected, strict checks passed`);
  } catch {
    console.log(`FAIL  ${name}  missing report: ${completed.error?.message ?? completed.stderr.trim().split("\n").slice(-2).join(" | ")}`);
    failures++;
  }
}
console.log(`\n${specs.length - failures}/${specs.length} gallery figures passed strict checks; artifacts: ${destination}`);
process.exitCode = failures ? 1 : 0;
