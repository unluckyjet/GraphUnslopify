# Self-contained result tables

Table images now retain the declared title, row-key heading and metric/unit.
Grouped tables keep method names as column headings and show the metric above
them; a plain table uses the metric/unit as its value-column heading. No title
is invented when the spec omits one. Requested bounds and bold-selection meaning
are visible too. The same context accompanies Markdown and LaTeX outputs.

All formats share one numeric formatter. With `y.percent: true`, fractional
estimates and their bounds are multiplied by 100 for display and carry `%`.
For example, `0.85 [0.80, 0.90]` becomes `85.00% [80.00%, 90.00%]`. Use `%` as
the display unit, or omit the unit, with this setting. A unit label alone does
not convert data: values already measured on a 0–100 percent scale should leave
the percent formatter off. Raw estimates, intervals, winner comparisons and claim
thresholds remain unchanged; formatting does not transform the data.

Missing cells stay `-`. Unknown singleton bounds stay `[unavailable]`, not zero.
Bounds describe the requested uncertainty kind; a standard-error interval is
not relabeled as a 95% confidence interval.
Confidence percentages retain the requested precision, including 95.5% and 99.9%;
99.9% is not rounded into a claim of 100% confidence. Descriptions report displayed cell
quantities with the same precision/percent formatter, rather than describing
nonexistent shaded bands or error bars. Bold interval candidates do not establish
equivalence or statistical significance.

Author and data labels are literal text. Images disable math/TeX interpretation
for table text, Markdown escapes label markup/pipes/HTML, and LaTeX uses the
existing literal-text encoder once, including title/metric spanning rows. Table
rows and numeric estimates are preserved. Plot-only log scales, axis limits,
temporal axes and percent row labels produce `unsupported_table_axes`; point
annotations, reference lines and series emphasis are also explicitly unsupported.
They cannot be silently ignored while descriptions claim they appear.

Static table outputs undergo the [actual export-width font check](export-legibility.md).
An oversized title/header can therefore fail strict mode while leaving files for
review. Choose a suitable column width, fewer columns or clearer shorter labels;
the tool does not hide context or disable inspection to make the result pass.
Downstream LaTeX document layout still belongs to the manuscript workflow.

`python/tests/test_table_context.py` has 28 independent artist, bounding-box,
numeric-string, raw-value, highlight, PDF-text, provenance and refusal controls.
The existing real-TeX gate additionally compiles literal title/metric labels and
percentage bounds and reads the actual PDF text. Its original 23 context controls
failed before this change. Fresh-wheel smoke renders a percent/range table
outside the checkout, checks Markdown and actual PDF text, and requires strict
actual-width inspection with external runtime connections blocked.

The [published synthetic example](../examples/references/README.md) now has
committed CSV/JSON inputs and source/data fingerprint checks. It replaces a table
image whose inputs were untracked. The 15 baseline figures and four other public
reference illustrations are unchanged. This presentation contract does not
complete the broader 21-kind scientific reference matrix.
