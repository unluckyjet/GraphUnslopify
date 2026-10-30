/** Table presentation accepts artists, never observations or estimators. */
export function emitTableLayout(out: string[]): void {
  out.push("", ...String.raw`
def fit_table_layout(fig, ax, drawn, context):
    from matplotlib.text import Text
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    budget = fig.bbox.width * 0.92
    if (drawn.get_window_extent(renderer).width <= budget and
            all(text.get_window_extent(renderer).width <= budget for text in context)):
        return
    cells = drawn.get_celld()
    rows = sorted({row for row, column in cells})
    columns = sorted({column for row, column in cells})
    original_heights = {row: max(cell.get_height() * ax.bbox.height / fig.dpi
                                for (r, column), cell in cells.items() if r == row) for row in rows}
    padding = {row: max(0, original_heights[row] - max(
                       cell.get_text().get_window_extent(renderer).height / fig.dpi
                       for (r, column), cell in cells.items() if r == row)) for row in rows}

    def word_width(artist):
        probe = Text(fontproperties=artist.get_fontproperties(), parse_math=False, usetex=False)
        probe.set_figure(fig)
        widths = []
        for word in artist.get_text().split():
            probe.set_text(word)
            widths.append(probe.get_window_extent(renderer).width)
        return max(widths, default=0)

    minimum, natural = {}, {}
    for column in columns:
        entries = [(row, cell) for (row, col), cell in cells.items() if col == column]
        natural[column] = max(cell.get_required_width(renderer) * ax.bbox.width
                              for row, cell in entries)
        minimum[column] = max((word_width(cell.get_text()) if row == 0 or column == -1
                               else cell.get_text().get_window_extent(renderer).width)
                              * (1 + 2 * cell.PAD) for row, cell in entries)
    remaining = max(0, budget - sum(minimum.values()))
    demand = sum(max(0, natural[column] - minimum[column]) for column in columns)
    widths = {column: minimum[column] + min(1, remaining / demand if demand else 0)
              * max(0, natural[column] - minimum[column]) for column in columns}
    for (row, column), cell in cells.items():
        if row == 0 or column == -1:
            text = cell.get_text()
            original = text.get_text()
            wrapped = wrap_heading(original, text, renderer, widths[column] / (1 + 2 * cell.PAD))
            if wrapped != original:
                text._graphunslopify_heading_original = original
                text.set_text(wrapped)
    for text in context:
        original = text.get_text()
        if text.get_window_extent(renderer).width > budget:
            text._graphunslopify_heading_original = original
            text.set_text(wrap_heading(original, text, renderer, budget))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    row_heights = {row: max(original_heights[row], padding[row] + max(
                          cell.get_text().get_window_extent(renderer).height / fig.dpi
                          for (r, column), cell in cells.items() if r == row)) for row in rows}
    column_widths = {column: max(cell.get_width() * ax.bbox.width / fig.dpi
                               for (row, col), cell in cells.items() if col == column)
                     for column in columns}
    context_heights = [text.get_window_extent(renderer).height / fig.dpi for text in context]
    header = 0.08 + sum(height + 0.04 for height in context_heights)
    body = max(ax.bbox.height / fig.dpi, sum(row_heights.values()) + 0.16)
    bottom = ax.get_position().y0 * fig.get_figheight()
    height = max(fig.get_figheight(), header + body + bottom)
    width = fig.get_figwidth()
    fig.set_size_inches(width, height)
    # Native centered tables center their numeric grid, excluding row names.
    # Use the measured numeric width as the hidden axes width so the complete
    # table is centered without an oversized invisible axes export boundary.
    numeric_width = max(0.05, sum(value for column, value in column_widths.items() if column >= 0))
    total_width = sum(column_widths.values())
    left = (width - total_width) / 2 + column_widths.get(-1, 0)
    ax.set_position([left / width, bottom / height, numeric_width / width, body / height])
    offset = 0.04
    for text, text_height in zip(context, context_heights):
        text.set_position((0.5, 1 - offset / height))
        offset += text_height + 0.04
    for (row, column), cell in cells.items():
        cell.set_height(row_heights[row] / body)
    fig.canvas.draw()
`.trim().split("\n"), "");
}
