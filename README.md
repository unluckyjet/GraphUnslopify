# GraphUnslopify

A local figure generator and verifier that turns a JSON figure spec into reviewable matplotlib code.
It also exposes the same translator over MCP and HTTP.
Live at [json-translator-three.vercel.app](https://json-translator-three.vercel.app).

## Start locally

```sh
python -m pip install "https://github.com/unluckyjet/JSONTranslator/archive/refs/heads/main.zip#subdirectory=python"
graphunslopify demo
```

This creates public toy data, PNG/SVG/PDF figures, the generated Python program, and a strict JSON
verification report in `graphunslopify-demo/`. Python 3.10+ is required. The package supplies the
translator and its Node runtime; translation and rendering work offline after installation.
Use `graphunslopify render figure.json --strict --json` with your own spec and data.
For an offline browser editor, run `graphunslopify preview --open`: select a data file, edit the
spec, review diagnostics and offered fixes, then download figures, Python and verification evidence.
See the [local editor workflow](docs/local-editor.md).
Try batch auditing with `graphunslopify audit-init graphunslopify-demo`, then
`graphunslopify audit graphunslopify-demo --out-dir audit-output`.
See [paper manifests and change reports](docs/paper-audits.md) and
[reusable Figure CI](docs/figure-ci.md) for GitHub workflows and review artifacts.
See [installation and offline use](docs/installation.md), [executable notebooks](docs/notebooks.md),
[Python usage](python/README.md), [local agent setup](docs/agents.md),
[verification policy](docs/runtime-reports.md), and the [MIT license](LICENSE).

![Grouped horizontal bar chart of favourite ice cream flavours, split by age group](docs/first-pass.png)

*First pass with the translation tool with JSON*

Nothing in the spec sets a colour, a line width, or a font size. The generator picks those, which is
how two figures in one paper end up agreeing with each other.

![The same chart with the Adults series hatched](docs/second-pass.png)

*Same JSON, after the improvements*

Adults is hatched now. The spec did not change, the tool did.

| First pass | After |
| --- | --- |
| ![First pass in greyscale, both series the same grey](docs/first-pass-greyscale.png) | ![Second pass in greyscale, one series hatched](docs/second-pass-greyscale.png) |

*Both of them printed in black and white*

This is why the hatching is there. Okabe-Ito is colourblind-safe but not greyscale-safe, so blue and
vermillion land 0.07 apart in relative luminance, under the 0.10 a reader needs. Reordering the
palette does not save it. Of all 40,320 orderings the best still leaves four series 0.094 apart.
Hatching does save it, at any number of series.

Twenty-one kinds: line, scatter, bar, box, violin, ecdf, raincloud, ridgeline, forest,
paired difference, slope, dumbbell, calibration, qq, kaplan meier, scaling fit, confusion
matrix, waterfall, sparkline grid, heatmap and table. Panels, layers, insets and cut
axes compose them. Venue presets set the column width and the font floor from the real submission
guides, so a figure is measured against the width it will actually be printed at.

Set `"temporal": true` on the x axis of a line or scatter and the column is read as dates, sorted,
and laid out in time. The other kinds put categories on x, so the linter rejects it there rather
than drawing something misleading.

## Third pass, the rest of the chart types

| | |
| --- | --- |
| ![Heatmap of cafe customers by weekday and hour](docs/third-pass-heatmap.png) | ![Box plot of order wait times by store with a target line](docs/third-pass-box.png) |
| ![Scatter of menu price against rating with a Pareto frontier](docs/third-pass-pareto.png) | ![Stacked bars of drink units sold by store](docs/third-pass-stacked.png) |
| ![Violin plot of the same wait times, showing the full distribution](docs/third-pass-violin.png) | ![Animated training curve drawing itself](docs/animated-curve.gif) |

*Made-up coffee chain data, one chart per kind*

The data is invented, but each chart answers a real question rather than demonstrating a feature.

The heatmap finds the weekday commuter spike at 8am and the weekend brunch block without being told
either exists. The box plot carries a target line that says `"meaning": "target"` and lets the
generator decide how a target looks. The violin beside it shows the whole distribution where the box
shows five numbers. The last one is the same figure as a gif, because `animate` is a field rather
than a separate tool.

Building these found two bugs, and neither had shown up across thirty earlier figures. A scatter's
legend handle is a `PathCollection`, which has no marker to read, so four genuinely distinct marker
shapes all looked identical and the greyscale check complained about a problem the emitter had
already solved. And a colourbar is an axes, so every heatmap looked like two panels disagreeing
about their ranges.

The third finding was mine, not the tool's. It told me the legend was sitting on three data points
and suggested moving it outside, so I did.

## Fourth pass, most of it switched on at once

![Four training curves with confidence bands, two reference lines and two annotations](docs/fourth-pass-showcase.png)

*Every feature that fits on one figure*

Four methods, mean of five seeds with 95% bootstrap intervals, two reference lines that state what
they mean rather than how they look, and two annotations placed at `"crossover"` and `"max"` instead
of at coordinates. NeurIPS column width, and a dash pattern per series so it survives a black and
white print. The spec names no colour and no position.

```json
{
  "kind": "line",
  "x": { "field": "epoch", "label": "Training epoch" },
  "y": { "field": "accuracy", "label": "Top-1 accuracy", "unit": "%" },
  "group": "method",
  "aggregation": "mean",
  "uncertainty": { "kind": "ci", "level": 0.95, "over": "seed", "display": "band" },
  "series_order": ["ResNet-50", "+ MixUp", "+ Distill", "Ours"],
  "emphasis": { "series": "Ours" },
  "reference_lines": [
    { "axis": "y", "value": 76.5, "meaning": "human", "label": "prior SOTA" },
    { "axis": "x", "value": 8, "meaning": "threshold", "label": "warmup ends" }
  ],
  "annotate": [
    { "at": "crossover", "series": "Ours", "text": "overtakes" },
    { "at": "max", "series": "Ours", "text": "83.1%" }
  ],
  "style": { "venue": "neurips" }
}
```

![The same four curves labelled at the end of each line instead of in a legend](docs/fourth-pass-direct-labels.png)

*Direct labelling, which sidesteps the legend entirely*

A legend box has to sit somewhere, and somewhere is usually on top of the data. Setting
`legend.style` to `direct` puts each name at the end of its own line.

![Three panels, one per benchmark, sharing a y axis with one legend](docs/fourth-pass-facets.png)

*Faceting, with one legend and axis labels only on the outer panels*

`facet` splits the data into one panel per value. The panels share their axes so a reader can
compare them, the legend appears once, and only the outer panels carry axis labels.

### The part you cannot see

A figure can now carry the claim it makes, and the script tests it against the data. The integrity
work names this failure exactly, a caption asserting a gain the figure does not show, and notes that
looking at pixels cannot catch it because the checker cannot read the manuscript.

```json
"claims": [
  { "kind": "beats_everywhere", "subject": "ours", "reference": "baseline" },
  { "kind": "gap_widens", "subject": "ours", "reference": "baseline" }
]
```

Run against data where the baseline leads early, that prints:

```text
claims:
  FAILS     ours is above baseline at every x (12 of 20 x values are not above baseline)
            the figure does not support this. Do not write it in the caption.
  HOLDS     ours pulls further ahead of baseline as x grows (gap moves from -5.2 to +3.8)
```

Alt text writes itself, which several journals now require. Levels one to three of the accessibility
model are derivable, so the spec supplies the encoding and the script supplies the numbers and the
trend. Level four is left to you rather than invented, because guessing at why a result matters is
the fabrication this tool exists to avoid. Only claims that held get quoted.

Each figure also writes a `.tex` block at the right column width, an optional interactive HTML
version through plotly, and a hash of the data file so a stale figure can say so.

### One appearance per series, across a whole paper

| Figure 1 | Figure 7 |
| --- | --- |
| ![Two curves, baseline blue and ours orange](docs/lock-figure-1.png) | ![Three curves with baseline still blue and ours still orange](docs/lock-figure-2.png) |

*The second figure lists the series in a different order and adds a third*

`series_order` fixed colour inside one spec while figure 1 and figure 7 were free to disagree. Point
`palette_lock` at a shared file and the first figure to mention a series claims an appearance for
it. Adding a method later does not recolour the ones already in the paper.

## Fifth pass, composition and a library on top

| | |
| --- | --- |
| ![A y axis with 30 to 60 cut out and slanted marks at the join](docs/fifth-pass-axis-break.png) | ![The same curves with a magnified corner and its source region marked](docs/fifth-pass-inset.png) |

*A cut axis and a zoomed inset*

The slanted marks at the join are the point of a cut axis. Without them a reader takes the axis for
continuous and misreads every distance across the gap, which is the failure the truncation
literature is about. The inset marks its source region with a matching outline rather than connector
lines, because connectors on a flat chart read as a perspective box.

Vega-Lite's operators compose recursively, which is more than this needs. What recurs in a paper is
a short flat list, so that is what the spec takes.

```json
{
  "layers": [{ "mark": "scatter", "label": "observations" }, { "mark": "rug" }],
  "repeat": { "fields": ["accuracy", "loss", "latency_ms"], "columns": 3 },
  "axis_break": { "axis": "y", "from": 30, "to": 60 },
  "inset": { "x": [14, 20], "y": [65, 85], "corner": "lower_right" }
}
```

| | |
| --- | --- |
| ![Curves with individual observations and a rug of tick marks underneath](docs/fifth-pass-layers.png) | ![Three panels, one per metric, each with its own y label](docs/fifth-pass-repeat.png) |

*Layers over the same axes, and one panel per metric*

A layer adds a mark over the figure's own x, so observations can sit over a fitted line and a rug
can show where the data actually falls. `repeat` gives one panel per named column, and each panel
takes its own label rather than the spec's.

![A three row results table with the winning value bold in each row](docs/fifth-pass-table.png)

*The table kind, rendered as an image and written as markdown and LaTeX*

There is a `table` kind now, because sometimes six numbers should not be a chart. A printed number
is exact rather than estimated, so it outranks every graphical channel for reading one value. One
spec writes markdown, LaTeX and an image, so the readme, the manuscript and the slides cannot drift
apart, and `highlight` bolds the winner in each row or column.

Set `uncertainty` on a table to show the same intervals used by charts in every cell.
Highlighting then considers interval separation: overlapping candidates are highlighted together,
with a printed caveat that overlap does not establish equivalence. Missing intervals are labeled
`unavailable`, and no winner is highlighted for that comparison. Column widths grow to fit the
intervals rather than drawing neighboring values on top of each other.

For significance brackets, the historical `method: "bootstrap"` name runs a two-sided,
independent-sample permutation test of mean differences. Small samples enumerate all group
assignments exactly; larger samples use independent seeded permutations and include the observed
assignment in the p-value count. This significance test is separate from bootstrap confidence
intervals selected by `uncertainty.kind: "ci"`.

Significance uses `correction: "holm"` by default across the tested pairs in each panel.
`"benjamini_hochberg"` is available for appropriate exploratory families, and `"none"`
explicitly opts out (with a warning for multiple pairs). The script prints raw and adjusted
p-values, the procedure, and the number of comparisons. A non-significant result is not an
equivalence verdict.

Each generated script prints rows read, rows after filtering, and the number of finite
measurements. Aggregated figures also report the observations per point, disclose unequal sample
sizes, and include the counts in their alt text and PNG metadata. Skipped significance pairs name
the missing data or unavailable test. When `uncertainty.over` names a unit such as seed, repeated rows within that unit and point are
summarized first, so one prolific seed cannot outweigh another. Counts then refer to those unit
IDs. The author remains responsible for deciding whether the named units are independent;
without an identifier the rows themselves are assumed independent.

PNG, SVG and PDF carry [recoverable provenance](docs/provenance.md): the full spec, computed
description, and data/source fingerprints. Read it with `graphunslopify provenance figure.svg`.

Generated programs also write a [structured runtime report](docs/runtime-reports.md).
Run `python figure.py --strict` or `graphunslopify check figure.py --strict --json`
to fail on errors, failed claims, unavailable inspection, or untested required checks.
`--fail-on-warning` additionally rejects warnings. Claims are checked per panel and
metric; missing x coverage and one-point trends are explicitly untested.

### Writing specs in Python

The MCP tools are for an agent. `graphunslopify.Figure` is the same thing for a person in a
notebook.

```python
from graphunslopify import Figure

(
    Figure.line("results.csv")
    .x("epoch", "Training epoch")
    .y("accuracy", "Test accuracy", unit="%")
    .by("model", order=["baseline", "ours"], emphasise="ours")
    .average_over("seed")
    .claim("beats_everywhere", "ours", "baseline")
    .venue("neurips")
    .render()
)
```

`average_over` sets the aggregation and the spread together, because doing one without the other
throws away what a reader most needs. `render` translates locally, writes the script beside the data and
runs it, so what lands on disk is the same script an agent would have got. Nothing here
reimplements the emitter, because two emitters drift. `Figure.from_profile` ranks candidates for a
file and starts from the top-ranked candidate. Column roles and units are guesses; review them
against the experiment before using a suggestion.

## Writing a spec

Do not guess at the data. Ask it:

```bash
pip install ./python
graphunslopify describe results.csv
```

That reports the columns, their roles, how many distinct values each has, and whether x repeats per
series, along with a starting spec. On the example data it picks `epoch` over `seed` as the x axis
and adds the aggregation and confidence interval the repeats require.

Then hand that profile to `suggest_figures` and get candidates back, ranked by a weighted cost in
the shape Draco uses. The weights come from the Cleveland and McGill accuracy ranking, so a design
that reads by length scores worse than one that reads by position, and the suggestion quotes the
measured ratio rather than asserting a preference.

`apply_fixes` repairs a spec using its own findings. Every finding carries a machine-readable patch,
because the agent literature reports models recognising an error and failing to act on it, which is
an interface problem rather than a reasoning one. The loop has a budget so it says what it could not
fix instead of churning.

`list_recipes` has twenty-five known-good specs to start from. `validate_spec` checks one without
generating anything, and `score_spec` costs one so two can be compared.

## Connecting

```bash
claude mcp add --transport http graph-unslopify https://json-translator-three.vercel.app/api/mcp
```

Your data never leaves your machine. You get back a script that reads your own CSV.

## Other output formats

Set `animate` and the same figure draws itself as a gif or an mp4.

```json
{ "animate": { "style": "draw", "duration_s": 4, "easing": "smooth", "format": "gif" } }
```

Set `output.interactive` and you also get a self-contained HTML figure through plotly, with hover
and zoom, which is what a project page wants and a paper does not. Set `output.latex` and you get an
`\includegraphics` block at the right column width with the caption and alt text already in it.
Captions and table labels are escaped as literal text; see [text exports and disclosure](docs/text-exports.md).

On manim, with evidence rather than an opinion. It does not install here, because `moderngl` and
`glcontext` fail to build wheels without a C toolchain. Even where it installs it draws its own axes
rather than the ones this spent so long getting right. What makes those animations read well is
easing and staged construction, and both are a few lines over `FuncAnimation`. The rate functions
are ports of manim's and keep its names, so `easing: "rush_into"` does what you would expect.

plotly and scipy do install, and both are used. scipy makes the t-test and Mann-Whitney options real
rather than a fallback to the bootstrap.

## What checks the work

Seventy-three rules run on the server against the spec alone. The Python package checks the rendered
figure, which is where the rest hide.

It measures every text element at the width the figure will be printed and fails below the venue's
floor. It compares label positions, so an annotation on the title or an inset crowding its parent
gets caught. It measures colour distance in CIELAB under three simulated colour vision deficiencies.
And it refuses a truncated bar axis outright, because a bar's length is its value.

`docs/research.md` maps every rule to the paper or policy behind it.
`docs/future.md` parks what is worth building next and says why none of it is
scheduled yet. `examples/README.md` covers the
gallery and why its images are committed.


## Seventh pass, thirteen more kinds

Seven kinds in the morning, twenty-one by the evening. Each of these replaces a figure people
already draw, and draw worse.

| | |
| --- | --- |
| ![Empirical cumulative distributions of latency for three models](docs/seventh-pass-ecdf.png) | ![Raincloud plot with the violin, quartile box and every raw point](docs/seventh-pass-raincloud.png) |
| ![Ridgeline plot, one latency density per model](docs/seventh-pass-ridgeline.png) | ![Forest plot of four ablation components with confidence intervals](docs/seventh-pass-forest.png) |

*Distributions, and an ablation table with its intervals kept*

The ECDF has no bin width and no bandwidth, so nothing about its shape is a decision an author
makes. A histogram invents and destroys modes depending on where the bins land, and the step is
drawn as a step because the distribution is flat between observations.

The forest plot is the one I would keep if I could keep one. An ablation table is already a forest
plot with the intervals thrown away. Here `+ EMA` crosses zero, which no amount of bolding in a
table would have shown.

| | |
| --- | --- |
| ![Paired differences between two conditions with a bootstrap interval](docs/seventh-pass-paired-difference.png) | ![Slope chart of four methods before and after](docs/seventh-pass-slope.png) |
| ![Dumbbell chart, before and after per method on one scale](docs/seventh-pass-dumbbell.png) | ![Reliability diagram comparing two models against the diagonal](docs/seventh-pass-calibration.png) |

*Differences, change, and whether the probabilities mean anything*

The paired-difference plot draws the subtractions themselves. A paired test operates on those
numbers, so they are the distribution the p-value described; two overlapping boxes next to a
p-value are the commonest statistical mistake in papers. Its axis reads "Change in accuracy (pp)"
rather than "Accuracy (%)", because 2.4 here is a gain and the difference between two percentages
is measured in points.

Paired differences match unit IDs before subtracting conditions, disclose unmatched units and
show the matched sample size. Descriptions and runtime reports use those differences and their
bootstrap mean intervals; see [the paired reference contract](docs/paired-validation.md).

The reliability diagram prints the expected calibration error per model. The overconfident one
scores 0.080 against 0.026 and sits below the diagonal all the way along.

| | |
| --- | --- |
| ![Q-Q plot with a gaussian and a heavy-tailed sample](docs/seventh-pass-qq.png) | ![Kaplan-Meier curves for two arms with censoring marks](docs/seventh-pass-kaplan-meier.png) |
| ![Scaling plot on log-log axes with fitted power laws](docs/seventh-pass-scaling-fit.png) | ![Row-normalised confusion matrix over four classes](docs/seventh-pass-confusion.png) |

*Checking an assumption, surviving, scaling, and confusing*

Q–Q plots use accurate normal inverse probabilities and a reference through population/sample
quartiles. They disclose missing observations and refuse undersized samples instead of verifying
an empty plot. See [the Q–Q reference contract](docs/qq-validation.md).

The Q-Q plot checks the distributional assumption before a claim rests on it. The heavy-tailed
series bends away at both ends, and there is nothing else to read. Winitzki's approximation supplies the
normal quantile, so this needs no scipy.

Calibration validates probability/outcome domains and uses the same occupied-bin calculation for
points, ECE, descriptions and comparisons. See [the calibration reference contract](docs/calibration-validation.md).

The survival curve marks every censored record. A curve that hides them looks far more certain
than the data supports. Tied events share the correct risk set, and numeric claims use the plotted
survival estimates; see [the survival contract and independent references](docs/survival-validation.md).

The scaling fit prints the exponent and its interval instead of leaving it to be read off a log-log
axis by eye. On data generated with an exponent of 0.14 it recovered -0.1399 plus or minus 0.0023.

A confusion matrix is no longer a heatmap, because it makes a claim a heatmap does not.
`normalize` has no default. Row-normalised reads as recall, column-normalised as precision, and
raw counts as support, and nothing used to make an author say which was on screen.

| | |
| --- | --- |
| ![Waterfall chart of four ablation contributions from a baseline](docs/seventh-pass-waterfall.png) | ![Grid of twelve sparklines on one shared scale](docs/seventh-pass-sparklines.png) |

*Contributions, and many series at once*

A waterfall requires `category_order`, because a reader takes it left to right and the order is
part of the claim. The sparkline grid shares one scale across every cell, since free limits would let a
flat series look as dramatic as a real one.

The waterfall also found a hole in the render checker. Its bars are meant to float, so only the
first and the total touch the baseline, and the truncated-bar rule fired on it and told the author
to do something that would have destroyed the chart. That rule now skips bars which do not share a
starting edge.

Four of these thirteen shipped with a bug that typechecked, ran, and wrote a valid PNG. The
ridgeline drew with its axis labels swapped, reading "Model" over latency values. The confusion
matrix tried to average a class label. The waterfall's baseline sat outside the view, because
autoscale measures the bars and not the line they rise from. And four separate kinds crashed on a
missing `HATCHES`, from being added to the emitter without being added to the list of kinds whose
second channel is a dash. That list lives in one place now.

## The gallery, rebuilt and measured

Fifteen figures, one per branch of the emitter. They used to be built by POSTing each spec to the
deployed API, which meant the committed images recorded whatever happened to be live rather than
what the code in the tree does. They had fallen a version behind without anyone noticing. Every
script in `examples/generated` claimed 0.5.0 while the emitter stamped 0.6.0. They are translated
locally now, and `npm run baseline -- --check` fails if the two ever separate again.

| | |
| --- | --- |
| ![Line chart of test accuracy against training epoch, one series per model, ours in the foreground reaching 81.1 against baseline at 70](examples/baseline/01-training-curve.png) | ![The same four models on a logarithmic loss axis, ending between 0.281 and 0.302](examples/baseline/02-loss-log.png) |
| `01-training-curve`, mean over seeds with the argued series in front | `02-loss-log`, log axis and median aggregation |
| ![One filtered training run of ours with no legend](examples/baseline/03-single-run.png) | ![Grouped bars of top-1 accuracy per dataset, ours highest at 51.2 and baseline lowest at 43.8](examples/baseline/04-accuracy-by-dataset.png) |
| `03-single-run`, no group, legend suppressed | `04-accuracy-by-dataset`, grouped bars with the legend below |
| ![Horizontal bars of median latency by model](examples/baseline/05-latency-ranking.png) | ![Scatter of accuracy against latency, one marker shape per model, legend outside the data](examples/baseline/06-accuracy-vs-latency.png) |
| `05-latency-ranking`, horizontal bars sorted by value | `06-accuracy-vs-latency`, one marker shape per series |
| ![Ungrouped scatter of accuracy against parameter count with a linear fit](examples/baseline/07-params-trendline.png) | ![The four training curves at double column width in the compact preset](examples/baseline/08-compact-double-column.png) |
| `07-params-trendline`, linear fit on an ungrouped scatter | `08-compact-double-column`, compact preset at double width |
| ![Four training curves with shaded 95 percent confidence intervals and a chance line at 25](examples/baseline/09-uncertainty-band.png) | ![Three panels of accuracy bars, one per dataset, sharing a y axis with readable category names](examples/baseline/10-faceted-benchmarks.png) |
| `09-uncertainty-band`, bootstrap intervals and a labelled chance line | `10-faceted-benchmarks`, one panel per dataset |
| ![Box plot of accuracy across epochs per model, values from 65.3 to 82](examples/baseline/11-seed-spread.png) | ![Heatmap of validation accuracy over learning rate and batch size, largest 82.4 at 0.001 and 32](examples/baseline/12-sweep-heatmap.png) |
| `11-seed-spread`, distribution behind the summary | `12-sweep-heatmap`, annotated cells and a labelled colourbar |
| ![The four curves labelled at the end of each line with no legend box](examples/baseline/13-direct-labels.png) | ![The same training curves drawing themselves as an animation](examples/baseline/14-animated-curve.gif) |
| `13-direct-labels`, names at the end of each line | `14-animated-curve`, the same figure as a gif |
| ![Simulated share price over one trading year with its 20-day rolling average, dates along the x axis](examples/baseline/15-price-and-average.png) | |
| `15-price-and-average`, a temporal x axis | |

The gallery labels describe each example. The full descriptions are computed from the current
data and embedded in the exported files.

### What the checker says about its own gallery

Running all fifteen through the render-time checker in `python/graphunslopify` found three problems.
One of them was the checker's own fault.

It reported `02-loss-log` drawing a minus sign on top of a log-axis tick label. That tick was never
drawn. Matplotlib lays ticks on a round grid and keeps the ones past the view limits, and those
report themselves as visible and carry a real bounding box, so the collision checks were measuring
labels no reader can see. The checker now skips them, and `02-loss-log` is clean.

All fifteen now pass the strict runtime checker. The scatter legend sits below
the axes, and crowded categorical ticks rotate only when their measured text
boxes overlap. Names and font sizes are preserved. `npm run gallery-check`
regenerates every example, requires real inspection and rejects failed or
incomplete checks; GitHub CI runs it as a regression gate. Before these fixes,
the same gate failed with `legend_covers_data` and `tick_labels_collide` on 06/10.

The source specs, data, and generated artifacts remain together for review.

## Sixth pass, what one stock chart broke

Someone asked for a share price against its 20-day moving average. It is the most ordinary chart in
finance and the tool had three bugs and one gap sitting in the way of it.

### apply_fixes turned a year of prices into 252 bars

![252 hairline bars with a solid black smear of overlapping date labels along the bottom](docs/fix-apply-fixes-bar.png)

*What `apply_fixes` handed back for a daily price series*

The `line_implies_continuity` suggestion hedges properly. It says a bar chart makes the same
comparison **if** x is a set of unordered categories. Its patch did not hedge, so `apply_fixes` fired
`{ kind: "bar", aggregation: "mean" }` at every ungrouped line chart it saw, ordered x or not.

The spec carries column names and no column types, so nothing in it can tell a trading day from a
category. There is no clever fix here, only a wrong one, so the suggestion now carries no patch and
stays advice. A test sweeps every rule across every kind and fails if any fix payload touches `kind`,
because rewriting the kind of chart is the most destructive edit an auto-fixer can make.

### The checker measured labels that were never drawn

Setting `ylim` to `(28, 57)` produced a collision against a tick reading "60". There is no 60 on the
figure. Matplotlib lays ticks on a round grid and keeps the ones past the view limits, and those
report themselves as visible and carry a real bounding box:

```
view limits: (28.0, 57.0)
  tick '25'  data-y=25.0  visible=True  inside-view=False
  tick '60'  data-y=60.0  visible=True  inside-view=False
```

Every check that measures text was counting them. This is also the `02-loss-log` finding this readme
described two sections ago, where a minus sign supposedly collided with a log-axis tick. That figure
is clean now, and thirteen of the fifteen pass rather than twelve of fourteen. Chasing a phantom
label through three sets of axis limits before probing matplotlib directly is the most time any
single bug here has cost me.

### A date column had no axis to go on

![The same price curve with a solid black band of 252 overlapping date labels where the axis should be](docs/fix-temporal-before.png)

*A date column before `temporal` existed*

Dates arrived as strings, so matplotlib treated 252 of them as 252 categories. The curve above is
correct and the axis under it is unreadable.

`"temporal": true` on the x axis of a line or scatter now parses the column, sorts by it, and hands
the axis to `ConciseDateFormatter`. Sorting is not decoration. A date export in reverse order draws
the line backwards, and unlike a numeric x nobody notices until they read the ticks. Four rules bound
it, because only x can be temporal, only a line or scatter can carry it, time is not logarithmic, and
numeric limits cannot bound a date axis.

Then annotating one crashed:

```
TypeError: float() argument must be a string or a real number, not 'Timestamp'
```

`locate()` guarded with `np.isreal`, which asks whether a value is not complex. A Timestamp is not
complex, so it passed a test meant to mean "is a plain number" and reached `float()`. Three call
sites shared that mistake and now share one `as_coordinate` helper instead.

![Simulated share price for one trading year with its 20-day rolling average, dates along the x axis](examples/baseline/15-price-and-average.png)

*`examples/specs/15-price-and-average.json`, the chart that started it*

The faint line is the daily close and the bold line is the 20-day average. The average turns after
the price does at both the May peak and the August trough, which is the whole point. A moving average
describes what already happened. The data is simulated, and the alt text says so.

The typecheck passed and every test passed before I rendered that figure for the first time. The
`Timestamp` crash was waiting on the other side of a green suite, which is the argument for the
gallery in one sentence.

Composition behavior and supported combinations are described in [composition contracts](docs/composition.md).

[Interactive exports](docs/interactive-exports.md) share supported numeric analyses with static
figures and embed Plotly for offline viewing. Unsupported combinations fail explicitly.
