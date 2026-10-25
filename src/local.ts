/** JSON transport for the packaged local translator. No datasets are read here. */
import { readFileSync } from "node:fs";
import { z } from "zod";
import { FIGURE_KINDS, FigureSpec } from "./schema.ts";
import { translate } from "./translate.ts";
import { verify } from "./verify.ts";
import { ProfileSchema, repair, suggestFigures } from "./suggest.ts";
import { designCost } from "./perception.ts";
import { RECIPES, findRecipe } from "./recipes.ts";
import { TOOL_VERSION } from "./codegen/theme.ts";

export function dispatch(operation: string, payload: unknown): unknown {
  if (operation === "convert") return translate(payload);
  if (operation === "info") return { version: TOOL_VERSION, kinds: FIGURE_KINDS, node: process.version };
  if (operation === "schema") return z.toJSONSchema(FigureSpec, { target: "draft-7" });
  if (operation === "suggest") {
    const input = z.object({ profile: ProfileSchema, limit: z.number().int().min(1).max(5).default(3) }).parse(payload);
    return suggestFigures(input.profile, input.limit);
  }
  if (operation === "recipes") {
    const { name } = z.object({ name: z.string().optional() }).parse(payload);
    if (!name) return RECIPES;
    const recipe = findRecipe(name);
    if (!recipe) throw new Error(`Unknown recipe: ${name}`);
    return recipe;
  }
  if (operation === "repair") {
    const input = z.object({ spec: z.record(z.string(), z.unknown()), budget: z.number().int().min(1).max(5).default(3) }).parse(payload);
    return repair(input.spec, input.budget);
  }
  if (operation === "validate" || operation === "score") {
    const spec = FigureSpec.parse(payload);
    const findings = verify(spec);
    if (operation === "validate") return { ok: !findings.some(f => f.severity === "error"), findings, resolved: spec };
    const cost = designCost(spec);
    return { cost: cost.total, reasons: cost.reasons, findings };
  }
  throw new Error(`Unknown local operation: ${operation}`);
}

try {
  const request = z.object({ operation: z.string(), payload: z.unknown().optional() }).parse(JSON.parse(readFileSync(0, "utf8")));
  process.stdout.write(JSON.stringify({ ok: true, result: dispatch(request.operation, request.payload ?? {}) }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
}
