"""Checks that need pixels.

The MCP server checks the spec. It cannot know that a tick label collides with
its neighbour, that the legend sits on top of a data point, or that two series
become the same colour to a reader with deuteranopia. Those need a rendered
figure, so they run here, on the machine that has the data.

Every check is geometric or colorimetric. None of them asks a model for an
opinion, so the same figure always produces the same findings.
"""

from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pypdf.errors import PyPdfError

from .cell_colour import cell_text_contrast
from .colour import composite_over_white, relative_luminance, worst_case_distance
from .data_view import inspect_data_view
from .export_size import export_width_in

Severity = Literal["error", "warning"]
SourceLocator = tuple[str, int, int | None]


def _source(artist: Any, kind: str = "text", part: int | None = None) -> SourceLocator:
    return kind, id(artist), part


#: Below this, a reader with normal vision cannot separate two series.
MIN_COLOUR_DISTANCE = 11.0
#: Journals routinely reject anything under this once the figure is scaled.
MIN_TEXT_POINTS = 5.0
ADVISORY_TEXT_POINTS = 6.0
#: Two greys this close merge in a black and white print.
MIN_GREYSCALE_SEPARATION = 0.10
#: Above this share of the axes covered in marker ink, points hide each other.
MAX_INK_FRACTION = 0.45
#: A visible range this small next to the data's magnitude magnifies noise.
MIN_RANGE_TO_MAGNITUDE = 0.10


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str

    @property
    def consequence(self) -> str:
        from .diagnostics import advice

        return advice(self.code)["consequence"]

    @property
    def correction(self) -> str:
        from .diagnostics import advice

        return advice(self.code)["correction"]

    def __str__(self) -> str:
        from .diagnostics import format_finding

        return format_finding(
            {"severity": self.severity, "code": self.code, "message": self.message}
        )


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def add(
        self, severity: Severity, code: str, message: str, *, sources: Iterable[SourceLocator] = ()
    ) -> None:
        item = Finding(severity, code, message)
        # Non-owning, process-local locators. These are deliberately not public
        # dataclass fields: ordinary reports must not serialize IDs or retain figures.
        item._spatial_sources = tuple(sources)
        self.findings.append(item)

    def __bool__(self) -> bool:
        return bool(self.findings)

    def __str__(self) -> str:
        if not self.findings:
            return "figure checks: no problems found"
        lines = [f"figure checks: {len(self.findings)} finding(s)"]
        lines.extend(f"  {finding}" for finding in self.findings)
        return "\n".join(lines)


def _overlaps(a: Any, b: Any, pad: float = 0.0) -> bool:
    return not (
        a.x1 + pad <= b.x0 or b.x1 + pad <= a.x0 or a.y1 + pad <= b.y0 or b.y1 + pad <= a.y0
    )


def _drawn_tick_labels(axes: Any, which: str) -> list[Any]:
    """Tick labels that actually appear on this axes, in axis order.

    The locator lays ticks on a round grid and keeps the ones past the view
    limits. Those report get_visible() as True and carry a real bounding box,
    but nothing draws them, so anything that measures text has to drop them.
    Limits are sorted because an inverted axis reports them high to low.
    """
    labels, limits, index = (
        (axes.get_xticklabels(which="both"), axes.get_xlim(), 0)
        if which == "x"
        else (axes.get_yticklabels(which="both"), axes.get_ylim(), 1)
    )
    low, high = sorted(limits)
    return sorted(
        [
            label
            for label in labels
            if label.get_visible()
            and (label.get_text() or "").strip()
            and low <= label.get_position()[index] <= high
        ],
        key=lambda label: label.get_position()[index],
    )


def _undrawn_tick_ids(figure: Any) -> set[int]:
    """Tick labels that exist as artists but never reach the page."""
    drawn: set[int] = set()
    every: set[int] = set()
    for axes in figure.get_axes():
        for which in ("x", "y"):
            drawn.update(id(label) for label in _drawn_tick_labels(axes, which))
        every.update(id(label) for label in axes.get_xticklabels(which="both"))
        every.update(id(label) for label in axes.get_yticklabels(which="both"))
    return every - drawn


def _visible_texts(figure: Any) -> Iterable[Any]:
    from matplotlib.text import Text

    undrawn = _undrawn_tick_ids(figure)
    for artist in figure.findobj(Text):
        if not artist.get_visible():
            continue
        if not (artist.get_text() or "").strip():
            continue
        if id(artist) in undrawn:
            continue
        yield artist


def _check_text_size(figure: Any, report: Report, scale: float, floor: float) -> None:
    smallest = None
    for artist in _visible_texts(figure):
        effective = artist.get_fontsize() * scale
        if smallest is None or effective < smallest[0]:
            smallest = (effective, artist)

    if smallest is None:
        return

    size, artist = smallest
    text = artist.get_text()
    label = text if len(text) <= 24 else text[:21] + "..."
    if size < floor and not math.isclose(size, floor, rel_tol=1e-12, abs_tol=1e-12):
        report.add(
            "error",
            "text_too_small",
            f'"{label}" renders at {size!r}pt, below the required {floor}pt at the target width.',
            sources=(_source(artist),),
        )
    elif size < floor + 1.0:
        report.add(
            "warning",
            "text_near_minimum",
            f'"{label}" renders at {size:.1f}pt, close to the {floor}pt floor.',
            sources=(_source(artist),),
        )


def _check_tick_collisions(axes: Any, renderer: Any, report: Report) -> None:
    for name in ("x", "y"):
        boxes = [
            (label.get_text(), label.get_window_extent(renderer), label)
            for label in _drawn_tick_labels(axes, name)
        ]
        for i in range(len(boxes) - 1):
            left, right = boxes[i], boxes[i + 1]
            if _overlaps(left[1], right[1]):
                report.add(
                    "error",
                    "tick_labels_collide",
                    f'{name} tick labels "{left[0]}" and "{right[0]}" overlap. '
                    "Rotate them, thin them out, or widen the figure.",
                    sources=(_source(left[2]), _source(right[2])),
                )
                break


def _check_text_collisions(figure: Any, renderer: Any, report: Report) -> None:
    """Any two pieces of text landing on each other.

    Tick labels within one axes have their own check, which knows they come in a
    row. This one covers everything else: an annotation on the title, a
    reference label on an annotation, and an inset's tick labels running into
    the parent's, which is a collision between two axes rather than within one.
    """
    from matplotlib.text import Text

    entries: list[tuple[str, Any, int, bool, Any]] = []
    undrawn = _undrawn_tick_ids(figure)
    for axes in figure.get_axes():
        if not axes.get_visible():
            continue
        owner = id(axes)
        ticks = {
            id(t)
            for t in list(axes.get_xticklabels(which="both"))
            + list(axes.get_yticklabels(which="both"))
        }
        for artist in axes.findobj(Text):
            if not artist.get_visible() or not (artist.get_text() or "").strip():
                continue
            if id(artist) in undrawn:
                continue
            try:
                box = artist.get_window_extent(renderer)
            except (ValueError, RuntimeError):
                continue
            if box.width <= 0 or box.height <= 0:
                continue
            entries.append((artist.get_text(), box, owner, id(artist) in ticks, artist))

    for text in figure.texts:
        if not text.get_visible() or not (text.get_text() or "").strip():
            continue
        try:
            box = text.get_window_extent(renderer)
        except (ValueError, RuntimeError):
            continue
        entries.append((text.get_text(), box, 0, False, text))

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            left_text, left_box, left_axes, left_tick, left_artist = entries[i]
            right_text, right_box, right_axes, right_tick, right_artist = entries[j]
            # Two tick labels on the same axes are the other check's business.
            if left_tick and right_tick and left_axes == right_axes:
                continue
            if not _overlaps(left_box, right_box):
                continue
            overlap = (min(left_box.x1, right_box.x1) - max(left_box.x0, right_box.x0)) * (
                min(left_box.y1, right_box.y1) - max(left_box.y0, right_box.y0)
            )
            smaller = min(left_box.width * left_box.height, right_box.width * right_box.height)
            if smaller <= 0 or overlap / smaller < 0.12:
                continue
            across = " (an inset over its parent)" if left_axes != right_axes else ""
            report.add(
                "error",
                "labels_collide",
                f'"{left_text}" and "{right_text}" are drawn on top of each other{across}.',
                sources=(_source(left_artist), _source(right_artist)),
            )
            return


def _data_points_in_display(axes: Any, renderer: Any) -> list[Any]:
    """Display-space points and patch boxes a legend could be sitting on."""
    from matplotlib.collections import PathCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    found: list[Any] = []
    for line in axes.get_lines():
        if not line.get_visible():
            continue
        data = line.get_xydata()
        if len(data):
            found.extend(axes.transData.transform(data))
    for collection in axes.collections:
        if isinstance(collection, PathCollection) and collection.get_visible():
            offsets = collection.get_offsets()
            if len(offsets):
                found.extend(axes.transData.transform(offsets))
    for patch in axes.patches:
        if isinstance(patch, Rectangle) and patch.get_visible():
            box = patch.get_window_extent(renderer)
            found.append((box.x0 + box.width / 2, box.y0 + box.height / 2))
    _ = Line2D  # imported for the isinstance contract above staying honest
    return found


def _check_legend_occlusion(axes: Any, renderer: Any, report: Report) -> None:
    legend = axes.get_legend()
    if legend is None or not legend.get_visible():
        return

    box = legend.get_window_extent(renderer)
    axes_box = axes.get_window_extent(renderer)
    if not _overlaps(box, axes_box):
        return  # anchored outside, nothing to cover

    covered = sum(
        1
        for x, y in _data_points_in_display(axes, renderer)
        if box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1
    )
    if covered:
        report.add(
            "error",
            "legend_covers_data",
            f"the legend sits on top of {covered} plotted point(s). "
            'Move it, or set legend.position to "outside_right".',
            sources=(_source(legend, "legend"),),
        )


def _check_overplotting(axes: Any, renderer: Any, report: Report) -> None:
    from matplotlib.collections import PathCollection

    axes_box = axes.get_window_extent(renderer)
    axes_area = axes_box.width * axes_box.height
    if axes_area <= 0:
        return

    dpi_scale = (axes.figure.dpi / 72.0) ** 2
    ink = 0.0
    points = 0
    for collection in axes.collections:
        if (
            not isinstance(collection, PathCollection)
            or not collection.get_visible()
            or collection.get_alpha() == 0
            or collection.get_offset_transform() != axes.transData
        ):
            continue
        offsets = np.ma.asarray(collection.get_offsets(), dtype=float)
        coordinates = np.asarray(offsets.filled(np.nan))
        if coordinates.ndim != 2 or coordinates.shape[1] != 2:
            continue
        active = np.isfinite(coordinates).all(axis=1) & ~np.ma.getmaskarray(offsets).any(axis=1)
        display = axes.transData.transform(coordinates)
        active &= (
            (display[:, 0] >= axes_box.xmin)
            & (display[:, 0] <= axes_box.xmax)
            & (display[:, 1] >= axes_box.ymin)
            & (display[:, 1] <= axes_box.ymax)
        )
        sizes = collection.get_sizes()
        if len(sizes) == 0:
            continue
        areas = np.resize(sizes, len(coordinates))
        active &= np.isfinite(areas) & (areas > 0)
        points += int(active.sum())
        ink += float(areas[active].sum()) * dpi_scale

    if points and ink / axes_area > MAX_INK_FRACTION:
        report.add(
            "warning",
            "overplotting",
            f"{points} in-view marker centers have nominal ink about {ink / axes_area:.0%} "
            "of the plotting area (a density heuristic, not measured overlap). "
            "Inspect overplotting and consider transparency or a summary.",
        )


@dataclass(frozen=True)
class _SeriesAppearance:
    label: str
    colour: tuple[float, float, float]
    channel: str
    identity: tuple[str, str | int]


def _series_appearance(axes: Any) -> list[_SeriesAppearance]:
    """Colour and second channel per legend entry, as the reader receives them."""
    from matplotlib.colors import to_rgb

    handles, labels = axes.get_legend_handles_labels()
    # Matplotlib hides underscore-prefixed labels from automatic legends. The
    # generator supplies source identity for its own visible series instead;
    # augment the current scene rather than trusting a cached artist list.
    seen = {id(handle) for handle in handles}
    for handle in [*axes.get_children(), *axes.containers]:
        identity = getattr(handle, "_graphunslopify_legend_identity", None)
        target = getattr(handle, "_graphunslopify_legend_text_target", None)
        if ((identity is not None and identity.get("legend", True)) or target is not None) and id(
            handle
        ) not in seen:
            handles.append(handle)
            labels.append(handle.get_label())
            seen.add(id(handle))
    series = []
    for handle, label in zip(handles, labels, strict=True):
        # Bars hand back a BarContainer, which carries no colour of its own.
        mark = handle.patches[0] if getattr(handle, "patches", None) else handle

        colour = None
        for getter in ("get_color", "get_facecolor", "get_edgecolor"):
            if not hasattr(mark, getter):
                continue
            value = getattr(mark, getter)()
            if value is None:
                continue
            # A hex string is a sequence too, so isinstance has to come first.
            if (
                not isinstance(value, str)
                and hasattr(value, "__len__")
                and len(value)
                and hasattr(value[0], "__len__")
            ):
                value = value[0]
            try:
                colour = to_rgb(value)
            except (ValueError, TypeError):
                continue
            break
        if colour is None:
            continue

        alpha = mark.get_alpha() if hasattr(mark, "get_alpha") else None
        seen = composite_over_white(colour, 1.0 if alpha is None else alpha)

        channel = ""
        for getter in ("get_linestyle", "get_marker", "get_hatch"):
            if hasattr(mark, getter):
                channel += str(getattr(mark, getter)())
        # A scatter hands back a PathCollection, which has no get_marker. The
        # marker shape lives in the path itself, so hash that instead.
        if hasattr(mark, "get_paths"):
            paths = mark.get_paths()
            if paths:
                channel += hashlib.md5(paths[0].vertices.tobytes()).hexdigest()[:8]
        owner = getattr(handle, "_graphunslopify_legend_identity", None)
        target = getattr(handle, "_graphunslopify_legend_text_target", None)
        key = (
            ("source", str(owner["series"]))
            if owner is not None
            else (("layer", target["source"]["layer"]) if target is not None else ("label", label))
        )
        series.append(_SeriesAppearance(label, seen, channel, key))
    return series


def _check_colour_separation(axes: Any, report: Report) -> None:
    series = _series_appearance(axes)
    if len(series) < 2:
        return

    distinct_channels = len({item.channel for item in series}) == len(series)

    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            left_label, left_rgb = series[i].label, series[i].colour
            right_label, right_rgb = series[j].label, series[j].colour
            gap, condition = worst_case_distance(left_rgb, right_rgb)

            if gap < MIN_COLOUR_DISTANCE:
                severity: Severity = "error" if condition == "normal vision" else "warning"
                if severity == "warning" and distinct_channels:
                    continue
                report.add(
                    severity,
                    "series_indistinguishable",
                    f'"{left_label}" and "{right_label}" differ by only {gap:.1f} '
                    f"under {condition}. A reader cannot tell them apart.",
                )
                continue

            if distinct_channels:
                continue
            grey_gap = abs(relative_luminance(left_rgb) - relative_luminance(right_rgb))
            if grey_gap < MIN_GREYSCALE_SEPARATION:
                report.add(
                    "warning",
                    "greyscale_collision",
                    f'"{left_label}" and "{right_label}" merge in greyscale. '
                    "Give one a different line style or marker so colour is not the only channel.",
                )


def _bar_value_axis(axes: Any) -> str | None:
    """Which axis carries bar length, or None when there are no bars."""
    from matplotlib.container import BarContainer

    orientations = {
        container.orientation
        for container in axes.containers
        if isinstance(container, BarContainer) and any(p.get_visible() for p in container.patches)
    }
    if len(orientations) != 1:
        return None
    return {"vertical": "y", "horizontal": "x"}.get(orientations.pop())


def _bars_float(axes: Any, which: str) -> bool:
    """Whether any bar has an explicitly floating, nonzero origin.

    A waterfall stacks each contribution on the running total, so only the first
    and the last touch the baseline. Its bars are meant to float, and the
    truncation rule below assumes they do not: it would fire on every waterfall
    ever drawn and tell the author to do something that would destroy the chart.
    """
    from matplotlib.container import BarContainer

    bars = [
        p
        for container in axes.containers
        if isinstance(container, BarContainer)
        for p in container.patches
        if p.get_visible()
    ]
    return any((bar.get_y() if which == "y" else bar.get_x()) != 0 for bar in bars)


def _check_truncated_bars(axes: Any, report: Report) -> None:
    """A bar's length encodes its value, so a cut baseline overstates differences.

    Readers keep misreading truncated bars even after being taught about it, so
    this is an error rather than a matter of taste. Line charts are exempt; the
    same truncation is defensible there.
    """
    from matplotlib.container import BarContainer

    # Check actual transformed value extents before the common-baseline rule:
    # floating bars may have legitimate offsets but still must remain visible.
    bounds = axes.get_window_extent()
    clipped = 0
    clipped_intervals = 0
    bar_sources = []
    interval_sources = []
    for container in axes.containers:
        if not isinstance(container, BarContainer):
            continue
        coordinate = {"vertical": 1, "horizontal": 0}.get(container.orientation)
        if container.errorbar is not None and coordinate is not None:
            lower, upper = (
                (bounds.ymin, bounds.ymax) if coordinate == 1 else (bounds.xmin, bounds.xmax)
            )
            for collection in container.errorbar.lines[2]:
                if not collection.get_visible() or not collection.get_clip_on():
                    continue
                for segment_index, segment in enumerate(collection.get_segments()):
                    if not len(segment):
                        continue
                    display = collection.get_transform().transform(segment)[:, coordinate]
                    if all(math.isfinite(value) for value in display) and (
                        min(display) < lower - 1e-7 or max(display) > upper + 1e-7
                    ):
                        clipped_intervals += 1
                        interval_sources.append(_source(collection, "bar_interval", segment_index))
        for bar in container.patches:
            if not bar.get_visible() or not bar.get_clip_on():
                continue
            extent = bar.get_window_extent()
            if container.orientation == "vertical":
                low, high, lower, upper = extent.ymin, extent.ymax, bounds.ymin, bounds.ymax
            elif container.orientation == "horizontal":
                low, high, lower, upper = extent.xmin, extent.xmax, bounds.xmin, bounds.xmax
            else:
                continue
            if all(math.isfinite(value) for value in (low, high)) and (
                low < lower - 1e-7 or high > upper + 1e-7
            ):
                clipped += 1
                bar_sources.append(_source(bar, "bar"))
    if clipped:
        report.add(
            "error",
            "bar_mark_clipped",
            f"{clipped} bar value extents are clipped by the axes; widen the value limits "
            "so complete lengths are visible, or use a non-length-bearing mark.",
            sources=bar_sources,
        )
    if clipped_intervals:
        report.add(
            "error",
            "bar_interval_clipped",
            f"{clipped_intervals} bar uncertainty intervals are clipped by the axes; widen "
            "the value limits so both true endpoints remain visible.",
            sources=interval_sources,
        )

    which = _bar_value_axis(axes)
    if which is None:
        return
    if _bars_float(axes, which):
        return

    low, high = axes.get_ylim() if which == "y" else axes.get_xlim()
    if min(low, high) > 0 or max(low, high) < 0:
        report.add(
            "error",
            "truncated_bar_axis",
            f"the {which} axis excludes zero ({low:g} to {high:g}), so the bars overstate "
            "the differences between them. Set baseline_zero, or use a line chart.",
        )


def _check_exaggeration(axes: Any, report: Report) -> None:
    """A heavily zoomed axis turns a rounding error into a headline result."""
    from matplotlib.ticker import PercentFormatter, ScalarFormatter

    if _bar_value_axis(axes) is not None:
        return  # bars are covered by the stricter rule above

    for name in ("x", "y"):
        if name == "x" and (
            axes.get_xscale() != "linear"
            or not isinstance(axes.xaxis.get_major_formatter(), (ScalarFormatter, PercentFormatter))
        ):
            continue  # Date origins and categorical indices are not numeric magnitudes.
        low, high = getattr(axes, f"get_{name}lim")()
        span = abs(high - low)
        magnitude = max(abs(low), abs(high))
        if span <= 0 or magnitude <= 0:
            continue

        if span / magnitude < MIN_RANGE_TO_MAGNITUDE:
            report.add(
                "warning",
                "axis_exaggeration",
                f"the {name} axis shows a span of {span:g} around values near {magnitude:g}, "
                f"about {span / magnitude:.1%} of their size. Small differences will look large, "
                "so say in the caption that the axis is zoomed.",
            )


def _check_panel_consistency(figure: Any, report: Report) -> None:
    """Panels that share an axis must actually share its limits.

    Faceting makes this easy to get wrong and impossible to spot by eye, because
    each panel looks reasonable on its own while the comparison between them is
    silently broken.
    """
    # A colourbar is an axes but not a panel, and counting it makes every
    # heatmap look like two panels that disagree.
    axes = [
        ax
        for ax in figure.get_axes()
        if ax.get_visible() and ax.has_data() and ax.get_label() != "<colorbar>"
    ]
    if len(axes) < 2:
        return

    # A cut axis has intentionally different ranges on its two halves. Keep
    # these axes in the colour-drift check below, which still applies to them.
    panels = [ax for ax in axes if ax.get_label() != "<axis-break>"]
    for name, getter in (("y", "get_ylim"), ("x", "get_xlim")):
        spans = {tuple(round(v, 6) for v in getattr(ax, getter)()) for ax in panels}
        if len(spans) > 1:
            report.add(
                "warning",
                f"panels_disagree_on_{name}",
                f"the panels use {len(spans)} different {name} ranges, so they cannot be "
                "compared by eye. Set share_x or share_y, or say so in the caption.",
            )

    # A series must keep one colour across every panel or the legend lies.
    seen: dict[tuple[str, str | int], set[tuple[float, float, float]]] = {}
    labels = {}
    for ax in axes:
        for item in _series_appearance(ax):
            seen.setdefault(item.identity, set()).add(tuple(round(c, 4) for c in item.colour))
            labels[item.identity] = (
                f"Layer {item.identity[1] + 1} ({item.label})"
                if item.identity[0] == "layer"
                else item.label
            )
    drifted = sorted(labels[key] for key, colours in seen.items() if len(colours) > 1)
    if drifted:
        report.add(
            "error",
            "series_colour_drifts_between_panels",
            f"{', '.join(drifted)} changes colour from one panel to the next.",
        )


def _check_cell_text_contrast(axes: Any, report: Report) -> None:
    if not axes.images:
        return
    for text in axes.texts:
        if not text.get_visible() or not text.get_text().strip():
            continue
        try:
            ratio = cell_text_contrast(axes, text)
        except NotImplementedError as exc:
            report.add("warning", "cell_text_contrast_untested", str(exc))
            continue
        if ratio is not None and ratio < 4.5:
            report.add(
                "error",
                "cell_text_low_contrast",
                f"Cell annotation {text.get_text()!r} has contrast {ratio!r}:1, below 4.5:1.",
            )


def inspect_figure(
    figure: Any,
    target_width_in: float | None = None,
    min_text_pt: float = MIN_TEXT_POINTS,
    *,
    export_paths: Iterable[str | Path] | None = None,
) -> Report:
    """Check a rendered figure and return everything wrong with it.

    `target_width_in` is the width the figure will occupy in the manuscript. Pass
    it when the figure will be scaled down on the page. Pass `export_paths` to
    assess the actual PNG/SVG/PDF file widths, including tight crops/padding.
    Without paths the calculation uses the nominal canvas, not a final export.
    """
    report = Report()

    if target_width_in is not None and (not math.isfinite(target_width_in) or target_width_in <= 0):
        raise ValueError("target_width_in must be finite and positive")
    if not math.isfinite(min_text_pt) or min_text_pt <= 0:
        raise ValueError("min_text_pt must be finite and positive")

    figure_width = float(figure.get_size_inches()[0])
    if not math.isfinite(figure_width) or figure_width <= 0:
        raise ValueError("Figure width must be finite and positive")
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()

    evaluated_width = figure_width
    widths = {}
    basis = "nominal"
    if export_paths is not None:
        basis = "exports"
        paths = list(export_paths)
        if not paths:
            report.add(
                "error",
                "export_size_unavailable",
                "No written static exports supplied for final text-size assessment.",
            )
            basis = "unavailable"
        for path in paths:
            try:
                widths[str(path)] = export_width_in(path)
            except (OSError, ValueError, ET.ParseError, PyPdfError) as exc:
                report.add(
                    "error",
                    "export_size_unavailable",
                    f"Cannot establish physical width of {str(path)!r}: {exc}",
                )
                basis = "unavailable"
        evaluated_width = max(widths.values()) if basis == "exports" else None
    scale = (
        None
        if evaluated_width is None
        else min(target_width_in / evaluated_width, 1.0)
        if target_width_in is not None
        else 1.0
    )
    report.measurements = {
        "basis": basis,
        "nominal_width_in": figure_width,
        "widths_in": widths,
        "target_width_in": target_width_in,
        "evaluated_width_in": evaluated_width,
        "text_scale": scale,
        "data_view": [],
    }

    if scale is not None:
        _check_text_size(figure, report, scale, min_text_pt)
    for axes in figure.get_axes():
        view, findings = inspect_data_view(axes)
        report.measurements["data_view"].append(view)
        for severity, code, message in findings:
            report.add(severity, code, message)
        _check_tick_collisions(axes, renderer, report)
        _check_legend_occlusion(axes, renderer, report)
        _check_overplotting(axes, renderer, report)
        _check_colour_separation(axes, report)
        _check_cell_text_contrast(axes, report)
        _check_truncated_bars(axes, report)
        _check_exaggeration(axes, report)

    _check_text_collisions(figure, renderer, report)
    _check_panel_consistency(figure, report)
    return report
