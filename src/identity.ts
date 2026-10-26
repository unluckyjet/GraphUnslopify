import { derivedAxis, hasCategoricalX, type FigureSpec } from "./schema.ts";

/** Semantic names have one textual identity; measurements keep their own types. */
export function requiredIdentityFields(spec: FigureSpec): string[] {
  return [...new Set([
    ...(spec.group ? [spec.group] : []),
    ...(spec.series_from_columns ? [spec.series_from_columns.series_name] : []),
    ...(spec.facet ? [spec.facet.by, ...(spec.facet.rows ? [spec.facet.rows] : [])] : []),
    ...(hasCategoricalX(spec) || ["table", "heatmap", "confusion_matrix"].includes(spec.kind) ? [spec.x.field] : []),
    ...(["heatmap", "confusion_matrix"].includes(spec.kind) ? [spec.y.field] : []),
    ...(spec.kind === "paired_difference" ? [spec.pair] : []),
  ])];
}

export function identityFields(spec: FigureSpec): string[] {
  return [...new Set([...requiredIdentityFields(spec),
    ...("uncertainty" in spec && spec.uncertainty?.over ? [spec.uncertainty.over] : []),
  ])];
}

/** A shared source column cannot be rewritten as text and also used as a measurement. */
export function identityConflicts(spec: FigureSpec): string[] {
  const categoricalX = hasCategoricalX(spec) || ["table", "heatmap", "confusion_matrix"].includes(spec.kind);
  const categoricalY = ["heatmap", "confusion_matrix"].includes(spec.kind);
  const numeric = new Set([
    ...(!categoricalX && !derivedAxis(spec, "x") ? [spec.x.field] : []),
    ...(!categoricalY && !derivedAxis(spec, "y") ? [spec.y.field] : []),
    ...("value" in spec && spec.value ? [spec.value] : []),
    ...(spec.kind === "calibration" ? [spec.outcome] : []),
    ...(spec.kind === "kaplan_meier" ? [spec.event] : []),
    ...(spec.repeat?.fields ?? []),
    ...(spec.layers?.map(layer => layer.y) ?? []),
    ...(spec.kind === "line" && spec.y2 ? [spec.y2.field] : []),
    ...(spec.series_from_columns?.fields ?? []),
  ]);
  return identityFields(spec).filter(field => numeric.has(field));
}
