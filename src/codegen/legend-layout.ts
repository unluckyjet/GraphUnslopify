import type {FigureSpec} from "../schema.ts";
import {unusedGrouping} from "../capabilities.ts";

/** Sparkline series headings have their own child-axes layout. */
export function hasOutsideLegendLayout(spec: FigureSpec): boolean {
  return !!spec.group && !unusedGrouping(spec) && !["table", "sparkline_grid"].includes(spec.kind) &&
    spec.legend.show && spec.legend.style === "box" &&
    ["outside_right", "outside_bottom"].includes(spec.legend.position);
}

export function emitLegendLayout(spec: FigureSpec, out: string[]): void {
  if (!hasOutsideLegendLayout(spec)) return;
  out.push("", ...String.raw`
def fit_outside_legends(fig, axes, frame, layout=None):
    axes = [ax for ax in axes if ax.get_visible()]
    legends = [ax.get_legend() for ax in axes if ax.get_legend() is not None]
    if not legends:
        if layout is not None:
            layout()
        return
    fig.canvas.draw()
    minimum = {ax: ax.bbox.height / fig.dpi for ax in axes}
    rows = max((ax.get_subplotspec().get_gridspec().nrows for ax in axes
                if ax.get_subplotspec() is not None), default=1)
    position = RUN_REPORT["spec"]["legend"]["position"]
    for attempt in range(4):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        changed = False
        for index, legend in enumerate(legends):
            local = legend._graphunslopify_panel_legend
            budget = (legend.axes.bbox.width * 0.94 if local else
                      fig.bbox.width * (0.38 if position == "outside_right" else 0.92))
            box = legend.get_window_extent(renderer)
            if position == "outside_bottom" and legend._ncols > 1 and box.width > budget:
                owner, source = legend.axes, legend._graphunslopify_legend_frame
                choices = []
                for columns in range(legend._ncols - 1, 0, -1):
                    legend.remove()
                    legend = add_legend(fig, owner, source, layout_columns=columns)
                    candidate = legend.get_window_extent(renderer)
                    if candidate.width <= budget:
                        choices.append((candidate.height, candidate.width, columns))
                selected = min(choices, default=(0, 0, 1))[2]
                if legend._ncols != selected:
                    legend.remove()
                    legend = add_legend(fig, owner, source, layout_columns=selected)
                legends[index] = legend
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                box = legend.get_window_extent(renderer)
                changed = True
            texts = legend.get_texts()
            font = renderer.points_to_pixels(texts[0].get_fontsize())
            overhead = (font * (2 * legend.borderpad + legend.handlelength + legend.handletextpad)
                        if legend._ncols == 1 else
                        max(0, box.width - max((text.get_window_extent(renderer).width
                                               for text in texts), default=0)))
            for text in [*texts, legend.get_title()]:
                width = max(1, budget - (2 * font * legend.borderpad
                                        if text is legend.get_title() else overhead))
                if not text.get_visible() or not text.get_text().strip():
                    continue
                if text.get_window_extent(renderer).width <= width:
                    continue
                original = getattr(text, "_graphunslopify_heading_original", text.get_text())
                wrapped = wrap_heading(original, text, renderer, width)
                if wrapped != text.get_text():
                    text._graphunslopify_heading_original = original
                    text.set_text(wrapped)
                    changed = True
            displayed = [text.get_text().strip() for text in texts]
            if len(set(displayed)) != len(displayed):
                raise ValueError("Legend wrapping makes visible source names ambiguous; review display names")
        shared = [legend for legend in legends if not legend._graphunslopify_panel_legend]
        states = [(legend, legend.get_in_layout()) for legend in shared]
        for legend, state in states:
            legend.set_in_layout(False)
        try:
            if layout is not None:
                layout()
                layout = None
            else:
                fit_headings(fig)
                fit_category_labels(fig, axes)
${spec.x.temporal ? "            fit_date_labels(fig, axes, tight=False)" : ""}
            fig.tight_layout()
            fig.canvas.draw()
            deficit = max((height - ax.bbox.height / fig.dpi
                           for ax, height in minimum.items()), default=0)
            if deficit > 1 / fig.dpi:
                # Text consumes fixed physical space, not a fraction of the
                # enlarged canvas. Dividing by the current usable fraction
                # compounds margins and unnecessarily enlarges the data area.
                fig.set_size_inches(fig.get_figwidth(), fig.get_figheight() + rows * deficit + 0.05)
                changed = True
        finally:
            for legend, state in states:
                legend.set_in_layout(state)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        visible = [ax for ax in fig.axes if ax.get_visible()]
        boxes = [ax.get_tightbbox(renderer, bbox_extra_artists=[]) for ax in visible]
        boxes = [box for box in boxes if box is not None]
        if boxes:
            left = min(box.x0 for box in boxes)
            right = max(box.x1 for box in boxes)
            bottom = min(box.y0 for box in boxes)
            center = (min(ax.bbox.y0 for ax in visible) + max(ax.bbox.y1 for ax in visible)) / 2
            for legend in shared:
                point = ((right + fig.dpi * 0.08, center) if position == "outside_right" else
                         ((left + right) / 2, bottom - fig.dpi * 0.08))
                anchor = fig.transFigure.inverted().transform(point)
                legend.set_bbox_to_anchor(tuple(anchor), transform=fig.transFigure)
        if not changed:
            return
`.trim().split("\n"), "");
}
