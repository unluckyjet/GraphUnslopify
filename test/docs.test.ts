import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { RECIPES } from "../src/recipes.ts";
import { FIGURE_KINDS } from "../src/schema.ts";

/**
 * The readmes quote counts, and a count in prose drifts silently. The gallery
 * readme claimed eight specs when there were fourteen, and two CSVs when there
 * were three, for long enough that both numbers read as deliberate.
 */

const root = join(import.meta.dirname, "..");

const WORDS: Record<number, string> = {
  3: "three",
  4: "four",
  7: "Seven",
  10: "Ten",
  11: "eleven",
  14: "Fourteen",
  18: "Eighteen",
  21: "Twenty-one",
  25: "twenty-five",
  15: "Fifteen",
  47: "Forty-seven",
  51: "Fifty-one",
  52: "Fifty-two",
  53: "Fifty-three",
  56: "Fifty-six",
  57: "Fifty-seven",
};

function read(path: string): string {
  return readFileSync(join(root, path), "utf8");
}

function word(count: number): string {
  const spelled = WORDS[count];
  assert.ok(spelled, `README counts are spelled out; add a word for ${count}`);
  return spelled;
}

test("the readme states the number of figure kinds", () => {
  assert.match(read("README.md"), new RegExp(`${word(FIGURE_KINDS.length)} kinds`));
});

test("the readme states the number of recipes", () => {
  assert.match(read("README.md"), new RegExp(`${word(RECIPES.length)} known-good specs`));
});

test("the readme states the number of lint rules", () => {
  const source = read("src/verify.ts");
  const codes = new Set<string>();
  const call = /\badd\(\s*"(?:error|warning)"\s*,\s*"([a-z0-9_]+)"/g;
  for (let m = call.exec(source); m; m = call.exec(source)) codes.add(m[1] ?? "");
  assert.ok(codes.size > 0, "no rule codes found in src/verify.ts");
  assert.match(read("README.md"), new RegExp(`${word(codes.size)} rules run on the server`));
});

test("the gallery readme states how many specs and data files it has", () => {
  const specs = readdirSync(join(root, "examples/specs")).filter((f) => f.endsWith(".json"));
  const data = readdirSync(join(root, "examples/data")).filter((f) => f.endsWith(".csv"));
  const gallery = read("examples/README.md");
  assert.match(gallery, new RegExp(`${word(specs.length)} figures`));
  assert.match(gallery, new RegExp(`the ${word(specs.length).toLowerCase()} inputs`));
  assert.match(gallery, new RegExp(`the ${word(data.length)} CSVs`));
});
