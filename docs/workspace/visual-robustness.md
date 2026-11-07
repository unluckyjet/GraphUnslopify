# Visualization robustness tests

Compare a baseline with up to four justified display alternatives. For example,
check whether a logarithmic scale compresses separation between visible points,
a narrower axis range hides them, or a different bin count changes a calibration
diagram's apparent error. Every run uses the same source data, filters,
estimators, palette, and authored claim definitions.

## Compare in the local workspaces

Open **Visualization robustness tests** with a figure and dataset in the
single editor or a current saved figure in the paper workspace. Name each
alternative, give its display justification, and choose the settings to
vary. Set a materiality threshold when changing axes or calibration bins.
Review the baseline and alternatives, then confirm and render. Compare the
actual native PNGs, quantified display changes, and any strict findings.
Download the report to keep the comparison. The terminal workflow retains
the generated programs, observations, and full native evidence.

## Run from the terminal

Save a plan such as `display-plan.json` for a line or scatter figure.

```json
{
  "alternatives": [
    {
      "label": "Log response",
      "justification": "A log scale makes proportional changes easier to compare.",
      "changes": { "y.scale": "log" }
    },
    {
      "label": "Focus on the observed operating range",
      "justification": "Check which points remain visible at the intended viewing limits.",
      "changes": { "y.limits": [1, 100], "style.grid": true }
    }
  ],
  "thresholds": { "axis_fraction": 0.15 }
}
```

```sh
graphunslopify robustness baseline.figure.json --plan display-plan.json --out-dir display-results
graphunslopify robustness baseline.figure.json --plan display-plan.json --out-dir display-results --reviewed
```

The first invocation lists the choices for review. The second strictly renders
each choice to PNG in a new output directory. It preserves the original inputs
and writes `robustness.json`, generated programs, native verification reports,
and per-figure visual observations. The visual observations bind the measured
geometry to the SHA-256 of each PNG and its generated program. They include
plotted coordinates and group labels, so treat them as research data when sharing.

## Read the measurements

- **Axes.** For matched data centers, measure the largest horizontal or vertical
  movement as a fraction of the relevant axis. A threshold of `0.15` means
  fifteen percent of the width or height. The report also counts centers
  that enter or leave the axes and identifies nonpositive values on log scales.
  Center counts describe plotted positions. Line segments and overlapping marks
  require separate visual review.
- **Calibration.** Compare bin membership counts, mean probabilities, observed
  outcome fractions, and the signed change in expected calibration error (ECE).
  Set `ece_delta` to the smallest absolute change that merits review. A value of
  `0.025` means 2.5 percentage points. ECE changes describe the effect of binning
  on these predictions and outcomes.
- **Display.** Compare the visible legend labels and legend bounds, grid, line
  markers, and counts of interval bands and error bars. Use the PNGs to judge
  readability. An alternative that removes all baseline legend labels is flagged.
- **Claims.** Compare the recorded native verdicts for the existing claims.
  A changed verdict, a threshold reached, or changed center visibility calls for
  review. The researcher decides what the change means for the manuscript.

The CLI returns `0` for a checked report and `2` when review is required or
when evidence is partial. A partial comparison retains any verified preview
and records the reason a render or observation could not be completed.

## Supported choices

Use a single line, scatter, or calibration panel with an ordinary box legend
when a legend is needed. Line and scatter support `x.scale` and `y.scale`
(`linear`, `log`, `symlog`) and `x.limits` and `y.limits` (two increasing values,
or `null` for automatic limits). These changes require `axis_fraction`.
Calibration uses fixed probability axes and supports `bins` from 3 through 50
with an `ece_delta` threshold. Both thresholds accept values above 0 through 1.

All three accept `style.grid`, `legend.show`, and `legend.position` (`best`,
`upper_left`, `upper_right`, `lower_left`, `lower_right`, `outside_right`,
`outside_bottom`). Lines also accept `marker` and can switch between `band`
and `bar` via `uncertainty.display` when uncertainty is already declared.
Facets, layered figures, axis breaks, insets, smoothing, secondary axes,
frontiers, repeated panels, and animation require separate workflows.
