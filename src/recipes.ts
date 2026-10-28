/**
 * Starting specs for the figures that keep recurring in papers.
 *
 * Assembling a spec field by field is where an agent gets things wrong, so
 * these encode the combinations that are already known to be right. Every one
 * passes `verify` with no findings once its field names are filled in.
 */

import type { z } from "zod";
import { FigureSpec } from "./schema.ts";

export type Recipe = {
  name: string;
  purpose: string;
  /** The input side of the schema, so a recipe may leave every defaulted field out. */
  spec: z.input<typeof FigureSpec>;
};

export const RECIPES: Recipe[] = [
  {
    name: "confusion_row_normalised",
    purpose:
      "Row-normalised, so each cell reads as recall for that true class. The normalisation is required because raw counts and column-normalised make different claims.",
    spec: {
      kind: "confusion_matrix",
      x: { field: "predicted", label: "Predicted" },
      y: { field: "actual", label: "True label" },
      normalize: "row",
      data: { path: "confusion.csv" },
    },
  },
  {
    name: "ablation_waterfall",
    purpose:
      "Contributions stacked from a baseline to a total. The order is part of the claim, so category_order is required.",
    spec: {
      kind: "waterfall",
      x: { field: "component", label: "Component" },
      y: { field: "delta", label: "Change in accuracy", unit: "pp" },
      start: 74.2,
      category_order: ["+ MixUp", "+ Distill", "+ EMA", "+ Longer"],
      data: { path: "waterfall.csv" },
    },
  },
  {
    name: "head_sparklines",
    purpose: "Many short series at once on one shared scale, where free limits would make a flat series look dramatic.",
    spec: {
      kind: "sparkline_grid",
      x: { field: "step", label: "Step" },
      y: { field: "activation", label: "Activation" },
      group: "head",
      columns: 4,
      output: { size: "double_column" },
      data: { path: "heads.csv" },
    },
  },

  {
    name: "reliability_diagram",
    purpose:
      "Predicted probability against the frequency actually observed, with the expected calibration error printed per model.",
    spec: {
      kind: "calibration",
      x: { field: "confidence", label: "Predicted probability" },
      y: { field: "observed", label: "Observed frequency" },
      outcome: "correct",
      group: "model",
      bins: 12,
      data: { path: "calibration.csv" },
    },
  },
  {
    name: "normal_qq",
    purpose:
      "Check the normality assumption before making a claim that depends on it. Tails that bend away from the line are the answer.",
    spec: {
      kind: "qq",
      x: { field: "theoretical", label: "Theoretical quantile" },
      y: { field: "residual", label: "Sample quantile" },
      data: { path: "residuals.csv" },
    },
  },
  {
    name: "survival_curve",
    purpose:
      "Time to an event with censored records marked, so the curve does not look more certain than the data supports.",
    spec: {
      kind: "kaplan_meier",
      x: { field: "hours", label: "Time", unit: "h" },
      y: { field: "survival", label: "Surviving fraction" },
      event: "failed",
      group: "arm",
      data: { path: "survival.csv" },
    },
  },
  {
    name: "power_law_fit",
    purpose:
      "Loss against scale on log-log axes, with the fitted exponent and its interval printed rather than eyeballed.",
    spec: {
      kind: "scaling_fit",
      x: { field: "params_m", label: "Parameters", unit: "M", scale: "log" },
      y: { field: "loss", label: "Validation loss", scale: "log" },
      group: "family",
      data: { path: "scaling.csv" },
    },
  },

  {
    name: "ablation_forest",
    purpose:
      "One row per ablated component, each with its effect and interval, and a line at no effect. What an ablation table looks like when the intervals are kept.",
    spec: {
      kind: "forest",
      x: { field: "component", label: "Component" },
      y: { field: "delta_pp", label: "Change in accuracy", unit: "pp" },
      aggregation: "mean",
      uncertainty: { kind: "ci", level: 0.95, over: "seed" },
      data: { path: "ablation_effects.csv" },
    },
  },
  {
    name: "paired_gain",
    purpose:
      "The per-dataset differences between two conditions, which is the quantity a paired test operates on.",
    spec: {
      kind: "paired_difference",
      x: { field: "condition", label: "Condition" },
      y: { field: "accuracy", label: "Accuracy", unit: "%" },
      pair: "dataset",
      baseline: "baseline",
      data: { path: "paired.csv" },
    },
  },
  {
    name: "before_after_slope",
    purpose: "Change between two stages, read as the angle of each line rather than two bar heights.",
    spec: {
      kind: "slope",
      x: { field: "stage", label: "Stage" },
      y: { field: "score", label: "Score" },
      group: "method",
      category_order: ["before", "after"],
      data: { path: "stages.csv" },
    },
  },
  {
    name: "before_after_dumbbell",
    purpose: "The same two stages as one row per method, where the gap itself is the quantity.",
    spec: {
      kind: "dumbbell",
      x: { field: "method", label: "Method" },
      y: { field: "score", label: "Score" },
      group: "stage",
      series_order: ["before", "after"],
      data: { path: "stages.csv" },
    },
  },

  {
    name: "latency_ecdf",
    purpose:
      "Compare whole latency distributions without choosing a bin width. Every observation is on the page and the tail is readable.",
    spec: {
      kind: "ecdf",
      x: { field: "latency_ms", label: "Latency", unit: "ms" },
      y: { field: "proportion", label: "Proportion of runs" },
      group: "model",
      data: { path: "latency.csv" },
    },
  },
  {
    name: "raincloud_by_model",
    purpose:
      "The distribution, its quartiles and every raw observation together, so a claim resting on six runs cannot hide inside a smooth curve.",
    spec: {
      kind: "raincloud",
      x: { field: "model", label: "Model" },
      y: { field: "latency_ms", label: "Latency", unit: "ms" },
      data: { path: "latency.csv" },
    },
  },
  {
    name: "ridgeline_by_model",
    purpose: "One density per category down the page, for comparing many distributions at once.",
    spec: {
      kind: "ridgeline",
      x: { field: "model", label: "Model" },
      y: { field: "latency_ms", label: "Latency", unit: "ms" },
      data: { path: "latency.csv" },
    },
  },

  {
    name: "training_curve",
    purpose:
      "Accuracy or loss over epochs for several models, averaged across seeds with a confidence band.",
    spec: {
      kind: "line",
      x: { field: "epoch", label: "Training epoch" },
      y: { field: "accuracy", label: "Test accuracy", unit: "%" },
      group: "model",
      aggregation: "mean",
      uncertainty: { kind: "ci", level: 0.95, over: "seed", display: "band" },
      series_order: ["baseline", "ours"],
      emphasis: { series: "ours" },
      legend: { position: "outside_right" },
      data: { path: "results.csv" },
    },
  },
  {
    name: "ablation_bar",
    purpose: "What each component contributes, as a sorted bar chart with error bars.",
    spec: {
      kind: "bar",
      x: { field: "variant", label: "Configuration" },
      y: { field: "accuracy", label: "Top-1 accuracy", unit: "%" },
      aggregation: "mean",
      uncertainty: { kind: "sem", display: "bar" },
      sort: { by: "value", direction: "desc" },
      value_labels: true,
      data: { path: "ablation.csv" },
    },
  },
  {
    name: "benchmark_comparison",
    purpose: "One score per model across several datasets, grouped and emphasised.",
    spec: {
      kind: "bar",
      x: { field: "dataset", label: "Dataset" },
      y: { field: "accuracy", label: "Top-1 accuracy", unit: "%" },
      group: "model",
      aggregation: "mean",
      series_order: ["baseline", "ours"],
      emphasis: { series: "ours" },
      legend: { position: "outside_bottom" },
      data: { path: "benchmarks.csv" },
    },
  },
  {
    name: "pareto",
    purpose: "Accuracy against cost, with the non-dominated set drawn.",
    spec: {
      kind: "scatter",
      x: { field: "latency_ms", label: "Latency", unit: "ms" },
      y: { field: "accuracy", label: "Top-1 accuracy", unit: "%" },
      group: "model",
      frontier: { x: "min", y: "max" },
      legend: { position: "outside_bottom" },
      data: { path: "benchmarks.csv" },
    },
  },
  {
    name: "seed_distribution",
    purpose: "How much run-to-run variance each model has, as a box per model.",
    spec: {
      kind: "box",
      x: { field: "model", label: "Model" },
      y: { field: "accuracy", label: "Final accuracy", unit: "%" },
      show_points: true,
      sort: { by: "value", direction: "desc" },
      data: { path: "results.csv" },
    },
  },
  {
    name: "confusion_matrix",
    purpose: "Predicted against true labels as a heatmap with the counts printed.",
    spec: {
      kind: "heatmap",
      x: { field: "predicted", label: "Predicted label" },
      y: { field: "actual", label: "True label" },
      value: "count",
      value_label: "Examples",
      aggregation: "sum",
      annotate_cells: true,
      data: { path: "confusion.csv" },
    },
  },
  {
    name: "hyperparameter_grid",
    purpose: "A sweep over two hyperparameters as a heatmap of the resulting score.",
    spec: {
      kind: "heatmap",
      x: { field: "learning_rate", label: "Learning rate" },
      y: { field: "batch_size", label: "Batch size" },
      value: "accuracy",
      value_label: "Validation accuracy (%)",
      aggregation: "mean",
      annotate_cells: true,
      data: { path: "sweep.csv" },
    },
  },
  {
    name: "faceted_curves",
    purpose: "One training curve panel per dataset, sharing axes so the panels compare.",
    spec: {
      kind: "line",
      x: { field: "epoch", label: "Training epoch" },
      y: { field: "accuracy", label: "Test accuracy", unit: "%" },
      group: "model",
      facet: { by: "dataset", columns: 3, share_y: true, panel_letters: true },
      aggregation: "mean",
      uncertainty: { kind: "sem", display: "band" },
      output: { size: "double_column" },
      data: { path: "results.csv" },
    },
  },
  {
    name: "delta_vs_baseline",
    purpose: "How far each method moves the needle, as a signed change against the baseline.",
    spec: {
      kind: "bar",
      x: { field: "dataset", label: "Dataset" },
      y: { field: "accuracy", label: "Change in accuracy", unit: "pp" },
      group: "model",
      transform: { kind: "delta_vs_baseline", baseline: "baseline" },
      aggregation: "mean",
      baseline_zero: false,
      reference_lines: [{ axis: "y", value: 0, meaning: "baseline", label: "no change" }],
      data: { path: "results.csv" },
    },
  },
  {
    name: "scaling_law",
    purpose: "Loss against parameters on log-log axes, which is where a power law looks straight.",
    spec: {
      kind: "scatter",
      x: { field: "params_m", label: "Parameters", unit: "M", scale: "log" },
      y: { field: "loss", label: "Test loss", scale: "log" },
      group: "family",
      data: { path: "scaling.csv" },
    },
  },
  {
    name: "animated_curve",
    purpose: "A training curve that draws itself, for a talk or a project page.",
    spec: {
      kind: "line",
      x: { field: "epoch", label: "Training epoch" },
      y: { field: "accuracy", label: "Test accuracy", unit: "%" },
      group: "model",
      aggregation: "mean",
      series_order: ["baseline", "ours"],
      emphasis: { series: "ours" },
      animate: { style: "draw", duration_s: 5, easing: "smooth", stagger_s: 0.4, format: "gif" },
      output: { size: "double_column", formats: ["png"], stem: "animated" },
      data: { path: "results.csv" },
    },
  },
];

export function recipeNames(): string[] {
  return RECIPES.map((r) => r.name);
}

export function findRecipe(name: string): Recipe | undefined {
  return RECIPES.find((r) => r.name === name);
}
