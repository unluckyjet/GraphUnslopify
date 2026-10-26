import { interactiveLimitations } from "../capabilities.ts";
import type { FigureSpec } from "../schema.ts";
import { encodingSentence } from "../alttext.ts";
import { pyOptStr, pyStr } from "./py.ts";

/**
 * Everything the script writes besides the figure itself.
 *
 * A figure alone is not a deliverable. A journal wants alt text, a reviewer
 * wants to know the data has not moved since the figure was made, and a paper
 * wants a LaTeX block that already has the right width in it.
 */

/** A hash of the data file, so a stale figure can say so. */
export function emitDataFingerprint(out: string[]): void {
  out.push(
    "",
    "def data_fingerprint():",
    "    # A figure built from a file that has since changed is worse than no",
    "    # figure, because it looks current.",
    "    try:",
    '        with open(DATA_PATH, "rb") as handle:',
    "            digest = hashlib.sha256()",
    '            for block in iter(lambda: handle.read(65536), b""):',
    "                digest.update(block)",
    "        return digest.hexdigest()[:16]",
    "    except OSError:",
    '        return "unreadable"',
    "", "", "def script_fingerprint():",
    "    try:",
    '        with open(__file__, "rb") as handle:',
    "            digest = hashlib.sha256()",
    '            for block in iter(lambda: handle.read(65536), b""):',
    "                digest.update(block)",
    "        return digest.hexdigest()",
    "    except (NameError, OSError):",
    "        return None",
    "",
  );
}

export function emitAltTextConstants(spec: FigureSpec, out: string[]): void {
  out.push(`ENCODING_SENTENCE = ${pyStr(encodingSentence(spec))}`);
  out.push(`AUTHOR_CONTEXT = ${pyOptStr(spec.alt_text)}`);
  out.push(`CAPTION = ${pyOptStr(spec.caption)}`);
  out.push(
    `X_LABEL_PLAIN = ${pyStr(spec.x.label.toLowerCase())}`,
  );
}

/** Escape literal author/data text once, without interpreting it as TeX source. */
export function emitLatexText(spec: FigureSpec, out: string[]): void {
  if (!spec.output.latex && spec.kind !== "table") return;
  const replacements = {
    "\\": String.raw`\textbackslash{}`,
    "{": String.raw`\{`, "}": String.raw`\}`,
    "$": String.raw`\$`, "&": String.raw`\&`,
    "#": String.raw`\#`, "%": String.raw`\%`, "_": String.raw`\_`,
    "^": String.raw`\textasciicircum{}`, "~": String.raw`\textasciitilde{}`,
    "\n": " ", "\r": " ", "\t": " ",
  };
  out.push("", "def latex_text(value):",
    '    """Literal text; inserted escape commands are never escaped a second time."""',
    `    replacements = json.loads(${pyStr(JSON.stringify(replacements))})`,
    '    return "".join(replacements.get(character, character) for character in str(value))', "");
}

export function emitLatex(spec: FigureSpec, out: string[]): void {
  if (!spec.output.latex) return;
  // Doubled here so the emitted Python f-string holds a single LaTeX backslash
  // rather than an invalid escape.
  const width = spec.output.size === "single_column" ? "\\\\columnwidth" : "\\\\textwidth";
  out.push(
    "",
    "def write_latex(description):",
    "    # Width is set from output.size, so the figure is not silently rescaled",
    "    # on the page into fonts the checker never measured.",
    "    body = (",
    '        "\\\\begin{figure}[t]\\n"',
    '        "  \\\\centering\\n"',
    `        f"  \\\\includegraphics[width=${width}]{{{STEM}}}\\n"`,
    '        f"  \\\\caption{{{latex_text(CAPTION or \'\')}}}\\n"',
    '        f"  \\\\Description{{{latex_text(description)}}}\\n"',
    '        f"  \\\\label{{fig:{STEM}}}\\n"',
    '        "\\\\end{figure}\\n"',
    "    )",
    '    path = f"{STEM}.tex"',
    '    with open(path, "w", encoding="utf8") as handle:',
    "        handle.write(body)",
    "    record_output(path)",
    '    print(f"wrote {path}")',
    "",
  );
}

/**
 * A second, interactive rendering through plotly.
 *
 * matplotlib is right for the paper and wrong for a project page, where a
 * reader wants to hover a point and read its value rather than estimate it off
 * an axis. This is the same spec through a different backend, not a second
 * figure that might disagree with the first.
 */
export function emitInteractive(spec: FigureSpec, out: string[]): void {
  if (!spec.output.interactive) return;
  const limitations = interactiveLimitations(spec);
  if (limitations.length) {
    out.push("", "def write_interactive(frame):", `    skip_output("html", ${pyStr(`unsupported interactive features: ${limitations.join(", ")}`)})`, "");
    return;
  }
  out.push("", "def write_interactive(frame):", "    try:", "        import plotly.graph_objects as go",
    "    except ImportError:", '        skip_output("html", "install graphunslopify[interactive] for Plotly")', "        return",
    "    figure = go.Figure()");
  if (spec.kind === "heatmap") {
    out.push(
      `    matrix = frame.pivot_table(index=Y_FIELD, columns=X_FIELD, values=VALUE_FIELD, aggfunc=${pyStr(spec.aggregation)}, sort=False)`,
      "    values = matrix.to_numpy(dtype=float)",
      `    colourmap = DIVERGING_MAP if ${spec.diverging ? "True" : "False"} else plt.get_cmap(SEQUENTIAL_MAP)`,
      '    options = {"colorscale": [[i / 255, mcolors.to_hex(colourmap(i / 255))] for i in range(256)]}',
      ...(spec.diverging ? ["    reach = (float(np.nanmax(np.abs(values))) or 1.0) if np.isfinite(values).any() else 1.0", '    options.update(zmin=-reach, zmax=reach)'] : []),
      ...(spec.annotate_cells ? ["    reach = float(np.nanmax(np.abs(values))) if np.isfinite(values).any() else 1.0", "    digits = 0 if reach >= 100 else 1 if reach >= 10 else 2 if reach >= 1 else 3",
        '    options["text"] = [[f"{value:.{digits}f}" if np.isfinite(value) else "" for value in row] for row in values]'] : []),
      '    figure.add_trace(go.Heatmap(z=values.tolist(), x=list(map(str,matrix.columns)), y=list(map(str,matrix.index)), colorbar={"title": VALUE_LABEL}, **options))',
      '    figure.update_xaxes(type="category")',
      '    figure.update_yaxes(type="category", autorange="reversed")',
      ...(spec.annotate_cells ? [
        '    from plotly.colors import sample_colorscale',
        '    low = options.get("zmin", float(np.nanmin(values)))',
        '    high = options.get("zmax", float(np.nanmax(values)))',
        '    for row in range(values.shape[0]):',
        '        for column in range(values.shape[1]):',
        '            value = values[row, column]',
        '            if not np.isfinite(value): continue',
        '            fraction = float((value - low) / (high - low)) if high > low else 0.5',
        '            rgb = sample_colorscale(options["colorscale"], [fraction], colortype="tuple")[0]',
        '            # Category serial positions avoid Plotly coercing names such as 01 and 1.',
        '            figure.add_annotation(x=column, y=row,',
        '                                  text=options["text"][row][column], showarrow=False,',
        '                                  font={"color": cell_colour_for_rgb(rgb), "size":13})',
      ] : []),
    );
  } else {
    out.push(spec.kind === "scatter" ? "    prepared = frame" : "    prepared = summarise(frame)",
      "    names = series_names(prepared) if GROUP is not None else [None]",
      "    for index, name in enumerate(names):",
      "        block = prepared if name is None else prepared[prepared[GROUP] == name]",
      ...(spec.kind === "line" && !spec.sort_x ? [] : ["        block = block.sort_values(X_FIELD)"]),
      ...(spec.kind === "bar" ? ["        categories = category_order(prepared)", "        block = block.set_index(X_FIELD).reindex(categories).reset_index()"] : []),
      "        if block.empty: continue",
      ...(spec.group ? ['        style = series_style(name, index, len(names))'] : ['        style = {"colour": PALETTE[0], "alpha": 1.0}']),
      '        options = {"name": str(name) if name is not None else Y_AXIS_LABEL, "marker_color": style["colour"], "opacity": style["alpha"]}',
    );
    const uncertainty = "uncertainty" in spec ? spec.uncertainty : undefined;
    if (uncertainty && spec.kind === "line" && uncertainty.display === "band") {
      out.push('        figure.add_trace(go.Scatter(x=block[X_FIELD].tolist(), y=block["_low"].tolist(), mode="lines", line={"width":0}, showlegend=False, hoverinfo="skip"))',
        '        rgba = mcolors.to_rgba(style["colour"], BAND_ALPHA)',
        '        fill = f"rgba({int(rgba[0]*255)},{int(rgba[1]*255)},{int(rgba[2]*255)},{rgba[3]})"',
        '        figure.add_trace(go.Scatter(x=block[X_FIELD].tolist(), y=block["_high"].tolist(), mode="lines", line={"width":0}, fill="tonexty", fillcolor=fill, showlegend=False, hoverinfo="skip"))');
    } else if (uncertainty) {
      const axis = spec.kind === "bar" && spec.orientation === "horizontal" ? "x" : "y";
      out.push(`        options["error_${axis}"] = {"type":"data", "symmetric":False, "array":np.abs(block["_high"]-block[Y_FIELD]).tolist(), "arrayminus":np.abs(block[Y_FIELD]-block["_low"]).tolist()}`);
    }
    if (spec.kind === "bar") {
      if (spec.group) out.push('        options["marker_pattern_shape"] = {"o":".", "*":"+"}.get(style["hatch"][:1], style["hatch"][:1])');
      const horizontal = spec.orientation === "horizontal";
      out.push(...(spec.value_labels ? ['        options.update(text=[f"{value:.3g}" if np.isfinite(value) else "" for value in block[Y_FIELD]], textposition="outside")'] : []),
        `        figure.add_trace(go.Bar(x=block[${horizontal ? "Y_FIELD" : "X_FIELD"}].tolist(), y=block[${horizontal ? "X_FIELD" : "Y_FIELD"}].tolist(), orientation=${pyStr(horizontal ? "h" : "v")}, **options))`,
        '    figure.update_layout(barmode="group")');
    } else {
      if (spec.kind === "scatter" && spec.group) out.push('        options["marker_symbol"] = {"o":"circle", "s":"square", "D":"diamond", "^":"triangle-up", "v":"triangle-down", "P":"cross", "X":"x", "*":"star"}.get(style["marker"], "circle")');
      out.push(spec.kind === "scatter" ? '        options["mode"] = "markers"' : `        options["mode"] = "lines+markers" if ${spec.kind === "line" && spec.marker ? "True" : "len(block) == 1"} else "lines"`,
        ...(spec.kind === "line" && spec.group ? ['        options["line"] = {"dash": {"-":"solid", "--":"dash", ":":"dot", "-.":"dashdot"}.get(style["linestyle"], "solid")}'] : []),
        '        figure.add_trace(go.Scatter(x=block[X_FIELD].tolist(), y=block[Y_FIELD].tolist(), **options))');
    }
  }
  const horizontal = spec.kind === "bar" && spec.orientation === "horizontal";
  if (spec.kind === "bar") out.push(`    figure.update_${horizontal ? "y" : "x"}axes(type="category", categoryorder="array", categoryarray=category_order(prepared))`);
  out.push('    figure.update_layout(template="simple_white", font={"size":13}, title=FIGURE_TITLE,',
    `        xaxis_title=${horizontal ? "Y_AXIS_LABEL" : "X_AXIS_LABEL"}, yaxis_title=${horizontal ? "X_AXIS_LABEL" : "Y_AXIS_LABEL"},`,
    `        showlegend=${spec.group && spec.legend.show ? "True" : "False"})`);
  for (const axis of ["x", "y"] as const) {
    const target = horizontal ? axis === "x" ? "y" : "x" : axis;
    const definition = spec[axis];
    if (spec.kind === "heatmap" || spec.kind === "bar" && axis === "x") continue;
    if (definition.scale === "log") out.push(`    figure.update_${target}axes(type="log")`);
    if (definition.percent) out.push(`    figure.update_${target}axes(tickformat=".0%")`);
    if (definition.limits) {
      const limits = definition.scale === "log" ? definition.limits.map(Math.log10) : definition.limits;
      out.push(`    figure.update_${target}axes(range=[${limits.join(", ")}])`);
    } else if (spec.kind === "bar" && axis === "y" && spec.baseline_zero && definition.scale !== "log") {
      out.push(`    figure.update_${target}axes(rangemode="tozero")`);
    }
  }
  out.push(
    '    path = f"{STEM}.html"',
    '    body = figure.to_html(include_plotlyjs=True, full_html=True, div_id=f"figure-{SPEC_HASH}")',
    '    evidence = json.dumps({"schema_version":1, "tool":TOOL, "script_sha256":script_fingerprint(), "spec":json.loads(SPEC_JSON), "spec_hash":SPEC_HASH, "data_sha256_prefix":DATA_HASH, "alt_text":ALT_TEXT}, ensure_ascii=False).replace("<", r"\\u003c")',
    `    description = f'<p id="figure-description">{escape(ALT_TEXT)}</p><script type="application/json" id="graphunslopify-provenance">{evidence}</script>'`,
    '    before, after = body.rsplit("</body>", 1)',
    '    Path(path).write_text(before + description + "</body>" + after, encoding="utf8")',
    '    record_output(path)', '    print(f"wrote {path}")', "",
  );
}
