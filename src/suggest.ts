import { z } from "zod";
import { designCost } from "./perception.ts";
import { FigureSpec } from "./schema.ts";
import { hasErrors, verify, type Finding } from "./verify.ts";

/**
 * Candidate figures for a data profile, ranked.
 *
 * This is the constraint-and-weight shape Draco uses. Hard constraints reject a
 * design outright, soft constraints carry a cost, and the lowest total wins.
 * The difference from a rule list is that this can compare two designs, which
 * is what an agent staring at a fresh CSV actually needs.
 *
 * Input is the JSON that `graphunslopify describe` prints, so the agent does
 * not have to reshape anything between the two calls.
 */

/**
 * What `graphunslopify describe` prints, as the one place that shape is written.
 *
 * Loose because describe reports more per column than the ranking reads, and
 * dropping the rest would make the profile a client passes through lossy.
 */
export const ColumnSchema = z
  .object({
    name: z.string(),
    role: z.enum(["measure", "category", "ordinal", "flag", "identifier"]),
    distinct: z.number(),
    min: z.number().optional(),
    max: z.number().optional(),
    finite: z.number().int().nonnegative().optional(),
  })
  .loose();

export const ProfileSchema = z
  .object({
    columns: z.array(ColumnSchema),
    repeats: z
      .array(z.object({ x: z.string(), group: z.string(), repeated_rows: z.number() }))
      .optional(),
  })
  .loose();

export type Column = z.infer<typeof ColumnSchema>;
export type Profile = z.infer<typeof ProfileSchema>;

export type Candidate = {
  spec: FigureSpec;
  cost: number;
  why: string;
  reasons: string[];
};

function titleCase(field: string): string {
  const words = field.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** A unit guessed from the column name, which is better than none at all. */
function guessUnit(field: string): string | undefined {
  const name = field.toLowerCase();
  if (/(_ms|latency|duration|time)$/.test(name)) return "ms";
  if (/(_s|seconds)$/.test(name)) return "s";
  if (/(accuracy|acc|precision|recall|f1|rate|pct|percent)/.test(name)) return "%";
  if (/(_m|params|millions)$/.test(name)) return "M";
  return undefined;
}

function axis(field: string): Record<string, unknown> {
  const unit = guessUnit(field);
  return unit ? { field, label: titleCase(field), unit } : { field, label: titleCase(field) };
}

export function suggestFigures(profile: Profile, limit = 3): Candidate[] {
  const path = typeof profile.path === "string" ? profile.path : "results.csv";
  // Profiling JSON Lines is supported, but emitting its reader is not. Do not
  // substitute an unrelated default CSV for an unsupported source format.
  if (/\.(jsonl|ndjson)$/i.test(path)) return [];
  const format = /\.(xlsx|xls|xlsm)$/i.test(path) ? "excel" : /\.parquet$/i.test(path) ? "parquet" : /\.json$/i.test(path) ? "json" : "csv";
  const measures = profile.columns.filter((c) => c.role === "measure" && c.finite !== 0);
  const categories = profile.columns.filter((c) => c.role === "category");
  const ordinals = profile.columns
    .filter((c) => c.role === "ordinal")
    .sort((a, b) => b.distinct - a.distinct);

  const repeats = profile.repeats ?? [];
  const candidates: { spec: Record<string, unknown>; why: string }[] = [];

  const [longestOrdinal] = ordinals;
  const [measure, secondMeasure] = measures;
  const [category, secondCategory] = categories;

  const group = category?.name;
  const replicate = ordinals.length > 1 ? ordinals.at(-1)?.name : undefined;

  // A curve along the longest ordinal, which is what a training run looks like.
  if (longestOrdinal && measure) {
    const x = longestOrdinal.name;
    const y = measure.name;
    const repeated = repeats.some((r) => r.x === x && r.group === group);
    const spec: Record<string, unknown> = {
      kind: "line",
      x: axis(x),
      y: axis(y),
      ...(group ? { group } : {}),
      ...(repeated ? { aggregation: "mean" } : {}),
      ...(repeated && replicate
        ? { uncertainty: { kind: "ci", over: replicate, display: "band" } }
        : {}),
    };
    candidates.push({
      spec,
      why: repeated
        ? `${x} repeats within each ${group}, so this averages and shows the spread`
        : `${x} has the most steps, so it reads as the axis a curve travels along`,
    });
  }

  // One bar per category, which is the comparison a table would otherwise make.
  if (category && measure) {
    const x = category.name;
    const y = measure.name;
    const second = secondCategory?.name;
    candidates.push({
      spec: {
        kind: "bar",
        x: axis(x),
        y: axis(y),
        ...(second ? { group: second } : {}),
        aggregation: "mean",
        uncertainty: { kind: "sem", display: "bar" },
        sort: { by: "value", direction: "desc" },
      },
      why: `${x} is categorical, so bars put the comparison on a shared baseline`,
    });
  }

  // Two measures against each other, which is where a trade-off lives.
  if (measure && secondMeasure) {
    candidates.push({
      spec: {
        kind: "scatter",
        x: axis(measure.name),
        y: axis(secondMeasure.name),
        ...(group ? { group } : {}),
        frontier: { x: "min", y: "max" },
      },
      why: `${measure.name} and ${secondMeasure.name} are both measured, so this shows the trade-off`,
    });
  }

  // The distribution behind a summary, which a bar chart hides.
  if (category && measure) {
    candidates.push({
      spec: {
        kind: "box",
        x: axis(category.name),
        y: axis(measure.name),
        show_points: true,
      },
      why: `shows the spread within each ${category.name} rather than only its average`,
    });
  }

  // A grid, when two low-cardinality keys index one measure.
  const [gridX, gridY] = [...ordinals, ...categories].filter((c) => c.distinct <= 12);
  if (gridX && gridY && measure) {
    candidates.push({
      spec: {
        kind: "heatmap",
        x: axis(gridX.name),
        y: axis(gridY.name),
        value: measure.name,
        value_label: titleCase(measure.name),
        aggregation: "mean",
        annotate_cells: true,
      },
      why: `${gridX.name} and ${gridY.name} form a small grid over ${measure.name}`,
    });
  }

  const scored: Candidate[] = [];
  for (const candidate of candidates) {
    const parsed = FigureSpec.safeParse({ ...candidate.spec, data: { path, format,
      ...(format === "excel" && typeof profile.sheet === "string" ? { sheet: profile.sheet } : {}) } });
    if (!parsed.success) continue;
    const findings = verify(parsed.data);
    if (hasErrors(findings)) continue;

    const { total, reasons } = designCost(parsed.data);
    const warnings = findings.filter((f) => f.severity === "warning").length;
    scored.push({
      spec: parsed.data,
      cost: total + warnings,
      why: candidate.why,
      reasons: [...reasons, ...(warnings ? [`${warnings} lint warning(s)`] : [])],
    });
  }

  return scored.sort((a, b) => a.cost - b.cost).slice(0, limit);
}

/**
 * Apply a finding's fix to a spec.
 *
 * Shallow merge, one level deep for nested objects, which covers every fix the
 * linter currently emits and refuses to guess beyond that.
 */
export function applyFix(
  spec: Record<string, unknown>,
  fix: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...spec };
  for (const [key, value] of Object.entries(fix)) {
    const existing = merged[key];
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      existing !== null &&
      typeof existing === "object" &&
      !Array.isArray(existing)
    ) {
      merged[key] = { ...existing, ...value };
    } else {
      merged[key] = value;
    }
  }
  return merged;
}

export type RepairResult = {
  spec: Record<string, unknown>;
  applied: string[];
  remaining: { code: string; message: string }[];
  rounds: number;
};

/**
 * Repeatedly apply every fix the linter offers, up to a budget.
 *
 * The budget matters. The agent literature describes models that recognise an
 * error, fail to fix it, and keep trying until they give up, so this stops and
 * says what it could not repair instead of looping.
 */
export function repair(spec: Record<string, unknown>, budget = 3): RepairResult {
  let current = spec;
  const applied: string[] = [];

  for (let round = 1; round <= budget; round += 1) {
    const parsed = FigureSpec.safeParse(current);
    if (!parsed.success) {
      return {
        spec: current,
        applied,
        remaining: parsed.error.issues.map((i) => ({
          code: "invalid_spec",
          message: `${i.path.join(".") || "(root)"}: ${i.message}`,
        })),
        rounds: round,
      };
    }

    const findings = verify(parsed.data);
    const fixable = findings.filter(
      (f): f is Finding & { fix: Record<string, unknown> } => !!f.fix && !applied.includes(f.code),
    );
    if (!fixable.length) {
      return {
        spec: { ...parsed.data },
        applied,
        remaining: findings.map((f) => ({ code: f.code, message: f.message })),
        rounds: round,
      };
    }

    for (const finding of fixable) {
      current = applyFix(current, finding.fix);
      applied.push(finding.code);
    }
  }

  const parsed = FigureSpec.safeParse(current);
  const findings = parsed.success ? verify(parsed.data) : [];
  return {
    spec: parsed.success ? { ...parsed.data } : current,
    applied,
    remaining: findings.map((f) => ({ code: f.code, message: f.message })),
    rounds: budget,
  };
}
