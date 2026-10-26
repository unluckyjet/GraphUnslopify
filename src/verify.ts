import { interactiveLimitations } from "./capabilities.ts";
import { COMPARATIVE, NEEDS_TOLERANCE } from "./claims.ts";
import { encodingSuggestions } from "./perception.ts";
import { derivedAxis, hasCategoricalX, type FigureSpec } from "./schema.ts";

/**
 * Checks that need only the spec, no rendering.
 *
 * An error means the script will fail or the figure will misrepresent the data.
 * A warning means it will run and be wrong for a reviewer rather than wrong for
 * the maths. Anything needing pixels, such as overlapping tick labels or a
 * clipped legend, belongs to the render-time checker in python/graphunslopify.
 */

export type Severity = "error" | "warning";

export type Finding = {
  severity: Severity;
  code: string;
  message: string;
  /**
   * A partial spec to merge in, so an agent can apply the fix rather than
   * re-derive it. The agent literature reports models recognising an error and
   * failing to act on it, which is a solvable interface problem.
   */
  fix?: Record<string, unknown>;
};

const MAX_LEGIBLE_SERIES = 8;
const MAX_STACK_SEGMENTS = 6;
const MIN_PUBLICATION_DPI = 300;
const MAX_FACET_PANELS_PER_ROW = 4;

/** Levenshtein, so an unknown field can suggest the column the author meant. */
function editDistance(a: string, b: string): number {
  const rows = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j += 1) rows[0]![j] = j;
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      rows[i]![j] = Math.min(rows[i - 1]![j]! + 1, rows[i]![j - 1]! + 1, rows[i - 1]![j - 1]! + cost);
    }
  }
  return rows[a.length]![b.length]!;
}

/**
 * The column the author probably meant.
 *
 * Two mistakes matter and they need different measures. A typo is close by edit
 * distance. An abbreviation, "acc" for "accuracy", is far by edit distance but
 * is a prefix, and an agent shortening a column name is at least as common as
 * mistyping one.
 */
function nearest(field: string, columns: string[]): string | undefined {
  const needle = field.toLowerCase();

  const abbreviations = columns.filter((column) => {
    const candidate = column.toLowerCase();
    return candidate !== needle && (candidate.startsWith(needle) || needle.startsWith(candidate));
  });
  if (abbreviations.length === 1) return abbreviations[0];
  if (abbreviations.length > 1) {
    return abbreviations.reduce((a, b) => (a.length <= b.length ? a : b));
  }

  let best: { name: string; score: number } | undefined;
  for (const column of columns) {
    const score = editDistance(needle, column.toLowerCase());
    if (!best || score < best.score) best = { name: column, score };
  }
  if (!best) return undefined;
  return best.score <= Math.max(2, Math.floor(field.length / 3)) ? best.name : undefined;
}

type Add = (severity: Severity, code: string, message: string, fix?: Record<string, unknown>) => void;

/**
 * One group of related checks. A rule reports through `add` and never decides
 * whether the figure is acceptable, so the order below is the order a reader
 * sees the findings in.
 */
type Rule = (spec: FigureSpec, add: Add) => void;

const axisLimits: Rule = (spec, add) => {
  for (const [name, axis] of [
    ["x", spec.x],
    ["y", spec.y],
  ] as const) {
    if (!axis.limits) continue;
    const [lo, hi] = axis.limits;
    if (lo >= hi) {
      add("error", "axis_limits_inverted", `${name} limits are [${lo}, ${hi}], so lower is not below upper.`);
    }
    if (axis.scale === "log" && lo <= 0) {
      add(
        "error",
        "log_scale_nonpositive_limit",
        `${name} is on a log scale but its lower limit is ${lo}. A log axis cannot reach zero or below.`,
      );
    }
  }
};

const temporalAxis: Rule = (spec, add) => {
  if (spec.y.temporal) {
    add(
      "error",
      "temporal_y_axis",
      "Only the x axis reads as time. A date on y would need a horizontal timeline, which this " +
        "does not draw.",
      { y: { temporal: false } },
    );
  }

  if (!spec.x.temporal) return;

  if (spec.kind !== "line" && spec.kind !== "scatter") {
    add(
      "error",
      "temporal_x_on_categories",
      `A ${spec.kind} puts categories on x, so it cannot also lay that axis out in time.`,
    );
  }
  if (spec.x.scale !== "linear") {
    add(
      "error",
      "temporal_log_axis",
      `x is temporal but its scale is ${spec.x.scale}. Time is not logarithmic.`,
      { x: { scale: "linear" } },
    );
  }
  if (spec.x.limits) {
    add(
      "error",
      "temporal_axis_limits",
      "x.limits are numbers, so they cannot bound a temporal axis. Filter the rows instead.",
    );
  }
};

const fieldReferences: Rule = (spec, add) => {
  const columns = spec.data.columns;
  if (!columns) return;

  const known = new Set(columns);
  if (spec.series_from_columns) {
    for (const field of spec.series_from_columns.fields) known.delete(field);
    known.add(spec.series_from_columns.series_name);
    known.add(spec.series_from_columns.value_name);
  }
  const refs: [string, string][] = [];
  // Some kinds compute an axis rather than reading it. That axis still needs a
  // label, so it still carries an AxisSpec, but its field names no column.
  if (!derivedAxis(spec, "x")) refs.push(["x.field", spec.x.field]);
  if (!derivedAxis(spec, "y")) refs.push(["y.field", spec.y.field]);
  if (spec.group) refs.push(["group", spec.group]);
  if (spec.facet) refs.push(["facet.by", spec.facet.by]);
  if (spec.facet?.rows) refs.push(["facet.rows", spec.facet.rows]);
  for (const field of spec.repeat?.fields ?? []) refs.push(["repeat.fields", field]);
  for (const layer of spec.layers ?? []) {
    if (layer.y) refs.push(["layer.y", layer.y]);
    if (layer.y2) refs.push(["layer.y2", layer.y2]);
    for (const clause of layer.filter ?? []) refs.push(["layer.filter", clause.field]);
  }
  if (spec.kind === "paired_difference") refs.push(["pair", spec.pair]);
  if (spec.kind === "calibration") refs.push(["outcome", spec.outcome]);
  if (spec.kind === "kaplan_meier") refs.push(["event", spec.event]);
  if (spec.kind === "confusion_matrix" && spec.value) refs.push(["value", spec.value]);
  if (spec.kind === "heatmap") refs.push(["value", spec.value]);
  if (spec.kind === "line" && spec.y2) refs.push(["y2.field", spec.y2.field]);
  for (const clause of spec.filter ?? []) refs.push([`filter on ${clause.field}`, clause.field]);
  if ("uncertainty" in spec && spec.uncertainty?.over) {
    refs.push(["uncertainty.over", spec.uncertainty.over]);
  }
  for (const field of spec.series_from_columns?.fields ?? []) {
    refs.push(["series_from_columns", field]);
  }

  for (const [where, field] of refs) {
    if ((where.startsWith("filter on ") || where === "series_from_columns" ? columns.includes(field) : known.has(field))) continue;
    const guess = nearest(field, columns);
    add(
      "error",
      "unknown_field",
      `${where} refers to "${field}", which is not in data.columns.` +
        (guess ? ` Did you mean "${guess}"?` : ""),
    );
  }
};

const seriesAndEmphasis: Rule = (spec, add) => {
  if (spec.emphasis && !spec.group) {
    add(
      "error",
      "emphasis_without_group",
      "emphasis names a series, but there is no group column, so there is only one series.",
    );
  }

  if (spec.emphasis && spec.series_order && !spec.series_order.includes(spec.emphasis.series)) {
    add(
      "error",
      "emphasis_series_unknown",
      `emphasis.series is "${spec.emphasis.series}", which does not appear in series_order.`,
    );
  }

  if (
    spec.legend.show &&
    !spec.group &&
    spec.kind !== "heatmap" &&
    spec.kind !== "paired_difference"
  ) {
    add(
      "warning",
      "legend_without_group",
      "legend.show is true but there is no group column, so the legend has nothing to list.",
    );
  }

  if (spec.series_order && !spec.group) {
    add("warning", "series_order_without_group", "series_order has no effect without a group column.");
  }

  if (spec.series_order && spec.series_order.length > MAX_LEGIBLE_SERIES) {
    add(
      "warning",
      "too_many_series",
      `${spec.series_order.length} series will not stay distinguishable at column width. ` +
        `Consider faceting, or cutting to ${MAX_LEGIBLE_SERIES}.`,
    );
  }

  if (spec.legend.style === "direct" && !spec.group) {
    add("warning", "direct_labels_without_group", "Direct labelling needs a group to label.");
  }

  if (spec.legend.style === "direct" && hasCategoricalX(spec)) {
    add(
      "warning",
      "direct_labels_on_categories",
      "Direct labelling puts a name at the end of each line. On a categorical chart use a legend.",
    );
  }
};

const rasterResolution: Rule = (spec, add) => {
  if (spec.output.formats.includes("png") && spec.output.dpi < MIN_PUBLICATION_DPI) {
    add(
      "warning",
      "low_dpi_raster",
      `dpi is ${spec.output.dpi}. Most venues want at least ${MIN_PUBLICATION_DPI} for raster figures.`,
    );
  }
};

const transforms: Rule = (spec, add) => {
  const transform = spec.transform;
  if (transform && transform.kind !== "none") {
    const needsBaseline = transform.kind === "delta_vs_baseline" || transform.kind === "percent_of_baseline";
    if (needsBaseline && !transform.baseline) {
      add("error", "transform_needs_baseline", `transform ${transform.kind} needs transform.baseline set.`);
    }
    if (needsBaseline && !spec.group && !spec.series_from_columns) {
      add(
        "error",
        "transform_needs_group",
        `transform ${transform.kind} compares series, so it needs a group column.`,
      );
    }
    if (transform.baseline && spec.series_order && !spec.series_order.includes(transform.baseline)) {
      add(
        "error",
        "baseline_series_unknown",
        `transform.baseline is "${transform.baseline}", which does not appear in series_order.`,
      );
    }
  }

  if (spec.series_from_columns && spec.group) {
    add(
      "error",
      "series_from_columns_conflicts_with_group",
      "series_from_columns creates the grouping column, so group must be left unset.",
    );
  }
  const melt = spec.series_from_columns;
  if (melt && (spec.y.field !== melt.value_name || melt.series_name === melt.value_name
      || new Set(melt.fields).size !== melt.fields.length
      || [melt.series_name, melt.value_name].some(name => spec.data.columns?.includes(name) && !melt.fields.includes(name)))) {
    add("error", "invalid_series_reshape", "Wide-series output needs y.field=value_name, distinct output names and source columns, and no overwritten retained columns.");
  }

};

const uncertainty: Rule = (spec, add) => {
  if (!("uncertainty" in spec) || !spec.uncertainty) return;

  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  if (aggregation === "none") {
    add(
      "error",
      "uncertainty_without_aggregation",
      "uncertainty describes the spread around a summary, so set aggregation to mean or median.",
    );
  }
  if (aggregation !== "none" && aggregation !== "mean" && aggregation !== "median") {
    add("error", "uncertainty_aggregation_unsupported",
      "Uncertainty requires a mean or median over observations; a sum or count has a different sampling meaning.");
  }
  const over = spec.uncertainty.over;
  if (over && [spec.x.field, spec.group, spec.facet?.by, spec.facet?.rows].includes(over)) {
    add("error", "replicate_matches_grouping_key",
      "The replicate identifier must differ from x, group, and facet fields so repeats can vary within a point.");
  }
  if (spec.uncertainty.kind === "iqr" && aggregation === "mean") {
    add(
      "warning",
      "iqr_around_a_mean",
      "An interquartile range is a spread around the median. Pair it with aggregation median.",
    );
  }
  if (spec.uncertainty.kind === "std" && aggregation === "median") {
    add(
      "warning",
      "std_around_a_median",
      "A standard deviation is a spread around the mean. Pair it with aggregation mean.",
    );
  }
  if (spec.kind === "bar" && spec.uncertainty.display === "band") {
    add(
      "warning",
      "band_on_categories",
      "A shaded band across categories implies continuity between them. Use display bar.",
    );
  }
};

const faceting: Rule = (spec, add) => {
  if (!spec.facet) return;

  if (spec.facet.by === spec.group || spec.facet.rows === spec.group && spec.group !== undefined) {
    add(
      "error",
      "facet_by_the_group",
      `facet.by and group are both "${spec.facet.by}", which would give every panel one series.`,
    );
  }
  if (spec.facet.columns > MAX_FACET_PANELS_PER_ROW && spec.output.size === "single_column") {
    add(
      "warning",
      "too_many_panels_per_row",
      `${spec.facet.columns} panels across a single column leaves each one very narrow.`,
    );
  }
  if (spec.facet.rows === spec.facet.by) {
    add("error", "facet_keys_identical", "A two-key grid needs different row and column fields.");
  }

};

const annotations: Rule = (spec, add) => {
  for (const note of spec.annotate ?? []) {
    if (spec.group && !note.series) {
      add(
        "error",
        "annotation_without_series",
        `The annotation "${note.text}" does not say which series to attach to.`,
      );
    }
    if (note.series && spec.series_order && !spec.series_order.includes(note.series)) {
      add(
        "error",
        "annotation_series_unknown",
        `The annotation "${note.text}" targets "${note.series}", which is not in series_order.`,
      );
    }
    if (note.at === "crossover" && !spec.group) {
      add("error", "crossover_needs_two_series", "A crossover annotation needs at least two series.");
    }
  }
};

const referenceLines: Rule = (spec, add) => {
  for (const line of spec.reference_lines ?? []) {
    const axis = line.axis === "x" ? spec.x : spec.y;
    if (axis.scale === "log" && line.value <= 0) {
      add(
        "error",
        "reference_line_off_log_axis",
        `A reference line at ${line.value} cannot sit on the logarithmic ${line.axis} axis.`,
      );
    }
    if (axis.limits && (line.value < axis.limits[0] || line.value > axis.limits[1])) {
      add(
        "warning",
        "reference_line_outside_limits",
        `The reference line at ${line.value} falls outside the ${line.axis} limits, so it will not be visible.`,
      );
    }
  }
};

const barRules: Rule = (spec, add) => {
  if (spec.kind !== "bar") return;

  if (spec.aggregation === "none") {
    add(
      "warning",
      "unaggregated_bar",
      'aggregation is "none", so repeated x values draw overlapping bars instead of a summary. ' +
        "Set mean or median if the data has repeats.",
    );
  }
  if (spec.baseline_zero && spec.y.scale === "log") {
    add(
      "error",
      "log_bar_baseline",
      "baseline_zero is true on a log value axis. A log axis cannot include zero, so pick one.",
    );
  }
  if (spec.stacked && !spec.group) {
    add("error", "stacked_without_group", "Stacking needs a group column to supply the segments.");
  }
  if (spec.stacked && spec.series_order && spec.series_order.length > MAX_STACK_SEGMENTS) {
    add(
      "warning",
      "too_many_stack_segments",
      `${spec.series_order.length} stacked segments cannot be compared by eye. ` +
        "Only the bottom segment shares a baseline.",
    );
  }
  if (spec.stacked && spec.transform?.kind === "delta_vs_baseline") {
    add(
      "error",
      "stacking_signed_values",
      "delta_vs_baseline produces negative values, which cannot be stacked meaningfully.",
    );
  }
  if (spec.significance && !spec.uncertainty) {
    add(
      "warning",
      "significance_without_uncertainty",
      "Marking significance without showing spread asks the reader to trust the test blindly.",
    );
  }
  if (spec.significance?.correction === "none" && spec.significance.pairs.length > 1) {
    add(
      "warning",
      "uncorrected_multiple_comparisons",
      `${spec.significance.pairs.length} significance pairs are tested without correction. ` +
        "Use Holm, or choose Benjamini-Hochberg for an appropriate exploratory family.",
    );
  }
  if (spec.sort && spec.category_order) {
    add("warning", "sort_overrides_category_order", "category_order is ignored when sort is set.");
  }
};

const scatterRules: Rule = (spec, add) => {
  if (spec.kind !== "scatter" || spec.trendline !== "linear") return;

  if (spec.x.scale !== "linear" || spec.y.scale !== "linear") {
    add(
      "warning",
      "trendline_on_log_axis",
      "A linear trendline is fitted in linear space but an axis is not linear, so the drawn " +
        "line is not the fit a reader expects.",
    );
  }
};

const lineRules: Rule = (spec, add) => {
  if (spec.kind !== "line") return;

  if (spec.y2) {
    add(
      "warning",
      "dual_axis_in_use",
      "Two independently scaled y axes can make any pair of series look related. " +
        `Stated justification: ${spec.y2.justification}`,
    );
    if (spec.group) {
      add(
        "error",
        "dual_axis_with_group",
        "A second axis plus multiple series makes it impossible to tell which line uses which scale.",
      );
    }
  }
  if (spec.smooth && spec.aggregation === "none" && !spec.group) {
    add(
      "warning",
      "smoothing_raw_repeats",
      "Smoothing before collapsing repeated x values smooths across the repeats too. " +
        "Set aggregation first.",
    );
  }
};

const heatmapRules: Rule = (spec, add) => {
  if (spec.kind === "heatmap" && spec.diverging && spec.aggregation === "count") {
    add(
      "error",
      "diverging_counts",
      "A diverging scale centres on zero, but counts cannot be negative. Use the default scale.",
    );
  }
};

const animation: Rule = (spec, add) => {
  if (!spec.animate) return;

  if (spec.output.formats.includes("pdf") || spec.output.formats.includes("svg")) {
    add(
      "warning",
      "animation_with_vector_output",
      "An animation is written alongside the stills. The vector exports stay static.",
    );
  }
  if (spec.animate.style === "trace" && hasCategoricalX(spec)) {
    add(
      "warning",
      "trace_on_categories",
      'The "trace" style follows a continuous x. On a categorical chart use "grow" or "reveal".',
    );
  }
  if (spec.animate.style === "grow" && spec.kind !== "bar") {
    add("warning", "grow_outside_bars", 'The "grow" style raises bars. Use "draw" or "reveal" here.');
  }
};

/**
 * Composition features on kinds that cannot carry them.
 *
 * A cut axis is honest on a line or a scatter, where position encodes the
 * value and the reader reads a coordinate. It is not honest where the mark's
 * own size is the value: cutting the axis shortens every mark by the width of
 * the gap, so two bars that differ by five points can come out the same
 * length. That is the failure _check_truncated_bars already treats as an
 * error, moved from the foot of the bar to its middle.
 */
const composition: Rule = (spec, add) => {
  if (spec.output.interactive && interactiveLimitations(spec).length) {
    add("error", "interactive_not_supported", `Interactive export does not reproduce: ${interactiveLimitations(spec).join(", ")}. Use static output or a supported spec.`);
  }
  if (spec.axis_break && hasCategoricalX(spec)) {
    add(
      "error",
      "axis_break_on_length_marks",
      `A ${spec.kind} encodes its value as the length or extent of a mark, so cutting the ` +
        `${spec.axis_break.axis} axis leaves the drawn lengths no longer proportional to the ` +
        `values. Put the value axis on a log scale to bring distant values together, or use ` +
        `kind "table" when the numbers matter more than the comparison.`,
    );
  }
  if (spec.kind === "table" && (spec.facet || spec.repeat || spec.layers?.length || spec.inset || spec.axis_break || spec.animate || spec.output.interactive)) {
    add("error", "table_composition_unsupported", "Tables support cell summaries and static/Markdown/LaTeX output; panel, overlay, cut, animation and interactive options are not implemented.");
  }
  if (spec.facet && spec.repeat) {
    add("error", "facet_repeat_conflict", "Choose row facets or repeated metrics; their combination is not implemented.");
  }
  if (spec.axis_break?.axis === "x") {
    add("error", "x_break_unsupported", "Only y-axis breaks are implemented; an x break must not silently become a y break.");
  }
  if (spec.axis_break && (spec.axis_break.from >= spec.axis_break.to || spec[spec.axis_break.axis].limits)) {
    add("error", "invalid_axis_break", "A cut needs from < to and cannot also set limits on the cut axis.");
  }
  if (spec.axis_break && (spec.facet || spec.repeat || spec.layers?.length || spec.inset)) {
    add("error", "axis_break_composition_unsupported", "Axis breaks currently require one base panel without facets, repeats, layers or insets.");
  }
  if (spec.repeat && (new Set(spec.repeat.fields).size !== spec.repeat.fields.length
      || derivedAxis(spec, "x") || derivedAxis(spec, "y")
      || ["heatmap", "confusion_matrix", "ridgeline", "sparkline_grid"].includes(spec.kind)
      || spec.kind === "bar" && spec.orientation === "horizontal" || spec.kind === "forest" || spec.kind === "dumbbell")) {
    add("error", "unsupported_repeat", "Repeat needs distinct numeric y metrics on a supported vertical value axis; this kind/orientation cannot repeat metrics correctly.");
  }
  for (const layer of spec.layers ?? []) {
    if (layer.mark === "band" && !layer.y2 || layer.mark === "rule" && layer.value === undefined) {
      add("error", "incomplete_layer", "A band needs y2 and a rule needs an explicit value.");
    }
  }

};

const pairedKinds: Rule = (spec, add) => {
  if ((spec.kind === "dumbbell" || spec.kind === "slope") && !spec.group) {
    add(
      "error",
      "comparison_without_group",
      `A ${spec.kind} draws one mark per series and compares them, so it needs a group column. ` +
        "With one series there is nothing to join.",
    );
  }

  if (spec.kind === "paired_difference" && spec.pair === spec.x.field) {
    add(
      "error",
      "pair_is_the_condition",
      "pair names the same column as x, so every unit would be paired with itself. " +
        "pair is the thing measured twice, x is the two conditions it was measured under.",
    );
  }

  if (spec.kind === "paired_difference" && spec.group) {
    add(
      "error",
      "paired_difference_group_ignored",
      "Paired differences compare conditions on x within unit IDs. A raw group cannot be " +
        "silently ignored or used to test claims about a different quantity.",
    );
  }
  if (spec.kind === "paired_difference" && (
      new Set([spec.x.field, spec.y.field, spec.pair]).size !== 3
      || spec.transform && spec.transform.kind !== "none"
      || spec.claims?.length || spec.layers?.length || spec.y.scale === "log")) {
    add("error", "unsupported_paired_semantics",
      "Paired differences need distinct condition, measurement and unit fields. " +
      "Raw-y transforms, series claims and raw overlays are not implemented for matched differences. " +
      "Use linear or symlog y so zero and negative differences remain representable.");
  }
};

const survivalSemantics: Rule = (spec, add) => {
  if (spec.kind !== "kaplan_meier") return;
  const roles = [spec.x.field, spec.y.field, ...(spec.group ? [spec.group] : [])];
  if (spec.transform && spec.transform.kind !== "none"
      || spec.claims?.length && new Set(roles).size !== roles.length) {
    add("error", "unsupported_survival_semantics",
      "Kaplan-Meier estimates use original follow-up/event data, so raw-y transforms are unsupported. " +
      "Survival claims also need distinct time, derived survival-output and cohort field names.");
  }
};

const calibrationSemantics: Rule = (spec, add) => {
  if (spec.kind !== "calibration") return;
  const roles = [spec.x.field, spec.y.field, ...(spec.group ? [spec.group] : [])];
  if (spec.transform && spec.transform.kind !== "none"
      || spec.claims?.length && new Set(roles).size !== roles.length) {
    add("error", "unsupported_calibration_semantics",
      "Calibration computes frequencies from original probabilities/outcomes, so raw-y transforms are unsupported. " +
      "Claims need distinct probability, derived frequency-output and series field names.");
  }
};

const qqSemantics: Rule = (spec, add) => {
  if (spec.kind !== "qq") return;
  const roles = [spec.x.field, spec.y.field, ...(spec.group ? [spec.group] : [])];
  if (spec.transform && !["none", "normalize"].includes(spec.transform.kind)
      || spec.layers?.length || (spec.claims?.length || spec.annotate?.length) && new Set(roles).size !== roles.length
      || spec.distribution === "normal" && spec.x.scale === "log" || spec.x.temporal) {
    add("error", "unsupported_qq_semantics",
      "Q-Q computes theoretical x quantiles. Raw-x transforms/overlays and temporal x are unsupported; " +
      "normalize observed values or transform source data explicitly. Normal theoretical quantiles cannot use log x. " +
      "Derived claims/annotations need distinct theoretical, observed and series field names.");
  }
};

const claims: Rule = (spec, add) => {
  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  const spread = "uncertainty" in spec ? spec.uncertainty : undefined;
  if (spec.claims?.length && aggregation !== "none" && !spread) {
    add(
      "warning",
      "claims_without_uncertainty",
      "The claims will be tested against a summary whose spread was thrown away. " +
        "Collapsing repeats without measuring them means a claim can hold on the means " +
        "while the runs disagree. Set uncertainty.over to the column the repeats vary along.",
    );
  }
  for (const claim of spec.claims ?? []) {
    if (!spec.group) {
      add(
        "error",
        "claim_without_group",
        `The claim about "${claim.subject}" needs a group column, because it names a series.`,
      );
      break;
    }
    if (COMPARATIVE.has(claim.kind) && !claim.reference) {
      add(
        "error",
        "claim_without_reference",
        `A ${claim.kind} claim compares two series, so it needs claim.reference.`,
      );
    }
    if (NEEDS_TOLERANCE.has(claim.kind) && claim.tolerance === undefined) {
      add(
        "error",
        "claim_without_tolerance",
        `A ${claim.kind} claim has to say how close counts, so set claim.tolerance.`,
      );
    }
    if (claim.subject === claim.reference) {
      add("error", "claim_compares_a_series_to_itself", `"${claim.subject}" cannot beat itself.`);
    }
    for (const [role, name] of [
      ["subject", claim.subject],
      ["reference", claim.reference],
    ] as const) {
      if (name && spec.series_order && !spec.series_order.includes(name)) {
        add(
          "error",
          "claim_series_unknown",
          `claim.${role} is "${name}", which does not appear in series_order.`,
        );
      }
    }
  }

  if (spec.claims?.length && spec.kind === "heatmap") {
    add(
      "error",
      "claims_need_series",
      "Claims compare series against each other, which a heatmap does not have.",
    );
  }
};

/** Encoding choice is ranked rather than forbidden, so these are always warnings. */
const encodingChoice: Rule = (spec, add) => {
  for (const suggestion of encodingSuggestions(spec)) {
    add("warning", suggestion.code, suggestion.message, suggestion.patch);
  }
};

export const RULES: Rule[] = [
  axisLimits,
  temporalAxis,
  fieldReferences,
  seriesAndEmphasis,
  rasterResolution,
  transforms,
  uncertainty,
  faceting,
  annotations,
  referenceLines,
  barRules,
  scatterRules,
  lineRules,
  heatmapRules,
  animation,
  composition,
  pairedKinds,
  survivalSemantics,
  calibrationSemantics,
  qqSemantics,
  claims,
  encodingChoice,
];

export function verify(spec: FigureSpec): Finding[] {
  const findings: Finding[] = [];
  const add: Add = (severity, code, message, fix) =>
    findings.push(fix ? { severity, code, message, fix } : { severity, code, message });

  const effective = spec.series_from_columns && !spec.group
    ? { ...spec, group: spec.series_from_columns.series_name } : spec;
  for (const rule of RULES) rule(rule === fieldReferences || rule === transforms ? spec : effective, add);
  return findings;
}

export function hasErrors(findings: Finding[]): boolean {
  return findings.some((f) => f.severity === "error");
}
