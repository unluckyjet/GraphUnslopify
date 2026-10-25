import type { FigureSpec } from "./schema.ts";

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
