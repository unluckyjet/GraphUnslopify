# Baseline gallery

Rendered from `examples/specs` by the emitter in this working tree.
Regenerate with `npm run baseline`, then look at the image diff.
`npm run baseline -- --check` reports emitter drift without needing Python.

| Spec | Kind | Findings |
| --- | --- | --- |
| `01-training-curve` | line | clean |
| `02-loss-log` | line | clean |
| `03-single-run` | line | warning:line_implies_continuity |
| `04-accuracy-by-dataset` | bar | clean |
| `05-latency-ranking` | bar | clean |
| `06-accuracy-vs-latency` | scatter | clean |
| `07-params-trendline` | scatter | clean |
| `08-compact-double-column` | line | clean |
| `09-uncertainty-band` | line | clean |
| `10-faceted-benchmarks` | bar | clean |
| `11-seed-spread` | box | clean |
| `12-sweep-heatmap` | heatmap | clean |
| `13-direct-labels` | line | clean |
| `14-animated-curve` | line | clean |
| `15-price-and-average` | line | clean |
