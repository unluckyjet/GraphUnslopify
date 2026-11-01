/** Column identities for portable intent. This reads no observations and changes no validator rules. */
import { FigureSpec, derivedAxis } from "./schema.ts";
import { z } from "zod";

type Path = (string | number)[];
export type TemplateField = { path: Path; field: string };

export function templateFields(input: unknown): TemplateField[] {
  const spec = FigureSpec.parse(input);
  const virtual = new Set(spec.series_from_columns ? [spec.series_from_columns.series_name, spec.series_from_columns.value_name] : []);
  const refs: TemplateField[] = [];
  const add = (path: Path, value: unknown, raw = false) => {
    if (typeof value === "string" && (raw || !virtual.has(value))) refs.push({path, field:value});
  };
  function walk(value: unknown, path: Path = []) {
    if (Array.isArray(value)) { value.forEach((v,i) => walk(v,[...path,i]));return; }
    if (!value || typeof value !== "object") return;
    for (const [key, child] of Object.entries(value)) {
      const next = [...path,key];
      if (key === "field" && !(path.length === 1 && (path[0] === "x" || path[0] === "y") && derivedAxis(spec,path[0]))) add(next,child,path[0] === "filter");
      walk(child,next);
    }
  }
  walk(spec);
  const at = (path: string[]) => path.reduce<unknown>((v,k) => v && typeof v === "object" ? (v as Record<string,unknown>)[k] : undefined,spec);
  for (const path of [["group"],["facet","by"],["facet","rows"],["pair"],["outcome"],["event"],["value"],["uncertainty","over"],["significance","pair_by"]]) add(path,at(path));
  spec.repeat?.fields.forEach((v,i) => add(["repeat","fields",i],v));
  spec.series_from_columns?.fields.forEach((v,i) => add(["series_from_columns","fields",i],v,true));
  spec.layers?.forEach((v,i) => { add(["layers",i,"y"],v.y);add(["layers",i,"y2"],v.y2); });
  return refs;
}

export function remapTemplateFields(input: unknown, mapping: unknown): unknown {
  const spec = FigureSpec.parse(input), refs = templateFields(spec);
  if (!mapping || typeof mapping !== "object" || Array.isArray(mapping)) throw Error("Field mapping must be an object.");
  // Parsing an entire record can silently discard __proto__. Columns are
  // ordinary strings, including that name; validate values and retain all keys.
  const map = new Map(Object.entries(mapping).map(([key,value]) => [key,z.string().min(1).parse(value)])), known = new Set(refs.map(r => r.field));
  for (const key of map.keys()) if (!known.has(key)) throw Error(`Template has no source field named ${JSON.stringify(key)}.`);
  const result = structuredClone(spec) as unknown as Record<string,unknown>;
  for (const ref of refs) {
    if (!map.has(ref.field)) continue;
    let target: any = result;
    for (const key of ref.path.slice(0,-1)) target = target[key];
    target[ref.path.at(-1)!] = map.get(ref.field)!;
  }
  // Wide columns also create series identities. Keep their logical references
  // attached when their source column is remapped, never rename ordinary values.
  const wide = new Set(spec.series_from_columns?.fields || []);
  const identity = (s:string) => wide.has(s) ? map.get(s) || s : s;
  const remapped = result as any;
  if (wide.size) {
    if (spec.series_order) remapped.series_order = spec.series_order.map(identity);
    if (spec.emphasis) remapped.emphasis.series = identity(spec.emphasis.series);
    if (spec.transform?.baseline) remapped.transform.baseline = identity(spec.transform.baseline);
    for (const row of remapped.legend.labels || []) row.series = identity(row.series);
    for (const row of remapped.annotate || []) if (row.series) row.series = identity(row.series);
    for (const row of remapped.claims || []) for (const key of ["subject","reference"]) if (row[key]) row[key] = identity(row[key]);
  }
  return FigureSpec.parse(result);
}
