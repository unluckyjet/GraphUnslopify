import { hasCategoricalX, type AxisSpec, type FigureSpec, type Significance } from "../schema.ts";
import { pyOptStr, pyStr } from "./py.ts";
import { LEGEND_LOCATIONS, PRESETS, REFERENCE_STYLES } from "./theme.ts";

/**
 * Everything drawn on top of the data.
 *
 * The spec places an annotation semantically, at "max" or "crossover", and the
 * geometry is worked out here at runtime because only the script has the data.
 */

function axisLabel(axis: AxisSpec): string {
  return axis.unit ? `${axis.label} (${axis.unit})` : axis.label;
}

/**
 * The label for an axis that carries differences rather than values.
 *
 * A paired-difference plot draws subtractions, so an axis reading "Accuracy
 * (%)" invites a reader to take 2.4 as an accuracy instead of a gain of 2.4.
 * The unit changes too: the difference between two percentages is measured in
 * percentage points, not in percent.
 */
function differenceLabel(axis: AxisSpec): string {
  const unit = axis.unit === "%" ? "pp" : axis.unit;
  const name = `Change in ${axis.label.charAt(0).toLowerCase()}${axis.label.slice(1)}`;
  return unit ? `${name} (${unit})` : name;
}

/**
 * Which plot axis a spec axis lands on.
 *
 * Two kinds swap them. A horizontal bar lists categories up the vertical axis,
 * and a ridgeline stacks one density per category down the page with the
 * measured value running across. Both are presentation decisions the generator
 * owns, and both will label the wrong axis if this mapping forgets them.
 */
function plotAxis(spec: FigureSpec, specAxis: "x" | "y"): "x" | "y" {
  const swapped =
    (spec.kind === "bar" && spec.orientation === "horizontal") ||
    spec.kind === "ridgeline" ||
    spec.kind === "forest" ||
    spec.kind === "dumbbell";
  return swapped ? (specAxis === "x" ? "y" : "x") : specAxis;
}

function isCategorical(spec: FigureSpec, specAxis: "x" | "y"): boolean {
  return hasCategoricalX(spec) && specAxis === "x";
}

export function emitHelpers(spec: FigureSpec, out: string[]): void {
  const preset = PRESETS[spec.style.preset];

  if (spec.kind === "scatter" && spec.trendline === "linear") {
    out.push(
      "",
      "def add_trendline(ax, xs, ys, colour):",
      "    x = np.asarray(xs, dtype=float)",
      "    y = np.asarray(ys, dtype=float)",
      "    usable = np.isfinite(x) & np.isfinite(y)",
      "    if usable.sum() < 2:",
      "        return",
      "    slope, intercept = np.polyfit(x[usable], y[usable], 1)",
      "    span = np.linspace(x[usable].min(), x[usable].max(), 100)",
      '    ax.plot(span, slope * span + intercept, color=colour, linewidth=1.0, linestyle="--", zorder=1)',
      "",
    );
  }

  if (spec.kind === "scatter" && spec.frontier) {
    const betterX = spec.frontier.x === "min" ? "<=" : ">=";
    const betterY = spec.frontier.y === "min" ? "<=" : ">=";
    out.push(
      "",
      "def draw_frontier(ax, frame):",
      "    # The non-dominated set: no other point is at least as good on both axes.",
      "    points = frame[[X_FIELD, Y_FIELD]].dropna().to_numpy(dtype=float)",
      "    keep = []",
      "    for candidate in points:",
      "        dominated = any(",
      `            (other[0] ${betterX} candidate[0])`,
      `            and (other[1] ${betterY} candidate[1])`,
      "            and not np.array_equal(other, candidate)",
      "            for other in points",
      "        )",
      "        if not dominated:",
      "            keep.append(candidate)",
      "    if len(keep) < 2:",
      "        return",
      "    ordered = np.array(sorted(keep, key=lambda p: p[0]))",
      "    ax.plot(",
      "        ordered[:, 0],",
      "        ordered[:, 1],",
      '        color="#404040",',
      "        linewidth=1.0,",
      '        linestyle="--",',
      "        zorder=1,",
      '        label="Pareto frontier",',
      "    )",
      "",
    );
  }

  if (spec.kind === "bar" && spec.uncertainty) {
    out.push(
      "",
      "def error_pair(block):",
      '    if "_low" not in block:',
      "        return None",
      "    centre = block[Y_FIELD].to_numpy(dtype=float)",
      "    return np.vstack([",
      '        np.abs(centre - block["_low"].to_numpy(dtype=float)),',
      '        np.abs(block["_high"].to_numpy(dtype=float) - centre),',
      "    ])",
      "",
    );
  }

  if (spec.kind === "bar" && spec.value_labels) {
    const horizontal = spec.orientation === "horizontal";
    out.push(
      "",
      "def label_bars(ax, values, positions):",
      "    numbers = np.asarray(values, dtype=float)",
      "    reach = np.nanmax(np.abs(numbers)) if np.isfinite(numbers).any() else 1.0",
      "    pad = reach * 0.02",
      "    for position, value in zip(positions, numbers):",
      "        if not np.isfinite(value):",
      "            continue",
      "        ax.text(",
      horizontal ? "            value + pad," : "            position,",
      horizontal ? "            position," : "            value + pad,",
      '            f"{value:.3g}",',
      horizontal ? '            ha="left",' : '            ha="center",',
      horizontal ? '            va="center",' : '            va="bottom",',
      "            fontsize=ANNOTATION_PT - 1,",
      "        )",
      "",
    );
  }

  if (spec.kind === "bar" && spec.significance) {
    emitSignificance(spec.significance, out);
  }

  if (spec.annotate?.length) emitAnnotations(spec, out);
  if (spec.legend.style === "direct" && spec.group) {
    out.push(
      "",
      "def label_series_directly(ax, frame):",
      "    # A name at the end of each line beats a legend box that covers data.",
      "    for index, name in enumerate(series_names(frame)):",
      "        block = frame[frame[GROUP] == name].sort_values(X_FIELD)",
      "        if block.empty:",
      "            continue",
      "        style = series_style(name, index, len(series_names(frame)))",
      "        ax.annotate(",
      "            str(name),",
      "            xy=(block[X_FIELD].iloc[-1], block[Y_FIELD].iloc[-1]),",
      "            xytext=(4, 0),",
      '            textcoords="offset points",',
      '            va="center",',
      '            ha="left",',
      "            fontsize=ANNOTATION_PT,",
      '            color=style["colour"],',
      "        )",
      "    ax.margins(x=0.16)",
      "",
    );
  }
  void preset;
}

function emitSignificance(significance: Significance, out: string[]): void {
  const method = significance.method;
  out.push(
    "",
    "def compare(left, right):",
    '    """Return a p value, or None when the test cannot run."""',
    "    left = np.asarray(left, dtype=float)",
    "    right = np.asarray(right, dtype=float)",
    "    left = left[np.isfinite(left)]",
    "    right = right[np.isfinite(right)]",
    "    if len(left) < 2 or len(right) < 2:",
    "        return None",
  );

  if (method === "bootstrap") {
    out.push(
      "    rng = np.random.default_rng(BOOTSTRAP_SEED)",
      "    observed = left.mean() - right.mean()",
      "    pooled = np.concatenate([left, right])",
      "    tolerance = abs(observed) * 100 * np.finfo(float).eps",
      "    partitions = math.comb(len(pooled), len(left))",
      "    extreme = 0",
      "    if partitions <= BOOTSTRAP_DRAWS:",
      "        # Enumerate small independent-sample problems exactly.",
      "        from itertools import combinations",
      "        for indices in combinations(range(len(pooled)), len(left)):",
      "            mask = np.ones(len(pooled), dtype=bool)",
      "            mask[list(indices)] = False",
      "            difference = pooled[list(indices)].mean() - pooled[mask].mean()",
      "            extreme += abs(difference) >= abs(observed) - tolerance",
      "        return float(extreme / partitions)",
      "    # Each draw needs a fresh permutation. Permuting a transposed tiled",
      "    # array once gave every draw the same assignment and p only 0 or 1.",
      "    for _ in range(BOOTSTRAP_DRAWS):",
      "        draw = rng.permutation(pooled)",
      "        difference = draw[:len(left)].mean() - draw[len(left):].mean()",
      "        extreme += abs(difference) >= abs(observed) - tolerance",
      "    # Include the observed assignment: Monte Carlo p must never be zero.",
      "    return float((extreme + 1) / (BOOTSTRAP_DRAWS + 1))",
    );
  } else {
    const call =
      method === "ttest"
        ? "stats.ttest_ind(left, right, equal_var=False).pvalue"
        : 'stats.mannwhitneyu(left, right, alternative="two-sided").pvalue';
    out.push(
      "    try:",
      "        from scipy import stats",
      "    except ImportError:",
      '        print("scipy is not installed, so significance markers were skipped")',
      "        return None",
      `    return float(${call})`,
    );
  }

  out.push(
    "",
    "",
    "def mark_significance(ax, df, categories, positions):",
    "    index_of = {name: position for name, position in zip(categories, positions)}",
    "    reach = df[Y_FIELD].max()",
    "    step = abs(reach) * 0.06 if np.isfinite(reach) and reach else 1.0",
    "    level = reach",
    "    for left_name, right_name in SIGNIFICANCE_PAIRS:",
    "        if left_name not in index_of or right_name not in index_of:",
    "            continue",
    "        p = compare(",
    "            df[df[X_FIELD] == left_name][Y_FIELD],",
    "            df[df[X_FIELD] == right_name][Y_FIELD],",
    "        )",
    "        if p is None:",
    "            continue",
    "        level = level + step",
    "        left_pos, right_pos = index_of[left_name], index_of[right_name]",
    "        ax.plot(",
    "            [left_pos, left_pos, right_pos, right_pos],",
    "            [level, level + step * 0.3, level + step * 0.3, level],",
    '            color="#404040",',
    "            linewidth=0.8,",
    "        )",
    '        mark = "n.s." if p > SIGNIFICANCE_ALPHA else ("***" if p < 0.001 else "**" if p < 0.01 else "*")',
    "        ax.text(",
    "            (left_pos + right_pos) / 2,",
    "            level + step * 0.35,",
    "            mark,",
    '            ha="center",',
    '            va="bottom",',
    "            fontsize=ANNOTATION_PT,",
    "        )",
    '        print(f"  {left_name} vs {right_name}: p = {p:.4g} ({mark})")',
    "",
  );
}

function emitAnnotations(spec: FigureSpec, out: string[]): void {
  out.push(
    "",
    "def as_coordinate(value):",
    '    """A float where matplotlib wants one, and the value itself for a date.',
    "",
    "    np.isreal answers a different question: a Timestamp is not complex, so it",
    '    passed a test meant to mean "is a plain number" and then failed float().',
    '    """',
    "    if isinstance(value, (int, float, np.integer, np.floating)):",
    "        return float(value)",
    "    return value",
    "",
    "",
    "def locate(frame, where, series):",
    '    """Turn a semantic position into a data point."""',
    "    block = frame if series is None else frame[frame[GROUP] == series]",
    "    block = block.dropna(subset=[X_FIELD, Y_FIELD]).sort_values(X_FIELD)",
    "    if block.empty:",
    "        return None",
    '    if where == "max":',
    "        row = block.loc[block[Y_FIELD].idxmax()]",
    '    elif where == "min":',
    "        row = block.loc[block[Y_FIELD].idxmin()]",
    '    elif where == "first":',
    "        row = block.iloc[0]",
    '    elif where == "last":',
    "        row = block.iloc[-1]",
    '    elif where == "crossover":',
    "        return crossover_point(frame, series)",
    "    else:",
    "        target = pd.to_datetime(where) if X_TEMPORAL else where",
    "        by_distance = X_TEMPORAL or isinstance(target, (int, float, np.integer, np.floating))",
    "        nearest = (block[X_FIELD] - target).abs().idxmin() if by_distance else None",
    "        if nearest is None:",
    "            match = block[block[X_FIELD] == target]",
    "            if match.empty:",
    "                return None",
    "            row = match.iloc[0]",
    "        else:",
    "            row = block.loc[nearest]",
    "    return as_coordinate(row[X_FIELD]), float(row[Y_FIELD])",
    "",
    "",
    "def crossover_point(frame, series):",
    '    """Where the named series first overtakes every other one."""',
    "    if GROUP is None or series is None:",
    "        return None",
    "    pivot = frame.pivot_table(index=X_FIELD, columns=GROUP, values=Y_FIELD, aggfunc=\"mean\")",
    "    if series not in pivot.columns or pivot.shape[1] < 2:",
    "        return None",
    "    others = pivot.drop(columns=[series]).max(axis=1)",
    "    ahead = pivot[series] > others",
    "    if not ahead.any():",
    "        return None",
    "    at = ahead.idxmax()",
    "    return as_coordinate(at), float(pivot[series].loc[at])",
    "",
    "",
    "def place_annotations(ax, frame):",
    "    # Offsets alternate so two notes near each other do not land on top.",
    "    offsets = [(8, 10), (8, -14), (-10, 12), (-10, -16)]",
    "    for index, note in enumerate(ANNOTATIONS):",
    '        found = locate(frame, note["at"], note.get("series"))',
    "        if found is None:",
    '            print(f"  annotation {note[\'text\']!r} had nowhere to attach")',
    "            continue",
    "        x, y = found",
    "        ax.annotate(",
    '            note["text"],',
    "            xy=(x, y),",
    "            xytext=offsets[index % len(offsets)],",
    '            textcoords="offset points",',
    "            fontsize=ANNOTATION_PT,",
    '            color="#202020",',
    "            arrowprops={",
    '                "arrowstyle": "-",',
    '                "linewidth": 0.7,',
    '                "color": "#767676",',
    "            },",
    "        )",
    "",
  );
}

export function emitDecoratePanel(spec: FigureSpec, out: string[]): void {
  out.push("", "def decorate_panel(ax, frame, panel_label, show_x=True, show_y=True):");

  for (const specAxis of ["x", "y"] as const) {
    const axis = spec[specAxis];
    const target = plotAxis(spec, specAxis);
    // A shared axis only needs its label on the outer panels.
    out.push(
      `    if show_${target}:`,
      `        ax.set_${target}label(${pyStr(
        spec.kind === "paired_difference" && specAxis === "y"
          ? differenceLabel(axis)
          : axisLabel(axis),
      )})`,
    );
    if (isCategorical(spec, specAxis) || spec.kind === "heatmap") continue;
    if (axis.scale !== "linear") out.push(`    ax.set_${target}scale(${pyStr(axis.scale)})`);
    if (axis.temporal) {
      out.push(
        `    _dates = mdates.AutoDateLocator()`,
        `    ax.${target}axis.set_major_locator(_dates)`,
        `    ax.${target}axis.set_major_formatter(mdates.ConciseDateFormatter(_dates))`,
      );
    }
    if (axis.percent) {
      out.push(
        `    ax.${target}axis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))`,
      );
    }
  }

  if (spec.kind === "bar" && spec.baseline_zero && spec.y.scale !== "log") {
    out.push(
      plotAxis(spec, "y") === "y" ? "    ax.set_ylim(bottom=0)" : "    ax.set_xlim(left=0)",
    );
  }

  for (const specAxis of ["x", "y"] as const) {
    const axis = spec[specAxis];
    if (!axis.limits || isCategorical(spec, specAxis)) continue;
    const target = plotAxis(spec, specAxis);
    out.push(`    ax.set_${target}lim(${axis.limits[0]}, ${axis.limits[1]})`);
  }

  for (const line of spec.reference_lines ?? []) {
    const style = REFERENCE_STYLES[line.meaning];
    const call = line.axis === "y" ? "axhline" : "axvline";
    out.push(
      `    ax.${call}(`,
      `        ${line.value},`,
      `        color=${style.colour},`,
      `        linestyle=${style.style},`,
      `        linewidth=${style.width},`,
      "        zorder=0,",
      // A labelled line carries its name inline, so it stays out of the legend.
      `        label=${line.label ? "None" : pyOptStr(line.label)},`,
      "    )",
    );
    if (line.label) {
      // A vertical line's label goes at the bottom. Putting it at the top of the
      // axes lands it on the title, which is where this used to collide.
      const vertical = line.axis === "x";
      // Horizontal line labels sit on the left. Data and its annotations pile up
      // at the right, where the last point is.
      const xy = vertical ? `(${line.value}, 0.02)` : `(0.01, ${line.value})`;
      out.push(
        "    ax.annotate(",
        `        ${pyStr(line.label)},`,
        `        xy=${xy},`,
        vertical
          ? "        xycoords=ax.get_xaxis_transform(),"
          : "        xycoords=ax.get_yaxis_transform(),",
        "        xytext=(3, 3),",
        '        textcoords="offset points",',
        '        ha="left",',
        '        va="bottom",',
        "        fontsize=ANNOTATION_PT - 1,",
        `        color=${style.colour},`,
        "    )",
      );
    }
  }

  if (spec.annotate?.length) out.push("    place_annotations(ax, frame)");

  out.push(spec.style.grid ? "    ax.grid(True, linewidth=0.4, alpha=0.5)" : "    ax.grid(False)");
  if (spec.style.despine && spec.kind !== "heatmap") {
    out.push('    for side in ("top", "right"):', "        ax.spines[side].set_visible(False)");
  }

  out.push(
    "    if panel_label is not None:",
    "        ax.set_title(str(panel_label), loc=\"left\", fontsize=PANEL_LETTER_PT)",
  );
  out.push("");
}

export function emitLegend(spec: FigureSpec, out: string[]): void {
  out.push("", "def add_legend(fig, ax, frame):");

  if (spec.kind === "heatmap" || !spec.group || !spec.legend.show) {
    out.push("    return", "");
    return;
  }

  if (spec.legend.style === "direct") {
    out.push("    label_series_directly(ax, frame)", "");
    return;
  }

  out.push(
    "    handles, labels = ax.get_legend_handles_labels()",
    "    if not handles:",
    "        return",
    "    ax.legend(",
    "        handles,",
    "        labels,",
    `        title=${pyOptStr(spec.legend.title)},`,
    "        frameon=False,",
    `        ${LEGEND_LOCATIONS[spec.legend.position]},`,
  );
  if (spec.legend.position === "outside_bottom") {
    out.push("        ncol=min(len(handles), 4),");
  }
  out.push("    )", "");
}
