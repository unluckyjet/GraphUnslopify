# Interactive HTML exports

Install `graphunslopify[interactive]`, then set `output.interactive=true`.
HTML embeds Plotly itself; it does not require a CDN. It includes the computed
figure description and the same recoverable provenance envelope as static exports.
`graphunslopify provenance figure.html` reads it without executing JavaScript.

Supported numerical exports:

- Line/scatter series, retaining observed series not listed in an expected order.
- Line/bar summaries and intervals using the same declared repeat units as the
  static chart. Lines support bands or error bars; bars support either orientation.
- Bar ordering, category spacing, value labels and zero baselines.
- Heatmap aggregation, cell values, row orientation and sequential/diverging scales.
- Linear/log axes, explicit limits and percentage formatting where implemented.

Presentation is responsive HTML rather than a pixel copy of the publication
figure. Colors and series channels are carried across, and hover/legend controls
provide interactive identification. A single-point line always has a visible
marker in both backends.

Other kinds and unsupported analysis/composition options produce
`interactive_not_supported`. These include grids/repeats/overlays/cuts/insets,
secondary axes/smoothing, scatter fits/frontiers, significance/stacked bars,
annotations/reference lines and unsupported axis transforms. The generator does
not replace them with a generic scatter plot. Static exports retain their broader
supported capabilities. Remove the HTML request or choose a supported spec.

Descriptions compare series at one shared endpoint and disclose absent values;
they do not compare each series's different last x. Heatmap descriptions use the
aggregated displayed cells. A figure with no finite value measurements is
incomplete under strict policy. Series ordering never silently filters data:
unlisted observed series are retained with a warning. Use an explicit row filter
when exclusion is intended.

Static confusion-matrix descriptions use the same count matrix as the image,
including precomputed and sparse counts. Counts must be finite nonnegative
integers; an explicitly missing count is not silently replaced with zero.
Normalization is disclosed in the description. These static matrices currently
refuse HTML export rather than changing to a different analysis.
