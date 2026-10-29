import { hasCategoricalX, type FigureSpec, type PlottedSpec } from "../schema.ts";
import { sharedCategoryAxes, sharedSeriesStyles } from "../capabilities.ts";
import { pyStr } from "./py.ts";
import { BAND_ALPHA, DASHED_KINDS, MARKER_KINDS, PRESETS, RAW_ALPHA } from "./theme.ts";
import { needsMissingIntervalReport } from "./data.ts";

/**
 * One `draw_panel` function per chart kind.
 *
 * Every one takes an axes and the rows for that panel, so faceting is just
 * calling the same function once per panel. Nothing here reads the spec at
 * runtime; the constants it needs were emitted into the preamble.
 */

/**
 * Kinds whose draw_panel calls series_style even for a single series.
 *
 * They loop over `[None]` when there is no group, which is tidier than writing
 * every plot call twice, but it means the helper has to exist regardless.
 */
const ALWAYS_STYLED = new Set(["ecdf", "qq", "calibration", "kaplan_meier", "scaling_fit", "slope"]);

export function emitSeriesHelpers(spec: FigureSpec, out: string[]): void {
  if (spec.kind === "heatmap") return;
  if (!spec.group && !ALWAYS_STYLED.has(spec.kind)) return;

  const preset = PRESETS[spec.style.preset];
  const pointOnlyFit = spec.kind === "scaling_fit" && !spec.show_points;
  const scatter = MARKER_KINDS.has(spec.kind) && !pointOnlyFit;
  const sizes = scatter ? preset.marker : preset.line;
  const key = scatter ? "size" : "width";
  const dashed = DASHED_KINDS.has(spec.kind) || pointOnlyFit;
  const channelConst = scatter ? "MARKERS" : dashed ? "LINE_STYLES" : "HATCHES";
  const channelKey = scatter ? "marker" : dashed ? "linestyle" : "hatch";
  const plain = scatter ? pyStr("o") : dashed ? pyStr("-") : pyStr("");
  if (sharedSeriesStyles(spec)) out.push("", "SERIES_STYLE_ORDER = None", "");

  out.push(
    "",
    "def locked_appearance(names):",
    "    # A shared lock keeps a model the same colour in figure 1 and figure 7.",
    "    if PALETTE_LOCK is None:",
    "        return None",
    "    try:",
    "        from graphunslopify.lockfile import appearance",
    "    except ImportError:",
    '        print(diagnostic_text("palette_lock_unavailable", "The lockfile appearance helper is unavailable, so palette_lock was ignored."))',
    "        return None",
    "    return appearance(PALETTE_LOCK, [str(n) for n in names])",
    "",
    "",
    "def series_names(frame):",
    "    if GROUP is None:",
    "        return [None]",
    "    if SERIES_ORDER is not None:",
    "        observed = sorted(frame[GROUP].dropna().unique().tolist(), key=str)",
    "        return [n for n in SERIES_ORDER if n in observed] + [n for n in observed if n not in SERIES_ORDER]",
    "    return sorted(frame[GROUP].dropna().unique().tolist(), key=str)",
    "",
    "",
    "def series_style(name, index, total):",
    ...(sharedSeriesStyles(spec) ? [
      "    if SERIES_STYLE_ORDER is not None:",
      "        index = SERIES_STYLE_ORDER.index(name)",
      "        total = len(SERIES_STYLE_ORDER)",
    ] : []),
    "    locked = LOCKED.get(str(name)) if LOCKED else None",
    "    colour = locked[\"colour\"] if locked else PALETTE[index % len(PALETTE)]",
    "    # Colour alone is not enough in greyscale, so add a second channel.",
    "    if total <= SECOND_CHANNEL_THRESHOLD:",
    `        channel = ${plain}`,
    "    elif EMPHASIS is None:",
    `        channel = ${channelConst}[index % len(${channelConst})]`,
    "    else:",
    "        # The emphasised series keeps the plain form, so the others must skip",
    "        # it. Without this, series zero is also plain and the two collide.",
    `        rest = ${channelConst}[1:] or ${channelConst}`,
    "        channel = rest[index % len(rest)]",
    "    if locked and total > SECOND_CHANNEL_THRESHOLD:",
    `        channel = locked[${pyStr(channelKey)}]`,
    "    if name == EMPHASIS:",
    `        channel = ${plain}`,
    "    if EMPHASIS is None:",
    `        style = {"colour": colour, ${pyStr(key)}: ${sizes.base}, "alpha": 1.0, "zorder": 2}`,
    "    elif name == EMPHASIS:",
    `        style = {"colour": colour, ${pyStr(key)}: ${sizes.emphasis}, "alpha": 1.0, "zorder": 3}`,
    "    else:",
    `        style = {"colour": colour, ${pyStr(key)}: ${sizes.muted}, "alpha": RECEDED_ALPHA, "zorder": 1}`,
    `    style[${pyStr(channelKey)}] = channel`,
    "    return style",
    "",
  );
}

function emitCategories(spec: FigureSpec, out: string[]): void {
  const sortable = spec.kind === "bar" || spec.kind === "box" || spec.kind === "dumbbell";
  out.push(
    "",
    "def category_order(frame):",
    "    observed = list(dict.fromkeys(frame[X_FIELD].tolist()))",
    "    if CATEGORY_ORDER is not None:",
    "        omitted = [name for name in observed if name not in CATEGORY_ORDER]",
    "        if omitted:",
    '            raise ValueError("category_order omits observed categories; filter explicitly or list all identifiers: " + ", ".join(map(str, omitted)))',
    "        if len(CATEGORY_ORDER) != len(set(CATEGORY_ORDER)):",
    '            raise ValueError("category_order must contain unique identifiers")',
    "        if not observed:",
    '            raise ValueError("No observed categories are available")',
    sharedCategoryAxes(spec) ? "        return list(CATEGORY_ORDER)" : "        return [c for c in CATEGORY_ORDER if c in set(frame[X_FIELD])]",
  );
  if (sortable && "sort" in spec && spec.sort?.by === "value") {
    const ascending = spec.sort.direction === "asc" ? "True" : "False";
    out.push(
      "    ranked = frame.groupby(X_FIELD, sort=False, observed=True)[Y_FIELD].mean()",
      `    return list(ranked.sort_values(ascending=${ascending}).index)`,
    );
  } else if (sortable && "sort" in spec && spec.sort?.by === "category") {
    const reverse = spec.sort.direction === "desc" ? "True" : "False";
    out.push(
      `    return sorted(dict.fromkeys(frame[X_FIELD].tolist()), key=str, reverse=${reverse})`,
    );
  } else {
    out.push("    return list(dict.fromkeys(frame[X_FIELD].tolist()))");
  }
  out.push("");
}

function emitLine(spec: FigureSpec & { kind: "line" }, out: string[]): void {
  const preset = PRESETS[spec.style.preset];
  const band = spec.uncertainty?.display === "band";

  out.push("", "def draw_panel(ax, df):", "    frame = summarise(df)");
  if (needsMissingIntervalReport(spec)) out.push("    note_missing_interval(frame)");

  const plot = (indentLevel: string, source: string, styleExpr: string, label: string) => {
    const lines: string[] = [];
    if (spec.smooth?.show_raw) {
      lines.push(
        `${indentLevel}ax.plot(`,
        `${indentLevel}    ${source}[X_FIELD],`,
        `${indentLevel}    ${source}[Y_FIELD],`,
        `${indentLevel}    color=${styleExpr}["colour"],`,
        `${indentLevel}    linewidth=${styleExpr}["width"] * 0.8,`,
        `${indentLevel}    alpha=RAW_ALPHA,`,
        `${indentLevel}    zorder=${styleExpr}["zorder"] - 1,`,
        `${indentLevel})`,
      );
    }
    const values = spec.smooth ? `smooth(${source}[Y_FIELD])` : `${source}[Y_FIELD]`;
    lines.push(
      `${indentLevel}${spec.annotate?.length ? "_annotation_curve, = " : ""}ax.plot(`,
      `${indentLevel}    ${source}[X_FIELD],`,
      `${indentLevel}    ${values},`,
      label ? `${indentLevel}    label=${label},` : `${indentLevel}    label=None,`,
      `${indentLevel}    color=${styleExpr}["colour"],`,
      `${indentLevel}    linewidth=${styleExpr}["width"],`,
      `${indentLevel}    alpha=${styleExpr}["alpha"],`,
      `${indentLevel}    zorder=${styleExpr}["zorder"],`,
      `${indentLevel}    linestyle=${styleExpr}["linestyle"],`,
    );
    lines.push(`${indentLevel}    marker="o" if ${spec.marker ? "True" : `len(${source}) == 1`} else None,`);
    lines.push(`${indentLevel})`);
    if (spec.annotate?.length) lines.push(
      `${indentLevel}_annotation_curve._graphunslopify_annotation_primary = True`,
      `${indentLevel}_annotation_curve._graphunslopify_annotation_series = ${spec.group ? "name" : "None"}`,
    );
    if (spec.uncertainty && band) {
      lines.push(
        `${indentLevel}if "_low" in ${source}:`,
        `${indentLevel}    ax.fill_between(`,
        `${indentLevel}        ${source}[X_FIELD],`,
        `${indentLevel}        ${source}["_low"],`,
        `${indentLevel}        ${source}["_high"],`,
        `${indentLevel}        color=${styleExpr}["colour"],`,
        `${indentLevel}        alpha=BAND_ALPHA,`,
        `${indentLevel}        linewidth=0,`,
        `${indentLevel}        zorder=${styleExpr}["zorder"] - 1,`,
        `${indentLevel}    )`,
      );
    } else if (spec.uncertainty) {
      lines.push(
        `${indentLevel}if "_low" in ${source}:`,
        `${indentLevel}    ax.errorbar(`,
        `${indentLevel}        ${source}[X_FIELD],`,
        `${indentLevel}        ${source}[Y_FIELD],`,
        `${indentLevel}        yerr=[`,
        `${indentLevel}            ${source}[Y_FIELD] - ${source}["_low"],`,
        `${indentLevel}            ${source}["_high"] - ${source}[Y_FIELD],`,
        `${indentLevel}        ],`,
        `${indentLevel}        fmt="none",`,
        `${indentLevel}        ecolor=${styleExpr}["colour"],`,
        `${indentLevel}        elinewidth=0.9,`,
        `${indentLevel}        capsize=2,`,
        `${indentLevel}        zorder=${styleExpr}["zorder"],`,
        `${indentLevel}    )`,
      );
    }
    return lines;
  };

  if (spec.group) {
    out.push("    names = series_names(frame)", "    for index, name in enumerate(names):");
    out.push("        block = frame[frame[GROUP] == name]");
    if (spec.sort_x) out.push("        block = block.sort_values(X_FIELD)");
    out.push("        style = series_style(name, index, len(names))");
    out.push(...plot("        ", "block", "style", "str(name)"));
  } else {
    out.push("    block = frame");
    if (spec.sort_x) out.push("    block = block.sort_values(X_FIELD)");
    out.push(
      `    style = {"colour": PALETTE[0], "width": ${preset.line.base}, "alpha": 1.0, "zorder": 2, "linestyle": "-"}`,
    );
    out.push(...plot("    ", "block", "style", ""));
  }

  if (spec.y2) {
    out.push(
      "    twin = ax.twinx()",
      "    second = df.sort_values(X_FIELD)",
      "    twin.plot(",
      "        second[X_FIELD],",
      "        second[Y2_FIELD],",
      "        color=PALETTE[1],",
      `        linewidth=${preset.line.base},`,
      '        linestyle="--",',
      "        zorder=1,",
      "    )",
      "    twin.set_ylabel(Y2_LABEL, color=PALETTE[1])",
      '    edit_target(twin.yaxis.label, ["y2", "label"], "axis_label", Y2_FIELD)',
      '    twin.tick_params(axis="y", labelcolor=PALETTE[1])',
      `    twin.set_yscale(${pyStr(spec.y2.scale)})`,
      "    ax._gu_twin = twin",
    );
  }
  out.push("");
}

function emitScatter(spec: FigureSpec & { kind: "scatter" }, out: string[]): void {
  const preset = PRESETS[spec.style.preset];
  out.push("", "def draw_panel(ax, df):", "    frame = df");

  const body = (level: string, source: string, styleExpr: string, label: string) => [
    `${level}ax.scatter(`,
    `${level}    ${source}[X_FIELD],`,
    `${level}    ${source}[Y_FIELD],`,
    label ? `${level}    label=${label},` : `${level}    label=None,`,
    `${level}    color=${styleExpr}["colour"],`,
    `${level}    s=${styleExpr}["size"],`,
    `${level}    alpha=${styleExpr}["alpha"],`,
    `${level}    zorder=${styleExpr}["zorder"],`,
    `${level}    marker=${styleExpr}["marker"],`,
    `${level})`,
  ];

  if (spec.group) {
    out.push(
      "    names = series_names(frame)",
      "    for index, name in enumerate(names):",
      "        block = frame[frame[GROUP] == name]",
      "        style = series_style(name, index, len(names))",
      ...body("        ", "block", "style", "str(name)"),
    );
    if (spec.trendline === "linear") {
      out.push('        add_trendline(ax, block[X_FIELD], block[Y_FIELD], style["colour"])');
    }
  } else {
    out.push(
      `    style = {"colour": PALETTE[0], "size": ${preset.marker.base}, "alpha": 1.0, "zorder": 2, "marker": "o"}`,
      ...body("    ", "frame", "style", ""),
    );
    if (spec.trendline === "linear") {
      out.push("    add_trendline(ax, frame[X_FIELD], frame[Y_FIELD], PALETTE[0])");
    }
  }

  if (spec.frontier) out.push("    draw_frontier(ax, frame)");
  out.push("");
}

function emitBar(spec: FigureSpec & { kind: "bar" }, out: string[]): void {
  const vertical = spec.orientation === "vertical";
  const plot = vertical ? "bar" : "barh";
  const tick = vertical ? "x" : "y";
  const errKey = vertical ? "yerr" : "xerr";

  out.push(
    "",
    "def draw_panel(ax, df):",
    "    frame = summarise(df)",
    ...(needsMissingIntervalReport(spec) ? ["    note_missing_interval(frame)"] : []),
    "    categories = category_order(frame)",
    "    positions = np.arange(len(categories))",
  );

  if (spec.group && spec.stacked) {
    out.push(
      ...(spec.uncertainty ? ['    raise ValueError("Stacked bar uncertainty is unsupported; use grouped bars to show individual intervals.")'] : []),
      "    names = series_names(frame)",
      "    running = np.zeros(len(categories))",
      "    for index, name in enumerate(names):",
      "        observed = frame[frame[GROUP] == name].set_index(X_FIELD)",
      "        block = observed.reindex(categories)",
      `        required = ${["sum", "count"].includes(spec.aggregation) ? "observed.index" : "frame[X_FIELD]"}`,
      "        if (block[Y_FIELD].isna() & block.index.isin(required)).any():",
      '            raise ValueError("Stacked bars need known contributions for observed groups; filter unknown values or use grouped bars/table")',
      "        values = np.nan_to_num(block[Y_FIELD].to_numpy(dtype=float))",
      "        style = series_style(name, index, len(names))",
      `        ax.${plot}(`,
      "            positions,",
      "            values,",
      "            0.72,",
      vertical ? "            bottom=running," : "            left=running,",
      "            label=str(name),",
      '            color=style["colour"],',
      '            alpha=style["alpha"],',
      '            zorder=style["zorder"],',
      '            hatch=style["hatch"],',
      '            edgecolor="white",',
      "            linewidth=0.0,",
      "        )",
      "        running = running + values",
    );
  } else if (spec.group) {
    out.push(
      "    names = series_names(frame)",
      "    width = 0.8 / max(len(names), 1)",
      "    for index, name in enumerate(names):",
      "        block = frame[frame[GROUP] == name].set_index(X_FIELD).reindex(categories)",
      "        offset = (index - (len(names) - 1) / 2) * width",
      "        style = series_style(name, index, len(names))",
      `        ax.${plot}(`,
      "            positions + offset,",
      "            block[Y_FIELD].to_numpy(dtype=float),",
      "            width,",
      "            label=str(name),",
      '            color=style["colour"],',
      '            alpha=style["alpha"],',
      '            zorder=style["zorder"],',
      '            hatch=style["hatch"],',
      '            edgecolor="white",',
      "            linewidth=0.0,",
      spec.uncertainty
        ? `            ${errKey}=error_pair(block),`
        : "",
      spec.uncertainty ? '            ecolor="#404040",' : "",
      spec.uncertainty ? "            capsize=2," : "",
      "        )",
    );
    if (spec.value_labels) out.push("        label_bars(ax, block[Y_FIELD], positions + offset)");
  } else {
    out.push(
      "    block = frame.set_index(X_FIELD).reindex(categories)",
      `    ax.${plot}(`,
      "        positions,",
      "        block[Y_FIELD].to_numpy(dtype=float),",
      "        0.7,",
      "        color=PALETTE[0],",
      "        zorder=2,",
      spec.uncertainty ? `        ${errKey}=error_pair(block),` : "",
      spec.uncertainty ? '        ecolor="#404040",' : "",
      spec.uncertainty ? "        capsize=2," : "",
      "    )",
    );
    if (spec.value_labels) out.push("    label_bars(ax, block[Y_FIELD], positions)");
  }

  out.push(
    `    ax.set_${tick}ticks(positions)`,
    `    ax.set_${tick}ticklabels([str(value) for value in categories])`,
  );
  if (!vertical) {
    out.push(
      "    # barh puts the first category at the bottom; readers expect it at the top.",
      "    ax.invert_yaxis()",
    );
  }
  if (spec.significance) out.push("    mark_significance(ax, df, categories, positions)");
  out.push("");
}

function emitDistribution(spec: FigureSpec & { kind: "box" | "violin" }, out: string[]): void {
  const violin = spec.kind === "violin";
  const shared = sharedCategoryAxes(spec);
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    groups = [df[df[X_FIELD] == c][Y_FIELD].dropna().to_numpy(dtype=float) for c in categories]",
    ...(shared ? [
      "    category_positions = np.arange(len(categories))",
      "    positions = np.array([i for i, values in enumerate(groups) if len(values)])",
      "    groups = [values for values in groups if len(values)]",
    ] : [
      "    groups = [g if len(g) else np.array([np.nan]) for g in groups]",
      "    positions = np.arange(len(categories))",
    ]),
  );

  if (violin) {
    out.push(
      "    parts = ax.violinplot(",
      "        groups,",
      "        positions=positions,",
      `        showmedians=${spec.show_box ? "False" : "True"},`,
      "        showextrema=False,",
      "        widths=0.7,",
      "    )",
      '    for index, body in enumerate(parts["bodies"]):',
      shared ? "        body.set_facecolor(PALETTE[int(positions[index]) % len(PALETTE)])" : "        body.set_facecolor(PALETTE[index % len(PALETTE)])",
      "        body.set_alpha(0.55)",
      '        body.set_edgecolor("white")',
    );
    if (spec.show_box) {
      out.push(
        "    ax.boxplot(",
        "        groups,",
        "        positions=positions,",
        "        widths=0.14,",
        "        showfliers=False,",
        "        patch_artist=True,",
        '        boxprops={"facecolor": "white", "linewidth": 0.8},',
        '        medianprops={"color": "#202020", "linewidth": 1.2},',
        '        whiskerprops={"linewidth": 0.8},',
        '        capprops={"linewidth": 0.8},',
        "    )",
      );
    }
  } else {
    out.push(
      "    drawn = ax.boxplot(",
      "        groups,",
      "        positions=positions,",
      "        widths=0.6,",
      `        notch=${spec.notch ? "True" : "False"},`,
      "        showfliers=True,",
      "        patch_artist=True,",
      '        medianprops={"color": "#202020", "linewidth": 1.2},',
      '        flierprops={"marker": "o", "markersize": 2, "markerfacecolor": "#808080", "markeredgecolor": "none"},',
      "    )",
      '    for index, box in enumerate(drawn["boxes"]):',
      shared ? "        box.set_facecolor(PALETTE[int(positions[index]) % len(PALETTE)])" : "        box.set_facecolor(PALETTE[index % len(PALETTE)])",
      "        box.set_alpha(0.55)",
      '        box.set_edgecolor("#404040")',
      "        box.set_linewidth(0.8)",
    );
  }

  if (spec.show_points) {
    out.push(
      "    jitter = np.random.default_rng(POINT_JITTER_SEED)",
      "    for index, values in enumerate(groups):",
      "        spread = jitter.uniform(-0.09, 0.09, size=len(values))",
      "        ax.scatter(",
      shared ? "            np.full(len(values), positions[index]) + spread," : "            np.full(len(values), index) + spread,",
      "            values,",
      "            s=6,",
      '            color="#303030",',
      "            alpha=0.5,",
      "            zorder=4,",
      "            linewidths=0,",
      "        )",
    );
  }

  out.push(
    shared ? "    ax.set_xticks(category_positions)" : "    ax.set_xticks(positions)",
    "    ax.set_xticklabels([str(value) for value in categories])",
    "",
  );
}

function emitEcdf(spec: FigureSpec & { kind: "ecdf" }, out: string[]): void {
  // A step function through every observation. No bin width and no bandwidth,
  // so nothing about the shape is an author's choice: a histogram invents and
  // destroys modes depending on where the bins land.
  const value = spec.complementary
    ? "1.0 - np.arange(1, len(values) + 1) / len(values)"
    : "np.arange(1, len(values) + 1) / len(values)";
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    names = series_names(df) if GROUP is not None else [None]",
    "    for index, name in enumerate(names):",
    "        block = df if name is None else df[df[GROUP] == name]",
    "        values = np.sort(block[X_FIELD].dropna().to_numpy(dtype=float))",
    "        if not len(values):",
    "            continue",
    `        proportion = ${value}`,
    "        style = series_style(name, index, len(names))",
    "        # A step, not a line. The distribution is flat between observations,",
    "        # and joining them with a slope claims data that was never seen.",
    "        ax.step(",
    "            np.concatenate([values[:1], values]),",
    "            np.concatenate([[1.0 if COMPLEMENTARY else 0.0], proportion]),",
    '            where="post",',
    "            label=None if name is None else str(name),",
    '            color=style["colour"],',
    '            linewidth=style["width"],',
    '            alpha=style["alpha"],',
    '            zorder=style["zorder"],',
    '            linestyle=style["linestyle"],',
    "        )",
    "    ax.set_ylim(-0.02, 1.02)",
    "",
  );
}

function emitRaincloud(spec: FigureSpec & { kind: "raincloud" }, out: string[]): void {
  const shared = sharedCategoryAxes(spec);
  // Half a violin, a quartile box and every raw point. The cloud shows the
  // shape, the box shows the summary a reader expects, and the rain is the
  // evidence for both, so a claim resting on six observations cannot hide
  // inside a smooth curve.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    groups = [df[df[X_FIELD] == c][Y_FIELD].dropna().to_numpy(dtype=float) for c in categories]",
    ...(shared ? [
      "    category_positions = np.arange(len(categories))",
      "    positions = np.array([i for i, values in enumerate(groups) if len(values)])",
      "    groups = [values for values in groups if len(values)]",
    ] : [
      "    groups = [g if len(g) else np.array([np.nan]) for g in groups]",
      "    positions = np.arange(len(categories))",
    ]),
    "    parts = ax.violinplot(",
    "        groups,",
    "        positions=positions + 0.08,",
    "        showmedians=False,",
    "        showextrema=False,",
    "        widths=0.55,",
    "    )",
    '    for index, body in enumerate(parts["bodies"]):',
    "        # Clip each violin to its right half, leaving room for the rain.",
    "        vertices = body.get_paths()[0].vertices",
    "        vertices[:, 0] = np.clip(vertices[:, 0], positions[index] + 0.08, np.inf)",
    shared ? "        body.set_facecolor(PALETTE[int(positions[index]) % len(PALETTE)])" : "        body.set_facecolor(PALETTE[index % len(PALETTE)])",
    "        body.set_alpha(0.5)",
    '        body.set_edgecolor("white")',
    "    ax.boxplot(",
    "        groups,",
    "        positions=positions,",
    "        widths=0.1,",
    "        showfliers=False,",
    "        patch_artist=True,",
    '        boxprops={"facecolor": "white", "linewidth": 0.8},',
    '        medianprops={"color": "#202020", "linewidth": 1.2},',
    '        whiskerprops={"linewidth": 0.8},',
    '        capprops={"linewidth": 0.8},',
    "    )",
    "    jitter = np.random.default_rng(POINT_JITTER_SEED)",
    "    for index, values in enumerate(groups):",
    "        spread = jitter.uniform(-0.10, -0.02, size=len(values))",
    "        ax.scatter(",
    shared ? "            np.full(len(values), positions[index]) + spread," : "            np.full(len(values), index) + spread,",
    "            values,",
    "            s=6,",
    '            color="#303030",',
    "            alpha=0.55,",
    "            zorder=4,",
    "            linewidths=0,",
    "        )",
    shared ? "    ax.set_xticks(category_positions)" : "    ax.set_xticks(positions)",
    "    ax.set_xticklabels([str(value) for value in categories])",
    "",
  );
}

function emitRidgeline(spec: FigureSpec & { kind: "ridgeline" }, out: string[]): void {
  void spec;
  out.push(...String.raw`

def draw_panel(ax, df):
    categories, grid, profiles = density_profiles(df)
    for profile in reversed(profiles):
        base = float(len(categories) - 1 - profile["index"])
        colour = PALETTE[profile["index"] % len(PALETTE)]
        record_density(profile)
        if profile["status"] == "available":
            height = 0.92 * profile["density"] / profile["peak"]
            ax.fill_between(grid, base, base + height, color=colour, alpha=0.62, linewidth=0, zorder=base)
${spec.annotate?.length ? '            _annotation_density, = ' : '            '}ax.plot(grid, base + height, color="white", linewidth=0.7, zorder=base)
${spec.annotate?.length ? '            _annotation_density._graphunslopify_annotation_category = profile["category"]\n            _annotation_density._graphunslopify_annotation_base = base' : ""}
        else:
            values = profile["values"]
            if len(values):
                ax.plot(values, np.full(len(values), base), marker="|", markersize=8,
                        linestyle="none", color=colour, zorder=base)
                ax.annotate(f"density unavailable (n={len(values)})", (float(np.median(values)), base),
                            xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                            fontsize=ANNOTATION_PT - 1, parse_math=False, usetex=False)
            else:
                ax.text(0.5, base + 0.1, "density unavailable: no finite observations",
                        transform=ax.get_yaxis_transform(), ha="center", fontsize=ANNOTATION_PT - 1,
                        parse_math=False, usetex=False)
    ax.set_yticks(np.arange(len(categories)))
    ax.set_yticklabels([str(value) for value in reversed(categories)])
    ax.set_ylim(-0.15, len(categories) + 0.5)
`.trim().split("\n"), "");
}

/** Gaussian KDE with the explicit robust normal-reference bandwidth, without SciPy. */
function emitDensityHelper(out: string[]): void {
  out.push(...String.raw`

def _density_bandwidth(values):
    values = values[np.isfinite(values)]
    if len(values) < 2 or np.all(values == values[0]):
        return None
    spread = float(np.std(values, ddof=1))
    if not np.isfinite(spread) or spread <= 0:
        return None
    # Robust normal-reference rule; 1.349 is the normal-distribution IQR.
    bandwidth = 0.9 * min(spread, (np.percentile(values, 75) - np.percentile(values, 25)) / 1.349 or spread)
    bandwidth *= len(values) ** (-0.2)
    return float(bandwidth) if np.isfinite(bandwidth) and bandwidth > 0 else None


def _gaussian_density(values, grid):
    values = values[np.isfinite(values)]
    bandwidth = _density_bandwidth(values)
    if bandwidth is None:
        return np.full_like(grid, np.nan, dtype=float)
    offsets = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * offsets**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))


def density_profiles(df):
    categories = category_order(df)
    blocks = [df[df[X_FIELD] == category] for category in categories]
    groups = [pd.to_numeric(block[Y_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
              for block in blocks]
    groups = [values[np.isfinite(values)] for values in groups]
    if not any(len(values) for values in groups):
        raise ValueError("Ridgeline needs at least one finite measurement")
    grid_lo = min(float(values.min()) for values in groups if len(values))
    grid_hi = max(float(values.max()) for values in groups if len(values))
    span = grid_hi - grid_lo
    if not np.isfinite(span):
        raise ValueError("Ridgeline requires a finite drawable measurement span")
    pad = 0.05 * span if span > 0 else max(0.5, abs(grid_lo) * 0.05)
    grid = np.linspace(grid_lo - pad, grid_hi + pad, 256)
    if not np.isfinite(grid).all():
        raise ValueError("Ridgeline requires a finite drawable measurement domain")
    profiles = []
    for index, (category, values, block) in enumerate(zip(categories, groups, blocks)):
        if block.empty:
            continue  # A reserved/shared category slot is not an observed failed density.
        bandwidth = _density_bandwidth(values)
        density = _gaussian_density(values, grid) if bandwidth is not None else None
        peak = float(density.max()) if density is not None and np.isfinite(density).all() else None
        available = peak is not None and peak > 0
        reason = None if available else (
            "no finite observations" if not len(values) else
            "fewer than two finite observations" if len(values) < 2 else
            "constant sample" if np.ptp(values) == 0 else
            "automatic bandwidth unavailable" if bandwidth is None else
            "density unresolved on the evaluation grid")
        profiles.append({"index": index, "category": str(category), "values": values,
                         "n": len(values), "nonfinite": len(block) - len(values),
                         "bandwidth": bandwidth, "density": density, "peak": peak,
                         "status": "available" if available else "unavailable", "reason": reason})
    return categories, grid, profiles


def record_density(profile):
    record = {key: profile[key] for key in ("category", "n", "nonfinite", "bandwidth", "status", "reason")}
    record.update(panel=CURRENT_PANEL, metric=Y_FIELD, kernel="Gaussian",
                  bandwidth_method="0.9 * min(sample_sd, IQR / 1.349) * n**(-0.2)",
                  peak_normalized=profile["status"] == "available")
    records = ROW_COUNTS.setdefault("densities", [])
    records[:] = [item for item in records if (item["panel"], item["metric"], item["category"]) !=
                 (record["panel"], record["metric"], record["category"])]
    records.append(record)
    if record["status"] == "unavailable":
        reason = f"density unavailable in panel {CURRENT_PANEL}, category {record['category']}: {record['reason']}"
        finding("warning", "density_unavailable", reason)
        if reason not in RUN_REPORT["untested"]:
            RUN_REPORT["untested"].append(reason)
    print(f"density {record['category']}: n={record['n']}, nonfinite={record['nonfinite']}, "
          f"bandwidth={record['bandwidth']}, status={record['status']}; profiles are normalized to their own peak")
`.trim().split("\n"), "");
}

function emitForest(spec: FigureSpec & { kind: "forest" }, out: string[]): void {
  void spec;
  // One row per entry, the effect as a dot and its interval as the bar through
  // it, with a line at the value that means nothing happened. An ablation
  // table is this figure with the intervals thrown away.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    frame = summarise(df)",
    "    note_missing_interval(frame)",
    "    categories = category_order(frame)",
    "    for index, name in enumerate(categories):",
    "        block = frame[frame[X_FIELD] == name]",
    "        if not len(block):",
    "            continue",
    "        row = len(categories) - 1 - index",
    "        centre = float(block[Y_FIELD].iloc[0])",
    '        low = float(block["_low"].iloc[0]) if "_low" in block else np.nan',
    '        high = float(block["_high"].iloc[0]) if "_high" in block else np.nan',
    "        colour = PALETTE[index % len(PALETTE)]",
    "        if np.isfinite(low) and np.isfinite(high):",
    "            ax.plot(",
    "                [low, high],",
    "                [row, row],",
    "                color=colour,",
    "                linewidth=1.5,",
    '                solid_capstyle="butt",',
    "                zorder=2,",
    "            )",
    "            for edge in (low, high):",
    "                ax.plot([edge, edge], [row - 0.14, row + 0.14], color=colour, linewidth=1.0, zorder=2)",
    '        ax.plot([centre], [row], marker="o", markersize=5, color=colour, zorder=3, linestyle="none")',
    "    ax.axvline(",
    "        NULL_VALUE,",
    '        color="#606060",',
    "        linewidth=0.9,",
    "        linestyle=(0, (4, 3)),",
    "        zorder=1,",
    "    )",
    "    ax.set_yticks(np.arange(len(categories)))",
    "    ax.set_yticklabels([str(value) for value in reversed(categories)])",
    "    ax.set_ylim(-0.6, len(categories) - 0.4)",
    "",
  );
}

function emitPairedDifference(spec: FigureSpec & { kind: "paired_difference" }, out: string[]): void {
  void spec;
  out.push(...String.raw`

def paired_input(frame):
    if frame.empty:
        raise ValueError("Paired differences need observations")
    if GROUP is not None or CLAIMS:
        raise ValueError("Paired differences do not support raw series groups or claims")
    labels = [PAIR_FIELD, X_FIELD, *[field for field in (globals().get("FACET_BY"), globals().get("FACET_ROWS")) if field is not None]]
    missing = [field for field in [*labels, Y_FIELD] if field not in frame]
    if missing:
        raise ValueError("Paired differences are missing required columns: " + ", ".join(missing))
    if frame[labels].isna().any(axis=None):
        raise ValueError("Paired differences require nonmissing unit, condition and panel identifiers")
    for field in labels:
        if frame[field].map(lambda value: isinstance(value, str) and not value.strip()
                            or isinstance(value, (float, np.floating)) and not np.isfinite(value)).any():
            raise ValueError("Paired identifiers must be nonempty and finite when numeric")
    source = frame.copy()
    values = pd.to_numeric(source[Y_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if np.any(source[Y_FIELD].notna().to_numpy() & ~np.isfinite(values)):
        raise ValueError("Paired nonmissing measurements must be finite numbers")
    source[Y_FIELD] = values
    return source


def _mean_interval(values):
    if len(values) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(PAIR_SEED)
    draws = rng.choice(values, size=(2000, len(values)), replace=True)
    return tuple(np.percentile(draws.mean(axis=1), [2.5, 97.5]))


def paired_estimates(frame):
    source = paired_input(frame)
    conditions = list(source[X_FIELD].unique())
    names = [str(value) for value in conditions]
    if len(names) != len(set(names)):
        raise ValueError("Paired condition names have ambiguous string representations")
    if BASELINE not in names:
        raise ValueError(f"Paired baseline {BASELINE!r} is not a value of {X_FIELD}")
    source[X_FIELD] = source[X_FIELD].map(str)
    others = sorted(name for name in names if name != BASELINE)
    if not others:
        raise ValueError("Paired differences need a condition other than the baseline")
    cells = source.groupby([PAIR_FIELD, X_FIELD], observed=True)[Y_FIELD].agg(["mean", "count"])
    if ((cells["count"] > 0) & ~np.isfinite(cells["mean"])).any():
        raise ValueError("Paired unit means must remain finite")
    wide = cells["mean"].unstack(X_FIELD)
    estimates = []
    for other in others:
        baseline_ok, candidate_ok = wide[BASELINE].notna(), wide[other].notna()
        complete = wide.loc[baseline_ok & candidate_ok]
        with np.errstate(over="ignore", invalid="ignore"):
            values = (complete[other] - complete[BASELINE]).to_numpy(dtype=float)
            center = float(values.mean()) if len(values) else None
        if not np.isfinite(values).all() or center is not None and not np.isfinite(center):
            raise ValueError("Paired differences must remain finite after subtraction and averaging")
        with np.errstate(over="ignore", invalid="ignore"):
            low, high = _mean_interval(values)
        if len(values) >= 2 and not np.isfinite([low, high]).all():
            raise ValueError("Paired bootstrap interval must remain finite")
        relevant = source[source[X_FIELD].isin([BASELINE, other])]
        finite = relevant.dropna(subset=[Y_FIELD])
        estimates.append({"condition": other, "baseline": BASELINE, "values": values,
                          "mean": center, "low": low, "high": high, "n": len(values),
                          "units": len(wide), "baseline_only": int((baseline_ok & ~candidate_ok).sum()),
                          "candidate_only": int((~baseline_ok & candidate_ok).sum()),
                          "neither": int((~baseline_ok & ~candidate_ok).sum()),
                          "missing_measurements": int(relevant[Y_FIELD].isna().sum()),
                          "technical_repeats": len(finite) - len(finite.drop_duplicates([PAIR_FIELD, X_FIELD]))})
    if not any(estimate["n"] for estimate in estimates):
        raise ValueError("Paired differences have no complete unit pairs")
    return estimates


def record_pairing(estimate):
    record = {key: value for key, value in estimate.items() if key != "values"}
    record.update(panel=CURRENT_PANEL, metric=Y_FIELD,
                  interval={"method": "percentile_bootstrap_mean", "level": 0.95,
                            "resamples": 2000, "seed": PAIR_SEED})
    for key in ("low", "high"):
        record[key] = float(record[key]) if np.isfinite(record[key]) else None
    old = ROW_COUNTS.setdefault("pairing", [])
    old[:] = [item for item in old if (item["panel"], item["condition"]) != (CURRENT_PANEL, record["condition"])]
    old.append(record)
    who = f"panel {CURRENT_PANEL}, {record['condition']} minus {BASELINE}"
    if record["n"] != record["units"]:
        finding("warning", "paired_units_excluded", f"{who}: {record['n']} of {record['units']} units have complete pairs")
    if record["technical_repeats"]:
        finding("warning", "paired_technical_repeats_averaged", f"{who}: {record['technical_repeats']} technical repeat rows averaged within unit/condition")
    if record["n"] < 2:
        reason = f"Paired {who}: interval unavailable with {record['n']} matched pairs"
        if reason not in RUN_REPORT["untested"]:
            RUN_REPORT["untested"].append(reason)
        finding("warning", "paired_interval_unavailable", reason)
    print(f"paired: {who}, n={record['n']} of {record['units']}, "
          f"{record['baseline_only']} baseline-only, {record['candidate_only']} candidate-only, {record['neither']} neither")


def draw_panel(ax, df):
    estimates = paired_estimates(df)
${spec.annotate?.length ? '    ax._graphunslopify_annotation_keys = [estimate["condition"] for estimate in estimates]' : ""}
    jitter = np.random.default_rng(PAIR_SEED)
    labels = []
    for index, estimate in enumerate(estimates):
        record_pairing(estimate)
        values = estimate["values"]
        counts = f"n={len(values)}" + ("; CI unavailable" if len(values) < 2 else "")
        labels.append(f"{estimate['condition']} minus {BASELINE}\n({counts})")
        if not len(values):
            continue
        colour = PALETTE[index % len(PALETTE)]
        spread = jitter.uniform(-0.07, 0.07, size=len(values))
        ax.scatter(np.full(len(values), index) + spread, values, s=10, color=colour,
                   alpha=0.55, linewidths=0, zorder=2)
        low, high = estimate["low"], estimate["high"]
        if np.isfinite(low) and np.isfinite(high):
            ax.plot([index, index], [low, high], color=colour, linewidth=1.6, zorder=3)
        ax.plot([index], [estimate["mean"]], marker="o", markersize=6, color=colour,
                markeredgecolor="white", zorder=4, linestyle="none")
    ax.axhline(0.0, color="#606060", linewidth=0.9, linestyle=(0, (4, 3)), zorder=1)
    ax.set_xticks(np.arange(len(estimates)))
    ax.set_xticklabels(labels)
    ax.set_xlim(-0.6, len(estimates) - 0.4)
`.split("\n"));
}

function emitSlope(spec: FigureSpec & { kind: "slope" }, out: string[]): void {
  void spec;
  // Two positions and the line between them. The reader takes the change from
  // the angle, so every series shares one scale.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    positions = np.arange(len(categories))",
    "    names = series_names(df) if GROUP is not None else [None]",
    "    for index, name in enumerate(names):",
    "        block = df if name is None else df[df[GROUP] == name]",
    "        values = np.array(",
    "            [block[block[X_FIELD] == c][Y_FIELD].mean() for c in categories],",
    "            dtype=float,",
    "        )",
    "        if not np.isfinite(values).any():",
    "            continue",
    "        style = series_style(name, index, len(names))",
    "        ax.plot(",
    "            positions,",
    "            values,",
    '            marker="o",',
    "            markersize=4,",
    "            label=None if name is None else str(name),",
    '            color=style["colour"],',
    '            linewidth=style["width"],',
    '            alpha=style["alpha"],',
    '            zorder=style["zorder"],',
    '            linestyle=style["linestyle"],',
    "        )",
    "    ax.set_xticks(positions)",
    "    ax.set_xticklabels([str(value) for value in categories])",
    "    ax.set_xlim(-0.35, len(categories) - 0.65)",
    "",
  );
}

function emitDumbbell(spec: FigureSpec & { kind: "dumbbell" }, out: string[]): void {
  void spec;
  // Two dots per row joined by a line. The gap is the quantity, and a reader
  // measures it along one shared scale instead of comparing two bar lengths
  // that start in different places.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    names = series_names(df) if GROUP is not None else [None]",
    "    labelled = set()",
    "    for index, category in enumerate(categories):",
    "        row = len(categories) - 1 - index",
    "        block = df[df[X_FIELD] == category]",
    "        values = [",
    "            float(block[Y_FIELD].mean())",
    "            if name is None",
    "            else float(block[block[GROUP] == name][Y_FIELD].mean())",
    "            for name in names",
    "        ]",
    "        finite = [value for value in values if np.isfinite(value)]",
    "        if len(finite) > 1:",
    '            ax.plot([min(finite), max(finite)], [row, row], color="#9a9a9a", linewidth=1.4, zorder=1)',
    "        for position, (name, value) in enumerate(zip(names, values)):",
    "            if not np.isfinite(value):",
    "                continue",
    "            style = series_style(name, position, len(names))",
    `            ${spec.annotate?.length ? "_annotation_mark, = " : ""}ax.plot(`,
    "                [value],",
    "                [row],",
    '                marker="o",',
    "                markersize=5.5,",
    '                color=style["colour"],',
    '                markeredgecolor="white",',
    "                markeredgewidth=0.6,",
    "                zorder=3,",
    '                linestyle="none",',
    "                label=(str(name) if name is not None and name not in labelled else None),",
    "            )",
    ...(spec.annotate?.length ? ["            _annotation_mark._graphunslopify_annotation_series = name"] : []),
    "            labelled.add(name)",
    "    ax.set_yticks(np.arange(len(categories)))",
    "    ax.set_yticklabels([str(value) for value in reversed(categories)])",
    "    ax.set_ylim(-0.6, len(categories) - 0.4)",
    "",
  );
}

function emitCalibration(spec: FigureSpec & { kind: "calibration" }, out: string[]): void {
  void spec;
  // One binned estimate owns marks, ECE, descriptions and claim inputs.
  out.push(...String.raw`

def calibration_input(frame):
    if frame.empty:
        raise ValueError("Calibration needs at least one observation")
    labels = [field for field in (GROUP, globals().get("FACET_BY"), globals().get("FACET_ROWS")) if field is not None]
    missing = [field for field in [X_FIELD, OUTCOME_FIELD, *labels] if field not in frame]
    if missing:
        raise ValueError("Calibration is missing required columns: " + ", ".join(missing))
    if labels and frame[labels].isna().any(axis=None):
        raise ValueError("Calibration requires nonmissing series and panel labels")
    predicted = pd.to_numeric(frame[X_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    observed = pd.to_numeric(frame[OUTCOME_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if not (np.isfinite(predicted) & (predicted >= 0) & (predicted <= 1)).all():
        raise ValueError("Calibration predicted probabilities must be finite and between 0 and 1")
    if not (np.isfinite(observed) & np.isin(observed, [0, 1])).all():
        raise ValueError("Calibration observed outcomes must be binary 0 or 1")
    return predicted, observed


def calibration_estimate(frame):
    predicted, observed = calibration_input(frame)
    edges = np.linspace(0.0, 1.0, BINS + 1)
    # Right-closed interior boundaries; zero belongs to the first bin.
    slot = np.searchsorted(edges[1:-1], predicted, side="left")
    totals = np.bincount(slot, minlength=BINS)
    occupied = np.flatnonzero(totals)
    counts = totals[occupied]
    centres = np.bincount(slot, weights=predicted, minlength=BINS)[occupied] / counts
    rates = np.bincount(slot, weights=observed, minlength=BINS)[occupied] / counts
    ece = float(np.sum(counts * np.abs(rates - centres)) / len(predicted))
    return {"probability": centres, "frequency": rates, "counts": counts,
            "bin": occupied, "ece": ece, "observations": len(predicted)}


def calibration_claim_frame(frame):
    calibration_input(frame)
    roles = [X_FIELD, Y_FIELD, *([GROUP] if GROUP is not None else [])]
    if len(roles) != len(set(roles)):
        raise ValueError("Calibration claims need distinct probability, frequency-output and series field names")
    curves = [(name, calibration_estimate(frame if name is None else frame[frame[GROUP] == name]))
              for name in (series_names(frame) if GROUP is not None else [None])]
    canonical = {}
    for number in range(BINS):
        points = sorted({float(value) for _, curve in curves
                         for slot, value in zip(curve["bin"], curve["probability"]) if slot == number})
        anchor = None
        for value in points:
            if anchor is None or value - anchor > 1e-12:
                anchor = value
            canonical[number, value] = anchor
    blocks = []
    for name, curve in curves:
        # Match only within-bin roundoff, independent of series/row order.
        points = [canonical[int(slot), float(value)] for slot, value in zip(curve["bin"], curve["probability"])]
        data = {X_FIELD: points, Y_FIELD: curve["frequency"]}
        if GROUP is not None:
            data[GROUP] = [name] * len(points)
        blocks.append(pd.DataFrame(data))
    # Meaningfully different plotted probability means remain unaligned.
    return pd.concat(blocks, ignore_index=True)


def draw_panel(ax, df):
    calibration_input(df)
    names = series_names(df) if GROUP is not None else [None]
    for index, name in enumerate(names):
        block = df if name is None else df[df[GROUP] == name]
        curve = calibration_estimate(block)
        style = series_style(name, index, len(names))
        label = None if name is None else str(name)
        ax.plot(curve["probability"], curve["frequency"], marker="o", markersize=4,
                label=None if label is None else f"{label} (ECE {curve['ece']:.3g})",
                color=style["colour"], linewidth=style["width"], alpha=style["alpha"],
                zorder=style["zorder"], linestyle=style["linestyle"])
        who = "the model" if name is None else str(name)
        print(f"calibration: {who} has an expected calibration error of {curve['ece']:.4g} "
              f"over {curve['observations']} predictions in {len(curve['counts'])} of {BINS} bins")
    ax.plot([0, 1], [0, 1], color="#606060", linewidth=0.9, linestyle=(0, (4, 3)), zorder=1)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
`.split("\n"));
}

function emitQq(spec: FigureSpec & { kind: "qq" }, out: string[]): void {
  out.push("", `QQ_DISTRIBUTION = ${JSON.stringify(spec.distribution)}`);
  out.push(...String.raw`

def qq_input(frame):
    labels = [field for field in (GROUP, globals().get("FACET_BY"), globals().get("FACET_ROWS")) if field is not None]
    missing = [field for field in [Y_FIELD, *labels] if field not in frame]
    if missing:
        raise ValueError("Q-Q is missing required columns: " + ", ".join(missing))
    if labels and frame[labels].isna().any(axis=None):
        raise ValueError("Q-Q requires nonmissing series and panel identifiers")
    for field in labels:
        if frame[field].map(lambda value: isinstance(value, str) and not value.strip()
                            or isinstance(value, (float, np.floating)) and not np.isfinite(value)).any():
            raise ValueError("Q-Q identifiers must be nonempty and finite when numeric")
    source = frame.copy()
    values = pd.to_numeric(source[Y_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if np.any(source[Y_FIELD].notna().to_numpy() & ~np.isfinite(values)):
        raise ValueError("Q-Q nonmissing measurements must be finite numbers")
    if np.isfinite(values).sum() < 2:
        raise ValueError("Q-Q needs at least two finite observations per series and panel")
    source[Y_FIELD] = values
    return source


def qq_quantiles(probabilities):
    probabilities = np.asarray(probabilities, dtype=float)
    if not ((probabilities > 0) & (probabilities < 1)).all():
        raise ValueError("Q-Q plotting probabilities must be strictly between zero and one")
    if QQ_DISTRIBUTION == "normal":
        from statistics import NormalDist
        reference = NormalDist()
        return np.array([reference.inv_cdf(float(p)) for p in probabilities])
    return probabilities.copy()


def qq_estimate(frame):
    source = qq_input(frame)
    observed = np.sort(source[Y_FIELD].dropna().to_numpy(dtype=float))
    probabilities = (np.arange(1, len(observed) + 1) - 0.375) / (len(observed) + 0.25)
    theoretical = qq_quantiles(probabilities)
    with np.errstate(over="ignore", invalid="ignore"):
        q1, median, q3 = np.percentile(observed, [25, 50, 75], method="linear")
        theory_q = qq_quantiles([0.25, 0.75])
        slope = float((q3 - q1) / (theory_q[1] - theory_q[0]))
        intercept = float(q1 - slope * theory_q[0])
        axes = RUN_REPORT["spec"]
        nonlinear = any(axes[key]["scale"] != "linear" for key in ("x", "y"))
        line_x = np.linspace(theoretical[0], theoretical[-1], 100) if nonlinear else theoretical[[0, -1]]
        line_y = intercept + slope * line_x
    if not np.isfinite([q1, median, q3, slope, intercept]).all() or not np.isfinite(line_y).all():
        raise ValueError("Q-Q derived quartiles and reference line must remain finite")
    if axes["x"]["scale"] == "log" and np.any(theoretical <= 0):
        raise ValueError("Q-Q log x cannot display nonpositive theoretical quantiles")
    if axes["y"]["scale"] == "log" and (np.any(observed <= 0) or np.any(line_y <= 0)):
        raise ValueError("Q-Q log y needs positive observations and reference-line values")
    return {"observed": observed, "theoretical": theoretical, "probability": probabilities,
            "q1": float(q1), "median": float(median), "q3": float(q3),
            "slope": slope, "intercept": intercept, "line_x": line_x, "line_y": line_y,
            "observations": len(observed), "missing": len(source) - len(observed),
            "constant": bool(observed[0] == observed[-1])}


def qq_claim_frame(frame):
    roles = [X_FIELD, Y_FIELD, *([GROUP] if GROUP is not None else [])]
    if len(roles) != len(set(roles)):
        raise ValueError("Q-Q derived evidence needs distinct theoretical, observed and series field names")
    blocks = []
    for name in (series_names(frame) if GROUP is not None else [None]):
        curve = qq_estimate(frame if name is None else frame[frame[GROUP] == name])
        data = {X_FIELD: curve["theoretical"], Y_FIELD: curve["observed"]}
        if GROUP is not None:
            data[GROUP] = [name] * curve["observations"]
        blocks.append(pd.DataFrame(data))
    return pd.concat(blocks, ignore_index=True)


def record_qq(curve, name):
    record = {key: curve[key] for key in ("observations", "missing", "q1", "median", "q3", "slope", "intercept", "constant")}
    record.update(panel=CURRENT_PANEL, series=None if name is None else str(name), metric=Y_FIELD,
                  distribution=QQ_DISTRIBUTION, plotting_positions="Blom", reference_line="population_quartiles")
    entries = ROW_COUNTS.setdefault("qq", [])
    entries[:] = [item for item in entries if (item["panel"], item["series"]) != (record["panel"], record["series"])]
    entries.append(record)
    if curve["constant"]:
        finding("warning", "qq_constant_sample", f"Q-Q panel {CURRENT_PANEL}, series {record['series']}: constant sample cannot assess distribution shape")


def draw_panel(ax, df):
    qq_input(df)
    names = series_names(df) if GROUP is not None else [None]
    for index, name in enumerate(names):
        curve = qq_estimate(df if name is None else df[df[GROUP] == name])
        record_qq(curve, name)
        style = series_style(name, index, len(names))
        ax.scatter(curve["theoretical"], curve["observed"], s=10,
                   label=None if name is None else str(name), color=style["colour"],
                   marker=style["marker"], alpha=0.7, linewidths=0, zorder=3)
        ax.plot(curve["line_x"], curve["line_y"], color=style["colour"], linewidth=0.9,
                linestyle=(0, (4, 3)), zorder=2)
`.split("\n"));
}

function emitKaplanMeier(spec: FigureSpec & { kind: "kaplan_meier" }, out: string[]): void {
  void spec;
  // Events at a time share the risk set just before that time; tied censors
  // leave afterwards. One estimate owns marks, descriptions and claim inputs.
  out.push(...String.raw`

def survival_input(frame):
    if frame.empty:
        raise ValueError("Kaplan-Meier needs at least one observation")
    labels = [field for field in (GROUP, globals().get("FACET_BY"), globals().get("FACET_ROWS")) if field is not None]
    missing = [field for field in [X_FIELD, EVENT_FIELD, *labels] if field not in frame]
    if missing:
        raise ValueError("Kaplan-Meier is missing required columns: " + ", ".join(missing))
    if labels and frame[labels].isna().any(axis=None):
        raise ValueError("Kaplan-Meier requires nonmissing cohort and panel labels")
    times = pd.to_numeric(frame[X_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    events = pd.to_numeric(frame[EVENT_FIELD], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if not (np.isfinite(times) & (times >= 0)).all():
        raise ValueError("Kaplan-Meier follow-up times must be finite and non-negative")
    if not (np.isfinite(events) & np.isin(events, [0, 1])).all():
        raise ValueError("Kaplan-Meier event indicators must be 0 (right-censored) or 1 (observed)")
    return times, events


def survival_estimate(frame):
    times, events = survival_input(frame)
    moments, inverse, totals = np.unique(times, return_inverse=True, return_counts=True)
    deaths = np.bincount(inverse, weights=events).astype(int)
    at_risk, survival = len(times), 1.0
    steps_t, steps_s = [0.0], [1.0]
    censored_t, censored_s = [], []
    median = None
    for moment, total, observed in zip(moments, totals, deaths):
        survival *= 1.0 - int(observed) / at_risk
        steps_t.append(float(moment))
        steps_s.append(float(survival))
        censored = int(total - observed)
        censored_t.extend([float(moment)] * censored)
        censored_s.extend([float(survival)] * censored)
        # The first 50% crossing must not move one record because of roundoff.
        if median is None and (survival <= 0.5 or np.isclose(survival, 0.5, rtol=1e-12, atol=0)):
            median = float(moment)
        at_risk -= int(total)
    return {"time": np.asarray(steps_t), "survival": np.asarray(steps_s),
            "censor_time": np.asarray(censored_t), "censor_survival": np.asarray(censored_s),
            "observations": len(times), "events": int(events.sum()),
            "censored": int(len(times) - events.sum()), "last": float(moments[-1]), "median": median}


def survival_claim_frame(frame):
    times, _ = survival_input(frame)
    roles = [X_FIELD, Y_FIELD, *([GROUP] if GROUP is not None else [])]
    if len(roles) != len(set(roles)):
        raise ValueError("Kaplan-Meier claims need distinct time, survival-output and cohort field names")
    grid = np.unique(np.concatenate(([0.0], times)))
    blocks = []
    for name in series_names(frame) if GROUP is not None else [None]:
        block = frame if name is None else frame[frame[GROUP] == name]
        curve = survival_estimate(block)
        values = curve["survival"][np.searchsorted(curve["time"], grid, side="right") - 1].copy()
        # A censored cohort does not establish survival beyond its follow-up.
        values[grid > curve["last"]] = np.nan
        data = {X_FIELD: grid, Y_FIELD: values}
        if GROUP is not None:
            data[GROUP] = [name] * len(grid)
        blocks.append(pd.DataFrame(data))
    return pd.concat(blocks, ignore_index=True)


def draw_panel(ax, df):
    survival_input(df)
    names = series_names(df) if GROUP is not None else [None]
    for index, name in enumerate(names):
        block = df if name is None else df[df[GROUP] == name]
        curve = survival_estimate(block)
        style = series_style(name, index, len(names))
        ax.step(curve["time"], curve["survival"], where="post",
                label=None if name is None else str(name), color=style["colour"],
                linewidth=style["width"], alpha=style["alpha"],
                zorder=style["zorder"], linestyle=style["linestyle"])
        if len(curve["censor_time"]):
            ax.scatter(curve["censor_time"], curve["censor_survival"], marker="|", s=28,
                       color=style["colour"], zorder=4, linewidths=1.0)
        label = "the cohort" if name is None else str(name)
        print(f"survival: {label} had {curve['events']} events and {curve['censored']} "
              f"right-censored records out of {curve['observations']}")
    ax.set_ylim(-0.02, 1.02)
`.split("\n"));
}

function emitScalingFit(spec: FigureSpec & { kind: "scaling_fit" }, out: string[]): void {
  out.push("", `SCALING_INTERVAL = ${JSON.stringify(spec.interval)}`,
    `SCALING_SHOW_POINTS = ${spec.show_points ? "True" : "False"}`);
  out.push(...String.raw`

def scaling_input(frame):
    spec = RUN_REPORT["spec"]
    if not SCALING_SHOW_POINTS and (CLAIMS or spec.get("annotate")):
        raise ValueError("Scaling observation claims/annotations require visible observed points")
    if spec["x"].get("temporal") or spec["y"].get("temporal"):
        raise ValueError("Scaling fits require numeric axes")
    labels = [field for field in (GROUP, globals().get("FACET_BY"), globals().get("FACET_ROWS")) if field is not None]
    missing = [field for field in [X_FIELD, Y_FIELD, *labels] if field not in frame]
    if missing:
        raise ValueError("Scaling fit is missing required columns: " + ", ".join(missing))
    if labels and frame[labels].isna().any(axis=None):
        raise ValueError("Scaling fits require nonmissing series and panel identifiers")
    for field in labels:
        if frame[field].map(lambda value: isinstance(value, str) and not value.strip()
                            or isinstance(value, (float, np.floating)) and not np.isfinite(value)).any():
            raise ValueError("Scaling identifiers must be nonempty and finite when numeric")
    if len(frame) < 2:
        raise ValueError("Scaling fit needs at least two observations per series and panel")
    source = frame.copy()
    for field in (X_FIELD, Y_FIELD):
        values = pd.to_numeric(source[field], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        if not (np.isfinite(values) & (values > 0)).all():
            raise ValueError("Scaling retained x/y values must be finite and strictly positive")
        source[field] = values
    return source


def scaling_t_critical(df):
    try:
        from scipy.stats import t
    except ImportError:
        return None
    critical = float(t.ppf(0.975, df))
    if not np.isfinite(critical) or critical <= 0:
        raise ValueError("Scaling Student-t critical value is not finite and positive")
    return critical


def scaling_estimate(frame):
    source = scaling_input(frame).sort_values([X_FIELD, Y_FIELD], kind="mergesort")
    x, y = source[X_FIELD].to_numpy(dtype=float), source[Y_FIELD].to_numpy(dtype=float)
    log_x, log_y = np.log10(x), np.log10(y)
    mean_x = float(log_x.mean())
    constant = bool(np.all(y == y[0]))
    mean_y = float(log_y[0] if constant else log_y.mean())
    dx, dy = log_x - mean_x, np.zeros_like(log_y) if constant else log_y - mean_y
    spread = float(np.dot(dx, dx))
    if not np.isfinite(spread) or spread <= 0:
        raise ValueError("Scaling fit needs representable variation in log x")
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        slope = float(np.dot(dx, dy) / spread)
        intercept = float(mean_y - slope * mean_x)
        residual = dy - slope * dx
        residual_ss = float(np.dot(residual, residual))
        total_ss = float(np.dot(dy, dy))
        df = len(x) - 2
        residual_se = float(np.sqrt(residual_ss / df)) if df > 0 else None
        stderr = float(residual_se / np.sqrt(spread)) if df > 0 else None
        grid_x = np.logspace(log_x.min(), log_x.max(), 100)
        grid_x[0], grid_x[-1] = x[0], x[-1]
        grid_y = 10.0 ** (mean_y + slope * (np.log10(grid_x) - mean_x))
    scalars = [slope, intercept, residual_ss, total_ss, *([] if stderr is None else [stderr, residual_se])]
    if not np.isfinite(scalars).all() or not (np.isfinite(grid_x) & (grid_x > 0)).all() or not (np.isfinite(grid_y) & (grid_y > 0)).all():
        raise ValueError("Scaling fitted parameters and curve must remain finite and positive where required")
    interval = {"method": "none", "level": None, "status": "not_requested", "low": None,
                "high": None, "critical": None, "margin": None, "reason": "interval not requested"}
    if SCALING_INTERVAL == "t95":
        interval.update(method="student_t", level=0.95, status="unavailable")
        if df <= 0:
            interval["reason"] = "at least three observations are needed for residual uncertainty"
        else:
            critical = scaling_t_critical(df)
            if critical is None:
                interval["reason"] = "install graphunslopify[statistics] for the requested Student-t interval"
            else:
                margin = float(critical * stderr)
                low, high = slope - margin, slope + margin
                if not np.isfinite([low, high, margin]).all():
                    raise ValueError("Scaling confidence bounds must remain finite")
                interval.update(status="available", low=float(low), high=float(high), critical=critical, margin=margin, reason=None)
    return {"x": x, "y": y, "grid_x": grid_x, "grid_y": grid_y,
            "observations": len(x), "df": df, "slope": slope, "intercept": intercept,
            "stderr": stderr, "residual_se": residual_se, "log_x_center": mean_x, "log_y_center": mean_y,
            "r_squared": None if total_ss == 0 else float(max(0.0, 1.0 - residual_ss / total_ss)),
            "constant_response": constant, "interval": interval}


def record_scaling_fit(fit, name):
    record = {key: value for key, value in fit.items() if key not in ("x", "y", "grid_x", "grid_y")}
    record.update(panel=CURRENT_PANEL, series=None if name is None else str(name), metric=Y_FIELD,
                  method="least_squares_log10")
    entries = ROW_COUNTS.setdefault("scaling_fits", [])
    entries[:] = [item for item in entries if (item["panel"], item["series"]) != (record["panel"], record["series"])]
    entries.append(record)
    who = f"Scaling panel {CURRENT_PANEL}, series {record['series']}"
    if fit["interval"]["status"] == "unavailable":
        reason = f"{who}: interval unavailable; {fit['interval']['reason']}"
        if reason not in RUN_REPORT["untested"]:
            RUN_REPORT["untested"].append(reason)
        finding("warning", "scaling_interval_unavailable", reason)
    if fit["stderr"] is None:
        finding("warning", "scaling_residual_variance_unavailable", f"{who}: no residual degrees of freedom")


def draw_panel(ax, df):
    scaling_input(df)
    names = series_names(df) if GROUP is not None else [None]
    for index, name in enumerate(names):
        fit = scaling_estimate(df if name is None else df[df[GROUP] == name])
        record_scaling_fit(fit, name)
        style = series_style(name, index, len(names))
        label = None if name is None else str(name)
        if SCALING_SHOW_POINTS:
            ax.scatter(fit["x"], fit["y"], s=14, label=label, color=style["colour"],
                       marker=style["marker"], alpha=0.75, linewidths=0, zorder=3)
        ax.plot(fit["grid_x"], fit["grid_y"], color=style["colour"], linewidth=1.3,
                label=None if SCALING_SHOW_POINTS else label,
                linestyle=(0, (5, 2)) if SCALING_SHOW_POINTS else style["linestyle"], zorder=2)
        text = f"scaling: {label or 'the fit'} has fitted exponent {fit['slope']:+.4g} over {fit['observations']} observations"
        interval = fit["interval"]
        if interval["status"] == "available":
            text += f"; conditional 95% Student-t interval: plus or minus {interval['margin']:.4g} (df={fit['df']})"
        else:
            text += f"; {interval['reason']}"
        print(text)
`.split("\n"));
}

function emitConfusionMatrix(
  spec: FigureSpec & { kind: "confusion_matrix" },
  out: string[],
): void {
  const counts = spec.value
    ? 'df.pivot_table(index=Y_FIELD, columns=X_FIELD, values=VALUE_FIELD, aggfunc="sum", fill_value=0, observed=True)'
    : 'df.pivot_table(index=Y_FIELD, columns=X_FIELD, aggfunc="size", fill_value=0, observed=True)';
  out.push("", "def confusion_counts(df):");
  if (spec.value) out.push(
    "    df = df.copy()",
    '    values = pd.to_numeric(df[VALUE_FIELD], errors="raise").to_numpy(dtype=float)',
    "    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values != np.floor(values)):",
    '        raise ValueError("confusion counts must be finite nonnegative integers")',
    "    df[VALUE_FIELD] = values",
  );
  out.push(
    `    matrix = ${counts}`,
    "    labels = sorted(set(matrix.index) | set(matrix.columns), key=str)",
    "    return matrix.reindex(index=labels, columns=labels, fill_value=0)",
    "", "", "def draw_panel(ax, df):",
    "    matrix = confusion_counts(df)",
    "    labels = list(matrix.index)",
    "    raw = matrix.to_numpy(dtype=float)",
    "    shown = raw.copy()",
  );
  if (spec.normalize === "row") {
    out.push(
      "    # Each row sums to one, so a cell reads as recall for that true class.",
      "    totals = raw.sum(axis=1, keepdims=True)",
      "    shown = np.divide(raw, totals, out=np.zeros_like(raw), where=totals > 0)",
    );
  } else if (spec.normalize === "column") {
    out.push(
      "    # Each column sums to one, so a cell reads as precision for that",
      "    # predicted class.",
      "    totals = raw.sum(axis=0, keepdims=True)",
      "    shown = np.divide(raw, totals, out=np.zeros_like(raw), where=totals > 0)",
    );
  }
  out.push(
    "    image = ax.imshow(shown, cmap=SEQUENTIAL_MAP, aspect=\"equal\", vmin=0, vmax=shown.max() or 1)",
    "    ax.set_xticks(np.arange(len(labels)))",
    "    ax.set_yticks(np.arange(len(labels)))",
    "    ax.set_xticklabels([str(value) for value in labels])",
    "    ax.set_yticklabels([str(value) for value in labels])",
    "    bar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.04)",
    `    bar.set_label(${JSON.stringify(
      spec.normalize === "none" ? "Count" : `Share of each ${spec.normalize}`,
    )})`,
  );
  if (spec.annotate_cells) {
    out.push(
      "    # A printed number is exact where shading is estimated, and a",
      "    # confusion matrix is usually read one cell at a time.",
      "    for row in range(len(labels)):",
      "        for column in range(len(labels)):",
      `            text = ${
        spec.normalize === "none"
          ? 'f"{int(raw[row, column])}"'
          : 'f"{shown[row, column]:.2f}"'
      }`,
      "            ax.text(",
      "                column,",
      "                row,",
      "                text,",
      '                ha="center",',
      '                va="center",',
      "                color=cell_text_colour(ax, column, row),",
      "                fontsize=ANNOTATION_PT,",
      "            )",
    );
  }
  out.push("");
}

function emitWaterfall(spec: FigureSpec & { kind: "waterfall" }, out: string[]): void {
  void spec;
  // Each bar starts where the last one ended. Only the first and the total sit
  // on the baseline, so every other bar is read by length alone, which is why
  // the running total is printed as well as drawn.
  out.push(
    "",
    "def waterfall_estimate(df):",
    "    categories = category_order(df)",
    "    contributions = [",
    "        float(df[df[X_FIELD] == name][Y_FIELD].sum(min_count=1)) for name in categories",
    "    ]",
    "    if not np.isfinite(contributions).all():",
    '        raise ValueError("Waterfall needs a finite contribution for every observed step")',
    '    with np.errstate(over="ignore", invalid="ignore"):',
    "        levels = np.r_[START, START + np.cumsum(contributions)]",
    "    if not np.isfinite(levels).all():",
    '        raise ValueError("Waterfall needs finite cumulative totals")',
    "    return categories, contributions, levels",
    "",
    "",
    "def draw_panel(ax, df):",
    "    categories, contributions, levels = waterfall_estimate(df)",
    "    running = START",
    "    positions = np.arange(len(categories) + 1)",
    "    for index, (name, delta) in enumerate(zip(categories, contributions)):",
    "        bottom = min(running, running + delta)",
    "        colour = PALETTE[0] if delta >= 0 else PALETTE[1]",
    `        ${spec.annotate?.length ? "_annotation_bars = " : ""}ax.bar(`,
    "            index,",
    "            abs(delta),",
    "            bottom=bottom,",
    "            width=0.62,",
    "            color=colour,",
    "            alpha=0.85,",
    "            linewidth=0,",
    "            zorder=2,",
    "        )",
    ...(spec.annotate?.length ? [
      "        _annotation_bars.patches[0]._graphunslopify_annotation_value = delta",
      "        _annotation_bars.patches[0]._graphunslopify_annotation_end = running + delta",
    ] : []),
    "        if index:",
    "            ax.plot(",
    "                [index - 0.69, index - 0.31],",
    "                [running, running],",
    '                color="#9a9a9a",',
    "                linewidth=0.8,",
    "                zorder=1,",
    "            )",
    "        running = float(levels[index + 1])",
    "    # Autoscale measures the bars, not the baseline they are measured from,",
    "    # so the start line and the first bar's foot fall outside the view.",
    "    floor, ceiling = min(levels), max(levels)",
    "    pad = 0.12 * (ceiling - floor) or 1.0",
    "    ax.set_ylim(floor - pad, ceiling + pad)",
    "    ax.bar(",
    "        len(categories),",
    "        running - START,",
    "        bottom=START,",
    "        width=0.62,",
    '        color="#5a5a5a",',
    "        alpha=0.85,",
    "        linewidth=0,",
    "        zorder=2,",
    "    )",
    '    ax.axhline(START, color="#606060", linewidth=0.9, linestyle=(0, (4, 3)), zorder=1)',
    "    ax.set_xticks(positions)",
    '    ax.set_xticklabels([str(value) for value in categories] + ["total"])',
    "    print(",
    '        f"waterfall: {START:.4g} plus {len(categories)} contributions gives {running:.4g}. "',
    '        "The order of the steps is the order given in the spec and changes the picture."',
    "    )",
    "",
  );
}

function emitSparklineGrid(spec: FigureSpec & { kind: "sparkline_grid" }, out: string[]): void {
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    names = series_names(df)",
    `    columns = min(${spec.columns}, max(len(names), 1))`,
    "    rows = int(np.ceil(len(names) / columns)) if names else 1",
    "    # One shared scale across every cell. Free limits would let a flat",
    "    # series look as dramatic as a real one.",
    "    ax.margins(y=0.08)",
    "    ax.set_xticks([])",
    "    ax.set_yticks([])",
    "    for side in ax.spines.values():",
    "        side.set_visible(False)",
    "    for index, name in enumerate(names):",
    "        block = df[df[GROUP] == name].dropna(subset=[X_FIELD, Y_FIELD]).sort_values(X_FIELD)",
    "        row, column = divmod(index, columns)",
    "        cell = ax.inset_axes(",
    "            [",
    "                column / columns + 0.012,",
    "                1.0 - (row + 1) / rows + 0.012,",
    "                1.0 / columns - 0.024,",
    "                1.0 / rows - 0.024,",
    "            ], sharex=ax, sharey=ax",
    "        )",
    "        style = series_style(name, index, len(names))",
    "        cell.plot(",
    "            block[X_FIELD],",
    "            block[Y_FIELD],",
    '            color=style["colour"],',
    "            linewidth=0.9,",
    "        )",
    "        cell.margins(y=0.08)",
    "        cell.set_xticks([])",
    "        cell.set_yticks([])",
    "        for side in cell.spines.values():",
    "            side.set_visible(False)",
    "        cell.set_title(str(name), fontsize=ANNOTATION_PT, pad=2)",
    "",
  );
}

function emitHeatmap(spec: FigureSpec & { kind: "heatmap" }, out: string[]): void {
  out.push(
    "",
    "def heatmap_matrix(df):",
    "    return df.pivot_table(",
    "        index=Y_FIELD,",
    "        columns=X_FIELD,",
    "        values=VALUE_FIELD,",
    `        aggfunc=${spec.aggregation === "sum" ? "lambda values: values.sum(min_count=1)" : pyStr(spec.aggregation)},`,
    "        sort=False,",
    "        observed=True, dropna=False,",
    "    )",
    "",
    "",
    "def draw_panel(ax, df):",
    "    matrix = heatmap_matrix(df)",
    "    values = matrix.to_numpy(dtype=float)",
  );

  if (spec.diverging) {
    out.push(
      "    reach = (float(np.nanmax(np.abs(values))) or 1.0) if np.isfinite(values).any() else 1.0",
      "    image = ax.imshow(",
      "        values,",
      '        aspect="auto",',
      "        cmap=DIVERGING_MAP,",
      "        vmin=-reach,",
      "        vmax=reach,",
      "    )",
    );
  } else {
    out.push("    image = ax.imshow(values, aspect=\"auto\", cmap=SEQUENTIAL_MAP)");
  }

  out.push(
    "    ax.set_xticks(range(len(matrix.columns)))",
    "    ax.set_xticklabels([str(c) for c in matrix.columns])",
    "    ax.set_yticks(range(len(matrix.index)))",
    "    ax.set_yticklabels([str(i) for i in matrix.index])",
    "    bar = ax.figure.colorbar(image, ax=ax)",
    "    bar.set_label(VALUE_LABEL)",
  );

  if (spec.annotate_cells) {
    out.push(
      "    # Compare actual normalized cell backgrounds with pure black and white.",
      "    # One precision for every cell, so the grid reads like a table.",
      "    reach = np.nanmax(np.abs(values)) if np.isfinite(values).any() else 1.0",
      "    digits = 0 if reach >= 100 else 1 if reach >= 10 else 2 if reach >= 1 else 3",
      "    for row in range(values.shape[0]):",
      "        for column in range(values.shape[1]):",
      "            cell = values[row, column]",
      "            if not np.isfinite(cell):",
      "                continue",
      "            ax.text(",
      "                column,",
      "                row,",
      '                f"{cell:.{digits}f}",',
      '                ha="center",',
      '                va="center",',
      "                color=cell_text_colour(ax, column, row),",
      "                fontsize=ANNOTATION_PT - 1,",
      "            )",
    );
  }
  out.push("");
}

export function emitDraw(spec: PlottedSpec, out: string[]): void {
  emitSeriesHelpers(spec, out);
  if (hasCategoricalX(spec)) {
    emitCategories(spec, out);
  }
  if (spec.kind === "ridgeline") emitDensityHelper(out);

  switch (spec.kind) {
    case "line":
      emitLine(spec, out);
      break;
    case "scatter":
      emitScatter(spec, out);
      break;
    case "bar":
      emitBar(spec, out);
      break;
    case "box":
    case "violin":
      emitDistribution(spec, out);
      break;
    case "ecdf":
      emitEcdf(spec, out);
      break;
    case "raincloud":
      emitRaincloud(spec, out);
      break;
    case "ridgeline":
      emitRidgeline(spec, out);
      break;
    case "forest":
      emitForest(spec, out);
      break;
    case "paired_difference":
      emitPairedDifference(spec, out);
      break;
    case "slope":
      emitSlope(spec, out);
      break;
    case "dumbbell":
      emitDumbbell(spec, out);
      break;
    case "calibration":
      emitCalibration(spec, out);
      break;
    case "qq":
      emitQq(spec, out);
      break;
    case "kaplan_meier":
      emitKaplanMeier(spec, out);
      break;
    case "scaling_fit":
      emitScalingFit(spec, out);
      break;
    case "confusion_matrix":
      emitConfusionMatrix(spec, out);
      break;
    case "waterfall":
      emitWaterfall(spec, out);
      break;
    case "sparkline_grid":
      emitSparklineGrid(spec, out);
      break;
    case "heatmap":
      emitHeatmap(spec, out);
      break;
    default: {
      const unhandled: never = spec;
      throw new Error(`no emitter for kind ${JSON.stringify(unhandled)}`);
    }
  }
  if (spec.annotate?.length) out.push("", "_primary_draw_panel = draw_panel", "", "def draw_panel(ax, frame):", "    _primary_draw_panel(ax, frame)", "    capture_annotation_geometry(ax, frame)", "");
}
