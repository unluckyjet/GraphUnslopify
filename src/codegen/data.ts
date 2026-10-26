import { derivedAxis, type FigureSpec, type FilterOp } from "../schema.ts";
import { pyList, pyStr, pyValue } from "./py.ts";
import { READERS } from "./theme.ts";

/**
 * The data pipeline the generated script runs before anything is drawn.
 *
 * Order matters and is fixed: read, filter, reshape, transform, then summarise.
 * Filtering before transforming means a baseline comparison is computed over
 * the rows that survive, which is what an author asking for both intends.
 */

const OPERATORS: Record<FilterOp, (field: string, value: string) => string> = {
  eq: (f, v) => `df[${f}] == ${v}`,
  ne: (f, v) => `df[${f}] != ${v}`,
  lt: (f, v) => `df[${f}] < ${v}`,
  lte: (f, v) => `df[${f}] <= ${v}`,
  gt: (f, v) => `df[${f}] > ${v}`,
  gte: (f, v) => `df[${f}] >= ${v}`,
  in: (f, v) => `df[${f}].isin(${v})`,
  not_in: (f, v) => `~df[${f}].isin(${v})`,
};

export function emitLoad(spec: FigureSpec, out: string[]): void {
  out.push("", "def load():", `    df = pd.${READERS[spec.data.format]}(DATA_PATH)`);
  out.push('    ROW_COUNTS.clear()', '    ROW_COUNTS["read"] = len(df)');
  if (spec.x.temporal) {
    out.push(
      "    df[X_FIELD] = pd.to_datetime(df[X_FIELD])",
      // A date export in reverse order draws the line backwards, and unlike a
      // numeric x nobody notices until they read the dates.
      "    df = df.sort_values(X_FIELD)",
    );
  }
  out.push("    return df", "");
}

export function emitPrepare(spec: FigureSpec, out: string[]): void {
  out.push("", "def prepare(df):");
  const body: string[] = [];

  for (const clause of spec.filter ?? []) {
    const build = OPERATORS[clause.op];
    body.push(`    df = df[${build(pyStr(clause.field), pyValue(clause.value))}]`);
  }
  body.push('    ROW_COUNTS["after_filter"] = len(df)');
  if (spec.filter?.length) {
    body.push("    if df.empty:", '        raise SystemExit("every row was filtered out")');
  }
  const melt = spec.series_from_columns;
  if (melt) {
    body.push(
      "    # Wide columns become one series each.",
      `    keep = [c for c in df.columns if c not in ${pyList(melt.fields)}]`,
      "    df = df.melt(",
      "        id_vars=keep,",
      `        value_vars=${pyList(melt.fields)},`,
      `        var_name=${pyStr(melt.series_name)},`,
      `        value_name=${pyStr(melt.value_name)},`,
      "    )",
    );
  }

  if (spec.kind === "kaplan_meier" || spec.kind === "calibration" || spec.kind === "paired_difference") {
    const name = spec.kind === "kaplan_meier" ? "survival" : spec.kind === "calibration" ? "calibration" : "paired";
    const label = spec.kind === "kaplan_meier" ? "Kaplan-Meier" : spec.kind === "calibration" ? "Calibration" : "Paired differences";
    body.push(`    ${name}_input(df)`);
    if (spec.transform && spec.transform.kind !== "none") {
      body.push(`    raise ValueError(${pyStr(`${label} does not apply transforms to a raw y column`)})`);
    }
  }

  const transform = spec.transform;
  if (spec.kind !== "kaplan_meier" && spec.kind !== "calibration" && spec.kind !== "paired_difference" && transform && transform.kind !== "none") {
    body.push(...transformBody(spec, transform));
  }

  body.push("    return df");
  out.push(...body, "");
}

/** Figure-wide accounting uses the prepared rows, before any panel is drawn. */
export function emitCounts(spec: FigureSpec, out: string[]): void {
  const aggregated = "aggregation" in spec && spec.aggregation !== "none";
  const measure = spec.kind === "confusion_matrix" || derivedAxis(spec, "y")
    ? undefined : spec.kind === "heatmap" ? spec.value : spec.y.field;
  const fields = spec.repeat?.fields ?? (measure ? [measure] : []);
  const keys = spec.kind === "heatmap"
    ? [spec.x.field, spec.y.field]
    : [spec.x.field, ...(spec.group ? [spec.group] : []), ...(spec.facet ? [spec.facet.by, ...(spec.facet.rows ? [spec.facet.rows] : [])] : [])];
  const filters = spec.filter?.map(f => `${f.field} ${f.op} ${JSON.stringify(f.value)}`).join(" and ") || "none";
  const over = "uncertainty" in spec ? spec.uncertainty?.over : undefined;
  out.push(
    "", "ROW_COUNTS = {}", 'SAMPLE_SIZE_TEXT = ""', "",
    "def report_counts(frame):",
    "    global SAMPLE_SIZE_TEXT",
    '    SAMPLE_SIZE_TEXT = ""',
    '    ROW_COUNTS["prepared"] = len(frame)',
    '    print(f"data: {DATA_PATH}, sha256 {DATA_HASH}")',
    '    print(f"  {ROW_COUNTS.get(\'read\', len(frame))} rows read")',
    `    print(f"  {ROW_COUNTS.get('after_filter', len(frame))} rows after filter (" + ${pyStr(filters)} + ")")`,
    '    if len(frame) != ROW_COUNTS.get("after_filter", len(frame)):',
    '        print(f"  {len(frame)} rows after reshape and transform")',
  );
  const plotKeys = [...new Set([
    ...(!derivedAxis(spec, "x") ? [spec.x.field] : []),
    ...(["heatmap", "confusion_matrix"].includes(spec.kind) ? [spec.y.field] : []),
    ...(spec.group ? [spec.group] : []),
    ...(spec.facet ? [spec.facet.by, ...(spec.facet.rows ? [spec.facet.rows] : [])] : []),
  ])];
  out.push(
    `    plot_keys = [field for field in ${pyList(plotKeys)} if field in frame]`,
    '    ROW_COUNTS["missing_plot_keys"] = int(frame[plot_keys].isna().any(axis=1).sum()) if plot_keys else 0',
    '    if ROW_COUNTS["missing_plot_keys"]:',
    '        print(f"warning: {ROW_COUNTS[\'missing_plot_keys\']} rows lack plotting keys and cannot be assigned to a point, panel or series")',
  );
  if (spec.group) out.push(
    "    if SERIES_ORDER is not None and GROUP in frame:",
    '        ROW_COUNTS["unlisted_series"] = [str(name) for name in frame[GROUP].dropna().unique() if name not in SERIES_ORDER]',
  );
  out.push(
    '    ROW_COUNTS["measurements"] = {}',
    `    for field in ${pyList(fields)}:`,
    "        if field not in frame:", "            continue",
    '        finite = np.isfinite(pd.to_numeric(frame[field], errors="coerce").to_numpy(dtype=float))',
    '        counts = {"finite": int(finite.sum()), "nonfinite": int((~finite).sum())}',
    '        ROW_COUNTS["measurements"][field] = counts',
    '        print(f"  {counts[\'finite\']} rows with a finite {field} ({counts[\'nonfinite\']} non-finite)")',
  );
  if (measure) {
    out.push(
      `    if ${pyStr(measure)} in ROW_COUNTS["measurements"]:`,
      `        ROW_COUNTS.update(ROW_COUNTS["measurements"][${pyStr(measure)}])`,
    );
  }
  if (aggregated) {
    out.push(
      "    sizes = []",
      `    keys = ${pyList([...new Set(keys)])}`,
      `    for field in ${pyList(fields)}:`,
      "        if field not in frame:", "            continue",
      "        source = summary_input(frame, field)",
      '        measured = source.assign(_finite=np.isfinite(pd.to_numeric(source[field], errors="coerce")).astype(int))',
      '        sizes.extend(measured.groupby(keys, sort=False)["_finite"].sum().tolist())',
      '    ROW_COUNTS["sample_sizes"] = [int(n) for n in sizes]',
      "    if sizes:",
      "        low, high = int(min(sizes)), int(max(sizes))",
      '        SAMPLE_SIZE_TEXT = f"n = {low} per point" if low == high else f"n ranges from {low} to {high} across {len(sizes)} points"',
      ...(over ? [`        SAMPLE_SIZE_TEXT += ${pyStr(` (unit IDs: ${over})`)}`] : []),
      '        print(f"  {SAMPLE_SIZE_TEXT}")',
      "        if low != high:",
      '            print("warning: sample sizes differ between groups")',
    );
    if (over && measure) {
      out.push(
        `    unit = ${pyStr(over)}`,
        '    ROW_COUNTS["unit_column"] = unit',
        '    ROW_COUNTS["missing_unit_ids"] = int(frame[unit].isna().sum())',
        `    unit_values = summary_input(frame, ${pyStr(measure)})[${pyStr(measure)}]`,
        '    ROW_COUNTS["unit_observations"] = int(np.isfinite(unit_values).sum())',
        '    print(f"  {ROW_COUNTS[\'unit_observations\']} unit observations after grouping repeated {unit} IDs within each point")',
        '    if ROW_COUNTS["missing_unit_ids"]:',
        '        print(f"warning: {ROW_COUNTS[\'missing_unit_ids\']} rows have no {unit} identifier and cannot contribute to uncertainty")',
      );
    }
  }
  out.push("");
}

/** Numeric summaries use finite measurements and one value per declared unit. */
export function emitSummaryInput(spec: FigureSpec, out: string[]): void {
  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  const over = "uncertainty" in spec ? spec.uncertainty?.over : undefined;
  out.push("", "def summary_input(frame, field):");
  if (aggregation !== "mean" && aggregation !== "median") {
    out.push("    return frame", "");
    return;
  }
  out.push(
    "    measured = frame.copy()",
    '    measured[field] = pd.to_numeric(measured[field], errors="coerce").replace([np.inf, -np.inf], np.nan)',
  );
  if (over) {
    const keys = [...new Set([spec.x.field, ...(spec.group ? [spec.group] : []),
      ...(spec.facet ? [spec.facet.by, ...(spec.facet.rows ? [spec.facet.rows] : [])] : []), over])];
    out.push(
      `    if ${pyStr(over)} not in measured:`,
      `        raise ValueError(${pyStr(`replicate identifier column ${over} is missing`)})`,
      `    measured = measured.groupby(${pyList(keys)}, as_index=False, sort=False)[field].${aggregation}()`,
      "    if measured.empty:",
      `        raise ValueError(${pyStr(`no usable replicate identifiers in ${over}`)})`,
    );
  }
  out.push("    return measured", "");
}

function transformBody(
  spec: FigureSpec,
  transform: NonNullable<FigureSpec["transform"]>,
): string[] {
  const value = spec.kind === "heatmap" ? "VALUE_FIELD" : "Y_FIELD";

  if (transform.kind === "cumulative") {
    return [
      "    # Running total along x within each series.",
      "    order = [X_FIELD] if GROUP is None else [GROUP, X_FIELD]",
      "    df = df.sort_values(order)",
      `    key = GROUP if GROUP is not None else lambda _: 0`,
      `    df[${value}] = df.groupby(key, sort=False)[${value}].cumsum()`,
    ];
  }

  if (transform.kind === "normalize") {
    return [
      "    # Rescale each series to its own 0-1 range.",
      "    def _unit(values):",
      "        low, high = values.min(), values.max()",
      "        return values * 0 if high == low else (values - low) / (high - low)",
      "    if GROUP is None:",
      `        df[${value}] = _unit(df[${value}])`,
      "    else:",
      `        df[${value}] = df.groupby(GROUP, sort=False)[${value}].transform(_unit)`,
    ];
  }

  const percent = transform.kind === "percent_of_baseline";
  return [
    `    # Compare every series against ${pyStr(transform.baseline ?? "")}.`,
    "    reference = (",
    "        df[df[GROUP] == BASELINE_SERIES]",
    `        .groupby(X_FIELD, sort=False)[${value}]`,
    "        .mean()",
    "    )",
    "    if reference.empty:",
    '        raise SystemExit(f"baseline series {BASELINE_SERIES!r} is not in the data")',
    "    matched = df[X_FIELD].map(reference)",
    percent
      ? `    df[${value}] = 100.0 * df[${value}] / matched`
      : `    df[${value}] = df[${value}] - matched`,
    "    df = df[df[GROUP] != BASELINE_SERIES]",
  ];
}

/**
 * Collapsing repeats and measuring their spread.
 *
 * The confidence interval is a percentile bootstrap rather than a t interval,
 * so the script needs numpy and nothing else, and it makes no assumption about
 * the shape of the distribution over seeds.
 */
export function emitSummarise(spec: FigureSpec, out: string[]): void {
  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  const uncertainty = "uncertainty" in spec ? spec.uncertainty : undefined;

  out.push("", "def summarise(frame):");
  if (aggregation === "none") {
    out.push("    return frame", "");
    return;
  }

  out.push(
    "    frame = summary_input(frame, Y_FIELD)",
    "    keys = [X_FIELD] + ([GROUP] if GROUP is not None else [])",
    "    # sort=False keeps the file's category order instead of an alphabetical one.",
    "    grouped = frame.groupby(keys, as_index=False, sort=False)[Y_FIELD]",
    `    summary = grouped.${aggregation === "median" ? "median" : aggregation}()`,
  );

  if (!uncertainty) {
    out.push("    return summary", "");
    return;
  }

  out.push(
    "    spread = frame.groupby(keys, sort=False)[Y_FIELD]",
    "    centre = summary[Y_FIELD].to_numpy(dtype=float)",
  );

  switch (uncertainty.kind) {
    case "std":
      out.push(
        "    width = spread.std(ddof=1).to_numpy(dtype=float)",
        "    low, high = centre - width, centre + width",
      );
      break;
    case "sem":
      out.push(
        "    width = spread.sem(ddof=1).to_numpy(dtype=float)",
        "    low, high = centre - width, centre + width",
      );
      break;
    case "range":
      out.push(
        "    low = spread.min().to_numpy(dtype=float)",
        "    high = spread.max().to_numpy(dtype=float)",
      );
      break;
    case "iqr":
      out.push(
        "    low = spread.quantile(0.25).to_numpy(dtype=float)",
        "    high = spread.quantile(0.75).to_numpy(dtype=float)",
      );
      break;
    case "ci":
      out.push(
        "    low, high = bootstrap_interval(frame, keys)",
      );
      break;
    default: {
      const unhandled: never = uncertainty.kind;
      throw new Error(`no spread emitter for uncertainty ${String(unhandled)}`);
    }
  }

  // Keep the NaN. Substituting the centre turned "no interval could be
  // measured" into "the interval is exactly zero", which draws a band pinched
  // to a hairline and reads as perfect agreement across seeds.
  out.push(
    "    # A singleton has no measured spread, including for range and IQR.",
    "    counts = spread.count().to_numpy()",
    "    low = np.where(counts >= 2, low, np.nan)",
    "    high = np.where(counts >= 2, high, np.nan)",
    '    summary["_low"] = low',
    '    summary["_high"] = high',
    "    return summary",
    "",
  );
}

/**
 * The line that says a band is absent because nothing was measurable.
 *
 * Cumming, Fidler and Vaux put it as a rule: error bars are for independently
 * repeated experiments, never for replicates. A group of one was not repeated,
 * so it gets no bar and the reader gets told why.
 *
 * Counting and printing are separate because the count belongs to the figure
 * and the summary belongs to a panel. Each panel notes what it drew, and main
 * prints one line at the end. Reporting from inside summarise() printed twice
 * on a plain figure, since main summarises again for the alt text, and once per
 * panel with a panel-local denominator on a faceted one.
 */
export function emitMissingIntervalReport(spec: FigureSpec, out: string[]): void {
  if (!needsMissingIntervalReport(spec)) return;

  out.push(
    "",
    "PANEL_KEY = 0",
    "MISSING_INTERVALS = {}",
    "",
    "",
    "def note_missing_interval(summary):",
    "    # Keyed by panel, which is the only thing that tracks the points a reader",
    "    # sees. Not by axes: a cut axis draws one panel above and below the break,",
    "    # and an inset redraws its parent magnified, so both must count once. Not",
    "    # by frame either: repeat hands every panel the same frame with a",
    "    # different y field, so frame identity collapses them.",
    '    if "_low" not in summary or PANEL_KEY in MISSING_INTERVALS:',
    "        return",
    '    missing = ~np.isfinite(summary["_low"].to_numpy(dtype=float))',
    "    names = set()",
    "    if GROUP is not None and missing.any():",
    "        names = {str(value) for value in summary.loc[missing, GROUP]}",
    "    MISSING_INTERVALS[PANEL_KEY] = (int(missing.sum()), len(summary), names)",
    "",
    "",
    "def report_missing_interval():",
    "    counted = list(MISSING_INTERVALS.values())",
    "    missing = sum(count for count, _, _ in counted)",
    "    if missing == 0:",
    "        return",
    "    total = sum(size for _, size, _ in counted)",
    "    names = sorted(set().union(*(seen for _, _, seen in counted)))",
    "    detail = f\" (series: {', '.join(names)})\" if names else \"\"",
    "    print(",
    '        f"uncertainty: {missing} of {total} points have fewer than 2 "',
    '        f"observations, so no interval is drawn for them{detail}"',
    "    )",
    "",
  );
}

/** Whether the script collapses repeats and measures their spread at all. */
export function needsMissingIntervalReport(spec: FigureSpec): boolean {
  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  if (aggregation === "none") return false;
  return "uncertainty" in spec && Boolean(spec.uncertainty);
}

export function emitBootstrap(spec: FigureSpec, out: string[]): void {
  const uncertainty = "uncertainty" in spec ? spec.uncertainty : undefined;
  if (uncertainty?.kind !== "ci") return;

  const centre = "aggregation" in spec && spec.aggregation === "median" ? "median" : "mean";
  out.push(
    "",
    "def bootstrap_interval(frame, keys):",
    "    # Percentile bootstrap, so no distributional assumption and no scipy.",
    "    rng = np.random.default_rng(BOOTSTRAP_SEED)",
    "    lows, highs = [], []",
    "    for _, block in frame.groupby(keys, sort=False):",
    "        values = block[Y_FIELD].dropna().to_numpy(dtype=float)",
    "        if len(values) < 2:",
    "            lows.append(np.nan)",
    "            highs.append(np.nan)",
    "            continue",
    "        draws = rng.choice(values, size=(BOOTSTRAP_DRAWS, len(values)), replace=True)",
    `        stat = np.${centre}(draws, axis=1)`,
    "        tail = (1.0 - CI_LEVEL) / 2.0",
    "        lows.append(float(np.quantile(stat, tail)))",
    "        highs.append(float(np.quantile(stat, 1.0 - tail)))",
    "    return np.array(lows), np.array(highs)",
    "",
  );
}

export function emitSmooth(spec: FigureSpec, out: string[]): void {
  if (spec.kind !== "line" || !spec.smooth) return;
  const { kind, window } = spec.smooth;
  out.push(
    "",
    "def smooth(values):",
    kind === "ema"
      ? `    return values.ewm(span=${window}, adjust=False).mean()`
      : `    return values.rolling(${window}, min_periods=1, center=True).mean()`,
    "",
  );
}
