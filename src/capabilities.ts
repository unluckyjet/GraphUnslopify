import { derivedAxis, hasCategoricalX, type FigureSpec } from "./schema.ts";

/** These drawing paths do not encode the declared series grouping. */
export function unusedGrouping(spec: FigureSpec): boolean {
  return !!spec.group && ["box", "violin", "raincloud", "ridgeline", "forest", "heatmap", "confusion_matrix", "waterfall"].includes(spec.kind);
}

/** Map semantic input axes to their physical presentation. */
export function plotAxis(spec: FigureSpec, specAxis: "x" | "y"): "x" | "y" {
  const swapped = (spec.kind === "bar" && spec.orientation === "horizontal")
    || ["ridgeline", "forest", "dumbbell"].includes(spec.kind);
  return swapped ? (specAxis === "x" ? "y" : "x") : specAxis;
}

/** A shared categorical axis needs a single mapping, including absent local levels. */
export function sharedCategoryAxes(spec: FigureSpec): boolean {
  if (!hasCategoricalX(spec) || ["waterfall", "paired_difference"].includes(spec.kind)) return false;
  const axis = plotAxis(spec, "x");
  return axis === "x" ? !!(spec.facet?.share_x || spec.repeat?.share_x)
    : !!(spec.facet?.share_y || spec.repeat?.share_y);
}

/** Raw overlay coordinates must have a defined meaning on the base axes. */
export function layerCoordinateLimitations(spec: FigureSpec): string[] {
  if (!spec.layers?.length) return [];
  const reasons: string[] = [];
  if (["forest", "ridgeline", "dumbbell", "paired_difference", "heatmap", "confusion_matrix", "sparkline_grid"].includes(spec.kind)
      || spec.kind === "bar" && spec.orientation === "horizontal") {
    reasons.push(`${spec.kind} does not expose a supported raw overlay coordinate system`);
  }
  if (["qq", "waterfall"].includes(spec.kind) && spec.layers.some(layer => layer.mark !== "rule")) {
    reasons.push(`${spec.kind} supports horizontal numeric-y rules, not raw x overlays`);
  }
  if (derivedAxis(spec, "y") && spec.layers.some(layer =>
    ["line", "scatter", "band"].includes(layer.mark) && !layer.y)) {
    reasons.push("an overlay on derived y needs an explicit numeric y column");
  }
  return reasons;
}

/** A refused export is safer than a different analysis under the same name. */
export function interactiveLimitations(spec: FigureSpec): string[] {
  const reasons: string[] = [];
  if (!["line", "scatter", "bar", "heatmap"].includes(spec.kind)) reasons.push(`kind ${spec.kind}`);
  if (spec.facet || spec.repeat || spec.layers?.length || spec.inset || spec.axis_break) reasons.push("composition");
  if (spec.annotate?.length || spec.reference_lines?.length) reasons.push("annotations/reference lines");
  if (spec.x.scale === "symlog" || spec.y.scale === "symlog") reasons.push("symlog scales");
  if (spec.kind === "line" && (spec.y2 || spec.smooth)) reasons.push("secondary axes/smoothing");
  if (spec.kind === "scatter" && (spec.trendline !== "none" || spec.frontier)) reasons.push("scatter analyses");
  if (spec.kind === "bar" && (spec.significance || spec.stacked)) reasons.push("significance/stacked bars");
  if (spec.kind === "heatmap" && [spec.x, spec.y].some(axis => axis.scale !== "linear" || axis.limits || axis.percent || axis.temporal)) reasons.push("matrix axis transforms");
  return reasons;
}
