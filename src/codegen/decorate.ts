import { plotAxis, sharedSeriesLegend } from "../capabilities.ts";
import { hasCategoricalX, type AxisSpec, type FigureSpec } from "../schema.ts";
import { pyOptStr, pyStr } from "./py.ts";
import { emitAnnotations } from "./annotations.ts";
import { emitSignificance } from "./significance.ts";
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
      '    low = block["_low"].to_numpy(dtype=float)',
      '    high = block["_high"].to_numpy(dtype=float)',
      "    known = np.isfinite(centre) & np.isfinite(low) & np.isfinite(high)",
      "    # Allow machine rounding only; a detached interval must never be reflected.",
      "    tolerance = 16 * np.finfo(float).eps",
      "    below = (centre < low) & ~np.isclose(centre, low, rtol=tolerance, atol=0)",
      "    above = (centre > high) & ~np.isclose(centre, high, rtol=tolerance, atol=0)",
      "    if np.any(known & (below | above)):",
      '        raise ValueError("Bar interval bounds exclude the estimate; use median with IQR, or a forest plot/table for detached bounds.")',
      "    return np.vstack([",
      "        np.maximum(centre - low, 0.0),",
      "        np.maximum(high - centre, 0.0),",
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
      horizontal ? "            value + (pad if value >= 0 else -pad)," : "            position,",
      horizontal ? "            position," : "            value + (pad if value >= 0 else -pad),",
      spec.y.percent ? '            f"{value * 100:.3g}%",' : '            f"{value:.3g}",',
      horizontal ? '            ha="left" if value >= 0 else "right",' : '            ha="center",',
      horizontal ? '            va="center",' : '            va="bottom" if value >= 0 else "top",',
      "            fontsize=ANNOTATION_PT - 1,",
      "        )",
      "",
    );
  }

  if (spec.kind === "bar" && spec.significance) {
    emitSignificance(out);
  }

  if (spec.annotate?.length) emitAnnotations(spec, out);
  if (spec.legend.style === "direct" && spec.group) {
    out.push(
      "",
      "def label_series_directly(ax, frame):",
      "    # A name at the end of each line beats a legend box that covers data.",
      "    for index, name in enumerate(series_names(frame)):",
      spec.kind === "qq" ? "        block = frame[frame[GROUP] == name]"
        : "        block = frame[frame[GROUP] == name].sort_values(X_FIELD)",
      "        if block.empty:",
      "            continue",
      ...(spec.kind === "calibration" ? ["        curve = calibration_estimate(block)"] : []),
      ...(spec.kind === "qq" ? ["        curve = qq_estimate(block)"] : []),
      ...(spec.kind === "scaling_fit" ? ["        curve = scaling_estimate(block)"] : []),
      "        style = series_style(name, index, len(series_names(frame)))",
      "        text = ax.annotate(",
      spec.kind === "calibration"
        ? `            f"{legend_alias(name)} (ECE {curve['ece']:.3g})",`
        : "            legend_alias(name),",
      spec.kind === "calibration"
        ? '            xy=(curve["probability"][-1], curve["frequency"][-1]),'
        : spec.kind === "qq" ? '            xy=(curve["theoretical"][-1], curve["observed"][-1]),'
          : spec.kind === "scaling_fit" ? '            xy=(curve["grid_x"][-1], curve["grid_y"][-1]),'
            : "            xy=(block[X_FIELD].iloc[-1], block[Y_FIELD].iloc[-1]),",
      "            xytext=(4, 0),",
      '            textcoords="offset points",',
      '            va="center",',
      '            ha="left",',
      "            fontsize=ANNOTATION_PT,",
      '            color=style["colour"],',
      "        )",
      '        edit_target(text, legend_alias_path(name), "legend_entry", str(name))',
      "    ax.margins(x=0.16)",
      "",
    );
  }
  void preset;
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
          : spec.kind === "qq" && specAxis === "y" && spec.transform?.kind === "normalize"
            ? `Normalized ${axis.label} (${axis.percent ? "% of observed range" : "0–1"})`
            : axisLabel(axis),
      )})`,
      `        edit_target(ax.${target}axis.label, [${pyStr(specAxis)}, "label"], "axis_label", ${pyStr(axis.field)})`,
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
    const target = plotAxis(spec, "y");
    out.push(
      `    _bar_low, _bar_high = sorted(ax.get_${target}lim())`,
      // Later panels must still extend shared automatic value limits.
      `    ax.set_${target}lim(min(_bar_low, 0), max(_bar_high, 0), auto=None)`,
    );
  }

  for (const specAxis of ["x", "y"] as const) {
    const axis = spec[specAxis];
    if (!axis.limits || isCategorical(spec, specAxis)) continue;
    const target = plotAxis(spec, specAxis);
    out.push(`    ax.set_${target}lim(${axis.limits[0]}, ${axis.limits[1]})`);
  }

  if (spec.kind === "scaling_fit") {
    for (const target of ["x", "y"] as const) {
      if (spec[target].scale !== "log" || spec[target].percent) continue;
      out.push(
        "    # Sub-decade log labels share one exponent on older and newer Matplotlib.",
        `    _low, _high = sorted(ax.get_${target}lim())`,
        "    if 0 < _low < _high and np.log10(_high) - np.log10(_low) < 1:",
        "        _power = int(np.floor(np.log10(_high)))",
        `        ax.${target}axis.set_major_locator(mticker.MaxNLocator(nbins=3, min_n_ticks=2))`,
        "        _formatter = mticker.ScalarFormatter(useOffset=False, useMathText=True)",
        "        _formatter.set_scientific(_power != 0)",
        "        if _power != 0:",
        "            _formatter.set_powerlimits((_power, _power))",
        `        ax.${target}axis.set_major_formatter(_formatter)`,
        `        ax.${target}axis.set_minor_formatter(mticker.NullFormatter())`,
      );
    }
  }

  for (const [index, line] of (spec.reference_lines ?? []).entries()) {
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
        "    reference_text = ax.annotate(",
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
        `    edit_target(reference_text, ["reference_lines", ${index}, "label"], "reference_label", {"axis": ${pyStr(line.axis)}, "value": ${line.value}})`,
      );
    }
  }

  if (spec.annotate?.length) out.push("    place_annotations(ax, frame)");

  out.push(spec.style.grid ? "    ax.grid(True, linewidth=0.4, alpha=0.5)" : "    ax.grid(False)");
  if (spec.kind === "sparkline_grid") {
    // Applying a log/temporal scale resets shared locators after the cells are drawn.
    out.push("    ax.set_xticks([])", "    ax.set_yticks([])");
  }
  if (spec.style.despine && spec.kind !== "heatmap") {
    out.push('    for side in ("top", "right"):', "        ax.spines[side].set_visible(False)");
  }

  out.push(
    "    if panel_label is not None:",
    "        mark_panel_text(ax.set_title(str(panel_label), loc=\"left\", fontsize=PANEL_LETTER_PT), CURRENT_PANEL)",
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
    ...(sharedSeriesLegend(spec) || spec.kind === "dumbbell" ? [
      "    by_label = {}",
      sharedSeriesLegend(spec) ? "    for panel in fig.axes:" : "    for panel in [ax]:",
      "        panel_handles, panel_labels = source_legend_handles(panel)",
      "        for handle, label in zip(panel_handles, panel_labels):",
      "            by_label.setdefault(legend_handle_key(handle, label), (handle, label))",
      '    desired = [("series", str(name)) for name in series_names(frame)]',
      "    keys = [key for key in desired if key in by_label]",
      "    keys += [key for key in by_label if key not in keys]",
      "    handles = [by_label[key][0] for key in keys]",
      "    labels = [by_label[key][1] for key in keys]",
    ] : ["    handles, labels = source_legend_handles(ax)"]),
    "    if not handles:",
    "        return",
    "    identities, displayed, label_targets = [], [], []",
    "    for handle, label in zip(handles, labels):",
    '        identity = getattr(handle, "_graphunslopify_legend_identity", None)',
    '        source = identity["series"] if identity is not None else None',
    '        suffix = identity.get("suffix", "") if identity is not None else ""',
    "        identities.append(source)",
    '        label_targets.append(getattr(handle, "_graphunslopify_legend_text_target", None))',
    "        displayed.append(label if source is None else legend_alias(source) + suffix)",
    '    if (RUN_REPORT["spec"]["legend"].get("labels") or any(label_targets)) and len({name.strip() for name in displayed}) != len(displayed):',
    '        raise ValueError("Legend display names collide with another visible legend entry")',
    "    legend = ax.legend(",
    "        handles,",
    '        [f"Series {index}" for index in range(len(handles))],',
    `        title=${pyOptStr(spec.legend.title)},`,
    "        frameon=False,",
    `        ${LEGEND_LOCATIONS[spec.legend.position]},`,
  );
  if (spec.legend.position === "outside_bottom") {
    out.push(spec.kind === "calibration" && spec.facet
      ? "        ncol=1,  # Per-panel errors need room without crossing into another legend."
      : "        ncol=min(len(handles), 4),");
  }
  out.push("    )",
    "    for text, source, original, shown, target in zip(legend.get_texts(), identities, labels, displayed, label_targets):",
    "        text.set_text(shown)",
    "        if source is None and target is not None:",
    '            edit_target(text, target["path"], target["role"], target["source"])',
    "        else:",
    '            edit_target(text, None if source is None else legend_alias_path(source), "legend_entry", original if source is None else source)',
    '    edit_target(legend.get_title(), ["legend", "title"], "legend_title")', "");
}

/** Keep complete category names and font sizes; rotate only when geometry needs it. */
export function emitCategoryLayout(spec: FigureSpec, out: string[]): void {
  out.push("", "def fit_category_labels(fig, axes):");
  if (!hasCategoricalX(spec) || plotAxis(spec, "x") !== "x") {
    out.push("    return", "");
    return;
  }
  out.push(
    "    for rotation in (45, 90):",
    "        fig.canvas.draw()",
    "        renderer = fig.canvas.get_renderer()",
    "        crowded = []",
    "        for ax in axes:",
    "            if not ax.get_visible():",
    "                continue",
    "            low, high = sorted(ax.get_xlim())",
    "            labels = [label for label in ax.get_xticklabels()",
    "                      if label.get_visible() and label.get_text().strip()",
    "                      and low <= label.get_position()[0] <= high]",
    "            boxes = sorted([label.get_window_extent(renderer) for label in labels], key=lambda box: box.x0)",
    "            if any(left.overlaps(right) for left, right in zip(boxes, boxes[1:])):",
    "                crowded.append(labels)",
    "        if not crowded:",
    "            return",
    "        for labels in crowded:",
    "            for label in labels:",
    "                label.set_rotation(rotation)",
    '                label.set_horizontalalignment("right" if rotation == 45 else "center")',
    '                label.set_verticalalignment("top")',
    '                label.set_rotation_mode("default")',
    "        fig.tight_layout()",
    "",
  );
}

/** Reduce native date tick density only after measuring a real label collision. */
export function emitDateLayout(spec: FigureSpec, out: string[]): void {
  if (!spec.x.temporal) return;
  out.push(
    "",
    "def fit_date_labels(fig, axes, tight=True):",
    "    for maximum in (7, 4):",
    "        fig.canvas.draw()",
    "        renderer = fig.canvas.get_renderer()",
    "        crowded = []",
    "        for ax in axes:",
    "            if not ax.get_visible():",
    "                continue",
    "            low, high = sorted(ax.get_xlim())",
    "            labels = [label for label in ax.get_xticklabels()",
    "                      if label.get_visible() and label.get_text().strip()",
    "                      and low <= label.get_position()[0] <= high]",
    "            boxes = sorted([label.get_window_extent(renderer) for label in labels], key=lambda box: box.x0)",
    "            if any(left.overlaps(right) for left, right in zip(boxes, boxes[1:])):",
    "                crowded.append(ax)",
    "        if not crowded:",
    "            break",
    "        for ax in crowded:",
    "            locator = mdates.AutoDateLocator(minticks=2, maxticks=maximum)",
    "            ax.xaxis.set_major_locator(locator)",
    "            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))",
    "    fig.canvas.draw()",
    "    renderer = fig.canvas.get_renderer()",
    "    moved = False",
    "    for ax in axes:",
    "        label, offset = ax.xaxis.label, ax.xaxis.get_offset_text()",
    "        if not ax.get_visible() or not label.get_visible() or not offset.get_visible():",
    "            continue",
    "        if label.get_text().strip() and offset.get_text().strip() and label.get_window_extent(renderer).overlaps(offset.get_window_extent(renderer)):",
    "            ax.xaxis.labelpad += (offset.get_window_extent(renderer).height + 2) * 72 / fig.dpi",
    "            moved = True",
    "    if moved and tight:",
    "        fig.tight_layout()",
    "",
  );
}
