import { RUNTIME_HELPERS } from "./runtime-source.ts";
import { derivedAxis, type FigureSpec, type FilterOp } from "../schema.ts";
import { pyList, pyStr, pyValue } from "./py.ts";
import { READERS } from "./theme.ts";
import { identityFields, identityConflicts, requiredIdentityFields, numericFields } from "../identity.ts";
import { WORKBOOK_SOURCE } from "./workbook-source.ts";
import { OBSERVATION_SOURCE_SHA256 } from "./observation-source.ts";

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

export function emitLoad(spec: FigureSpec, out: string[], traceObservations: boolean): void {
  const identities = identityFields(spec);
  if (spec.data.format === "excel") out.push("", WORKBOOK_SOURCE);
  if (traceObservations) {
    out.push("", "from graphunslopify import observation_provenance as _observations",
      `if hashlib.sha256(Path(_observations.__file__).read_bytes()).hexdigest() != ${pyStr(OBSERVATION_SOURCE_SHA256)}:`,
      '    raise RuntimeError("Observation capture requires the matching GraphUnslopify runtime")');
  }
  out.push("", `IDENTITY_FIELDS = ${pyList(identities)}`,
    `REQUIRED_IDENTITY_FIELDS = ${pyList(requiredIdentityFields(spec))}`,
    `IDENTITY_CONFLICTS = ${pyList(identityConflicts(spec))}`);
  out.push(...String.raw`

${RUNTIME_HELPERS.normalize_identities}
`.split("\n"));
  out.push("", "def load():", "    global DATA_HASH",
    '    with pd.io.common.get_handle(DATA_PATH, "rb", compression=None, is_text=False) as raw:',
    "        snapshot = raw.handle.read()",
    ...(traceObservations
      ? ['        transport_compression = raw.compression.get("method")', "        decoded = transport_compression is not None"]
      : ['        decoded = raw.compression.get("method") is not None']),
    "    DATA_HASH = hashlib.sha256(snapshot).hexdigest()[:16]");
  if (spec.data.format !== "parquet" && spec.data.format !== "excel") {
    out.push(
      "    # Keep pandas' filename-based compression behavior on the byte snapshot.",
      '    compression = None if decoded else pd.io.common.infer_compression(DATA_PATH, "infer")',
      '    with pd.io.common.get_handle(io.BytesIO(snapshot), "rb", compression=compression, is_text=False) as handle:',
      "        payload = handle.handle.read()",
    );
  } else out.push("    payload = snapshot");
  if (traceObservations && spec.data.format === "parquet") {
    out.push("    from pandas.io.parquet import get_engine",
      '    engine = get_engine("auto")',
      "    df = engine.read(io.BytesIO(payload))");
  } else {
    out.push(spec.data.format === "excel"
      ? `    df = read_excel_table(io.BytesIO(payload), sheet=${spec.data.sheet === undefined ? "None" : pyStr(spec.data.sheet)}, identity_fields=IDENTITY_FIELDS)`
      : `    df = pd.${READERS[spec.data.format]}(io.BytesIO(payload))`);
  }
  if (spec.data.format === "json" || identities.length && spec.data.format === "csv") {
    out.push(
      "    # Preserve names from the same bytes; filters still see the typed frame.",
      spec.data.format === "csv"
        ? '    names = pd.read_csv(io.BytesIO(payload), dtype={field: "string" for field in IDENTITY_FIELDS})'
        : "    names = pd.DataFrame(json.loads(payload), dtype=object)",
      "    if len(names) != len(df):",
      '        raise ValueError("Identifier and measurement rows do not align")',
      ...(spec.data.format === "json" ? [
        "    if len(names.columns) != len(df.columns):",
        '        raise ValueError("Identifier and measurement columns do not align")',
        "    df.columns = names.columns",
      ] : []),
      "    df = df.reset_index(drop=True)",
      '    df.attrs["_graphunslopify_identity_rows"] = {',
      "        field: names[field].to_numpy(dtype=object, na_value=None).tolist()",
      "        for field in IDENTITY_FIELDS if field in names}",
    );
  }
  out.push('    ROW_COUNTS.clear()', '    ROW_COUNTS["read"] = len(df)');
  if (traceObservations) {
    out.push(
      `    reader = {"format": ${pyStr(spec.data.format)}, "pandas_version": pd.__version__,`,
      '              "transport_compression": transport_compression, "identity_fields": IDENTITY_FIELDS}',
      ...(spec.data.format === "excel" ? [
        '    reader.update(sheet=df.attrs["_graphunslopify_excel_sheet"],',
        '                  engine=df.attrs["_graphunslopify_excel_engine"])',
      ] : spec.data.format === "parquet" ? [
        "    reader.update(engine=engine.api.__name__, engine_version=engine.api.__version__)",
      ] : ["    reader.update(compression=compression)"]),
      "    selection = _observations._ObservationSelection(",
      "        snapshot, reader=reader, record_count=len(df), spec_json=SPEC_JSON,",
      '        program_sha256=script_fingerprint(), runtime_sha256=RUNTIME_BINDING["source_sha256"])',
    );
  }
  if (spec.x.temporal) {
    out.push(
      "    df[X_FIELD] = pd.to_datetime(df[X_FIELD])",
      // A date export in reverse order draws the line backwards, and unlike a
      // numeric x nobody notices until they read the dates.
      traceObservations ? "    df = selection.sort(df, X_FIELD)" : "    df = df.sort_values(X_FIELD)",
    );
  }
  out.push(traceObservations ? "    return df, selection" : "    return df", "");
}

export function emitPrepare(spec: FigureSpec, out: string[], traceObservations: boolean): void {
  const ordinary = !["kaplan_meier", "calibration", "paired_difference", "qq", "scaling_fit", "ridgeline", "confusion_matrix"].includes(spec.kind);
  if (ordinary) {
    // Mean/median summaries already retain finite measurements with explicit counts.
    const summarized = "aggregation" in spec && ["mean", "median"].includes(spec.aggregation)
      ? [spec.y.field, ...(spec.repeat?.fields ?? [])] : [];
    const numeric = numericFields(spec).filter(field => !(spec.x.temporal && field === spec.x.field)
      && (!summarized.includes(field) || field === spec.x.field));
    out.push("", traceObservations ? "def validate_numeric_domains(frame, selection):" : "def validate_numeric_domains(frame):",
      `    for field in ${pyList(numeric)}:`,
      "        if field not in frame:", "            continue",
      '        measured = pd.to_numeric(frame[field], errors="coerce")',
      '        values = measured.to_numpy(dtype=float, na_value=np.nan)',
      "        if (frame[field].notna() & measured.isna()).any() or np.isinf(values).any():",
      '            raise ValueError(f"Field {field} requires finite numeric measurements or missing values; filter invalid observations explicitly")',
      "        if isinstance(measured.dtype, pd.api.extensions.ExtensionDtype) and measured.isna().any():",
      "            measured = measured.astype(object).where(measured.notna(), np.nan)",
      ...(traceObservations ? ['        selection.numeric(field, frame[field], measured, "numeric_domain")'] : []),
      "        frame[field] = measured",
      "");
  }
  out.push("", traceObservations ? "def prepare(df, selection):" : "def prepare(df):");
  const body: string[] = [];

  if (spec.filter?.length) {
    body.push('    ROW_COUNTS["filtering"] = {"source_rows": len(df), "steps": []}');
  }

  for (const [index, clause] of (spec.filter ?? []).entries()) {
    const build = OPERATORS[clause.op];
    const mask = build(pyStr(clause.field), pyValue(clause.value));
    body.push("    before = len(df)");
    body.push(traceObservations ? `    df = selection.filter(df, ${mask}, ${index})` : `    df = df[${mask}]`);
    body.push(`    step = json.loads(${pyStr(JSON.stringify(clause))})`,
      '    step.update(before=before, after=len(df), removed=before - len(df))',
      '    ROW_COUNTS["filtering"]["steps"].append(step)');
  }
  body.push('    ROW_COUNTS["after_filter"] = len(df)');
  if (traceObservations) {
    body.push(`    selection.seal_filters(${spec.x.temporal ? "X_FIELD" : "None"}, ${spec.filter?.length ?? 0})`);
  }
  if (spec.filter?.length) {
    body.push('    ROW_COUNTS["filtering"].update(retained_rows=len(df), removed_rows=ROW_COUNTS["filtering"]["source_rows"] - len(df))',
      "    if df.empty:", '        raise SystemExit("every row was filtered out")');
  }
  const melt = spec.series_from_columns;
  const normalize = (final: boolean) => traceObservations
    ? `    df = selection.identifiers(df, normalize_identities, IDENTITY_FIELDS${final ? "" : ", final=False"})`
    : `    df = normalize_identities(df${final ? "" : ", final=False"})`;
  const validate = traceObservations ? "    validate_numeric_domains(df, selection)" : "    validate_numeric_domains(df)";
  const numericInput = (name: string, fields: string[]) => {
    if (traceObservations) body.push("    before_numeric = df");
    body.push(`    df = ${name}_input(df)`);
    if (traceObservations) body.push(...fields.map(field =>
      `    selection.numeric(${field}, before_numeric[${field}], df[${field}], "${name}_input")`));
  };
  body.push(normalize(!melt));
  if (melt) {
    body.push(
      "    # Wide columns become one series each.",
      `    keep = [c for c in df.columns if c not in ${pyList(melt.fields)}]`,
      traceObservations ? "    df = selection.melt(df," : "    df = df.melt(",
      "        id_vars=keep,",
      `        value_vars=${pyList(melt.fields)},`,
      `        var_name=${pyStr(melt.series_name)},`,
      `        value_name=${pyStr(melt.value_name)},`,
      "    )",
      normalize(true),
    );
  }
  if (ordinary) body.push(validate);

  if (spec.kind === "kaplan_meier" || spec.kind === "calibration" || spec.kind === "paired_difference") {
    const name = spec.kind === "kaplan_meier" ? "survival" : spec.kind === "calibration" ? "calibration" : "paired";
    const label = spec.kind === "kaplan_meier" ? "Kaplan-Meier" : spec.kind === "calibration" ? "Calibration" : "Paired differences";
    body.push(`    ${name}_input(df)`);
    if (spec.transform && spec.transform.kind !== "none") {
      body.push(`    raise ValueError(${pyStr(`${label} does not apply transforms to a raw y column`)})`);
    }
  }

  if (spec.kind === "qq") {
    numericInput("qq", ["Y_FIELD"]);
    if (spec.transform && !["none", "normalize"].includes(spec.transform.kind)) {
      body.push('    raise ValueError("Q-Q raw-x transforms are unsupported; normalize observations or transform the source data explicitly")');
    }
  }

  if (spec.kind === "scaling_fit") numericInput("scaling", ["X_FIELD", "Y_FIELD"]);

  const transform = spec.transform;
  if (spec.kind !== "kaplan_meier" && spec.kind !== "calibration" && spec.kind !== "paired_difference" && transform && transform.kind !== "none"
      && (spec.kind !== "qq" || transform.kind === "normalize")) {
    body.push(...transformBody(spec, transform, traceObservations));
    if (spec.kind === "qq") numericInput("qq", ["Y_FIELD"]);
    if (spec.kind === "scaling_fit") numericInput("scaling", ["X_FIELD", "Y_FIELD"]);
    if (ordinary) body.push(validate);
  }

  if (traceObservations) body.push("    selection.finish_preparation(df)");
  body.push("    return df");
  out.push(...body, "");
}

/** Figure-wide accounting uses the prepared rows, before any panel is drawn. */
export function emitCounts(spec: FigureSpec, out: string[]): void {
  const aggregated = "aggregation" in spec && spec.aggregation !== "none";
  const measure = spec.kind === "ecdf" ? spec.x.field : spec.kind === "confusion_matrix" || derivedAxis(spec, "y")
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
      '        sizes.extend(measured.groupby(keys, sort=False, observed=True)["_finite"].sum().tolist())',
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
export function emitSummaryInput(spec: FigureSpec, out: string[], traceSummary: boolean): void {
  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  const over = "uncertainty" in spec ? spec.uncertainty?.over : undefined;
  const recordsMembership = traceSummary && (aggregation === "mean" || aggregation === "median");
  out.push("", recordsMembership
    ? "def summary_input(frame, field, *, membership=False):"
    : "def summary_input(frame, field):");
  if (aggregation !== "mean" && aggregation !== "median") {
    out.push("    return frame", "");
    return;
  }
  out.push(
    "    measured = frame.copy()",
    ...(recordsMembership ? [
      '    numeric = pd.to_numeric(measured[field], errors="coerce")',
      '    measured[field] = numeric.replace([np.inf, -np.inf], np.nan)',
      "    if membership:",
      "        witness = _observations._summary_input_witness(frame[field], numeric, measured[field])",
    ] : ['    measured[field] = pd.to_numeric(measured[field], errors="coerce").replace([np.inf, -np.inf], np.nan)']),
  );
  if (over) {
    const keys = [...new Set([spec.x.field, ...(spec.group ? [spec.group] : []),
      ...(spec.facet ? [spec.facet.by, ...(spec.facet.rows ? [spec.facet.rows] : [])] : []), over])];
    out.push(
      `    if ${pyStr(over)} not in measured:`,
      `        raise ValueError(${pyStr(`replicate identifier column ${over} is missing`)})`,
      ...(recordsMembership ? [
        `    units = measured.groupby(${pyList(keys)}, as_index=False, sort=False, observed=True)[field]`,
        `    measured = units.${aggregation}()`,
      ] : [`    measured = measured.groupby(${pyList(keys)}, as_index=False, sort=False, observed=True)[field].${aggregation}()`]),
      "    if measured.empty:",
      `        raise ValueError(${pyStr(`no usable replicate identifiers in ${over}`)})`,
    );
  }
  if (recordsMembership) out.push(
    "    if membership:",
    over
      ? "        return measured, witness, _observations._summary_group_codes(units), measured[field].tolist()"
      : "        return measured, witness, None, None",
  );
  out.push("    return measured", "");
}

function transformBody(
  spec: FigureSpec,
  transform: NonNullable<FigureSpec["transform"]>,
  traceObservations: boolean,
): string[] {
  const value = spec.kind === "heatmap" ? "VALUE_FIELD" : "Y_FIELD";

  if (transform.kind === "cumulative") {
    return [
      "    # Running total along x within each series.",
      "    order = [X_FIELD] if GROUP is None else [GROUP, X_FIELD]",
      traceObservations ? "    df = selection.sort(df, order)" : "    df = df.sort_values(order)",
      `    key = GROUP if GROUP is not None else lambda _: 0`,
      ...(traceObservations ? [
        `    before_transform = df[${value}]`,
        `    grouped = df.groupby(key, sort=False, observed=True)[${value}]`,
        `    df[${value}] = grouped.cumsum()`,
        `    selection.cumulative(${value}, before_transform, df[${value}], grouped.indices)`,
      ] : [`    df[${value}] = df.groupby(key, sort=False, observed=True)[${value}].cumsum()`]),
    ];
  }

  if (transform.kind === "normalize") {
    return [
      "    # Rescale each series to its own 0-1 range.",
      ...(traceObservations ? [`    before_transform = df[${value}]`, "    ranges = {}"] : []),
      "    def _unit(values):",
      "        low, high = values.min(), values.max()",
      ...(traceObservations ? ["        ranges[values.name] = (low, high)"] : []),
      "        return values * 0 if high == low else (values - low) / (high - low)",
      "    if GROUP is None:",
      `        df[${value}] = _unit(df[${value}])`,
      ...(traceObservations ? ["        groups = {before_transform.name: range(len(df))}"] : []),
      "    else:",
      ...(traceObservations ? [
        `        grouped = df.groupby(GROUP, sort=False, observed=True)[${value}]`,
        `        df[${value}] = grouped.transform(_unit)`,
        "        groups = grouped.indices",
        `    selection.normalize(${value}, before_transform, df[${value}], groups, ranges)`,
      ] : [`        df[${value}] = df.groupby(GROUP, sort=False, observed=True)[${value}].transform(_unit)`]),
    ];
  }

  const percent = transform.kind === "percent_of_baseline";
  return [
    `    # Compare every series against ${pyStr(transform.baseline ?? "")}.`,
    ...(traceObservations ? [
      `    before_transform = df[${value}]`,
      "    baseline_mask = df[GROUP] == BASELINE_SERIES",
      `    baseline = df[baseline_mask].groupby(X_FIELD, sort=False, observed=True)[${value}]`,
      "    reference = baseline.mean()",
    ] : [
      "    reference = (",
      "        df[df[GROUP] == BASELINE_SERIES]",
      `        .groupby(X_FIELD, sort=False, observed=True)[${value}]`,
      "        .mean()",
      "    )",
    ]),
    "    if reference.empty:",
    '        raise SystemExit(f"baseline series {BASELINE_SERIES!r} is not in the data")',
    "    matched = df[X_FIELD].map(reference)",
    percent
      ? `    df[${value}] = 100.0 * df[${value}] / matched`
      : `    df[${value}] = df[${value}] - matched`,
    ...(traceObservations ? [
      `    df = selection.baseline(df, ${value}, before_transform, source_mask=baseline_mask,`,
      "                            display_mask=df[GROUP] != BASELINE_SERIES, reference=reference,",
      `                            groups=baseline.indices, x_field=X_FIELD, operation=${pyStr(transform.kind)})`,
    ] : ["    df = df[df[GROUP] != BASELINE_SERIES]"]),
  ];
}

/**
 * Collapsing repeats and measuring their spread.
 *
 * The confidence interval is a percentile bootstrap rather than a t interval,
 * so the script needs numpy and nothing else, and it makes no assumption about
 * the shape of the distribution over seeds.
 */
export function emitSummarise(spec: FigureSpec, out: string[], traceSummary: boolean, traceIntervals: boolean): void {
  const aggregation = "aggregation" in spec ? spec.aggregation : "none";
  const uncertainty = "uncertainty" in spec ? spec.uncertainty : undefined;

  if (traceSummary) {
    const collapses = aggregation === "mean" || aggregation === "median";
    out.push("", traceIntervals ? "def summarise(frame, *, for_intervals=False):" : "def summarise(frame):",
      "    result, witness, unit_codes, unit_values, point_codes = _summarise_with_membership(frame)",
      "    if OBSERVATION_CAPTURE is not None:",
      `        ${traceIntervals ? "interval_ids = " : ""}OBSERVATION_CAPTURE.record_summary(`,
      "            frame, result, witness, unit_codes, unit_values, point_codes,",
      "            keys=[X_FIELD] + ([GROUP] if GROUP is not None else []), field=Y_FIELD,",
      `            aggregation=${pyStr(aggregation)}, unit_field=${uncertainty?.over && collapses ? pyStr(uncertainty.over) : "None"},`,
      `            interval=${uncertainty ? pyStr(uncertainty.kind) : "None"},`,
      ...(uncertainty?.kind === "ci"
        ? [
          `            bootstrap={"method": "percentile", "statistic": "${aggregation === "median" ? "median" : "mean"}",`,
          '                       "seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS, "level": CI_LEVEL},',
        ]
        : []),
      ...(spec.repeat ? ["            panel=REPEAT_FIELDS.index(Y_FIELD) if Y_FIELD in REPEAT_FIELDS else None,"] : []),
      ...(spec.facet || spec.repeat ? [] : ["            panel=0,"]),
      "        )",
      ...(traceIntervals ? [
        "        if for_intervals:",
        "            return OBSERVATION_CAPTURE.summary_interval_frame(result, interval_ids)",
      ] : []),
      "    return result",
      "",
      "def _summarise_with_membership(frame):",
    );
  } else {
    out.push("", "def summarise(frame):");
  }
  if (aggregation === "median" && uncertainty?.kind === "sem") {
    out.push('    raise ValueError("SEM requires a mean summary; use an explicit bootstrap CI for median uncertainty")', "");
    return;
  }
  if (aggregation === "none") {
    out.push("    return frame", "");
    return;
  }

  out.push(
    ...(traceSummary
      ? aggregation === "mean" || aggregation === "median"
        ? ["    frame, witness, unit_codes, unit_values = summary_input(frame, Y_FIELD, membership=True)"]
        : [
          "    measured = frame[Y_FIELD]",
          "    witness = _observations._summary_input_witness(measured, measured, measured)",
          "    unit_codes, unit_values = None, None",
        ]
      : ["    frame = summary_input(frame, Y_FIELD)"]),
    "    keys = [X_FIELD] + ([GROUP] if GROUP is not None else [])",
    "    # sort=False keeps the file's category order instead of an alphabetical one.",
    "    grouped = frame.groupby(keys, as_index=False, sort=False, observed=True)[Y_FIELD]",
    `    summary = grouped.${aggregation === "median" ? "median" : aggregation}(${aggregation === "sum" ? "min_count=1" : ""})`,
  );

  const result = traceSummary
    ? "    return summary, witness, unit_codes, unit_values, _observations._summary_group_codes(grouped)"
    : "    return summary";
  if (!uncertainty) {
    out.push(result, "");
    return;
  }

  out.push(
    "    spread = frame.groupby(keys, sort=False, observed=True)[Y_FIELD]",
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
    result,
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
    "    # Percentile bootstrap: no parametric distribution, but resampling units must be appropriate.",
    "    rng = np.random.default_rng(BOOTSTRAP_SEED)",
    "    lows, highs = [], []",
    "    for _, block in frame.groupby(keys, sort=False, observed=True):",
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
