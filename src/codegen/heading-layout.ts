import { RUNTIME_HELPERS } from "./runtime-source.ts";
import type {FigureSpec} from "../schema.ts";
import {hasOutsideLegendLayout} from "./legend-layout.ts";

/** Font-measured wrapping changes owned presentation, never canonical wording. */
export function emitHeadingLayout(spec: FigureSpec, out: string[]): void {
  // These paths own their layout separately; do not emit an unused fitter.
  if (spec.kind === "table" || (!spec.axis_break && spec.group && spec.legend.show &&
      spec.legend.style === "box" && ["outside_right", "outside_bottom"].includes(spec.legend.position) &&
      !hasOutsideLegendLayout(spec) && spec.kind !== "sparkline_grid")) return;
  emitTextWrapping(out);
  out.push("", ...String.raw`
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


/** Literal/math-aware wrapping is shared by owned titles, child plots and tables. */
export function emitTextWrapping(out: string[]): void {
  out.push("", ...String.raw`
${RUNTIME_HELPERS.heading_dollars}


${RUNTIME_HELPERS.literal_heading_lines}


${RUNTIME_HELPERS.wrap_heading}

`.trim().split("\n"), "");
}
