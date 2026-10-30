import type {FigureSpec} from "../schema.ts";

/** Child titles need measured rows while native shared data scales stay intact. */
export function emitSparklineLayout(spec: FigureSpec, out: string[]): void {
  if (spec.kind !== "sparkline_grid") return;
  out.push("", ...String.raw`
def fit_sparkline_layout(fig, axes):
    from matplotlib.transforms import Bbox
    def owned(ax):
        return [child for child in ax.child_axes if hasattr(child, "_graphunslopify_sparkline_cell")]
    axes = [ax for ax in axes if ax.get_visible() and owned(ax)]
    fig.canvas.draw()
    for ax in axes:
        for child in owned(ax):
            if not hasattr(child, "_graphunslopify_sparkline_height"):
                child._graphunslopify_sparkline_height = child.bbox.height / fig.dpi
    active = any(hasattr(ax, "_graphunslopify_sparkline_layout") for ax in axes)
    grid_rows = max((ax.get_subplotspec().get_gridspec().nrows for ax in axes), default=1)
    for attempt in range(8):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        changed = False
        for ax in axes:
            for child in owned(ax):
                text = child.title
                if not text.get_visible() or not text.get_text():
                    continue
                width = child.bbox.width * 0.98
                if text.get_window_extent(renderer).width <= width:
                    continue
                original = getattr(text, "_graphunslopify_heading_original", text.get_text())
                wrapped = wrap_heading(original, text, renderer, width)
                if wrapped != text.get_text():
                    text._graphunslopify_heading_original = original
                    text.set_text(wrapped)
                    changed = active = True
        if not active:
            fit_headings(fig)
            fig.canvas.draw()
            if all(child.bbox.height / fig.dpi >= child._graphunslopify_sparkline_height - 1 / fig.dpi
                   for ax in axes for child in owned(ax)):
                return
            active = True
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        groups = {}
        for ax in axes:
            children = owned(ax)
            rows = children[0]._graphunslopify_sparkline_cell[2]
            key = (ax.get_subplotspec().rowspan.start, rows)
            plan = groups.setdefault(key, [[0, 0] for row in range(rows)])
            for child in children:
                row = child._graphunslopify_sparkline_cell[0]
                plan[row][0] = max(plan[row][0], child._graphunslopify_sparkline_height)
                title_height = child.title.get_window_extent(renderer).height / fig.dpi
                plan[row][1] = max(plan[row][1], title_height + 2 / 72 + 0.04)
            ax._graphunslopify_sparkline_layout = plan
        deficit = 0
        for ax in axes:
            plan = ax._graphunslopify_sparkline_layout
            required = sum(body + heading + 0.04 for body, heading in plan) + 0.04
            deficit = max(deficit, required - ax.bbox.height / fig.dpi)
            for child in owned(ax):
                row, column, rows, columns = child._graphunslopify_sparkline_cell

                def locate(cell, renderer, owner=ax, layout=plan, row=row, column=column, columns=columns):
                    box = owner.get_window_extent(renderer)
                    dpi = cell.figure.dpi
                    top = box.y1 - (sum(body + heading + 0.04 for body, heading in layout[:row])
                                    + layout[row][1]) * dpi
                    rectangle = Bbox.from_bounds(
                        box.x0 + (column / columns + 0.012) * box.width,
                        top - layout[row][0] * dpi,
                        (1 / columns - 0.024) * box.width,
                        layout[row][0] * dpi)
                    # Delay the inverse until draw, after figure/crop resizing.
                    return rectangle.transformed(cell.figure.transSubfigure.inverted())

                child.set_axes_locator(locate)
        if deficit > 1 / fig.dpi:
            fig.set_size_inches(fig.get_figwidth(), fig.get_figheight() + grid_rows * deficit + 0.04)
            continue
        fit_headings(fig)
        fig.canvas.draw()
        if not changed and all(
                ax.bbox.height / fig.dpi >= sum(body + heading + 0.04
                for body, heading in ax._graphunslopify_sparkline_layout) + 0.04 - 1 / fig.dpi
                for ax in axes):
            return
`.trim().split("\n"), "");
}
