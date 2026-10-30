# GraphUnslopify

**Turn experiment results into clear figures, with repeatable code and checks against your stated claims.**

GraphUnslopify reads structured figure instructions and generates reviewable Python/matplotlib
code. Run that code against your data to produce figures, computed descriptions and a verification
report. Use it through a local browser editor, Python, notebooks, the command line or an AI assistant.

**21 figure kinds · 25 recipes · 10 claim types · Local rendering · PNG / SVG / PDF**

[Get started](#get-started) · [Who it helps](#who-it-helps) · [Capabilities](#what-it-can-do) ·
[Figure types](#choose-a-figure) · [Gallery](#figure-gallery) ·
[Integrations](#integrations-and-automation) · [Documentation](#documentation)


![Four training curves with confidence bands, two reference lines and two annotations](docs/fourth-pass-showcase.png)


*Synthetic experiment results: several methods, uncertainty bands, reference lines and
annotations in one figure. The instructions describe the comparison; the generator owns styling.*

## Why use it?

A research figure connects several things: the observations, the calculation, the picture and the
statement you make about it. GraphUnslopify keeps those parts together in a repeatable workflow.

- **Build once, rerun with new results.** Save the data path and figure instructions rather than
  manually recreating a chart after every experiment.
- **Show variation and sample counts.** Summarize declared repeat units and disclose missing data
  or unavailable estimates instead of manufacturing certainty.
- **Check specific statements.** Test a claim such as “ours is above the baseline at every x”
  against the same summaries the figure displays.
- **Review the actual output.** Inspect rendered labels, contrast, clipped marks and panel
  consistency, then retain the program, figures and report for review.

```text
Data + figure instructions → generated Python → figures + descriptions + verification report
```

## Who it helps

| Who | Situation | How they use it |
| --- | --- | --- |
| ML researchers | Compare models across datasets, seeds and compute budgets. | Generate curves, uncertainty tables and diagnostic plots; check explicit comparisons. |
| PhD students and paper authors | Revise many related figures as results change. | Regenerate the collection, retain consistent series identities and review changed claims. |
| Research teams and lab leads | Collaborators use different plotting scripts and conventions. | Share recipes and palette locks, and inspect one aggregate audit. |
| Engineers running experiments | Compare configurations over repeated test runs. | Declare run IDs, summarize variation and compare results with a baseline. |
| Open-source benchmark maintainers | A release changes execution time or memory use. | Regenerate benchmark figures and retain change reports in GitHub Actions. |
| Research software developers | Results already come from an automated pipeline. | Add strict figure generation and verification as a pipeline stage. |
| Teachers and students | Explore how presentation and uncertainty affect interpretation. | Use notebooks, recipes and inspectable Python to compare supported designs. |
| Technical reviewers with source files | Check whether revised figures still match supplied results. | Rerun a manifest and inspect data, claim and output changes. |

For example, a paper author can add a new baseline, regenerate every affected figure and inspect
which claims still hold. A benchmark maintainer can review changed measurements and images before
accepting a performance update.

## Get started

### Install and try the demo

In a **Python 3.10+ virtual environment**, install the fixed 0.8.0 release:

```sh
python -m pip install graphunslopify==0.8.0
graphunslopify doctor
graphunslopify demo
```

The demo creates public synthetic data, a figure spec, generated Python, PNG/SVG/PDF exports and
a strict verification report in `graphunslopify-demo/`. `doctor` checks package/compiler agreement.
The package supplies its translator and Node runtime; translation and local-file rendering work
**offline after dependencies are installed**. A source checkout can use `python -m pip install ./python`.

Follow the [five-minute first-figure tour](docs/getting-started.md) for environment setup,
a complete editable example, reading evidence, and correcting a failed check.

### Use the local editor

```sh
graphunslopify preview --open
```

Select a CSV, regular JSON table or supported Parquet file; choose a kind or recipe; edit the
settings; and review live previews, diagnostics and claim verdicts. Some findings offer a proposed
fix you can inspect and apply.

Current source after 0.8.0 adds form controls for labels, units, uncertainty, claims,
exports and chart-specific fields across all 21 kinds. Advanced JSON remains available
for compound options, with control undo and preservation of unrelated settings.

Download individual outputs or a ZIP containing figures, the effective spec, generated Python and
runtime report. **Source data is excluded from the ZIP unless you explicitly include it.**
Uploads and previews are temporary, so save wanted outputs before stopping the editor.
See the [complete editor workflow](docs/local-editor.md).

Current source also supports [clicking chart text, reviewing wording and applying verified edits](docs/workspace/direct-text-editing.md), with keyboard selection and undo. Series names retain original source/claim IDs. Metric and facet labels keep their original source identities and automatic panel letters. [Measured heading layout](docs/workspace/heading-layout.md) wraps complete plot wording and makes room vertically while retaining fonts, units and observations.

Use [clickable diagnostic highlights](docs/workspace/clickable-diagnostics.md) to locate measured
collisions, small text or clipped bars/intervals and read their guidance. Unknown locations stay
explicit. Selecting a region leaves the figure unchanged; offered fixes rerun strict verification
and support undo, including with live preview off.

For optional [model-backed drafts](docs/workspace/model-drafts.md), configure a provider,
review exactly which metadata and authored intent will be sent, then explicitly
request and review a proposal. Applying it reruns strict checks and supports undo.
Raw observations are not automatically sent; manual authoring works offline.
These source features are newer than the published 0.8.0 package.

### Render your own spec

```sh
graphunslopify describe results.csv
graphunslopify render path/to/figure.json --out-dir figures --strict --json
```

`describe` profiles the file to help choose fields and a starting design. Review inferred roles
and units against your experiment. Relative data paths in a JSON spec resolve beside that spec.
Current development source defaults to strict verification; `--strict` remains accepted.
Version 0.8.0 enables strict verification by default. Older 0.7.0 installations require `--strict`.
Warnings remain visible, and `--fail-on-warning` rejects those too.
Current source adds [actionable explanations](docs/diagnostics.md): each owned finding
explains its scientific consequence and recommended correction in reports, the CLI
and both local browser views. Use `graphunslopify explain CODE` to look one up.
This addition requires a source installation after0.8.0.

See [installation and optional extras](docs/installation.md), [versioned documentation](docs/versioning.md)
and the [0.8.0 release notes](docs/releases/0.8.0.md).

## What it can do

### Prepare data and suggest designs

Read CSV, regular JSON tables or Parquet with its optional reader. Filter rows, establish groups,
sort categories, reshape separate measurement columns into series, and calculate supported means,
medians, sums or counts. Supported axes include dates, percentages, linear/log/symlog scales and
baseline-relative transforms.

The recipe catalogue provides twenty-five known-good specs as starting points. A profile-based
ranker suggests candidates and explains their design costs. Suggestions and inferred units are
starting points to review; a high design score does not validate an experiment.

### Keep uncertainty attached to the estimate

Show standard deviation, standard error, bootstrap confidence intervals, interquartile ranges or
full ranges where supported. Declare independent-unit IDs such as `seed`: repeated rows within
one unit and plotted point are summarized first, so one heavily measured run does not gain extra
weight. Without a unit ID, rows are assumed independent.

Reports disclose rows read, filtering, finite measurements and effective sample counts. Missing
intervals stay unavailable. Estimator-specific restrictions prevent choices such as mean SEM
around a median. Tables show the same intervals and use uncertainty-aware highlighting; overlapping
intervals do not establish equivalence.

Supported significance comparisons include independent-sample permutation tests, Welch's t-test
and Mann–Whitney. Holm correction is the default for multiple pairs; Benjamini–Hochberg and an
explicit unadjusted option are also available. The historical significance method name `bootstrap`
means a permutation test; it is separate from bootstrap confidence intervals.

Current source also supports [explicit paired comparisons](docs/comparison-design.md),
with matched unit IDs, assumption disclosures and correction over the planned family.
These additions require a source installation; the immutable PyPI 0.8.0 release
provides the independent comparisons above.

[Declared units and data identity](docs/data-identities.md) ·
[Estimator contracts](docs/uncertainty-estimators.md) · [Table context](docs/table-context.md)

### Test explicit claims

Attach the statement your figure is intended to support:

```json
{
  "claims": [
    { "kind": "beats_everywhere", "subject": "ours", "reference": "base" }
  ]
}
```

The ten claim types check numeric relationships: above a reference everywhere, on average or at
the endpoint; a widening or narrowing gap; never increasing or decreasing; convergence; no worse
than a reference within tolerance; or staying within a tolerance.

Claims use the displayed summaries and declared units, separately for each panel and repeated
metric. A failed claim stays failed; missing coverage or an untestable trend stays untested.
“Above” is a numeric comparison—you decide whether a larger value is desirable. A held claim is
not automatically statistically significant, causal or scientifically important.

| Runtime report | Meaning |
| --- | --- |
| `passed` | Implemented required checks completed without an error or failed claim. |
| `failed` | A check, claim or rendering operation failed. |
| `incomplete` | A required check, estimate, inspection or requested output was unavailable. |

Current source rejects failed or incomplete required verification by default. Explicit
`--no-strict` / `Figure.render(strict=False)` retains legacy exit behavior without changing
report verdicts. Warning rejection always implies strict policy. Regenerate older scripts to
use the new opt-out flag; released 0.7.0 still needs explicit strict mode.
See [runtime reports](docs/runtime-reports.md).

### Compose figures and preserve visual identity

Split data into panels, use a two-field grid, or repeat supported numeric metrics. Supported
combinations can add points, lines, rugs, bands, reference rules, annotations and zoomed insets.
Shared axes preserve category positions even when a panel has no observations for a category.
Unsupported options fail explicitly rather than silently becoming a different chart.

Series appearance and legends stay consistent across panels. A shared `palette_lock` extends that
identity across separate figures: adding another model does not recolour the existing ones.
Direct labels can name lines at their endpoints instead of using a legend box.


| | |
| --- | --- |
| ![The same four curves labelled at the end of each line instead of in a legend](docs/fourth-pass-direct-labels.png) | ![Three panels, one per benchmark, sharing a y axis with one legend](docs/fourth-pass-facets.png) |
| Names placed beside their series. | One panel per benchmark. |
| ![Two curves, baseline blue and ours orange](docs/lock-figure-1.png) | ![Three curves with baseline still blue and ours still orange](docs/lock-figure-2.png) |
| An initial figure with two series. | The same identities after adding a third series. |


<details>
<summary>More composition examples: overlays, repeated metrics, insets and an explicit axis cut</summary>

These are separate examples, not a promise that every option can be combined. Axis cuts have
restricted support and are refused on length-based marks such as ordinary bars.


| | |
| --- | --- |
| ![Curves with individual observations and a rug of tick marks underneath](docs/fifth-pass-layers.png) | ![Three panels, one per metric, each with its own y label](docs/fifth-pass-repeat.png) |
| Observations and a rug over the main plot. | One panel per measurement. |
| ![The same curves with a magnified corner and its source region marked](docs/fifth-pass-inset.png) | ![A y axis with 30 to 60 cut out and slanted marks at the join](docs/fifth-pass-axis-break.png) |
| A magnified region with its source marked. | A supported, explicitly marked y-axis cut. |


See [composition contracts](docs/composition.md) for supported coordinates and combinations.

</details>

### Inspect readability and accessibility

The renderer checks actual text placement, legend/data collisions, exported text size, clipped
bar bodies and intervals, panel consistency and series identity. Colour checks cover simulated
colour-vision deficiencies, greyscale separation and text contrast against actual matrix cells.
Single/double-column sizes and venue presets help target the intended manuscript width.

Current source adds [data-view and selection checks](docs/data-visibility.md):
nonpositive log coordinates are errors, cropped coordinates receive review warnings,
and filter exclusions and explicit view limits are disclosed. These additions require
a source installation after 0.8.0; they do not infer whether an omission was deliberate.

[Annotation anchors](docs/annotations.md) also follow the actual displayed summaries
and coordinates. Missing, ambiguous or off-view targets cannot silently pass strict
verification; authored annotation text remains unverified. These additions require
the current source installation.


| | |
| --- | --- |
| ![Grouped horizontal bar chart of favourite ice cream flavours, split by age group](docs/first-pass.png) | ![The same chart with the Adults series hatched](docs/second-pass.png) |
| Historical colour-only presentation. | Added hatching distinguishes the series. |
| ![First pass in greyscale, both series the same grey](docs/first-pass-greyscale.png) | ![Second pass in greyscale, one series hatched](docs/second-pass-greyscale.png) |
| The earlier series merge in greyscale. | The secondary channel survives a black-and-white print. |


Descriptions are computed from the spec and actual data, including supported counts and claim
caveats. Add context the measurements cannot supply; the tool does not invent why a result matters.
SVG includes native title/description elements. PDF descriptions are metadata, not a complete
tagged-document accessibility structure.

[Exported text size](docs/export-legibility.md) · [Cell contrast](docs/cell-contrast.md) ·
[Signed bars and clipping](docs/signed-bars.md) · [Literal text exports](docs/text-exports.md)

### Export, reproduce and trace a figure

| Output | Useful for |
| --- | --- |
| PNG | Images for slides, reports and ordinary sharing. |
| SVG / PDF | Scalable figures and manuscript workflows; PDF exports embed TrueType fonts. |
| Markdown / LaTeX tables | Exact values and intervals in documentation and manuscripts. |
| LaTeX figure blocks | Figure inclusion, captions and descriptions at the selected column width. |
| Self-contained HTML | Hover, zoom and series toggles for supported line/scatter/bar/heatmap specs. |
| GIF / MP4 | Supported animated presentations; MP4 additionally needs FFmpeg. |

Interactive HTML embeds Plotly for offline viewing. Its supported analyses/layouts are narrower
than static output; complex compositions and some options are explicitly refused.
Optional `[interactive]`, `[parquet]` and `[statistics]` dependencies enable their corresponding
backends, readers and statistical methods. See [installation](docs/installation.md).

PNG, SVG, PDF and supported HTML carry recoverable provenance: the parsed spec, tool version,
computed description and data/source fingerprints. Current source also records
[dependency, font, rendering and execution context](docs/environment.md), shared with the
runtime report. This addition requires a source installation after0.8.0. Read it without running the original program:

```sh
graphunslopify provenance figure.svg
```

The generated Python is inspectable and can be saved with the data and spec. Matching metadata is
not authentication; reproducing a figure still requires its inputs and a suitable environment.
See [provenance](docs/provenance.md) and [interactive export boundaries](docs/interactive-exports.md).

## Choose a figure

Twenty-one kinds cover trends, distributions, comparisons, diagnostics, matrices and exact tables.

| Kind | A question it helps answer |
| --- | --- |
| `line` | How does a measurement change across time or another ordered quantity? |
| `scatter` | How do two numeric measurements relate? Optional fits/frontiers support specific analyses. |
| `bar` | How do categories compare? Supported configurations include horizontal, grouped and stacked bars. |
| `box` | What are the middle, spread and unusual values in each group? |
| `violin` | Where are observations concentrated within a distribution? |
| `ecdf` | What fraction of observations falls below a chosen value? |
| `raincloud` | How do raw observations, distribution and summary look together? |
| `ridgeline` | How do several distributions differ? |
| `forest` | How do estimates and their intervals compare on one scale? |
| `paired_difference` | How much did matched observations change between two conditions? |
| `slope` | How do groups change across ordered conditions? |
| `dumbbell` | What is the gap between two groups in each category? |
| `calibration` | Do predicted probabilities agree with observed outcomes? |
| `qq` | How do sample quantiles compare with a supported reference distribution? |
| `kaplan_meier` | How does time-to-event behaviour evolve when some outcomes are censored? |
| `scaling_fit` | How does a measurement scale as another quantity grows? |
| `confusion_matrix` | Which classes are predicted correctly and which are confused? |
| `waterfall` | How do ordered contributions build up to a final total? |
| `sparkline_grid` | How do many small trends compare using consistent scales? |
| `heatmap` | Where are patterns or large/small values in a matrix? |
| `table` | What are the exact reported values, bounds and comparison highlights? |


![Synthetic accuracy table with visible title units row heading and uncertainty-aware bold candidates](docs/fifth-pass-table.png)


*A synthetic table with visible title, row/column context, units and intervals. The same spec
produces image, Markdown and LaTeX outputs.*

## Figure gallery

These existing illustrations use synthetic data. The committed regression gallery is regenerated
from local source; historical illustrations and before/after examples show the design choices.
Source specs and data are available in [examples](examples/README.md), including
[owned reference inputs](examples/references/README.md).

### Everyday comparisons and distributions


| | |
| --- | --- |
| ![Heatmap of cafe customers by weekday and hour](docs/third-pass-heatmap.png) | ![Box plot of order wait times by store with a target line](docs/third-pass-box.png) |
| Heatmap: patterns across weekday and hour. | Box plot: wait-time spread and a target. |
| ![Scatter of menu price against rating with a Pareto frontier](docs/third-pass-pareto.png) | ![Stacked bars of drink units sold by store](docs/third-pass-stacked.png) |
| Scatter: trade-offs and a Pareto frontier. | Stacked bars: category contributions. |
| ![Violin plot of the same wait times, showing the full distribution](docs/third-pass-violin.png) | ![Animated training curve drawing itself](docs/animated-curve.gif) |
| Violin: the distribution behind the summary. | Animation: the curve draws over time. |


### Distributions, estimates and changes


| | |
| --- | --- |
| ![Empirical cumulative distributions of latency for three models](docs/seventh-pass-ecdf.png) | ![Raincloud plot with the violin, quartile box and every raw point](docs/seventh-pass-raincloud.png) |
| ECDF: proportions below each threshold. | Raincloud: raw points, summary and distribution. |
| ![Ridgeline plot, one latency density per model](docs/seventh-pass-ridgeline.png) | ![Forest plot of four ablation components with confidence intervals](docs/seventh-pass-forest.png) |
| Ridgeline: distributions across groups. | Forest: estimates and their intervals. |
| ![Paired differences between two conditions with a bootstrap interval](docs/seventh-pass-paired-difference.png) | ![Slope chart of four methods before and after](docs/seventh-pass-slope.png) |
| Paired differences: matched-unit changes. | Slope: movement between conditions. |
| ![Dumbbell chart, before and after per method on one scale](docs/seventh-pass-dumbbell.png) | ![Reliability diagram comparing two models against the diagonal](docs/seventh-pass-calibration.png) |
| Dumbbell: two values on one scale. | Calibration: predicted versus observed probabilities. |


### Diagnostics, contributions and many series


| | |
| --- | --- |
| ![Q-Q plot with a gaussian and a heavy-tailed sample](docs/seventh-pass-qq.png) | ![Kaplan-Meier curves for two arms with censoring marks](docs/seventh-pass-kaplan-meier.png) |
| Q–Q: compare sample and reference quantiles. | Kaplan–Meier: events and censored observations. |
| ![Scaling plot on log-log axes with fitted power laws](docs/seventh-pass-scaling-fit.png) | ![Row-normalised confusion matrix over four classes](docs/seventh-pass-confusion.png) |
| Scaling fit: a power-law relationship. | Confusion matrix: class-level errors. |
| ![Waterfall chart of four ablation contributions from a baseline](docs/seventh-pass-waterfall.png) | ![Grid of twelve sparklines on one shared scale](docs/seventh-pass-sparklines.png) |
| Waterfall: ordered contributions and a total. | Sparkline grid: many comparable trends. |


<details>
<summary>Open the full 15-example regression gallery</summary>

All fifteen examples pass the strict gallery gate at the reviewed release. Their current
source specs, synthetic data and generated programs live together in [examples](examples/README.md).
The image captions identify the examples; complete computed descriptions are embedded in exports.


| | |
| --- | --- |
| ![Line chart of test accuracy against training epoch, one series per model, ours in the foreground reaching 81.1 against baseline at 70](examples/baseline/01-training-curve.png) | ![The same four models on a logarithmic loss axis, ending between 0.281 and 0.302](examples/baseline/02-loss-log.png) |
| `01` Training curves and series emphasis. | `02` Logarithmic loss and median aggregation. |
| ![One filtered training run of ours with no legend](examples/baseline/03-single-run.png) | ![Grouped bars of top-1 accuracy per dataset, ours highest at 51.2 and baseline lowest at 43.8](examples/baseline/04-accuracy-by-dataset.png) |
| `03` A filtered single run. | `04` Grouped category comparisons. |
| ![Horizontal bars of median latency by model](examples/baseline/05-latency-ranking.png) | ![Scatter of accuracy against latency, one marker shape per model, legend outside the data](examples/baseline/06-accuracy-vs-latency.png) |
| `05` Sorted horizontal bars. | `06` A two-measurement trade-off. |
| ![Ungrouped scatter of accuracy against parameter count with a linear fit](examples/baseline/07-params-trendline.png) | ![The four training curves at double column width in the compact preset](examples/baseline/08-compact-double-column.png) |
| `07` Scatter with a fitted trend. | `08` A compact double-column layout. |
| ![Four training curves with shaded 95 percent confidence intervals and a chance line at 25](examples/baseline/09-uncertainty-band.png) | ![Three panels of accuracy bars, one per dataset, sharing a y axis with readable category names](examples/baseline/10-faceted-benchmarks.png) |
| `09` Intervals and a reference line. | `10` One panel per dataset. |
| ![Box plot of accuracy across epochs per model, values from 65.3 to 82](examples/baseline/11-seed-spread.png) | ![Heatmap of validation accuracy over learning rate and batch size, largest 82.4 at 0.001 and 32](examples/baseline/12-sweep-heatmap.png) |
| `11` The distribution behind the summary. | `12` A parameter sweep with cell values. |
| ![The four curves labelled at the end of each line with no legend box](examples/baseline/13-direct-labels.png) | ![The same training curves drawing themselves as an animation](examples/baseline/14-animated-curve.gif) |
| `13` Endpoint labels instead of a legend. | `14` An animated export. |
| ![Simulated share price over one trading year with its centered 20-observation rolling mean, dates along the x axis](examples/baseline/15-price-and-average.png) |  |
| `15` Dates and a rolling average. |  |


</details>

## Integrations and automation

### Python and notebooks

Use the same compiler from Python. After running the demo above, this example uses its actual
column names and generates another strict-checked figure:

```python
from graphunslopify import Figure

result = (
    Figure.line("graphunslopify-demo/results.csv")
    .x("epoch", "Epoch")
    .y("score", "Score")
    .by("model", order=["base", "ours"], emphasise="ours")
    .average_over("seed")
    .claim("beats_everywhere", "ours", "base")
    .set(legend={"position": "outside_bottom"})
    .render(cwd="figures", strict=True, api="local")
)
```

All canonical kinds have Python constructors. `Figure.from_profile` can start from a ranked
candidate that you then review. The package also includes an executable notebook example with
synthetic data, real figure outputs and an expected false-claim rejection.
See [Python usage](python/README.md) and [notebook setup](docs/notebooks.md).

### AI assistants, MCP and HTTP

The local MCP integration exposes the canonical schema, recipes, suggestions, validation,
design scoring, offered repairs and Python generation. The tools are `get_figure_schema`,
`list_recipes`, `suggest_figures`, `validate_spec`, `score_spec`, `apply_fixes` and
`figure_to_matplotlib`. Offered fixes are bounded patches; some findings require an author edit.
Code being returned does not override an error finding.

The agent compiler does not open datasets or run generated programs. Run the resulting program
locally to evaluate actual data-dependent claims and rendered checks. Local translation is the
default; optional HTTP translation receives the supplied spec/profile. What an external AI host
sends to its model is controlled by that host, so review what you share.

[Local agent setup](docs/agents.md) ·
[Project homepage](https://unluckyjet.github.io/GraphUnslopify/) ·
[Hosted translator API](https://json-translator-three.vercel.app/api/health) ·
[HTTP MCP endpoint](https://json-translator-three.vercel.app/api/mcp)

### Connect your research workspace

Current source after0.8.0 can turn a paper manifest into a [research workspace](docs/research-workflows.md):
a project notebook for JupyterLab/VS Code, editor tasks using the selected Python interpreter,
and LaTeX preparation that includes accepted exports at their checked manuscript width.
Failed checks retain reports/previews and invalidate the generated manuscript include.
The optional [MLflow integration](docs/experiment-tracking.md) logs saved reports,
verified figures and acceptance to your chosen experiment or training run.
Source also adds [persistent paper projects](docs/project-management.md): shared
figure settings, per-figure input freshness and retained audit/settings history.
After `graphunslopify project-init paper/`, run `graphunslopify project-preview paper/ --open` to edit
definitions/bindings, apply shared settings, audit the paper and review saved runs.

```sh
graphunslopify workflow-init paper/
python paper/graphunslopify-workflow/run.py --latex
```

### Audit a paper's figures together

A manifest connects figure specs or compatible generated programs to local data, explicit claims
and optional published artifacts. The audit regenerates entries, runs strict checks and produces
one Markdown summary plus a machine-readable report, continuing after individual failures.

Try it on the demo:

```sh
graphunslopify audit-init graphunslopify-demo
graphunslopify audit graphunslopify-demo --out-dir audit-output
```

Compare with an earlier audit to identify added/removed figures and changed data, numeric inputs,
specs, descriptions, claims and outputs. PNG comparison separates file bytes from visible pixels:
metadata can change while the picture stays identical. Current source after0.8.0 also creates
[visual comparison reports](docs/figure-comparison.md): saved PNG/SVG/PDF previews, pixel
difference maps where comparable, blend controls and explanations of changed evidence.
Compare saved runs with `graphunslopify compare before.json after.json --out-dir comparison`.
Missing images and unknown pixel comparisons remain explicit; validation failures stay visible.

This supports source-linked figure review. Current development also provides
[PDF review packets](docs/pdf-review.md) with page previews, text, manually selected crops,
and source-only checks for small physical text and low-resolution embedded images
for ordinary manuscripts; unavailable numerical/source checks stay untested. It does not
interpret arbitrary paper claims or reconstruct their datasets.
See [paper manifests and change reports](docs/paper-audits.md).

### Run figure checks in GitHub Actions

The reusable composite action can regenerate the manifest on pushes or pull requests, enforce
strict policy and upload reviewable figures, programs, logs and reports—even after audit failure.
Optional policies can reject warnings or recorded changes against a saved baseline.

It stages the current audit's owned evidence rather than uploading unrelated files or source data.
A reviewer still decides whether a change is intended; the action does not approve revisions.
See [reusable Figure CI](docs/figure-ci.md) for a consumer workflow and version-pinned action.

## Verification, evidence and limits

Eighty-six rules run on the server against the spec alone; the packaged local compiler uses the
same verifier. This count follows distinct static finding codes, not every runtime check.
Python inspection adds checks against real rendered geometry, text, colours and exported sizes.

The [scientific reference matrix](docs/scientific-validation.md) documents independent known-answer
and domain evidence for all 21 kinds. The [0.7.0 delivery audit](docs/delivery-audit.md) links the
accepted capabilities to actual tests, public release assets and clean-install evidence.
The release was checked through local suites, strict gallery regeneration, real TeX/browser
checks and clean installs on Linux, macOS and Windows.

A reproducible [workflow pilot](docs/validation/benchmark.md) compares ordinary Matplotlib,
Matplotlib with hand-written assertions and the strict local CLI. On the eight selected
synthetic cases, the assertion-enabled baseline and GraphUnslopify catch the same false
comparison and abstain on the same unavailable checks. This is project-authored evidence;
independent researcher execution and human productivity/adoption remain unmeasured.
The [published-paper examples](docs/validation/published-papers.md) use real penguin and Iris
datasets with source hashes, separate numerical calculations, actual artist measurements,
and deliberately injected claim/uncertainty faults. Volunteer sessions are deferred;
the [prepared protocol](docs/validation/researcher-pilot.md) remains available for later.
The [NIST reference comparison](docs/validation/certified-benchmark.md) adds 72 measured
runs over all nine univariate reference datasets. Both validated workflows match the
external answers and reject the chosen missing-interval faults; Matplotlib is faster
on this workload. A [four-episode familiarized-agent creation study](docs/validation/authoring-study.md)
also accepts all 36 clean cases; Matplotlib is faster in both pairs. These
project-run observations establish no human or general productivity advantage.
The [review-list delivery audit](docs/review-completion-2026-10-29.md) maps all 20
items to implementation/evidence and keeps the user-deferred researcher trial explicit.

These checks validate their implemented computations and presentation conditions. Data origin,
experimental design, genuinely independent units and appropriate scientific interpretation remain
author responsibilities. Not every optional feature can be combined; unsupported combinations
and unavailable requested estimates stay explicit. Venue presets are layout aids, not a guarantee
of compliance with every current submission requirement.

<details>
<summary>Design lessons: why rendered checks and bounded fixes matter</summary>

These are historical failures, retained to show what the current workflow is designed to catch.


![252 hairline bars with a solid black smear of overlapping date labels along the bottom](docs/fix-apply-fixes-bar.png)


*An old automatic fix turned ordered daily observations into hundreds of bars.*

A finding can suggest a different chart without applying that transformation. Current automatic
repairs do not rewrite the chart kind; decisions that change the comparison need author review.


![The same price curve with a solid black band of 252 overlapping date labels where the axis should be](docs/fix-temporal-before.png)


*An old date axis treated dates as hundreds of categories.*

Supported temporal line/scatter axes now parse and sort dates. The current regression example
shows the result:


![Simulated share price for one trading year with its centered 20-observation rolling mean, dates along the x axis](examples/baseline/15-price-and-average.png)


A successful typecheck and a saved PNG do not establish that a reader can interpret the figure.
The regression gallery requires actual strict inspection, including checks that ignore tick
labels outside the visible axes rather than reporting collisions with invisible text.

</details>

## Documentation

| Topic | Guide |
| --- | --- |
| Installation, offline use and optional dependencies | [Installation](docs/installation.md) |
| Browser editing and portable bundles | [Local editor](docs/local-editor.md) |
| Python and notebooks | [Python package](python/README.md) · [Notebooks](docs/notebooks.md) |
| Agent integration | [Local MCP setup](docs/agents.md) |
| Reports and strict execution | [Runtime policies](docs/runtime-reports.md) |
| Batch review and automation | [Paper audits](docs/paper-audits.md) · [Figure CI](docs/figure-ci.md) |
| Shared settings and saved project runs | [Paper project management](docs/project-management.md) |
| Composition and HTML boundaries | [Composition](docs/composition.md) · [Interactive exports](docs/interactive-exports.md) |
| Numerical validation | [Scientific references](docs/scientific-validation.md) · [Interaction matrix](docs/interaction-validation.md) |
| Specialized estimator contracts | [Survival](docs/survival-validation.md) · [Calibration](docs/calibration-validation.md) · [Paired differences](docs/paired-validation.md) · [Q–Q](docs/qq-validation.md) · [Scaling](docs/scaling-validation.md) · [Density](docs/density-validation.md) |
| Design rationale and examples | [Research](docs/research.md) · [Gallery](examples/README.md) |
| Versions and release evidence | [Versioning](docs/versioning.md) · [Release notes](docs/releases/0.8.0.md) · [Delivery audit](docs/delivery-audit.md) |
| Contributing and direction | [Contribution guide](CONTRIBUTING.md) · [Public roadmap](ROADMAP.md) · [Issue forms](https://github.com/unluckyjet/GraphUnslopify/issues/new/choose) |
| Security | [Policy and private reporting](SECURITY.md) |
| License | [MIT](LICENSE) |

## Development

From a checkout, install Node dependencies and the Python package with development extras:

```sh
npm ci
python -m pip install -e "./python[dev,interactive,statistics]"
```

Run the required checks with `PYTHON` set to that environment's interpreter where necessary:

```sh
npm run typecheck
npm test
npm run test:python
npm run baseline -- --check
npm run render-check
npm run recipe-check
npm run compose-check
```

Run `npm run gallery-check` when changing figure layouts or gallery examples. Rebuild the packaged
translator with `npm run build:translator` after TypeScript or embedded cell-colour changes.
Before pushing, follow [CLAUDE.md](CLAUDE.md) and check CI after the push.
The [contribution guide](CONTRIBUTING.md) covers full setup, optional test contexts and review evidence.
Use `PYTHON=python npm run baseline` only when intentionally regenerating baselines; a bare
baseline generation command can select the wrong interpreter.

The [pipeline](pipeline/README.md) records audited improvements; [future work](docs/future.md)
contains proposals rather than promises. Version 0.8.0 is published on [PyPI](https://pypi.org/project/graphunslopify/0.8.0/) and
[GitHub](https://github.com/unluckyjet/GraphUnslopify/releases/tag/v0.8.0);
[publication evidence](docs/releases/0.8.0-publication.json) records verified hashes and fresh installs. npm registry publication is not claimed.
