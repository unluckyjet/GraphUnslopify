# Sensitivity analysis

Compare the current statistical choices for a figure with up to four justified
alternatives. Each choice uses the same data snapshot and generates its own
strictly checked PNG and report. Compare estimates, interval bounds, unit counts,
filter counts, and verdicts for the figure's existing machine-checkable claims.

## Compare in either local workspace

Open **Sensitivity analysis** with the current draft and data in the single
editor, or with the current saved figure in the paper workspace. Give each
alternative a name and scientific justification, then select an estimator,
uncertainty method or cohort-filter change. Add up to four alternatives.
Review the baseline and proposed settings, confirm the assumptions, and render
the comparison. The workspace shows native PNGs and group-aligned estimates,
intervals, counts and claim verdicts. Automatic axis limits may differ between
previews. Use the numerical table to compare values directly.

The preview keeps the original figure and project history intact. Changes to
the selected source, definition or alternatives require another review. The
comparison report can be downloaded separately from its browser previews.
The workspace displays up to 8 MiB of verified PNG previews per comparison.
The local CLI retains the full evidence in a selected output directory.

## Run from the terminal

Provide a JSON array containing the name, justification and changes for each
alternative. This example compares a mean with the corresponding median.

```json
[
  {
    "label": "Median instead of mean",
    "justification": "A small number of extreme measurements may influence the mean.",
    "changes": { "aggregation": "median" }
  }
]
```

```sh
graphunslopify sensitivity baseline.figure.json --alternatives choices.json --out-dir sensitivity-results
```

Review the listed changes and assumptions. Run again with `--reviewed` to
generate the report and native previews. The output directory must be new.
A failed claim or incomplete check yields exit status 2 and retains the
individual reports and any verified images. The original inputs are untouched.
The results folder includes the generated programs and ordinal observation
ledgers. Reproducing it requires the original data and palette inputs. Keep the
results local if group labels, estimates, or claims are sensitive.

## Supported choices

Use an ordinary one-panel bar, line, or forest figure with a mean or median
summary. You can change the estimator, replace the filter list, or vary the
uncertainty method, confidence level, or assumed independent unit. Setting
`filter` to `null` removes the filters. Setting `uncertainty.over` to `null`
declares rows as units. These choices need a scientific justification from the
author. The same data path, grouping and encodings, palette, and claims are used
for every run. The runner creates static PNG previews at the figure's chosen
size and density.

Values are aligned by their actual group keys. Missing groups remain visible
without a numerical difference. An interval is shown using the original
renderer's method and scale. Changes in cohort or estimator can change the
meaning of the comparison. Interpret each alternative on its stated
assumptions. The report makes no joint inference or selection of a preferred
result. [Specification curve analysis](https://doi.org/10.1038/s41562-020-0912-z)
describes a broader methodology with an additional joint inference step.
