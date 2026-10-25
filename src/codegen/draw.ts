import { hasCategoricalX, type FigureSpec, type PlottedSpec } from "../schema.ts";
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
  const scatter = MARKER_KINDS.has(spec.kind);
  const sizes = scatter ? preset.marker : preset.line;
  const key = scatter ? "size" : "width";
  const dashed = DASHED_KINDS.has(spec.kind);
  const channelConst = scatter ? "MARKERS" : dashed ? "LINE_STYLES" : "HATCHES";
  const channelKey = scatter ? "marker" : dashed ? "linestyle" : "hatch";
  const plain = scatter ? pyStr("o") : dashed ? pyStr("-") : pyStr("");

  out.push(
    "",
    "def locked_appearance(names):",
    "    # A shared lock keeps a model the same colour in figure 1 and figure 7.",
    "    if PALETTE_LOCK is None:",
    "        return None",
    "    try:",
    "        from graphunslopify.lockfile import appearance",
    "    except ImportError:",
    '        print("graphunslopify is not installed, so palette_lock was ignored")',
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
  const sortable = spec.kind === "bar" || spec.kind === "box";
  out.push(
    "",
    "def category_order(frame):",
    "    if CATEGORY_ORDER is not None:",
    "        return [c for c in CATEGORY_ORDER if c in set(frame[X_FIELD])]",
  );
  if (sortable && "sort" in spec && spec.sort?.by === "value") {
    const ascending = spec.sort.direction === "asc" ? "True" : "False";
    out.push(
      "    ranked = frame.groupby(X_FIELD, sort=False)[Y_FIELD].mean()",
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
      `${indentLevel}ax.plot(`,
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
      "    names = series_names(frame)",
      "    running = np.zeros(len(categories))",
      "    for index, name in enumerate(names):",
      "        block = frame[frame[GROUP] == name].set_index(X_FIELD).reindex(categories)",
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
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    groups = [df[df[X_FIELD] == c][Y_FIELD].dropna().to_numpy(dtype=float) for c in categories]",
    "    groups = [g if len(g) else np.array([np.nan]) for g in groups]",
    "    positions = np.arange(len(categories))",
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
      "        body.set_facecolor(PALETTE[index % len(PALETTE)])",
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
      "        box.set_facecolor(PALETTE[index % len(PALETTE)])",
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
      "            np.full(len(values), index) + spread,",
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
    "    ax.set_xticks(positions)",
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
  void spec;
  // Half a violin, a quartile box and every raw point. The cloud shows the
  // shape, the box shows the summary a reader expects, and the rain is the
  // evidence for both, so a claim resting on six observations cannot hide
  // inside a smooth curve.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    groups = [df[df[X_FIELD] == c][Y_FIELD].dropna().to_numpy(dtype=float) for c in categories]",
    "    groups = [g if len(g) else np.array([np.nan]) for g in groups]",
    "    positions = np.arange(len(categories))",
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
    "        body.set_facecolor(PALETTE[index % len(PALETTE)])",
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
    "            np.full(len(values), index) + spread,",
    "            values,",
    "            s=6,",
    '            color="#303030",',
    "            alpha=0.55,",
    "            zorder=4,",
    "            linewidths=0,",
    "        )",
    "    ax.set_xticks(positions)",
    "    ax.set_xticklabels([str(value) for value in categories])",
    "",
  );
}

function emitRidgeline(spec: FigureSpec & { kind: "ridgeline" }, out: string[]): void {
  void spec;
  // Rows of densities down the page, the measured value running across. The
  // spec still says category on x and value on y; turning that into rows is a
  // presentation decision and belongs here rather than in the schema.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    groups = [df[df[X_FIELD] == c][Y_FIELD].dropna().to_numpy(dtype=float) for c in categories]",
    "    grid_lo = min((g.min() for g in groups if len(g)), default=0.0)",
    "    grid_hi = max((g.max() for g in groups if len(g)), default=1.0)",
    "    if not np.isfinite(grid_lo) or grid_hi <= grid_lo:",
    "        grid_lo, grid_hi = 0.0, 1.0",
    "    pad = 0.05 * (grid_hi - grid_lo)",
    "    grid = np.linspace(grid_lo - pad, grid_hi + pad, 256)",
    "    # Rows overlap by a fixed fraction of the row pitch, so a taller",
    "    # distribution cannot silently swallow the one above it.",
    "    for index, values in enumerate(reversed(groups)):",
    "        base = float(index)",
    "        if len(values) < 2 or not np.isfinite(values).any():",
    "            continue",
    "        density = _gaussian_density(values, grid)",
    "        peak = density.max()",
    "        if peak <= 0:",
    "            continue",
    "        height = 0.92 * density / peak",
    "        colour = PALETTE[(len(groups) - 1 - index) % len(PALETTE)]",
    "        ax.fill_between(grid, base, base + height, color=colour, alpha=0.62, linewidth=0, zorder=index)",
    '        ax.plot(grid, base + height, color="white", linewidth=0.7, zorder=index)',
    "    ax.set_yticks(np.arange(len(categories)))",
    "    ax.set_yticklabels([str(value) for value in reversed(categories)])",
    "    ax.set_ylim(-0.15, len(categories) + 0.5)",
    "",
  );
}

/**
 * A Gaussian kernel density, so a ridgeline needs no scipy.
 *
 * Silverman's rule picks the bandwidth, and the script prints it, because
 * bandwidth is the one number that decides whether a distribution looks
 * bimodal.
 */
function emitDensityHelper(out: string[]): void {
  out.push(
    "",
    "def _gaussian_density(values, grid):",
    "    values = values[np.isfinite(values)]",
    "    if len(values) < 2:",
    "        return np.zeros_like(grid)",
    "    spread = np.std(values, ddof=1)",
    "    if spread <= 0:",
    "        return np.zeros_like(grid)",
    "    # Silverman's rule of thumb.",
    "    bandwidth = 0.9 * min(spread, (np.percentile(values, 75) - np.percentile(values, 25)) / 1.349 or spread)",
    "    bandwidth *= len(values) ** (-0.2)",
    "    if bandwidth <= 0:",
    "        return np.zeros_like(grid)",
    "    offsets = (grid[:, None] - values[None, :]) / bandwidth",
    "    return np.exp(-0.5 * offsets**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))",
    "",
  );
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
  // The differences themselves, not the two conditions side by side. A test on
  // paired data operates on these numbers, so this is the distribution the
  // p-value actually described. Two overlapping boxes are not.
  out.push(
    "",
    "def _mean_interval(values):",
    "    if len(values) < 2:",
    "        return np.nan, np.nan",
    "    rng = np.random.default_rng(PAIR_SEED)",
    "    draws = rng.choice(values, size=(2000, len(values)), replace=True)",
    "    return tuple(np.percentile(draws.mean(axis=1), [2.5, 97.5]))",
    "",
    "",
    "def draw_panel(ax, df):",
    '    wide = df.pivot_table(index=PAIR_FIELD, columns=X_FIELD, values=Y_FIELD, aggfunc="mean")',
    "    if BASELINE not in wide.columns:",
    '        raise SystemExit(f"baseline {BASELINE!r} is not a value of {X_FIELD}")',
    "    others = [name for name in wide.columns if name != BASELINE]",
    "    jitter = np.random.default_rng(PAIR_SEED)",
    "    for index, other in enumerate(others):",
    "        paired = wide[[BASELINE, other]].dropna()",
    "        values = (paired[other] - paired[BASELINE]).to_numpy(dtype=float)",
    "        if not len(values):",
    "            continue",
    "        colour = PALETTE[index % len(PALETTE)]",
    "        spread = jitter.uniform(-0.07, 0.07, size=len(values))",
    "        ax.scatter(",
    "            np.full(len(values), index) + spread,",
    "            values,",
    "            s=10,",
    "            color=colour,",
    "            alpha=0.55,",
    "            linewidths=0,",
    "            zorder=2,",
    "        )",
    "        low, high = _mean_interval(values)",
    "        if np.isfinite(low) and np.isfinite(high):",
    "            ax.plot([index, index], [low, high], color=colour, linewidth=1.6, zorder=3)",
    "        ax.plot(",
    "            [index],",
    "            [values.mean()],",
    '            marker="o",',
    "            markersize=6,",
    "            color=colour,",
    '            markeredgecolor="white",',
    "            zorder=4,",
    '            linestyle="none",',
    "        )",
    "    # Zero is where the two conditions agree, so it is the only reference a",
    "    # difference plot needs.",
    '    ax.axhline(0.0, color="#606060", linewidth=0.9, linestyle=(0, (4, 3)), zorder=1)',
    "    ax.set_xticks(np.arange(len(others)))",
    '    ax.set_xticklabels([f"{name} minus {BASELINE}" for name in others])',
    "    ax.set_xlim(-0.6, len(others) - 0.4)",
    "",
  );
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
    "            ax.plot(",
    "                [value],",
    "                [row],",
    '                marker="o",',
    "                markersize=5.5,",
    "                color=PALETTE[position % len(PALETTE)],",
    '                markeredgecolor="white",',
    "                markeredgewidth=0.6,",
    "                zorder=3,",
    '                linestyle="none",',
    "                label=(str(name) if index == 0 and name is not None else None),",
    "            )",
    "    ax.set_yticks(np.arange(len(categories)))",
    "    ax.set_yticklabels([str(value) for value in reversed(categories)])",
    "    ax.set_ylim(-0.6, len(categories) - 0.4)",
    "",
  );
}

function emitCalibration(spec: FigureSpec & { kind: "calibration" }, out: string[]): void {
  void spec;
  // Predicted probability against the frequency actually observed, with the
  // diagonal a perfectly calibrated model would sit on. The bin count is
  // printed because it decides how much miscalibration is visible.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    edges = np.linspace(0.0, 1.0, BINS + 1)",
    "    names = series_names(df) if GROUP is not None else [None]",
    "    for index, name in enumerate(names):",
    "        block = df if name is None else df[df[GROUP] == name]",
    "        block = block.dropna(subset=[X_FIELD, OUTCOME_FIELD])",
    "        predicted = block[X_FIELD].to_numpy(dtype=float)",
    "        observed = block[OUTCOME_FIELD].to_numpy(dtype=float)",
    "        if not len(predicted):",
    "            continue",
    "        slot = np.clip(np.digitize(predicted, edges[1:-1]), 0, BINS - 1)",
    "        centres, rates, weights = [], [], []",
    "        for b in range(BINS):",
    "            here = slot == b",
    "            if not here.any():",
    "                continue",
    "            centres.append(predicted[here].mean())",
    "            rates.append(observed[here].mean())",
    "            weights.append(here.sum())",
    "        if not centres:",
    "            continue",
    "        centres = np.array(centres)",
    "        rates = np.array(rates)",
    "        weights = np.array(weights, dtype=float)",
    "        ece = float(np.sum(weights * np.abs(rates - centres)) / weights.sum())",
    "        style = series_style(name, index, len(names))",
    "        label = None if name is None else str(name)",
    "        ax.plot(",
    "            centres,",
    "            rates,",
    '            marker="o",',
    "            markersize=4,",
    '            label=None if label is None else f"{label} (ECE {ece:.3f})",',
    '            color=style["colour"],',
    '            linewidth=style["width"],',
    '            alpha=style["alpha"],',
    '            zorder=style["zorder"],',
    '            linestyle=style["linestyle"],',
    "        )",
    "        print(",
    '            f"calibration: {label or \'the model\'} has an expected calibration error of "',
    '            f"{ece:.4f} over {int(weights.sum())} predictions in {len(centres)} of {BINS} bins"',
    "        )",
    "    # Where a perfectly calibrated model would sit.",
    '    ax.plot([0, 1], [0, 1], color="#606060", linewidth=0.9, linestyle=(0, (4, 3)), zorder=1)',
    "    ax.set_xlim(-0.02, 1.02)",
    "    ax.set_ylim(-0.02, 1.02)",
    "",
  );
}

function emitQq(spec: FigureSpec & { kind: "qq" }, out: string[]): void {
  const quantile =
    spec.distribution === "normal"
      ? "np.sqrt(2.0) * _erfinv(2.0 * probabilities - 1.0)"
      : "probabilities";
  out.push(
    "",
    "def _erfinv(values):",
    "    # Winitzki's approximation, so a Q-Q plot needs no scipy. Good to about",
    "    # 2e-3 across the range, which is finer than the ink.",
    "    a = 0.147",
    "    clipped = np.clip(values, -0.999999, 0.999999)",
    "    ln = np.log(1.0 - clipped**2)",
    "    first = 2.0 / (np.pi * a) + ln / 2.0",
    "    return np.sign(clipped) * np.sqrt(np.sqrt(first**2 - ln / a) - first)",
    "",
    "",
    "def draw_panel(ax, df):",
    "    names = series_names(df) if GROUP is not None else [None]",
    "    for index, name in enumerate(names):",
    "        block = df if name is None else df[df[GROUP] == name]",
    "        values = np.sort(block[Y_FIELD].dropna().to_numpy(dtype=float))",
    "        if len(values) < 2:",
    "            continue",
    "        # Blom's plotting positions, which are the usual choice for a",
    "        # normal Q-Q and behave at the tails.",
    "        ranks = np.arange(1, len(values) + 1)",
    "        probabilities = (ranks - 0.375) / (len(values) + 0.25)",
    `        theoretical = ${quantile}`,
    "        style = series_style(name, index, len(names))",
    "        ax.scatter(",
    "            theoretical,",
    "            values,",
    "            s=10,",
    "            label=None if name is None else str(name),",
    '            color=style["colour"],',
    '            marker=style["marker"],',
    "            alpha=0.7,",
    "            linewidths=0,",
    "            zorder=3,",
    "        )",
    "        # The line through the quartiles, which is where the points fall if",
    "        # the assumed distribution holds.",
    "        sample_q = np.percentile(values, [25, 75])",
    "        theory_q = np.percentile(theoretical, [25, 75])",
    "        if theory_q[1] > theory_q[0]:",
    "            slope = (sample_q[1] - sample_q[0]) / (theory_q[1] - theory_q[0])",
    "            intercept = sample_q[0] - slope * theory_q[0]",
    "            span = np.array([theoretical.min(), theoretical.max()])",
    "            ax.plot(",
    "                span,",
    "                intercept + slope * span,",
    '                color=style["colour"],',
    "                linewidth=0.9,",
    "                linestyle=(0, (4, 3)),",
    "                zorder=2,",
    "            )",
    "",
  );
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
  // A power law fitted in log space, with the exponent and its interval
  // printed. A scaling plot whose exponent is only eyeballed off a log-log
  // axis is the thing this replaces.
  out.push(
    "",
    "def draw_panel(ax, df):",
    "    names = series_names(df) if GROUP is not None else [None]",
    "    for index, name in enumerate(names):",
    "        block = df if name is None else df[df[GROUP] == name]",
    "        block = block.dropna(subset=[X_FIELD, Y_FIELD])",
    "        x = block[X_FIELD].to_numpy(dtype=float)",
    "        y = block[Y_FIELD].to_numpy(dtype=float)",
    "        usable = (x > 0) & (y > 0)",
    "        x, y = x[usable], y[usable]",
    "        style = series_style(name, index, len(names))",
    "        label = None if name is None else str(name)",
  );
  if (spec.show_points) {
    out.push(
      "        ax.scatter(",
      "            x,",
      "            y,",
      "            s=14,",
      "            label=label,",
      '            color=style["colour"],',
      '            marker=style["marker"],',
      "            alpha=0.75,",
      "            linewidths=0,",
      "            zorder=3,",
      "        )",
    );
  }
  out.push(
    "        if len(x) < 3:",
    "            continue",
    "        log_x, log_y = np.log10(x), np.log10(y)",
    "        exponent, intercept = np.polyfit(log_x, log_y, 1)",
    "        # The standard error of the slope, so the exponent is reported with",
    "        # the precision the data actually supports.",
    "        residual = log_y - (exponent * log_x + intercept)",
    "        spread = np.sum((log_x - log_x.mean()) ** 2)",
    "        error = float(np.sqrt(np.sum(residual**2) / max(len(x) - 2, 1) / spread)) if spread > 0 else float('nan')",
    "        grid = np.logspace(np.log10(x.min()), np.log10(x.max()), 100)",
    "        ax.plot(",
    "            grid,",
    "            10.0 ** (intercept + exponent * np.log10(grid)),",
    '            color=style["colour"],',
    "            linewidth=1.3,",
    "            linestyle=(0, (5, 2)),",
    "            zorder=2,",
    "        )",
    "        print(",
    '            f"scaling: {label or \'the fit\'} follows a power law with exponent "',
    '            f"{exponent:+.4g} plus or minus {1.96 * error:.2g} over {len(x)} points"',
    "        )",
    "",
  );
}

function emitConfusionMatrix(
  spec: FigureSpec & { kind: "confusion_matrix" },
  out: string[],
): void {
  const counts = spec.value
    ? 'df.pivot_table(index=Y_FIELD, columns=X_FIELD, values=VALUE_FIELD, aggfunc="sum", fill_value=0)'
    : 'df.pivot_table(index=Y_FIELD, columns=X_FIELD, aggfunc="size", fill_value=0)';
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
      "    threshold = (shown.max() or 1) * 0.6",
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
      '                color="white" if shown[row, column] > threshold else "#202020",',
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
    "def draw_panel(ax, df):",
    "    categories = category_order(df)",
    "    contributions = [",
    "        float(df[df[X_FIELD] == name][Y_FIELD].sum()) for name in categories",
    "    ]",
    "    running = START",
    "    levels = [START]",
    "    positions = np.arange(len(categories) + 1)",
    "    for index, (name, delta) in enumerate(zip(categories, contributions)):",
    "        bottom = min(running, running + delta)",
    "        colour = PALETTE[0] if delta >= 0 else PALETTE[1]",
    "        ax.bar(",
    "            index,",
    "            abs(delta),",
    "            bottom=bottom,",
    "            width=0.62,",
    "            color=colour,",
    "            alpha=0.85,",
    "            linewidth=0,",
    "            zorder=2,",
    "        )",
    "        if index:",
    "            ax.plot(",
    "                [index - 0.69, index - 0.31],",
    "                [running, running],",
    '                color="#9a9a9a",',
    "                linewidth=0.8,",
    "                zorder=1,",
    "            )",
    "        running += delta",
    "        levels.append(running)",
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
    "    values = df[Y_FIELD].dropna().to_numpy(dtype=float)",
    "    low, high = (values.min(), values.max()) if len(values) else (0.0, 1.0)",
    "    if not np.isfinite(low) or high <= low:",
    "        low, high = low - 0.5, low + 0.5",
    "    pad = 0.08 * (high - low)",
    "    ax.set_axis_off()",
    "    for index, name in enumerate(names):",
    "        block = df[df[GROUP] == name].dropna(subset=[X_FIELD, Y_FIELD]).sort_values(X_FIELD)",
    "        row, column = divmod(index, columns)",
    "        cell = ax.inset_axes(",
    "            [",
    "                column / columns + 0.012,",
    "                1.0 - (row + 1) / rows + 0.012,",
    "                1.0 / columns - 0.024,",
    "                1.0 / rows - 0.024,",
    "            ]",
    "        )",
    "        cell.plot(",
    "            block[X_FIELD],",
    "            block[Y_FIELD],",
    "            color=PALETTE[index % len(PALETTE)],",
    "            linewidth=0.9,",
    "        )",
    "        cell.set_ylim(low - pad, high + pad)",
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
    "def draw_panel(ax, df):",
    "    matrix = df.pivot_table(",
    "        index=Y_FIELD,",
    "        columns=X_FIELD,",
    "        values=VALUE_FIELD,",
    `        aggfunc=${pyStr(spec.aggregation)},`,
    "        sort=False,",
    "    )",
    "    values = matrix.to_numpy(dtype=float)",
  );

  if (spec.diverging) {
    out.push(
      "    reach = float(np.nanmax(np.abs(values))) if np.isfinite(values).any() else 1.0",
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
      "    # White on dark, black on light, so the number stays readable either way.",
      "    span = np.nanmax(values) - np.nanmin(values) if np.isfinite(values).any() else 1.0",
      "    midpoint = np.nanmin(values) + span / 2 if span else 0.0",
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
      '                color="white" if cell > midpoint else "#111111",',
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
}
