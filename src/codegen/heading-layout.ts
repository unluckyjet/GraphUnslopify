import type {FigureSpec} from "../schema.ts";

/** Font-measured wrapping changes owned presentation, never canonical wording. */
export function emitHeadingLayout(spec: FigureSpec, out: string[]): void {
  // These paths own their layout separately; do not emit an unused fitter.
  if (spec.kind === "table" || (!spec.axis_break && spec.group && spec.legend.show &&
      spec.legend.style === "box" && ["outside_right", "outside_bottom"].includes(spec.legend.position))) return;
  out.push("", ...String.raw`
def wrap_heading(original, artist, renderer, width):
    from matplotlib.text import Text
    probe = Text(fontproperties=artist.get_fontproperties(),
                 usetex=artist.get_usetex(), parse_math=artist.get_parse_math())
    probe.set_figure(artist.get_figure())
    dollars = original.count("$") - original.count(r"\$")
    mathematical = (artist.get_parse_math() or artist.get_usetex()) and dollars > 0 and dollars % 2 == 0
    lines = []
    for paragraph in original.split("\n"):
        tokens, token = [], ""
        math_mode, depth, escaped, space = False, 0, False, False
        for char in paragraph:
            separable = char.isspace() and not math_mode and depth == 0 and not escaped
            if token and separable != space:
                tokens.append(token)
                token = ""
            token += char
            space = separable
            if not escaped:
                if char == "$" and mathematical:
                    math_mode = not math_mode
                elif char == "{" and (math_mode or artist.get_usetex()):
                    depth += 1
                elif char == "}" and depth:
                    depth -= 1
            escaped = char == "\\" and not escaped
        if token:
            tokens.append(token)
        line, separator = "", ""
        for token in tokens:
            if token.isspace():
                separator += token
                continue
            candidate = line + separator + token
            probe.set_text(candidate)
            if line and probe.get_window_extent(renderer).width > width:
                lines.append(line)
                line = token
            else:
                line = candidate
            separator = ""
        lines.append(line + separator)
    return "\n".join(lines)


def fit_headings(fig):
    minimum_heights = {ax: getattr(ax, "_graphunslopify_heading_height", ax.bbox.height)
                       for ax in fig.axes if ax.get_visible()}
    for attempt in range(8):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        candidates = [(text, fig.bbox.width * 0.94, False) for text in fig.texts
                      if getattr(text, "_graphunslopify_text_target", {}).get("role") == "title"]
        for ax in fig.axes:
            if not ax.get_visible():
                continue
            candidates.extend((text, ax.bbox.width * 0.98, False)
                              for text in (ax.title, ax._left_title, ax._right_title))
            if ax.axison:
                # Axis wording may use free margins beyond the data rectangle.
                available_height = max(ax.bbox.height, minimum_heights[ax])
                grid = ax.get_subplotspec()
                if grid is not None:
                    rows = grid.get_gridspec().nrows
                    bottom = fig.bbox.y0 + fig.bbox.height * (1 - grid.rowspan.stop / rows)
                    top = fig.bbox.y0 + fig.bbox.height * (1 - grid.rowspan.start / rows)
                    center = ax.yaxis.label.get_transform().transform(ax.yaxis.label.get_position())[1]
                    available_height = max(available_height, 2 * min(center - bottom, top - center))
                candidates.extend([(ax.xaxis.label, ax.bbox.width * 0.98, False),
                                   (ax.yaxis.label, available_height * 0.98, True)])
        changed = False
        for artist, width, vertical in candidates:
            target = getattr(artist, "_graphunslopify_text_target", {})
            if target.get("role") not in {"title", "panel_title", "axis_label", "metric_label"}:
                continue
            if not artist.get_visible() or not artist.get_text().strip() or width <= 0:
                continue
            box = artist.get_window_extent(renderer)
            if (box.height if vertical else box.width) <= width:
                continue
            original = getattr(artist, "_graphunslopify_heading_original", artist.get_text())
            wrapped = wrap_heading(original, artist, renderer, width)
            if wrapped != artist.get_text():
                artist._graphunslopify_heading_original = original
                artist.set_text(wrapped)
                changed = True
        if not changed:
            return
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        row_heights = {}
        for ax, minimum in minimum_heights.items():
            grid = ax.get_subplotspec()
            if grid is None:
                continue
            ax._graphunslopify_heading_height = minimum
            box = ax.get_tightbbox(renderer)
            if box is None:
                continue
            height = minimum + max(0, box.y1 - ax.bbox.y1) + max(0, ax.bbox.y0 - box.y0)
            rows = list(grid.rowspan)
            for row in rows:
                row_heights[row] = max(row_heights.get(row, 0), height / len(rows))
        title_height = max((text.get_window_extent(renderer).height for text in fig.texts
                            if text.get_visible() and getattr(text, "_graphunslopify_text_target", {}).get("role") == "title"), default=0)
        required_height = sum(row_heights.values()) + title_height + fig.dpi * 0.3
        if row_heights and required_height > fig.bbox.height + 1:
            fig.set_size_inches(fig.get_figwidth(), required_height / fig.dpi)
        fig.tight_layout()
`.trim().split("\n"), "");
}
