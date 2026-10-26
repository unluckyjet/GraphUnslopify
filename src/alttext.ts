import { hasCategoricalX, derivedAxis, type FigureSpec } from "./schema.ts";

/**
 * Alternative text, built from the four-level semantic model in the
 * accessibility literature.
 *
 *   1. the encoding and the axes
 *   2. statistics computed from the data
 *   3. trends and comparisons
 *   4. context a human has to supply
 *
 * Levels 1 to 3 are derivable. The spec knows the encoding, and the script has
 * the data, so most of this writes itself. Level 4 is deliberately left blank
 * rather than invented, because guessing at why a result matters is exactly the
 * kind of confident fabrication that gets figures retracted.
 *
 * Two conventions come straight from the guidance. Alt text does not repeat the
 * caption, and it never opens with "this figure shows", because a screen reader
 * has already announced that it is reading an image.
 */

const KIND_PHRASING: Record<FigureSpec["kind"], string> = {
  line: "Line chart",
  scatter: "Scatter plot",
  bar: "Bar chart",
  box: "Box plot",
  violin: "Violin plot",
  ecdf: "Empirical cumulative distribution",
  raincloud: "Raincloud plot, showing the distribution, its quartiles and every observation",
  ridgeline: "Ridgeline plot, one distribution per row",
  forest: "Forest plot, one effect and its interval per row",
  paired_difference: "Paired-difference plot, showing the differences themselves rather than the two conditions",
  slope: "Slope chart",
  dumbbell: "Dumbbell chart, two values per row joined by a line",
  calibration: "Reliability diagram, comparing predicted probability against observed frequency",
  qq: "Quantile-quantile plot",
  kaplan_meier: "Kaplan-Meier survival curve",
  scaling_fit: "Scaling plot with a fitted power law",
  confusion_matrix: "Confusion matrix",
  waterfall: "Waterfall chart, each step a contribution from the one before",
  sparkline_grid: "Grid of sparklines on a shared scale, one per series",
  heatmap: "Heatmap",
  table: "Table",
};

function axisPhrase(label: string, unit?: string): string {
  return unit ? `${label} in ${unit}` : label;
}

/** Level 1, which needs only the spec. */
export function encodingSentence(spec: FigureSpec): string {
  const kind = KIND_PHRASING[spec.kind];
  const parts: string[] = [];

  if (spec.repeat) {
    parts.push(`${kind} of repeated metrics against ${axisPhrase(spec.x.label, spec.x.unit)}`);
  } else if (spec.kind === "table") {
    parts.push(
      `${kind} of ${axisPhrase(spec.y.label, spec.y.unit)}, one row per ${spec.x.label.toLowerCase()}`,
    );
  } else if (spec.kind === "heatmap") {
    parts.push(
      `${kind} of ${spec.value_label.toLowerCase()}, with ${axisPhrase(spec.x.label, spec.x.unit)} ` +
        `across the horizontal axis and ${axisPhrase(spec.y.label, spec.y.unit)} down the vertical axis`,
    );
  } else if (spec.kind === "qq") {
    const sample = spec.transform?.kind === "normalize"
      ? `normalized ${spec.y.label} (unitless observed range)` : axisPhrase(spec.y.label, spec.y.unit);
    parts.push(`${kind} of ${sample} against ${spec.distribution} theoretical quantiles`);
  } else if (spec.kind === "paired_difference") {
    parts.push(
      `${kind} of changes in ${axisPhrase(spec.y.label, spec.y.unit === "%" ? "percentage points" : spec.y.unit)} ` +
        `against ${spec.x.label}, paired by ${spec.pair} with baseline ${spec.baseline}`,
    );
  } else if (spec.kind === "bar" && spec.orientation === "horizontal") {
    parts.push(
      `${kind} with ${axisPhrase(spec.y.label, spec.y.unit)} along the horizontal axis and ` +
        `${spec.x.label} listed down the vertical axis`,
    );
  } else {
    parts.push(
      `${kind} of ${axisPhrase(spec.y.label, spec.y.unit)} against ` +
        `${axisPhrase(spec.x.label, spec.x.unit)}`,
    );
  }

  if (spec.group) {
    parts.push(
      spec.series_order
        ? `one series per ${spec.group}, with expected order ${spec.series_order.join(", ")}`
        : `one series per ${spec.group}`,
    );
  }

  for (const [name, axis] of [
    ["horizontal", spec.x],
    ["vertical", spec.y],
  ] as const) {
    if (axis.scale === "log") parts.push(`the ${name} axis is logarithmic`);
    if (axis.scale === "symlog") parts.push(`the ${name} axis is symmetric logarithmic`);
  }

  if ("uncertainty" in spec && spec.uncertainty) {
    const wording =
      spec.uncertainty.kind === "ci"
        ? `${Math.round(spec.uncertainty.level * 100)} percent confidence intervals`
        : spec.uncertainty.kind === "sem"
          ? "standard errors"
          : spec.uncertainty.kind === "std"
            ? "standard deviations"
            : spec.uncertainty.kind === "iqr"
              ? "interquartile ranges"
              : "full ranges";
    parts.push(
      spec.uncertainty.display === "band" ? `shaded ${wording}` : `${wording} as error bars`,
    );
  }

  if (spec.emphasis) parts.push(`${spec.emphasis.series} is drawn in the foreground`);

  for (const line of spec.reference_lines ?? []) {
    parts.push(
      `a ${line.meaning === "other" ? "reference" : line.meaning} line at ${line.value}` +
        (line.label ? ` labelled ${line.label}` : ""),
    );
  }

  if (spec.kind === "confusion_matrix") parts.push(spec.normalize === "none" ? "cells contain raw counts"
    : `each ${spec.normalize} is normalized to sum to one when nonempty`);

  if (spec.facet) parts.push(spec.facet.rows
    ? `panels arranged by ${spec.facet.by} across columns and ${spec.facet.rows} down rows`
    : `split into one panel per ${spec.facet.by}`);

  if (spec.axis_break) {
    const name = spec.axis_break.axis === "x" ? "horizontal" : "vertical";
    parts.push(
      `the ${name} axis is cut between ${spec.axis_break.from} and ${spec.axis_break.to}, ` +
        "so distances across the gap are not comparable",
    );
  }
  if (spec.inset) {
    parts.push(
      `an inset in the ${spec.inset.corner.replaceAll("_", " ")} corner magnifies ` +
        `x from ${spec.inset.x[0]} to ${spec.inset.x[1]} and ` +
        `y from ${spec.inset.y[0]} to ${spec.inset.y[1]}`,
    );
  }
  for (const layer of spec.layers ?? []) {
    if (layer.label) parts.push(`a ${layer.mark} layer labelled ${layer.label} is overlaid`);
  }
  if (spec.repeat) parts.push(`one panel per metric: ${spec.repeat.fields.join(", ")}`);

  // Each clause becomes its own sentence, so a screen reader pauses between them.
  return parts.map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(". ") + ".";
}

/**
 * Levels 2 and 3, which need the data, so they are computed by the script.
 * The emitted function returns a sentence, not a paragraph.
 */
export function emitAltText(spec: FigureSpec, out: string[]): void {
  // The grouped summary sorts along x and reads y, so it needs both to be
  // real columns.
  const grouped =
    Boolean(spec.group) &&
    spec.kind !== "heatmap" &&
    spec.kind !== "table" &&
    !derivedAxis(spec, "y") &&
    !derivedAxis(spec, "x");

  out.push(
    "",
    "def describe_figure(frame):",
    '    """Levels 2 and 3 of the alt text: the numbers and the trend."""',
    "    parts = []",
  );
  if ("aggregation" in spec && spec.aggregation !== "none") {
    out.push("    if SAMPLE_SIZE_TEXT:", "        parts.append(SAMPLE_SIZE_TEXT)");
  }

  if (spec.kind === "paired_difference") {
    out.push(...String.raw`
    for estimate in paired_estimates(frame):
        who = f"{estimate['condition']} minus {estimate['baseline']}"
        if estimate["n"]:
            parts.append(f"{who}: mean difference is {estimate['mean']:.3g} over {estimate['n']} matched pairs")
        else:
            parts.append(f"{who}: no complete pairs")
        if estimate["n"] >= 2:
            parts.append(f"95% percentile bootstrap mean interval is [{estimate['low']:.3g}, {estimate['high']:.3g}]")
        else:
            parts.append("interval unavailable with fewer than two matched pairs")
        parts.append(f"of {estimate['units']} units, {estimate['baseline_only']} baseline-only, "
                     f"{estimate['candidate_only']} candidate-only and {estimate['neither']} neither-condition units were excluded")
        if estimate["missing_measurements"]:
            parts.append(f"{estimate['missing_measurements']} missing measurement rows in this comparison")
        if estimate["technical_repeats"]:
            parts.append(f"{estimate['technical_repeats']} technical repeat rows were averaged within unit and condition")
`.split("\n"));
  } else if (spec.kind === "qq") {
    out.push(...String.raw`
    for name in (series_names(frame) if GROUP is not None else [None]):
        curve = qq_estimate(frame if name is None else frame[frame[GROUP] == name])
        who = "the sample" if name is None else str(name)
        parts.append(f"{who}: {curve['observations']} observations with {curve['missing']} missing measurements omitted")
        parts.append(f"sample quartiles are {curve['q1']:.3g}, {curve['median']:.3g}, {curve['q3']:.3g}")
        parts.append(f"the {QQ_DISTRIBUTION} reference uses Blom plotting positions and a population-quartile line "
                     f"with slope {curve['slope']:.4g} and intercept {curve['intercept']:.4g}")
        if curve["constant"]:
            parts.append("constant sample: distribution shape cannot be assessed")
    parts.append("this plot is not a normality test or a test of distributional equivalence")
`.split("\n"));
  } else if (spec.kind === "kaplan_meier") {
    out.push(...String.raw`
    for name in series_names(frame) if GROUP is not None else [None]:
        block = frame if name is None else frame[frame[GROUP] == name]
        curve = survival_estimate(block)
        who = "the cohort" if name is None else f"cohort {name}"
        parts.append(f"{who}: {curve['observations']} observations, {curve['events']} events and "
                     f"{curve['censored']} right-censored records")
        parts.append(f"at follow-up {curve['last']:.3g}, estimated survival is {curve['survival'][-1]:.3g}")
        if curve["median"] is None:
            parts.append("median survival is not reached within the observed follow-up")
        else:
            parts.append(f"median survival is {curve['median']:.3g}")
`.split("\n"));
  } else if (spec.kind === "calibration") {
    out.push(...String.raw`
    for name in series_names(frame) if GROUP is not None else [None]:
        block = frame if name is None else frame[frame[GROUP] == name]
        curve = calibration_estimate(block)
        who = "the model" if name is None else f"model {name}"
        parts.append(f"{who}: expected calibration error is {curve['ece']:.4g} over "
                     f"{curve['observations']} observations in {len(curve['counts'])} of {BINS} bins")
        parts.append(f"plotted mean predicted probabilities run from {curve['probability'].min():.3g} "
                     f"to {curve['probability'].max():.3g}")
        parts.append(f"observed bin frequencies run from {curve['frequency'].min():.3g} "
                     f"to {curve['frequency'].max():.3g}")
`.split("\n"));
  } else if (spec.kind === "confusion_matrix") {
    // Both axes are class labels, so there is no column to average. What a
    // reader wants is how much of the mass sits on the diagonal and which
    // off-diagonal cell is worst.
    out.push(
      "    counts = confusion_counts(frame)",
      "    labels = sorted(set(counts.index) | set(counts.columns), key=str)",
      "    counts = counts.reindex(index=labels, columns=labels, fill_value=0).to_numpy(dtype=float)",
      "    total = counts.sum()",
      "    if total:",
      "        correct = float(np.trace(counts))",
      '        parts.append(f"{correct / total:.1%} of {int(total)} cases fall on the diagonal")',
      "        off = counts - np.diag(np.diag(counts))",
      "        worst = np.unravel_index(int(np.argmax(off)), off.shape)",
      "        if off[worst]:",
      "            parts.append(",
      '                f"the commonest confusion is {labels[worst[0]]} read as "',
      '                f"{labels[worst[1]]}, {int(off[worst])} times"',
      "            )",
    );
  } else if (derivedAxis(spec, "y")) {
    // The vertical axis is a proportion the script computed, so there is
    // nothing to summarise there. What a reader wants is where each
    // distribution sits, which is the median and the quartile spread.
    out.push(
      "    for name in (series_names(frame) if GROUP is not None else [None]):",
      "        block = frame if name is None else frame[frame[GROUP] == name]",
      "        values = block[X_FIELD].dropna().to_numpy(dtype=float)",
      "        if not len(values):",
      "            continue",
      "        low, mid, high = np.percentile(values, [25, 50, 75])",
      "        who = \"the distribution\" if name is None else str(name)",
      '        parts.append(',
      '            f"{who} has a median of {mid:.3g} with the middle half between "',
      '            f"{low:.3g} and {high:.3g} over {len(values)} observations"',
      "        )",
    );
  } else if (spec.kind === "heatmap") {
    out.push(
      `    matrix = frame.pivot_table(index=Y_FIELD, columns=X_FIELD, values=VALUE_FIELD, aggfunc=${JSON.stringify(spec.aggregation)}, sort=False)`,
      "    values = matrix.to_numpy(dtype=float)",
      "    if np.isfinite(values).any():",
      "        row, column = np.unravel_index(np.nanargmax(values), values.shape)",
      '        parts.append(f"Values run from {np.nanmin(values):.3g} to {np.nanmax(values):.3g}")',
      '        parts.append(f"the largest is {values[row,column]:.3g} at {matrix.columns[column]}, {matrix.index[row]}")',
    );
  } else if (grouped) {
    out.push(
      "    ends, absent = {}, []",
      hasCategoricalX(spec) ? "    last = category_order(frame)[-1] if len(frame) else None" : "    last = frame[X_FIELD].dropna().max() if len(frame) else None",
    );
    // Numeric/time endpoints are shared; category endpoints follow the plotted order.
    out.push(
      "    repeated = False",
      "    for name in series_names(frame):",
      "        block = frame[(frame[GROUP] == name) & (frame[X_FIELD] == last)].dropna(subset=[Y_FIELD])",
      "        if len(block):",
      "            ends[name] = float(block[Y_FIELD].mean())",
      "            repeated = repeated or len(block) > 1",
      "        else:", "            absent.append(str(name))",
      "    if ends:",
      "        ranked = sorted(ends.items(), key=lambda kv: -kv[1])",
      "        best, worst = ranked[0], ranked[-1]",
      hasCategoricalX(spec) ? '        location = f"At the final category, {last}"' : '        location = f"At the largest {X_LABEL_PLAIN}"',
      '        qualifier = "mean observed values: " if repeated else ""',
      "        if len(ranked) > 1:",
      '            parts.append(f"{location}, {qualifier}{best[0]} is highest at {best[1]:.3g} and {worst[0]} is lowest at {worst[1]:.3g}")',
      '            parts.append(f"a spread of {best[1]-worst[1]:.3g}")',
      "        else:", '            parts.append(f"{location}, {qualifier}{best[0]} is {best[1]:.3g}")',
      "    if absent:", '        parts.append("No finite measurement at that x for " + ", ".join(absent))',
    );
  } else {
    out.push(
      "    values = frame[Y_FIELD].dropna()",
      "    if len(values):",
      '        parts.append(f"Values run from {values.min():.3g} to {values.max():.3g}")',
      '        parts.append(f"the mean is {values.mean():.3g}")',
    );
  }

  out.push(
    "    if not parts:",
    '        return ""',
    "    # Every clause is its own sentence, so a screen reader pauses between them.",
    '    return ". ".join(part[:1].upper() + part[1:] for part in parts) + "."',
    "",
    "",
    "def alt_text(frame):",
    "    detail = describe_figure(frame)",
    '    body = ENCODING_SENTENCE + (f" {detail}" if detail else "")',
    "    for claim in CLAIMS:",
    '        if claim.get("_verdict") is not True:',
    "            continue",
    '        wording = claim["wording"].replace("{reference}", str(claim.get("reference")))',
    '        sentence = f"{claim[\'subject\']} {wording}"',
    "        # A claim the spread does not separate is not quoted bare. The bands",
    "        # are what persuade a reader to trust the verdict, so a reader who",
    "        # cannot see them is owed the same caveat.",
    '        overlap = overlap_phrase(claim.get("_overlap"))',
    "        if overlap is not None:",
    '            sentence += f", though {overlap}"',
    '        body += " " + sentence[:1].upper() + sentence[1:] + "."',
    "    return body",
    "",
  );
}
