import { z } from "zod";
import { ClaimSpec } from "./claims.ts";

/**
 * What an agent is allowed to say about a figure.
 *
 * The rule this schema enforces is that a spec describes what the figure means,
 * never how matplotlib should draw it. There is no line width, no hex colour,
 * no font size, no pixel offset. Those belong to the emitter, which owns every
 * presentation decision so that two figures in one paper agree.
 *
 * Where a feature needs a position it takes a semantic one. An annotation
 * attaches to "max" or "crossover", not to x=3.2, and the emitter works out
 * where that lands and how to place the label clear of the data.
 */

export const AxisSpec = z.object({
  field: z.string().min(1).describe("Column name in the data file.").meta({ examples: ["epoch", "accuracy"] }),
  label: z.string().min(1).describe("Axis label as it should read in the paper.").meta({ examples: ["Training epoch", "Top-1 accuracy"] }),
  unit: z
    .string()
    .min(1)
    .optional()
    .describe('Unit appended to the label in parentheses, such as "%" or "ms".')
    .meta({ examples: ["%", "ms", "M", "pp"] }),
  scale: z
    .enum(["linear", "log", "symlog"])
    .default("linear")
    .describe("symlog suits data that crosses zero and still spans orders of magnitude."),
  limits: z
    .tuple([z.number(), z.number()])
    .optional()
    .describe("Explicit [lower, upper] bounds. Set these only when the science requires them."),
  percent: z
    .boolean()
    .default(false)
    .describe("Format ticks as percentages. For proportions in 0-1, not values already in 0-100."),
  temporal: z
    .boolean()
    .default(false)
    .describe(
      "Read this column as dates and lay the axis out in time. x only, and only on a line or " +
        "scatter, because the other kinds put categories on x.",
    ),
});
export type AxisSpec = z.infer<typeof AxisSpec>;

export const LegendSpec = z.object({
  show: z.boolean().default(true),
  labels: z.array(z.object({
    series: z.string().min(1).describe("Original source series ID; does not rename data or claim subjects."),
    text: z.string().min(1).describe("Literal display name. Computed legend details remain renderer-owned."),
  })).optional().describe("Display names for source series; IDs and numerical checks remain unchanged."),
  position: z
    .enum([
      "best",
      "upper_left",
      "upper_right",
      "lower_left",
      "lower_right",
      "outside_right",
      "outside_bottom",
    ])
    .default("best"),
  title: z.string().min(1).optional(),
  style: z
    .enum(["box", "direct"])
    .default("box")
    .describe('"direct" labels each series at the end of its line instead of drawing a box.'),
});

export const VENUES = ["none", "neurips", "icml", "iclr", "nature", "ieee"] as const;

export const OutputSpec = z.object({
  interactive: z
    .boolean()
    .default(false)
    .describe(
      "Also emit a self-contained HTML figure with hover, zoom and legend toggling, for a " +
        "project page or supplementary material. Needs plotly.",
    ),
  latex: z
    .boolean()
    .default(false)
    .describe("Also write a .tex block with the includegraphics, caption and alt text filled in."),
  size: z
    .enum(["single_column", "double_column"])
    .default("single_column")
    .describe("Target width in the manuscript. The emitter picks the actual figure size."),
  formats: z.array(z.enum(["png", "svg", "pdf"])).min(1).default(["png", "svg", "pdf"]),
  dpi: z.number().int().min(72).max(1200).default(600).describe("Raster export density."),
  stem: z.string().min(1).default("figure").describe("Output filename without extension."),
});

export const StyleSpec = z.object({
  preset: z.enum(["paper", "paper_compact"]).default("paper"),
  grid: z.boolean().default(false),
  despine: z.boolean().default(true),
  venue: z
    .enum(VENUES)
    .default("none")
    .describe("Sets column width and the minimum font size from that venue's submission guide."),
});

export const DataSpec = z.object({
  path: z.string().min(1).default("results.csv").describe("Path the generated script reads."),
  format: z.enum(["csv", "parquet", "json", "excel"]).default("csv"),
  sheet: z.string().min(1).optional().describe("Excel worksheet name. Required for multi-sheet workbooks."),
  columns: z
    .array(z.string().min(1))
    .optional()
    .describe("Columns the file is known to hold. Supply this and every field reference is checked."),
}).refine(data => data.sheet === undefined || data.format === "excel", {
  message: "Worksheet selection requires data.format excel", path: ["sheet"],
});

export const FilterSpec = z.object({
  field: z.string().min(1),
  op: z.enum(["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"]),
  value: z.union([z.string(), z.number(), z.boolean(), z.array(z.union([z.string(), z.number()]))]),
});

export type FilterOp = z.infer<typeof FilterSpec>["op"];

export const TransformSpec = z.object({
  kind: z
    .enum(["none", "delta_vs_baseline", "percent_of_baseline", "cumulative", "normalize"])
    .default("none"),
  baseline: z
    .string()
    .min(1)
    .optional()
    .describe("Which series is the baseline. Required by both baseline transforms."),
});

export const UncertaintySpec = z.object({
  kind: z
    .enum(["std", "sem", "ci", "iqr", "range"])
    .describe("What the spread means. ci takes a level, the rest follow from the data."),
  level: z.number().min(0.5).max(0.999).default(0.95).describe("Confidence level, for ci only."),
  over: z
    .string()
    .min(1)
    .optional()
    .describe('Identifier of units assumed independent, such as "seed". Repeated rows per unit and point are summarized first. Without it, repeated rows are assumed independent.'),
  display: z
    .enum(["band", "bar"])
    .default("band")
    .describe("A band suits a continuous x, error bars suit categories."),
});

export const SmoothSpec = z.object({
  kind: z.enum(["ema", "rolling"]),
  window: z.number().int().min(2).max(1000).default(10),
  show_raw: z.boolean().default(true).describe("Keep the raw series faint behind the smoothed one."),
});

export const SortSpec = z.object({
  by: z.enum(["value", "category", "series_order"]).default("category"),
  direction: z.enum(["asc", "desc"]).default("asc"),
});

export const ReferenceLineSpec = z.object({
  axis: z.enum(["x", "y"]),
  value: z.number(),
  label: z.string().min(1).optional(),
  meaning: z
    .enum(["chance", "human", "threshold", "baseline", "target", "other"])
    .default("other")
    .describe("What the line represents. The emitter decides how each kind is drawn."),
});

export const AnnotationSpec = z.object({
  at: z
    .union([
      z.enum(["max", "min", "first", "last", "crossover"]),
      z.object({ x: z.union([z.number(), z.string()]) }),
    ])
    .describe("Where to attach. The emitter finds the point and keeps the label clear of the data."),
  series: z.string().min(1).optional().describe("Which series. Needed when the figure has a group."),
  text: z.string().min(1),
});

export const FacetSpec = z.object({
  by: z.string().min(1).describe("Column that splits the figure into panels."),
  rows: z
    .string()
    .min(1)
    .optional()
    .describe("A second column, giving a grid of panels with by across and rows down."),
  columns: z.number().int().min(1).max(6).default(2),
  share_x: z.boolean().default(true),
  share_y: z.boolean().default(true),
  panel_letters: z.boolean().default(true).describe("Label panels (a), (b), (c) for the caption."),
});

export const SignificanceSpec = z.object({
  design: z.enum(["independent", "paired"]).default("independent")
    .describe("Author-declared sampling design, not a certification of independence. Paired tests match the same units across categories."),
  pair_by: z.string().min(1).optional()
    .describe("For paired comparisons, unit ID shared across categories. Must match uncertainty.over so bars and tests use the same technical-repeat summaries."),
  method: z.enum(["bootstrap", "ttest", "mannwhitney"]).describe(
    "bootstrap is the historical name for a two-sided absolute-mean-gap permutation test (paired design uses sign flips); " +
    "ttest uses Welch's test or paired t according to design; mannwhitney is independent-only and tests distributions, not median equality.",
  ),
  pairs: z
    .array(z.tuple([z.string(), z.string()]))
    .min(1)
    .describe("Category pairs to compare. The script runs the test rather than assuming a result."),
  alpha: z.number().min(0.0001).max(0.2).default(0.05),
  correction: z.enum(["none", "holm", "benjamini_hochberg"]).default("holm").describe(
    "Adjustment across the tested pairs in each panel. Holm is the default; " +
    "Benjamini-Hochberg suits exploratory independent/positively dependent tests. " +
    "none explicitly retains unadjusted p-values.",
  ),
});

export type Significance = z.infer<typeof SignificanceSpec>;

export const SecondaryAxisSpec = z.object({
  field: z.string().min(1),
  label: z.string().min(1),
  unit: z.string().min(1).optional(),
  scale: z.enum(["linear", "log"]).default("linear"),
  justification: z
    .string()
    .min(20)
    .describe(
      "Why two scales are needed here. Independently scaled axes can make any two series look " +
        "related, so this is recorded in the figure metadata and the figure always warns.",
    ),
});

export const AnimateSpec = z.object({
  style: z
    .enum(["draw", "grow", "reveal", "trace", "fade"])
    .default("draw")
    .describe("draw traces lines left to right, grow raises bars, reveal brings series in one by one."),
  duration_s: z.number().min(0.5).max(60).default(4),
  fps: z.number().int().min(10).max(60).default(30),
  easing: z
    .enum(["linear", "smooth", "smoothstep", "rush_into", "rush_from"])
    .default("smooth")
    .describe("Named after the manim rate functions they reproduce."),
  stagger_s: z.number().min(0).max(5).default(0.35).describe("Delay between series entering."),
  hold_s: z.number().min(0).max(10).default(1.2).describe("Still time on the finished figure."),
  format: z.enum(["mp4", "gif"]).default("mp4"),
});

/**
 * An extra mark drawn over the same axes.
 *
 * Vega-Lite's layer operator composes recursively. This is the constrained
 * version: one list of extra marks over the figure's own x, which covers the
 * cases that actually recur, observed points over a fitted line, a rug under a
 * distribution, a threshold rule. Recursive composition is not here.
 */
export const LayerSpec = z.object({
  mark: z
    .enum(["line", "scatter", "rug", "band", "rule"])
    .describe("rug draws ticks along the axis, band fills between two columns, rule is a line at a value."),
  y: z.string().min(1).optional().describe("Column for this layer. Defaults to the figure's y field."),
  y2: z.string().min(1).optional().describe("Upper column, for a band."),
  value: z.number().optional().describe("Where a rule sits."),
  label: z.string().min(1).optional().describe("Legend entry. Omit to keep it out of the legend."),
  filter: z.array(FilterSpec).min(1).optional().describe("Rows this layer draws, if not all of them."),
  recede: z.boolean().default(true).describe("Draw behind the figure's own marks."),
});

/** Small multiples over columns rather than over a data column. */
export const RepeatSpec = z.object({
  fields: z.array(z.string().min(1)).min(2).describe("One panel per column named here."),
  columns: z.number().int().min(1).max(6).default(2),
  share_x: z.boolean().default(true),
  share_y: z.boolean().default(false).describe("Off by default, since repeated metrics rarely share a range."),
});

/**
 * A gap cut out of an axis, for data with an empty middle.
 *
 * The honest alternative to a log scale when the range is bimodal rather than
 * exponential. The break is drawn explicitly with slanted marks so a reader
 * cannot mistake it for a continuous axis.
 */
export const BreakSpec = z.object({
  axis: z.enum(["x", "y"]).default("y"),
  from: z.number().describe("Where the gap starts."),
  to: z.number().describe("Where the gap resumes."),
});

/** A zoomed copy of one region, drawn inside the axes with its source marked. */
export const InsetSpec = z.object({
  x: z.tuple([z.number(), z.number()]).describe("The x range to magnify."),
  y: z.tuple([z.number(), z.number()]).describe("The y range to magnify."),
  corner: z.enum(["upper_left", "upper_right", "lower_left", "lower_right"]).default("lower_right"),
  size: z.number().min(0.15).max(0.6).default(0.35).describe("Fraction of the axes the inset covers."),
});

export const SeriesFromColumnsSpec = z.object({
  fields: z.array(z.string().min(1)).min(2).describe("Wide columns to turn into one series each."),
  series_name: z.string().min(1).default("metric").describe("Name for the new grouping column."),
  value_name: z.string().min(1).default("value").describe("Name for the new value column."),
});

const base = {
  title: z.string().min(1).optional(),
  group: z
    .string()
    .min(1)
    .optional()
    .describe("Column that splits the data into series.")
    .meta({ examples: ["model", "method", "dataset"] }),
  series_order: z
    .array(z.string().min(1))
    .min(1)
    .optional()
    .describe("Explicit series order. Fixes colour assignment across figures in one paper."),
  emphasis: z
    .object({ series: z.string().min(1) })
    .optional()
    .describe("The one series being argued for. The emitter foregrounds it and recedes the rest."),
  series_from_columns: SeriesFromColumnsSpec.optional(),
  filter: z.array(FilterSpec).min(1).optional(),
  transform: TransformSpec.optional(),
  facet: FacetSpec.optional(),
  reference_lines: z.array(ReferenceLineSpec).min(1).optional(),
  annotate: z.array(AnnotationSpec).min(1).optional(),
  legend: LegendSpec.prefault({}),
  output: OutputSpec.prefault({}),
  style: StyleSpec.prefault({}),
  data: DataSpec.prefault({}),
  animate: AnimateSpec.optional(),
  claims: z
    .array(ClaimSpec)
    .min(1)
    .optional()
    .describe(
      "What the figure is meant to show. The script tests each one against the data and refuses " +
        "to let a caption assert something the figure does not support.",
    ),
  alt_text: z
    .string()
    .min(20)
    .optional()
    .describe(
      "Context a reader needs that the data cannot supply, which is level four of the alt text " +
        "model. Levels one to three are generated. Leave this out rather than guessing.",
    ),
  caption: z.string().min(10).optional().describe("Plain-text caption, escaped as literal text in LaTeX output."),
  layers: z.array(LayerSpec).min(1).optional().describe("Extra marks over the same axes."),
  repeat: RepeatSpec.optional(),
  axis_break: BreakSpec.optional(),
  inset: InsetSpec.optional(),
  palette_lock: z
    .string()
    .min(1)
    .optional()
    .describe(
      "Path to a lock file shared by every figure in one paper, so a model keeps its colour and " +
        "marker across figure 1 and figure 7.",
    ),
};

const xy = { ...base, x: AxisSpec, y: AxisSpec };

export const LineSpec = z.object({
  ...xy,
  kind: z.literal("line"),
  marker: z.boolean().default(false),
  sort_x: z.boolean().default(true),
  aggregation: z
    .enum(["none", "mean", "median"])
    .default("none")
    .describe("How to collapse repeated x values. A curve over several seeds wants mean."),
  uncertainty: UncertaintySpec.optional(),
  smooth: SmoothSpec.optional(),
  y2: SecondaryAxisSpec.optional(),
});

export const ScatterSpec = z.object({
  ...xy,
  kind: z.literal("scatter"),
  trendline: z.enum(["none", "linear"]).default("none"),
  frontier: z
    .object({
      x: z.enum(["min", "max"]).default("min").describe("Whether a good x is small or large."),
      y: z.enum(["min", "max"]).default("max"),
    })
    .optional()
    .describe("Draw the non-dominated set, for an accuracy against cost figure."),
});

export const BarSpec = z.object({
  ...xy,
  kind: z.literal("bar"),
  orientation: z.enum(["vertical", "horizontal"]).default("vertical"),
  aggregation: z.enum(["none", "mean", "median", "sum", "count"]).default("none"),
  baseline_zero: z.boolean().default(true),
  stacked: z.boolean().default(false).describe("Parts of a whole. Leave false to compare categories."),
  sort: SortSpec.optional(),
  category_order: z.array(z.string().min(1)).min(1).optional(),
  value_labels: z.boolean().default(false).describe("Print each value on its bar."),
  uncertainty: UncertaintySpec.optional(),
  significance: SignificanceSpec.optional(),
});

export const BoxSpec = z.object({
  ...xy,
  kind: z.literal("box"),
  show_points: z.boolean().default(false).describe("Overlay the individual observations."),
  notch: z.boolean().default(false).describe("Notches give a rough visual test of median difference."),
  category_order: z.array(z.string().min(1)).min(1).optional(),
  sort: SortSpec.optional(),
});

export const ViolinSpec = z.object({
  ...xy,
  kind: z.literal("violin"),
  show_points: z.boolean().default(false),
  show_box: z.boolean().default(true).describe("Draw a quartile box inside each violin."),
  category_order: z.array(z.string().min(1)).min(1).optional(),
});

export const EcdfSpec = z.object({
  ...xy,
  kind: z.literal("ecdf"),
  complementary: z
    .boolean()
    .default(false)
    .describe("Draw 1 - F(x) instead, when the tail is what the argument rests on."),
});

export const RaincloudSpec = z.object({
  ...xy,
  kind: z.literal("raincloud"),
  category_order: z.array(z.string().min(1)).min(1).optional(),
});

export const RidgelineSpec = z.object({
  ...xy,
  kind: z.literal("ridgeline"),
  category_order: z.array(z.string().min(1)).min(1).optional(),
});

export const ForestSpec = z.object({
  ...xy,
  kind: z.literal("forest"),
  null_value: z
    .number()
    .default(0)
    .describe("The value that means no effect. The reference line is drawn here."),
  category_order: z.array(z.string().min(1)).min(1).optional(),
  aggregation: z.enum(["mean", "median"]).default("mean"),
  uncertainty: UncertaintySpec,
});

export const PairedDifferenceSpec = z.object({
  ...xy,
  kind: z.literal("paired_difference"),
  pair: z
    .string()
    .min(1)
    .describe("Column identifying the unit measured under both conditions.")
    .meta({ examples: ["subject", "seed", "dataset"] }),
  baseline: z.string().min(1).describe("The condition subtracted from the other."),
});

export const SlopeSpec = z.object({
  ...xy,
  kind: z.literal("slope"),
  category_order: z.array(z.string().min(1)).min(1).optional(),
});

export const DumbbellSpec = z.object({
  ...xy,
  kind: z.literal("dumbbell"),
  category_order: z.array(z.string().min(1)).min(1).optional(),
  sort: SortSpec.optional(),
});

export const CalibrationSpec = z.object({
  ...xy,
  kind: z.literal("calibration"),
  outcome: z
    .string()
    .min(1)
    .describe("Column holding the observed outcome, 0 or 1.")
    .meta({ examples: ["correct", "label", "hit"] }),
  bins: z
    .int()
    .min(3)
    .max(50)
    .default(10)
    .describe("How many probability bins. Fewer bins hide miscalibration, more make each noisy."),
});

export const QqSpec = z.object({
  ...xy,
  kind: z.literal("qq"),
  distribution: z
    .enum(["normal", "uniform"])
    .default("normal")
    .describe("The distribution being assumed. The line is where the data would fall if it held."),
});

export const KaplanMeierSpec = z.object({
  ...xy,
  kind: z.literal("kaplan_meier"),
  event: z
    .string()
    .min(1)
    .describe("Column that is 1 when the event was observed and 0 when the record was censored.")
    .meta({ examples: ["died", "failed", "converged"] }),
});

export const ScalingFitSpec = z.object({
  ...xy,
  kind: z.literal("scaling_fit"),
  show_points: z.boolean().default(true),
  interval: z.enum(["t95", "none"]).default("t95")
    .describe("Conditional 95% Student-t slope interval (requires statistics extra), or an explicit point-only fit."),
});

export const ConfusionMatrixSpec = z.object({
  ...base,
  kind: z.literal("confusion_matrix"),
  x: AxisSpec,
  y: AxisSpec,
  normalize: z
    .enum(["none", "row", "column"])
    .describe(
      "Required, because the three make different claims. Row-normalised reads as recall, " +
        "column-normalised as precision, and raw counts as support.",
    ),
  value: z.string().min(1).optional().describe("Column holding a precomputed count. Omit to count rows."),
  annotate_cells: z.boolean().default(true),
});

export const WaterfallSpec = z.object({
  ...xy,
  kind: z.literal("waterfall"),
  start: z.number().describe("The baseline the contributions are measured from."),
  category_order: z
    .array(z.string().min(1))
    .min(1)
    .describe("Required. A waterfall is read left to right, so the order is part of the claim."),
});

export const SparklineGridSpec = z.object({
  ...xy,
  kind: z.literal("sparkline_grid"),
  columns: z.int().min(1).max(12).default(4),
});

export const HeatmapSpec = z.object({
  ...base,
  kind: z.literal("heatmap"),
  x: AxisSpec,
  y: AxisSpec,
  value: z.string().min(1).describe("Column holding the cell value."),
  value_label: z.string().min(1).describe("Colourbar label. Without it the units are lost."),
  aggregation: z.enum(["mean", "median", "sum", "count"]).default("mean"),
  annotate_cells: z.boolean().default(false).describe("Print the number in each cell."),
  diverging: z
    .boolean()
    .default(false)
    .describe("Centre the colour scale on zero. For differences, not magnitudes."),
});

/**
 * A table, because sometimes six numbers should not be a chart.
 *
 * Position is the most accurately read channel and a printed number is exact,
 * so a small comparison across a handful of categories is better served by a
 * table than by bars. This emits markdown, LaTeX and a rendered image, so the
 * same spec can go into a paper or a readme.
 */
export const TableSpec = z.object({
  ...base,
  kind: z.literal("table"),
  x: AxisSpec.describe("The row key."),
  y: AxisSpec.describe("The value shown in each cell."),
  aggregation: z.enum(["none", "mean", "median", "sum", "count"]).default("mean"),
  precision: z.number().int().min(0).max(6).default(2),
  highlight: z
    .enum(["none", "best_per_row", "best_per_column"])
    .default("none")
    .describe("Bold the winning cell, which is what a results table is read for."),
  higher_is_better: z.boolean().default(true),
  uncertainty: UncertaintySpec.optional(),
});

export const FigureSpec = z.discriminatedUnion("kind", [
  LineSpec,
  ScatterSpec,
  BarSpec,
  BoxSpec,
  ViolinSpec,
  EcdfSpec,
  RaincloudSpec,
  RidgelineSpec,
  ForestSpec,
  PairedDifferenceSpec,
  SlopeSpec,
  DumbbellSpec,
  CalibrationSpec,
  QqSpec,
  KaplanMeierSpec,
  ScalingFitSpec,
  ConfusionMatrixSpec,
  WaterfallSpec,
  SparklineGridSpec,
  HeatmapSpec,
  TableSpec,
]);
export type FigureSpec = z.infer<typeof FigureSpec>;
export type FigureKind = FigureSpec["kind"];

export const FIGURE_KINDS = [
  "line",
  "scatter",
  "bar",
  "box",
  "violin",
  "ecdf",
  "raincloud",
  "ridgeline",
  "forest",
  "paired_difference",
  "slope",
  "dumbbell",
  "calibration",
  "qq",
  "kaplan_meier",
  "scaling_fit",
  "confusion_matrix",
  "waterfall",
  "sparkline_grid",
  "heatmap",
  "table",
] as const;


/**
 * Axes the script computes rather than reads from a column.
 *
 * An ECDF's proportion, a calibration plot's observed frequency, a survival
 * curve's probability and a Q-Q plot's theoretical quantile are all worked out
 * from the data. The axis still needs a label, so the spec still carries an
 * AxisSpec, but its `field` names no column and nothing should check it against
 * the file.
 */
export function derivedAxis(spec: FigureSpec, axis: "x" | "y"): boolean {
  if (axis === "y") {
    return spec.kind === "ecdf" || spec.kind === "calibration" || spec.kind === "kaplan_meier";
  }
  return spec.kind === "qq";
}

/** Kinds whose x is a category on an index rather than a number. */
export function hasCategoricalX(spec: FigureSpec): boolean {
  return (
    spec.kind === "bar" ||
    spec.kind === "box" ||
    spec.kind === "violin" ||
    spec.kind === "raincloud" ||
    spec.kind === "ridgeline" ||
    spec.kind === "forest" ||
    spec.kind === "paired_difference" ||
    spec.kind === "slope" ||
    spec.kind === "dumbbell" ||
    spec.kind === "waterfall"
  );
}

/** Kinds that draw one mark per series rather than a distribution. */
export function usesSeriesColours(spec: FigureSpec): boolean {
  return spec.kind !== "heatmap" && spec.kind !== "table";
}

/** Kinds that draw marks on axes, as opposed to laying out text. */
export function isPlotted(spec: FigureSpec): spec is PlottedSpec {
  return spec.kind !== "table";
}

/** What the mark emitters accept. A table lays out text and never reaches them. */
export type PlottedSpec = Exclude<FigureSpec, { kind: "table" }>;
