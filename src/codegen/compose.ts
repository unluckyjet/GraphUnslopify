import type { FigureSpec } from "../schema.ts";
import { pyList, pyOptStr, pyStr, pyValue } from "./py.ts";
import { PRESETS } from "./theme.ts";

/**
 * Composition: extra marks, repeated panels, a cut axis, and a zoomed inset.
 *
 * Vega-Lite's operators compose recursively, which is more than this needs.
 * What recurs in a paper is a short list: points over a fitted line, one panel
 * per metric, a gap in an axis whose data is bimodal, and a magnified corner.
 * Each is here as a flat option rather than a nestable algebra, which keeps the
 * spec something an agent can fill in without building a tree.
 */

const OPERATORS: Record<string, (field: string, value: string) => string> = {
  eq: (f, v) => `frame[${f}] == ${v}`,
  ne: (f, v) => `frame[${f}] != ${v}`,
  lt: (f, v) => `frame[${f}] < ${v}`,
  lte: (f, v) => `frame[${f}] <= ${v}`,
  gt: (f, v) => `frame[${f}] > ${v}`,
  gte: (f, v) => `frame[${f}] >= ${v}`,
  in: (f, v) => `frame[${f}].isin(${v})`,
  not_in: (f, v) => `~frame[${f}].isin(${v})`,
};

export function emitLayers(spec: FigureSpec, out: string[]): void {
  if (!spec.layers?.length) return;
  const preset = PRESETS[spec.style.preset];

  out.push("", "def draw_layers(ax, frame):");
  for (const [index, layer] of spec.layers.entries()) {
    const zorder = layer.recede ? 0 : 5;
    out.push(`    # layer ${index + 1}: ${layer.mark}`);
    out.push("    block = frame");
    for (const clause of layer.filter ?? []) {
      out.push(`    block = block[${OPERATORS[clause.op]!(pyStr(clause.field), pyValue(clause.value))}]`);
    }
    out.push("    block = block.sort_values(X_FIELD)");
    const field = layer.y ? pyStr(layer.y) : "Y_FIELD";
    const colour = `LAYER_COLOURS[${index} % len(LAYER_COLOURS)]`;
    const label = pyOptStr(layer.label);

    switch (layer.mark) {
      case "line":
        out.push(
          "    ax.plot(",
          "        block[X_FIELD],",
          `        block[${field}],`,
          `        color=${colour},`,
          `        linewidth=${preset.line.muted},`,
          '        linestyle="--",',
          `        zorder=${zorder},`,
          `        label=${label},`,
          "    )",
        );
        break;
      case "scatter":
        out.push(
          "    ax.scatter(",
          "        block[X_FIELD],",
          `        block[${field}],`,
          `        color=${colour},`,
          `        s=${preset.marker.muted},`,
          "        alpha=0.6,",
          "        linewidths=0,",
          `        zorder=${zorder},`,
          `        label=${label},`,
          "    )",
        );
        break;
      case "rug":
        out.push(
          "    # Ticks along the bottom, showing where the observations actually are.",
          "    ax.plot(",
          "        block[X_FIELD],",
          "        np.full(len(block), 0.01),",
          "        transform=ax.get_xaxis_transform(),",
          '        linestyle="none",',
          '        marker="|",',
          "        markersize=5,",
          `        color=${colour},`,
          "        alpha=0.6,",
          `        zorder=${zorder},`,
          `        label=${label},`,
          "    )",
        );
        break;
      case "band":
        out.push(
          "    ax.fill_between(",
          "        block[X_FIELD],",
          `        block[${field}],`,
          `        block[${layer.y2 ? pyStr(layer.y2) : field}],`,
          `        color=${colour},`,
          "        alpha=BAND_ALPHA,",
          "        linewidth=0,",
          `        zorder=${zorder},`,
          `        label=${label},`,
          "    )",
        );
        break;
      case "rule":
        out.push(
          `    ax.axhline(${layer.value ?? 0}, color=${colour}, linewidth=1.0, linestyle=":", zorder=${zorder}, label=${label})`,
        );
        break;
      default: {
        const unhandled: never = layer.mark;
        throw new Error(`no emitter for layer mark ${String(unhandled)}`);
      }
    }
  }
  out.push("");
}

export function emitInset(spec: FigureSpec, out: string[]): void {
  if (!spec.inset) return;
  const { corner, size } = spec.inset;

  // The inset carries its own tick labels, so a bottom corner needs clearance
  // above the parent's x axis or the two rows of numbers run together.
  const bottom = 0.16;
  const top = Number((1 - size - 0.04).toFixed(3));
  const left = 0.1;
  const right = Number((1 - size - 0.04).toFixed(3));

  const placement: Record<string, string> = {
    upper_left: `[${left}, ${top}, ${size}, ${size}]`,
    upper_right: `[${right}, ${top}, ${size}, ${size}]`,
    lower_left: `[${left}, ${bottom}, ${size}, ${size}]`,
    lower_right: `[${right}, ${bottom}, ${size}, ${size}]`,
  };

  out.push(
    "",
    "def add_inset(ax, frame):",
    "    # A magnified copy of one region, with that region outlined on the main",
    "    # axes. The outline and the inset border share a colour, which is what",
    "    # ties them together. Connector lines would do the same job but they read",
    "    # as a perspective box, and this is a flat figure.",
    `    zoom = ax.inset_axes(${placement[corner]})`,
    "    draw_panel(zoom, frame)",
    `    zoom.set_xlim(${spec.inset.x[0]}, ${spec.inset.x[1]})`,
    `    zoom.set_ylim(${spec.inset.y[0]}, ${spec.inset.y[1]})`,
    "    zoom.set_xlabel(None)",
    "    zoom.set_ylabel(None)",
    "    zoom.set_title(None)",
    "    legend = zoom.get_legend()",
    "    if legend is not None:",
    "        legend.remove()",
    "    zoom.tick_params(labelsize=ANNOTATION_PT - 2, length=2, pad=1.5)",
    "    zoom.set_facecolor(\"white\")",
    "    zoom.patch.set_alpha(0.96)",
    "    for side, spine in zoom.spines.items():",
    "        spine.set_visible(True)",
    "        spine.set_color(INSET_EDGE)",
    "        spine.set_linewidth(0.9)",
    "",
    "    outline, connectors = ax.indicate_inset_zoom(",
    "        zoom, edgecolor=INSET_EDGE, alpha=1.0, linewidth=0.9",
    "    )",
    "    outline.set_facecolor(\"none\")",
    "    for line in connectors or ():",
    "        line.set_visible(False)",
    "",
  );
}

/**
 * A cut axis, drawn as two stacked axes with slanted marks at the join.
 *
 * matplotlib has no broken axis, so this builds one. The marks matter: without
 * them a reader takes the axis for continuous and misreads every distance
 * across the gap, which is the failure the whole truncation literature is about.
 */
export function emitAxisBreak(spec: FigureSpec, out: string[]): void {
  if (!spec.axis_break) return;
  const { from, to } = spec.axis_break;

  out.push(
    "",
    "def draw_with_break(fig, df):",
    "    upper, lower = fig.subplots(",
    "        2,",
    "        1,",
    "        sharex=True,",
    '        gridspec_kw={"height_ratios": [1, 1], "hspace": 0.06},',
    "    )",
    '    upper.set_label("<axis-break>")',
    '    lower.set_label("<axis-break>")',
    "    for ax in (upper, lower):",
    "        draw_panel(ax, df)",
    `    lower.set_ylim(top=${from})`,
    `    upper.set_ylim(bottom=${to})`,
    "",
    '    upper.spines["bottom"].set_visible(False)',
    '    lower.spines["top"].set_visible(False)',
    "    upper.tick_params(bottom=False, labelbottom=False)",
    "",
    "    # Slanted marks at the join, so the gap cannot be read as continuous.",
    "    marks = {",
    '        "marker": [(-1, -0.6), (1, 0.6)],',
    '        "markersize": 7,',
    '        "linestyle": "none",',
    '        "color": "#404040",',
    '        "mec": "#404040",',
    '        "mew": 1,',
    '        "clip_on": False,',
    "    }",
    "    upper.plot([0, 1], [0, 0], transform=upper.transAxes, **marks)",
    "    lower.plot([0, 1], [1, 1], transform=lower.transAxes, **marks)",
    "    return upper, lower",
    "",
  );
}

/** One panel per named column, which is small multiples over metrics. */
export function emitRepeat(spec: FigureSpec, out: string[]): void {
  if (!spec.repeat) return;
  out.push(
    "",
    "def pretty(field):",
    '    """A column name as a label. latency_ms becomes Latency ms."""',
    '    words = str(field).replace("_", " ").replace("-", " ").strip()',
    "    return words[:1].upper() + words[1:] if words else str(field)",
    "",
  );
  out.push(
    "",
    "def repeated_panels(df):",
    "    # One panel per metric. The y field is swapped per panel, which is the",
    "    # difference between repeat and facet: facet splits rows, this splits",
    "    # columns.",
    "    return [(field, df) for field in REPEAT_FIELDS]",
    "",
  );
}

/**
 * A table, rendered three ways from one spec.
 *
 * A results table in a paper is markdown in the readme, LaTeX in the
 * manuscript, and an image in the slides. Generating all three from the same
 * numbers means they cannot drift apart.
 */
export function emitTable(spec: FigureSpec & { kind: "table" }, out: string[]): void {
  const digits = spec.precision;
  out.push(
    "",
    "def build_table(df):",
    "    summary = summarise(df)",
    "",
    "    def pivot(field):",
    "        if GROUP is None:",
    "            return summary.set_index(X_FIELD)[[field]].rename(columns={field: Y_FIELD})",
    "        return summary.pivot_table(",
    "            index=X_FIELD, columns=GROUP, values=field, aggfunc=\"mean\", sort=False",
    "        )",
    "",
    "    table = pivot(Y_FIELD)",
    "    low = pivot(\"_low\").reindex_like(table) if \"_low\" in summary else None",
    "    high = pivot(\"_high\").reindex_like(table) if \"_high\" in summary else None",
    "    return table, low, high",
    "",
    "",
    "def mark_winners(table, low=None, high=None):",
    "    \"\"\"Highlight measured leaders without treating interval overlap as equivalence.\"\"\"",
    "    if HIGHLIGHT == \"none\":",
    "        return set()",
    "    winners = set()",
    "    along_rows = HIGHLIGHT == \"best_per_row\"",
    "    for key in table.index if along_rows else table.columns:",
    "        values = (table.loc[key] if along_rows else table[key]).dropna()",
    "        if values.empty:",
    "            continue",
    "        best = values.idxmax() if HIGHER_IS_BETTER else values.idxmin()",
    "        selected = [best]",
    "        if low is not None and high is not None:",
    "            lows = (low.loc[key] if along_rows else low[key]).reindex(values.index)",
    "            highs = (high.loc[key] if along_rows else high[key]).reindex(values.index)",
    "            if not np.isfinite(lows.to_numpy(dtype=float)).all() or not np.isfinite(highs.to_numpy(dtype=float)).all():",
    "                print(f\"table: {key}: insufficient observations to assess interval separation\")",
    "                continue",
    "            possible = highs >= lows[best] if HIGHER_IS_BETTER else lows <= highs[best]",
    "            selected = list(values.index[possible])",
    "            if len(selected) == 1:",
    "                print(f\"table: {key}: {best} has an interval separated from the other cells\")",
    "            else:",
    "                print(f\"table: {key}: intervals overlap; no uniquely separated leader ({', '.join(map(str, selected))}). Overlap does not establish equivalence.\")",
    "        for name in selected:",
    "            winners.add((key, name) if along_rows else (name, key))",
    "    return winners",
    "",
    "",
    "def table_cell(table, low, high, row, column):",
    "    value = table.loc[row, column]",
    "    if pd.isna(value):",
    "        return \"-\"",
    `    text = f"{value:.${digits}f}"`,
    "    if low is not None and high is not None:",
    "        lo, hi = low.loc[row, column], high.loc[row, column]",
    `        text += f" [{lo:.${digits}f}, {hi:.${digits}f}]" if np.isfinite(lo) and np.isfinite(hi) else " [unavailable]"`,
    "    return text",
    "",
    "",
    "def write_table(table, low=None, high=None):",
    "    winners = mark_winners(table, low, high)",
    "    columns = [str(c) for c in table.columns]",
    "    markdown = [",
    "        \"| \" + \" | \".join([X_AXIS_LABEL] + columns) + \" |\",",
    "        \"| \" + \" | \".join([\"---\"] * (len(columns) + 1)) + \" |\",",
    "    ]",
    "    for row in table.index:",
    "        cells = []",
    "        for column in table.columns:",
    "            text = table_cell(table, low, high, row, column)",
    "            cells.append(f\"**{text}**\" if (row, column) in winners else text)",
    "        markdown.append(\"| \" + \" | \".join([str(row)] + cells) + \" |\")",
    "",
    "    latex = [",
    "        \"\\\\begin{tabular}{l\" + \"r\" * len(columns) + \"}\",",
    "        \"\\\\toprule\",",
    "        \" & \".join([X_AXIS_LABEL] + columns) + \" \\\\\\\\\",",
    "        \"\\\\midrule\",",
    "    ]",
    "    for row in table.index:",
    "        cells = []",
    "        for column in table.columns:",
    "            text = table_cell(table, low, high, row, column)",
    "            cells.append(f\"\\\\textbf{{{text}}}\" if (row, column) in winners else text)",
    "        latex.append(\" & \".join([str(row)] + cells) + \" \\\\\\\\\")",
    "    latex += [\"\\\\bottomrule\", \"\\\\end{tabular}\"]",
    "",
    "    with open(f\"{STEM}.md\", \"w\", encoding=\"utf8\") as handle:",
    "        handle.write(\"\\n\".join(markdown) + \"\\n\")",
    '    record_output(f"{STEM}.md")',
    "    print(f\"wrote {STEM}.md\")",
    "    with open(f\"{STEM}.tex\", \"w\", encoding=\"utf8\") as handle:",
    "        handle.write(\"\\n\".join(latex) + \"\\n\")",
    '    record_output(f"{STEM}.tex")',
    "    print(f\"wrote {STEM}.tex\")",
    "    print(\"\\n\".join(markdown))",
    "    return markdown, winners",
    "",
    "",
    "def render_table_image(table, winners, low=None, high=None):",
    "    with plt.rc_context(RC_PARAMS):",
    "        height = 0.32 * (len(table.index) + 2)",
    "        fig, ax = plt.subplots(figsize=(FIGSIZE[0], height))",
    "        ax.axis(\"off\")",
    "        body = [",
    "            [table_cell(table, low, high, r, c) for c in table.columns]",
    "            for r in table.index",
    "        ]",
    "        drawn = ax.table(",
    "            cellText=body,",
    "            rowLabels=[str(r) for r in table.index],",
    "            colLabels=[str(c) for c in table.columns],",
    "            loc=\"center\",",
    "            cellLoc=\"right\",",
    "        )",
    "        drawn.auto_set_font_size(False)",
    "        drawn.set_fontsize(RC_PARAMS[\"font.size\"])",
    "        drawn.scale(1, 1.35)",
    "        # Intervals need more room than scalar cells; include row labels.",
    "        drawn.auto_set_column_width(col=list(range(-1, len(table.columns))))",
    "        for (row, column), cellobj in drawn.get_celld().items():",
    "            cellobj.set_linewidth(0.4)",
    "            cellobj.set_edgecolor(\"#cccccc\")",
    "            if row == 0:",
    "                cellobj.set_text_props(weight=\"bold\")",
    "        for index, row in enumerate(table.index):",
    "            for position, column in enumerate(table.columns):",
    "                if (row, column) in winners:",
    "                    drawn[index + 1, position].set_text_props(weight=\"bold\")",
    "        check(fig)",
    "        for fmt in FORMATS:",
    "            path = f\"{STEM}.{fmt}\"",
    "            fig.savefig(path, bbox_inches=\"tight\", metadata=metadata_for(fmt),",
    "                        **({\"dpi\": DPI} if fmt == \"png\" else {}))",
    "            record_output(path)",
    "            print(f\"wrote {path}\")",
    "        plt.close(fig)",
    "        return fig",
  );
}
