# Baseline gallery

Fifteen figures covering every branch of the emitter. Each one is built by translating a spec with
the emitter in this working tree, running the Python that comes out, and committing both. The code
and the images are version controlled, so changing the emitter shows up as a reviewable diff instead
of a surprise in someone's paper.

## Rebuild it

```bash
npm run baseline                            # write the scripts and render them
npm run baseline -- --check                 # report emitter drift, no Python needed
PYTHON=/path/to/python npm run baseline     # pick the interpreter
```

You need matplotlib and pandas to render. `pip install -r requirements.txt` into a venv covers it.
`--check` needs neither, which is why CI runs that one on every push.

## What is here

`specs/` holds the fifteen inputs, one JSON file each. `data/` holds the four CSVs they read,
written by `scripts/make-example-data.ts` from a fixed seed so the images do not move for unrelated
reasons. `generated/` holds the emitted Python. `baseline/` holds the rendered images.

| Spec | Exercises |
| --- | --- |
| `01-training-curve` | mean over seeds, emphasis, legend outside right |
| `02-loss-log` | log y axis, median aggregation, four full-strength series |
| `03-single-run` | one model and seed selected, no aggregation, markers, legend suppressed |
| `04-accuracy-by-dataset` | grouped bars, emphasis, legend below as a strip |
| `05-latency-ranking` | horizontal bars, category order, inverted y axis |
| `06-accuracy-vs-latency` | grouped scatter, emphasis |
| `07-params-trendline` | ungrouped scatter with a linear fit |
| `08-compact-double-column` | compact preset, double column, grid, explicit y limits |
| `09-uncertainty-band` | bootstrap confidence band, chance line, annotation at the maximum |
| `10-faceted-benchmarks` | panels with letters, shared y, one legend, value labels |
| `11-seed-spread` | box plot, row filtering, sorted by value |
| `12-sweep-heatmap` | heatmap with a labelled colourbar and annotated cells |
| `13-direct-labels` | series named at the end of their lines instead of a legend box |
| `14-animated-curve` | the same curve drawing itself as a gif |
| `15-price-and-average` | a temporal x axis, with a rolling average over the raw series |

## Why the images are committed

Three of the four bugs fixed so far survived both the unit tests and a successful render. A
horizontal bar chart with its axis labels swapped runs perfectly and writes a valid PNG. So does
one whose categories came out alphabetical. So does a four-series chart where emphasis painted
three of them the same grey. Every one of those was caught by opening the file and looking.

Committed images turn that into a diff. The unit tests catch what a machine can check, and the
gallery catches what it cannot.

## Regenerating the data

```bash
npm run example-data
```

Only do this if you mean to. The CSVs are the fixed input behind every committed image, so
rewriting them makes the whole gallery move at once and the diff stops meaning anything.
