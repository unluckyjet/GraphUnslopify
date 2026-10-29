import type { FigureSpec } from "../schema.ts";
import { hasCategoricalX } from "../schema.ts";
import { plotAxis } from "../capabilities.ts";
import { pyBool, pyStr } from "./py.ts";

/** Resolve semantic targets using the primary marks already drawn, not a second analysis. */
export function emitAnnotations(spec: FigureSpec, out: string[]): void {
  out.push(`ANNOTATION_KIND = ${pyStr(spec.kind)}`,
    `ANNOTATION_CATEGORICAL = ${pyBool(hasCategoricalX(spec) || ["heatmap", "confusion_matrix"].includes(spec.kind))}`,
    `ANNOTATION_SWAPPED = ${pyBool(plotAxis(spec, "y") === "x")}`);
  out.push(...String.raw`

def annotation_scalar(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def capture_annotation_geometry(ax, frame):
    from matplotlib.collections import PathCollection, PolyCollection
    from matplotlib.container import BarContainer
    from matplotlib.path import Path as MplPath
    points = []
    names = series_names(frame) if GROUP is not None else [None]
    roots = list(ax.child_axes) if ANNOTATION_KIND == "sparkline_grid" else [ax]
    for region, target in enumerate(roots):
        owner = names[region] if ANNOTATION_KIND == "sparkline_grid" and region < len(names) else None
        axis = target.yaxis if ANNOTATION_SWAPPED else target.xaxis
        ticks = axis.get_ticklocs()
        labels = axis.get_major_formatter().format_ticks(ticks)
        keys = getattr(target, "_graphunslopify_annotation_keys", labels)
        def key_for(x, y):
            if ANNOTATION_CATEGORICAL:
                coordinate = y if ANNOTATION_SWAPPED else x
                if not len(ticks) or len(keys) != len(ticks):
                    return None
                return str(keys[int(np.argmin(np.abs(np.asarray(ticks) - coordinate)))])
            return float(x)
        def append(xs, ys, series=None, basis="rendered_point", values=None, category=None, category_position=None):
            pairs = np.ma.asarray(np.ma.column_stack((xs, ys)), dtype=float)
            mask = np.ma.getmaskarray(pairs).any(axis=1)
            pairs = np.asarray(pairs.filled(np.nan), dtype=float)
            for index, (x, y) in enumerate(pairs):
                if mask[index] or not np.isfinite([x, y]).all():
                    continue
                value = values[index] if values is not None else x if ANNOTATION_SWAPPED else y
                key = category if category is not None else key_for(x, y)
                if key is not None and np.isfinite(value):
                    order = (y if target.yaxis_inverted() else -y) if ANNOTATION_SWAPPED else (-x if target.xaxis_inverted() else x)
                    if category_position is not None:
                        order = category_position if target.yaxis_inverted() else -category_position
                    points.append({"x": float(x), "y": float(y), "key": key, "order": float(order),
                                   "value": float(value), "series": owner if owner is not None else series,
                                   "basis": basis, "axes": target, "region": region})
        kind = ANNOTATION_KIND
        if kind in ("bar", "waterfall"):
            for container in target.containers:
                if not isinstance(container, BarContainer):
                    continue
                series = container.get_label() if GROUP is not None else None
                for patch in container.patches:
                    if not patch.get_visible() or patch.get_alpha() == 0:
                        continue
                    if container.orientation == "horizontal":
                        x, y, value = patch.get_x() + patch.get_width(), patch.get_y() + patch.get_height() / 2, patch.get_width()
                    else:
                        x, y, value = patch.get_x() + patch.get_width() / 2, patch.get_y() + patch.get_height(), patch.get_height()
                    y = getattr(patch, "_graphunslopify_annotation_end", y)
                    value = getattr(patch, "_graphunslopify_annotation_value", value)
                    append([x], [y], series, "rendered_bar_value", [value])
        elif kind in ("heatmap", "confusion_matrix"):
            for image in target.images:
                array = np.ma.asarray(image.get_array())
                rows, columns = array.shape
                for row in range(rows):
                    for column in range(columns):
                        value = array[row, column]
                        if not np.ma.is_masked(value) and np.isfinite(value):
                            append([column], [row], basis="rendered_cell_value", values=[value])
        elif kind in ("scatter", "qq", "scaling_fit", "raincloud", "paired_difference"):
            collections = [c for c in target.collections if isinstance(c, PathCollection) and c.get_visible() and c.get_alpha() != 0]
            for index, collection in enumerate(collections):
                offsets = collection.get_offsets()
                series = names[index] if GROUP is not None and index < len(names) else None
                if len(offsets):
                    append(offsets[:, 0], offsets[:, 1], series, "rendered_observation" if kind not in ("qq", "paired_difference") else "rendered_derived_observation")
        elif kind == "violin":
            for collection in target.collections:
                if not isinstance(collection, PolyCollection) or not collection.get_visible() or collection.get_alpha() == 0:
                    continue
                for path in collection.get_paths():
                    vertices = path.vertices if path.codes is None else path.vertices[~np.isin(path.codes, [MplPath.CLOSEPOLY, MplPath.STOP])]
                    append(vertices[:, 0], vertices[:, 1], basis="rendered_distribution_boundary")
        else:
            lines = [line for line in target.lines if line.get_visible() and line.get_transform() == target.transData and line.get_alpha() != 0]
            if kind in ("forest", "dumbbell"):
                lines = [line for line in lines if line.get_marker() not in (None, "None", "", " ")]
            elif kind == "ridgeline":
                lines = [line for line in lines if hasattr(line, "_graphunslopify_annotation_category") or line.get_marker() == "|"]
            elif kind != "box":
                lines = [line for line in lines if line.get_linestyle() not in (None, "None", "", " ")]
                if kind == "calibration":
                    lines = [line for line in lines if line.get_marker() == "o"]
                elif kind == "line":
                    lines = [line for line in lines if getattr(line, "_graphunslopify_annotation_primary", False)]
                elif GROUP is not None and kind != "sparkline_grid":
                    lines = [line for line in lines if line.get_label() in names]
                elif lines:
                    highest = max(line.get_zorder() for line in lines)
                    lines = [line for line in lines if line.get_zorder() == highest]
            for index, line in enumerate(lines):
                series = getattr(line, "_graphunslopify_annotation_series", None)
                if GROUP is not None and kind not in ("sparkline_grid", "dumbbell", "line"):
                    series = names[index] if kind == "calibration" and index < len(names) else line.get_label()
                xy = line.get_xydata()
                if len(xy):
                    append(xy[:, 0], xy[:, 1], series, "rendered_curve" if kind not in ("forest", "dumbbell", "ridgeline", "box") else "rendered_mark",
                           category=getattr(line, "_graphunslopify_annotation_category", None),
                           category_position=getattr(line, "_graphunslopify_annotation_base", None))
    ax._graphunslopify_annotation_points = points


def locate_annotation(points, where, series, coordinate=False):
    selected = [point for point in points if point["series"] == series]
    if not selected:
        return None, "the requested series has no finite primary marks"
    if where == "crossover" and not coordinate:
        names = list(dict.fromkeys(point["series"] for point in points))
        if series is None or len(names) < 2:
            return None, "a crossover needs at least two rendered series"
        values = {}
        for point in points:
            key = (point["key"], point["series"])
            if key in values and values[key]["value"] != point["value"]:
                if ANNOTATION_KIND not in ("ecdf", "kaplan_meier"):
                    return None, "a crossover needs one value per series and aligned coordinate"
            values[key] = point
        keys = list(dict.fromkeys(point["key"] for point in sorted(points, key=lambda item: item["order"])))
        if any((key, name) not in values for key in keys for name in names):
            return None, "a crossover needs complete aligned coverage of every rendered series"
        previously_not_ahead = False
        for key in keys:
            own = values[key, series]
            ahead = all(own["value"] > values[key, name]["value"] for name in names if name != series)
            if ahead and previously_not_ahead:
                return own, None
            previously_not_ahead |= not ahead
        return None, "no observed transition from non-leading to leading exists"
    if where in ("max", "min") and not coordinate:
        return (max if where == "max" else min)(selected, key=lambda item: item["value"]), None
    ordered = sorted(selected, key=lambda item: item["key"] if not ANNOTATION_CATEGORICAL else item["order"])
    if ANNOTATION_KIND == "line" and not RUN_REPORT["spec"].get("sort_x", True):
        ordered = selected
    if where in ("first", "last") and not coordinate:
        endpoint = ordered[0 if where == "first" else -1]
        if ANNOTATION_CATEGORICAL and len({(point["x"], point["y"]) for point in selected if point["key"] == endpoint["key"]}) > 1:
            return None, "the endpoint category has multiple possible rendered anchors; choose a semantic extremum"
        return endpoint, None
    if ANNOTATION_CATEGORICAL:
        matches = [point for point in selected if point["key"] == str(where)]
    else:
        try:
            target = float(mdates.date2num(pd.to_datetime(where))) if X_TEMPORAL else float(where)
        except (TypeError, ValueError):
            return None, "the requested x is not valid for this axis"
        low, high = min(point["key"] for point in selected), max(point["key"] for point in selected)
        if not low <= target <= high:
            return None, "the requested x lies outside the observed domain; extrapolation is unavailable"
        distance = min(abs(point["key"] - target) for point in selected)
        matches = [point for point in selected if abs(point["key"] - target) == distance]
    unique = {(point["x"], point["y"]) for point in matches}
    if not matches:
        return None, "the requested category is absent"
    if len(unique) > 1:
        if ANNOTATION_KIND in ("ecdf", "kaplan_meier") and len({point["key"] for point in matches}) == 1:
            return matches[-1], None
        return None, "the requested x has multiple possible rendered anchors; choose a series or semantic extremum"
    return matches[0], None


def place_annotations(ax, frame):
    points = getattr(ax, "_graphunslopify_annotation_points", [])
    offsets = [(8, 10), (8, -14), (-10, 12), (-10, -16)]
    region = ax.figure.axes.index(ax) if ax in ax.figure.axes else 0
    for index, note in enumerate(ANNOTATIONS):
        point, reason = locate_annotation(points, note["at"], note.get("series"), note["coordinate"])
        record = {"panel": CURRENT_PANEL, "metric": Y_FIELD, "index": index, "region": region,
                  "requested": RUN_REPORT["spec"]["annotate"][index], "text": note["text"],
                  "text_verified": False, "status": "untested", "reason": reason}
        if point is not None:
            target = point["axes"]
            display = target.transData.transform([point["x"], point["y"]])
            bounds = target.get_window_extent()
            positive = (target.get_xscale() != "log" or point["x"] > 0) and (target.get_yscale() != "log" or point["y"] > 0)
            inside = positive and bounds.xmin - 1e-7 <= display[0] <= bounds.xmax + 1e-7 and bounds.ymin - 1e-7 <= display[1] <= bounds.ymax + 1e-7
            record["resolved"] = {key: annotation_scalar(point[key]) for key in ("x", "y", "key", "value", "basis")}
            if X_TEMPORAL and not ANNOTATION_CATEGORICAL:
                record["resolved"]["date"] = mdates.num2date(point["x"]).isoformat()
            if inside:
                record.update(status="resolved", reason=None)
                if not ANNOTATION_CATEGORICAL and note["coordinate"]:
                    requested = float(mdates.date2num(pd.to_datetime(note["at"]))) if X_TEMPORAL else float(note["at"])
                    record["snapped"] = point["key"] != requested
                artist = target.annotate(note["text"], xy=(point["x"], point["y"]),
                                xytext=offsets[index % len(offsets)], textcoords="offset points",
                                fontsize=ANNOTATION_PT, color="#202020", annotation_clip=False,
                                bbox={"facecolor": "white", "alpha": 0.95, "edgecolor": "none", "pad": 1} if ANNOTATION_KIND in ("heatmap", "confusion_matrix") else None,
                                arrowprops={"arrowstyle": "-", "linewidth": 0.7, "color": "#767676"})
                edit_target(artist, ["annotate", index, "text"], "annotation", {"panel": CURRENT_PANEL, "metric": Y_FIELD})
            else:
                record["reason"] = "the resolved primary mark lies outside this rendered view or log domain"
        records = RUN_REPORT.setdefault("annotations", [])
        records[:] = [old for old in records if (old["panel"], old["index"], old["region"]) != (CURRENT_PANEL, index, region)]
        records.append(record)
    _ = frame  # The marks, not reanalysis of raw rows, determine anchors.


def finalize_annotations():
    records = RUN_REPORT.get("annotations", [])
    panels = {item["index"] for item in RUN_REPORT["panels"]} or {0}
    for panel in panels:
        for index, note in enumerate(ANNOTATIONS):
            attempts = [item for item in records if item["panel"] == panel and item["index"] == index]
            resolved = [item for item in attempts if item["status"] == "resolved"]
            if not resolved:
                reason = f"annotation {index} in panel {panel}: " + (attempts[0]["reason"] if attempts else "no rendered primary geometry was available")
                if reason not in RUN_REPORT["untested"]:
                    RUN_REPORT["untested"].append(reason)
                finding("warning", "qq_annotation_unavailable" if ANNOTATION_KIND == "qq" else "annotation_unavailable", reason)
            elif any(item.get("snapped") for item in resolved):
                finding("warning", "annotation_snapped_to_observation", f"annotation {index} in panel {panel} uses the nearest unique observed point within the data domain; inspect requested/resolved coordinates")
`.split("\n"));
}
