"""Observe native robustness measurements during the final PNG draw."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from .preview_render import NAMESPACE_OBSERVER, _execute

_MAX_POINTS = 20_000
_LEGEND = "_graphunslopify_legend_identity"
_ELEMENT = "_graphunslopify_inspector_target"


def _xy(artist):
    from matplotlib.collections import PathCollection

    if isinstance(artist, PathCollection):
        return np.ma.asarray(artist.get_offsets(), dtype=float).filled(np.nan)
    return artist.get_xydata()


def _digest(points):
    canonical = np.array(points, dtype="<f8", copy=True)
    canonical[~np.isfinite(canonical)] = np.nan
    canonical[canonical == 0] = 0
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def _series(ax, artist):
    from matplotlib.lines import Line2D

    points = _xy(artist)
    finite = np.isfinite(points).all(axis=1)
    domain = finite.copy()
    scales = (ax.get_xscale(), ax.get_yscale())
    for index, scale in enumerate(scales):
        if scale == "log":
            domain &= points[:, index] > 0
    positions = np.full(points.shape, np.nan)
    positions[domain] = ax.transAxes.inverted().transform(ax.transData.transform(points[domain]))
    visible = (
        np.isfinite(positions).all(axis=1)
        & (positions >= -1e-9).all(axis=1)
        & (positions <= 1 + 1e-9).all(axis=1)
    )
    return {
        "series": getattr(artist, _LEGEND, {}).get("series"),
        "data_sha256": _digest(points),
        "points": len(points),
        "finite_points": int(finite.sum()),
        "outside_scale_domain": int((finite & ~domain).sum()),
        "centers_inside_axes": int(visible.sum()),
        "line_markers": isinstance(artist, Line2D)
        and artist.get_marker() not in (None, "None", "none", "", " "),
        "projected": [
            [float(x), float(y)] if np.isfinite([x, y]).all() else None for x, y in positions
        ],
        "inside": visible.tolist(),
    }


class Snapshot:
    def __init__(self):
        self.draws = []
        self.result = {}

    def observe_namespace(self, phase, context):
        if phase != "ready":
            return
        original = context["draw_panel"]
        estimator = context.get("calibration_estimate")

        def draw(ax, frame):
            from matplotlib.collections import PathCollection
            from matplotlib.container import ErrorbarContainer

            curves = []

            def estimate(block):
                result = estimator(block)
                name = context["GROUP"]
                series = str(block[name].iat[0]) if name is not None and len(block) else None
                curves.append(
                    {
                        "series": series,
                        "ece": result["ece"],
                        "observations": result["observations"],
                        "points": [
                            {
                                "bin": int(index),
                                "mean_probability": float(mean),
                                "observed_fraction": float(rate),
                                "observations": int(count),
                            }
                            for index, mean, rate, count in zip(
                                result["bin"],
                                result["probability"],
                                result["frequency"],
                                result["counts"],
                                strict=True,
                            )
                        ],
                    }
                )
                return result

            previous = set(ax.lines) | set(ax.collections)
            if estimator is not None:
                context["calibration_estimate"] = estimate
            try:
                result = original(ax, frame)
            finally:
                if estimator is not None:
                    context["calibration_estimate"] = estimator
            bars = [
                container for container in ax.containers if isinstance(container, ErrorbarContainer)
            ]
            bar_artists = {artist for container in bars for artist in container.get_children()}
            lines = [artist for artist in ax.lines if artist not in previous | bar_artists]
            dots = [
                artist
                for artist in ax.collections
                if artist not in previous and isinstance(artist, PathCollection)
            ]
            if estimator is not None:
                if len(lines) != len(curves) + 1:
                    raise ValueError("Calibration marks do not match the observed estimator calls")
                lines = lines[:-1]  # The calibration drawer appends one identity reference line.
                for line, curve in zip(lines, curves, strict=True):
                    expected = [
                        [point["mean_probability"], point["observed_fraction"]]
                        for point in curve["points"]
                    ]
                    if not np.array_equal(_xy(line), expected):
                        raise ValueError(
                            "Calibration evidence differs from the actual plotted coordinates"
                        )
            bands = [
                artist
                for artist in ax.collections
                if artist not in bar_artists
                if getattr(artist, _ELEMENT, {}).get("role") == "uncertainty"
            ]
            intervals = {"bars": len(bars), "bands": len(bands)}
            # Scatter overlays are Line2D. Count only the scatter collections.
            self.draws.append((ax, dots if dots else lines, intervals, curves, context.get("BINS")))
            return result

        context["draw_panel"] = draw

    def draw_event(self, event):
        figure = event.canvas.figure
        try:
            ((ax, artists, intervals, curves, bins),) = self.draws
            if ax.figure is not figure or not artists:
                raise ValueError("No supported native data artists appeared in the final draw")
            if sum(len(_xy(artist)) for artist in artists) > _MAX_POINTS:
                raise ValueError("Robustness geometry exceeds its 20,000-position limit")
            series = [_series(ax, artist) for artist in artists if artist.get_visible()]
            if not series or len({item["series"] for item in series}) != len(series):
                raise ValueError("Primary series in the final native draw are ambiguous")
            legends = [
                legend
                for legend in (*figure.legends, ax.get_legend())
                if legend and legend.get_visible()
            ]
            self.result = {
                "available": True,
                "axis_scales": [ax.get_xscale(), ax.get_yscale()],
                "axis_limits": [list(map(float, ax.get_xlim())), list(map(float, ax.get_ylim()))],
                "legend_labels": [
                    text.get_text()
                    for legend in legends
                    for text in legend.get_texts()
                    if text.get_visible()
                ],
                "legend_bounds_axes": [
                    list(
                        map(
                            float,
                            ax.transAxes.inverted()
                            .transform_bbox(legend.get_window_extent(event.renderer))
                            .bounds,
                        )
                    )
                    for legend in legends
                ],
                "grid_visible": any(
                    line.get_visible() for line in [*ax.get_xgridlines(), *ax.get_ygridlines()]
                ),
                "intervals": intervals,
                "series": series,
                "calibration": {"bins": bins, "series": curves} if bins is not None else None,
            }
        except (ValueError, TypeError, AttributeError, RuntimeError) as problem:
            self.result = {"available": False, "error": str(problem)}


def main():
    from matplotlib.figure import Figure

    script, *arguments = sys.argv[1:]
    script = Path(script).resolve()
    image = script.parent / "figure.png"
    snapshot = Snapshot()
    original = Figure.savefig

    def save(figure, filename, *positional, **options):
        if not isinstance(filename, (Path, str)) or Path(filename).resolve() != image:
            return original(figure, filename, *positional, **options)
        canvas = figure.canvas
        callback = canvas.mpl_connect("draw_event", snapshot.draw_event)
        try:
            result = original(figure, filename, *positional, **options)
        finally:
            canvas.mpl_disconnect(callback)
        witness = {
            **snapshot.result,
            "png_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "program_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        }
        (script.parent / "robustness-observation.json").write_text(
            json.dumps(witness, allow_nan=False), encoding="utf8"
        )
        return result

    previous = sys.argv
    token = NAMESPACE_OBSERVER.set(snapshot.observe_namespace)
    Figure.savefig = save
    sys.argv = [str(script), *arguments]
    try:
        _execute(script)
    finally:
        Figure.savefig = original
        sys.argv = previous
        NAMESPACE_OBSERVER.reset(token)


if __name__ == "__main__":
    main()
