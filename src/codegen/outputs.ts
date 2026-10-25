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
    '        f"  \\\\caption{{{CAPTION or \'\'}}}\\n"',
    '        f"  \\\\Description{{{description}}}\\n"',
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
  if (spec.kind === "violin" || spec.kind === "box") {
    out.push(
      "",
      "def write_interactive(frame):",
      '    print("interactive output is not implemented for this kind yet")',
      '    skip_output("html", "interactive output is not implemented for this kind")',
      "",
    );
    return;
  }

  const trace =
    spec.kind === "bar"
      ? "go.Bar"
      : spec.kind === "scatter"
        ? "go.Scatter"
        : spec.kind === "heatmap"
          ? "go.Heatmap"
          : "go.Scatter";

  out.push(
    "",
    "def write_interactive(frame):",
    "    try:",
    "        import plotly.graph_objects as go",
    "    except ImportError:",
    '        print("plotly is not installed, so the interactive figure was skipped")',
    '        skip_output("html", "plotly is not installed")',
    "        return",
    "",
    "    figure = go.Figure()",
  );

  if (spec.kind === "heatmap") {
    out.push(
      "    matrix = frame.pivot_table(",
      "        index=Y_FIELD, columns=X_FIELD, values=VALUE_FIELD, aggfunc=\"mean\", sort=False",
      "    )",
      "    figure.add_trace(",
      "        go.Heatmap(",
      "            z=matrix.to_numpy(),",
      "            x=[str(c) for c in matrix.columns],",
      "            y=[str(i) for i in matrix.index],",
      "            colorbar={\"title\": VALUE_LABEL},",
      "        )",
      "    )",
    );
  } else if (spec.group) {
    out.push(
      "    for index, name in enumerate(series_names(frame)):",
      "        block = frame[frame[GROUP] == name].sort_values(X_FIELD)",
      "        figure.add_trace(",
      `            ${trace}(`,
      "                x=block[X_FIELD],",
      "                y=block[Y_FIELD],",
      "                name=str(name),",
      "                marker_color=PALETTE[index % len(PALETTE)],",
      spec.kind === "scatter" ? '                mode="markers",' : '                mode="lines",',
      "            )",
      "        )",
    );
  } else {
    out.push(
      "    ordered = frame.sort_values(X_FIELD)",
      `    figure.add_trace(${trace}(x=ordered[X_FIELD], y=ordered[Y_FIELD], marker_color=PALETTE[0]))`,
    );
  }

  out.push(
    "",
    "    figure.update_layout(",
    "        template=\"simple_white\",",
    "        xaxis_title=X_AXIS_LABEL,",
    "        yaxis_title=Y_AXIS_LABEL,",
    "        title=FIGURE_TITLE,",
    "        font={\"size\": 13},",
    "        margin={\"l\": 60, \"r\": 30, \"t\": 50, \"b\": 55},",
    "    )",
  );
  if (spec.x.scale !== "linear") out.push(`    figure.update_xaxes(type=${pyStr(spec.x.scale === "log" ? "log" : "linear")})`);
  if (spec.y.scale !== "linear") out.push(`    figure.update_yaxes(type=${pyStr(spec.y.scale === "log" ? "log" : "linear")})`);

  out.push(
    '    path = f"{STEM}.html"',
    '    figure.write_html(path, include_plotlyjs="cdn", full_html=True)',
    "    record_output(path)",
    '    print(f"wrote {path}")',
    "",
  );
}
