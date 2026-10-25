# What people complain about, and which check answers it

There are 69 spec rules and 11 rendered finding categories. Visualization safeguards trace to
documented complaints; implementation-contract guards prevent accepted options being ignored.
This is the mapping, so a future change to a threshold has to argue with a source.

One honest note on method. X and similar platforms produced almost nothing usable, a single
throwaway joke about AI adding y-axes to misleading graphs. The substantive material is in papers,
publisher policy documents, and Retraction Watch, so that is what these rules are built on.

## Defects invisible in the code

A validation-driven chart-generation study discarded 33% of its candidates, and the unresolved
problems were low contrast, overplotting, unreadable axes, and unclear legends. Retargeting work
describes "pervasive element occlusion", specifically overlapping x tick labels and legends
covering data points. The recurring reviewer sentence is that a figure is unreadable at
single-column width, because 12pt in the draft becomes about 5pt once the journal scales the figure
to 89mm. Generated code also fails silently: it runs, writes a valid file, and the file is wrong.

| Complaint | Check | Where |
| --- | --- | --- |
| Unreadable at column width | `text_too_small`, `text_near_minimum` | `python/graphunslopify/inspect.py` |
| Overlapping tick labels | `tick_labels_collide` | same |
| Legend covering data | `legend_covers_data` | same |
| Overplotting | `overplotting` | same |
| Silent code failure | the script runs or it does not | `scripts/render-check.ts` |

`inspect_figure` takes `target_width_in`, so a 10-inch figure destined for a 3.4-inch column is
measured at the size it will actually be printed, not the size it was drawn.

## Series a reader cannot separate

Roughly one man in twelve has a colour vision deficiency. The standing advice is that colour must
never be the only channel and the figure has to survive greyscale.

`colour.py` converts to CIELAB and measures CIEDE2000, then repeats the measurement under simulated
protanopia, deuteranopia and tritanopia using the Machado, Oliveira and Fernandes (2009) matrices.
White against black scores exactly 100, which is the known reference value for the metric.

Two things fell out of running this on our own output. Red against green scores 6.7 under
deuteranopia, comfortably below the threshold of 11. And Okabe-Ito, which is colourblind-safe, is
not greyscale-safe: adjacent entries sit within 0.06 relative luminance, so three of them merge in
a black and white print. Reordering does not rescue it either. Searching all 40,320 orderings, the
best still leaves four series 0.094 apart, under the 0.10 a reader needs. Luminance runs out and a
second channel does not, so `SECOND_CHANNEL_THRESHOLD` is 1 and any multi-series figure gets line
styles, markers or hatching. The first entry of each cycle is the plain form, so a single-series
figure is untouched.

This check also catches, automatically, the bug fixed in `382c85b` where emphasis painted three
series the same grey. That one was found by hand, by opening a PNG.

## Misrepresentation

Truncated bar axes mislead viewers even after they have been explicitly taught about truncation,
with 83.5% still showing the effect. Vision-language models are fooled by the same axis
manipulations across 16,000 responses.

`truncated_bar_axis` is therefore an error, not a warning. Line charts are exempt, because the
literature genuinely disagrees about truncation there and a zoomed line axis is often the honest
choice, but `axis_exaggeration` warns when the visible span is under 10% of the values' magnitude.

## Disclosure and reproducibility

Undisclosed AI figure generation is a policy violation at every major publisher that has issued
guidance, and the standard is that anything representing results must be fully reproducible by the
authors. NEJM retracted a case study in May 2026 over an AI-altered image, and two 2024 papers were
retracted for anatomically wrong AI figures.

This is where the architecture does the work rather than a check. The tool emits a script instead of
an image, so the script is the reproducibility record. On top of that each script carries its tool
version and a spec hash, embeds the full spec in the PNG, SVG and PDF metadata, and prints a
methods sentence ready to paste.

## Uncertainty, which was the biggest gap

The tool could plot a mean over seeds and throw the spread away silently, which is arguably worse
than not aggregating at all. `uncertainty` now covers standard deviation, standard error, a
percentile bootstrap interval, interquartile range and full range.

The interval is a bootstrap rather than a t interval, so the script needs numpy and nothing else and
makes no assumption about the shape of the distribution over seeds. It is seeded, so the same data
gives the same band twice.

Four lint rules keep the statistics honest: uncertainty without aggregation, an interquartile range
around a mean, a standard deviation around a median, and a shaded band across categories, which
implies a continuity between them that does not exist.

## Chart type confusion

The largest single error class in generated charts is sub-chart-type confusion at 23%, mostly
stacked against grouped bars, then improper bar spacing at 18% and misaligned gridline counts at
15%.

The discriminated union in `src/schema.ts` makes the confusion unrepresentable. Stacking is a
boolean on `BarSpec`, not a separate `kind`, so a model choosing "bar" cannot accidentally choose
the other one, and switching between them is one field rather than a rewrite.

Two rules guard the choice. `stacked_without_group` catches stacking with nothing to stack, and
`too_many_stack_segments` fires past six, because only the bottom segment shares a baseline and the
rest cannot be compared by eye. `stacking_signed_values` refuses to stack the output of
`delta_vs_baseline`, which is negative by construction.

## Ranking designs rather than only rejecting them

Draco encodes visualisation design knowledge as hard and soft constraints with learned weights,
solved by an ASP solver, and ranks candidates by violation cost. A 2026 follow-up synthesised
knowledge bases beating Draco 2 by 1 to 15%, and noted Draco 2 still cannot separate designs in 4 of
30 graphical perception studies, so this is live research rather than settled.

`verify.ts` was an ad-hoc version of the same idea that could only reject. `src/perception.ts` adds
the missing half: `designCost` charges a spec by weight and `suggest_figures` ranks candidates. The
weights are hand-set from the perception ranking rather than learned, which is the obvious next step
once there is a corpus of accepted figures.

Cleveland and McGill ranked the elementary perceptual tasks by accuracy, position on a common scale
first, then length, direction, angle, slope, area, volume, shading and saturation. Position measured
1.4 to 2.5 times more accurate than length and 1.96 times more accurate than angle. Those ratios are
quoted in the suggestion text, so a recommendation against a stacked bar carries a number rather
than a preference.

## Claims the figure has to support

The integrity work names the failure precisely: a caption asserting a gain while the axis is
truncated cannot be caught by pixel inspection, because the checker cannot read the manuscript. The
Figure-seg benchmark holds 15,761 text-to-figure alignment instances built around exactly this.

`src/claims.ts` moves the claim into the spec, where the script can test it. Ten kinds, each
returning a verdict with its numbers. Only claims that hold are quoted in the alt text, and a failed
claim prints an instruction not to write it in the caption.

## Alt text

PNAS and others now require alternative text. The four-level semantic model behind MatplotAlt runs
encodings and axes, then statistics, then trends, then context. Level 1 comes from the spec, levels
2 and 3 from the data at run time, and level 4 is left to the author because inventing why a result
matters is the fabrication this whole tool exists to avoid. Alt text does not repeat the caption and
never opens with "this figure shows", both straight from the guidance.

## Repair, not just detection

The agent evaluation survey reports capability rising faster than reliability, and describes models
recognising an error, failing to fix it across many turns, and terminating. That is an interface
problem. Findings now carry a machine-readable patch, `apply_fixes` applies them, and the loop has a
budget so it reports what it could not repair instead of churning.

## Why not ask a model

PlotGen and similar systems loop a multimodal model over the rendered image. Every check here is
geometric or colorimetric, which is faster, cheaper, and gives the same answer twice. A model is
worth reaching for only for the subjective residue, and so far there has not been any.

## Sources

- [Generating Statistical Charts with Validation-Driven LLM Workflows](https://arxiv.org/html/2605.00800)
- [Challenges and Opportunities with LLM-Assisted Visualization Retargeting](https://arxiv.org/pdf/2507.01436)
- [PlotGen: Multi-Agent LLM-based Scientific Data Visualization via Multimodal Feedback](https://arxiv.org/html/2502.00988v1)
- [The ethics of erroneous AI-generated scientific figures](https://link.springer.com/article/10.1007/s10676-025-09835-4)
- [AI-Generated Figures in Academic Publishing: Policies, Tools, and Practical Guidelines](https://arxiv.org/pdf/2603.16159)
- [NEJM retracts case study for AI-manipulated imagery, Retraction Watch](https://retractionwatch.com/2026/05/01/nejm-retracts-case-study-for-ai-manipulated-imagery/)
- [Truncating the Y-Axis: Threat or Menace?](https://arxiv.org/pdf/1907.02035)
- [Truncating Bar Graphs Persistently Misleads Viewers](https://www.sciencedirect.com/science/article/abs/pii/S2211368120300978)
- [The Perils of Chart Deception: How Misleading Visualizations Affect Vision-Language Models](https://arxiv.org/html/2508.09716v1)
- [Automatic Synthesis of Visualization Design Knowledge Bases](https://arxiv.org/html/2601.19237)
- [Graphical Perception, Cleveland and McGill, via CSE 412](https://courses.cs.washington.edu/courses/cse412/21sp/lectures/CSE412-Perception1.pdf)
- [MatplotAlt: Adding Alt Text to Matplotlib Figures](https://arxiv.org/pdf/2503.20089)
- [PNAS Improves Accessibility with Alternative Text](https://www.pnas.org/post/update/pnas-improves-accessibility-alternative-text)
- [SciFigAlign: Scoring Scientific Figures by Alignment with Manuscript Evidence](https://arxiv.org/html/2607.27066)
- [A Survey on Evaluation of LLM-based Agents](https://arxiv.org/html/2503.16416v2)
- [Vega-Lite: A Grammar of Interactive Graphics](https://idl.cs.washington.edu/files/2017-VegaLite-InfoVis.pdf)
- Machado, Oliveira and Fernandes (2009), *A Physiologically-based Model for Simulation of Color Vision Deficiency*, for the dichromacy matrices in `colour.py`.


## Multiple comparisons and permutation reference checks

Significance brackets now use Holm adjustment by default within each panel's tested
family. Benjamini-Hochberg is an explicit exploratory alternative; opting out of
adjustment warns when more than one pair is requested. Raw and adjusted values,
procedure, and family size are printed. A non-significant result is not an
assertion of equivalence.

The adjustment formulas were checked against the documented
[statsmodels procedures](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html),
then tested using hand-calculated vectors with ties, clipping, original-order
restoration, and a family where Holm and BH make different decisions. No new
statistical dependency is needed by generated scripts.

The historically named bootstrap significance method is an absolute-mean-gap
permutation test, separate from confidence-interval bootstrapping. Regression
fixtures enumerate all 70 assignments of two four-observation samples and verify
32/70 and 2/70 tails. Larger problems use fresh seeded draws and include the
observed assignment in numerator and denominator, following the randomized-test
counting explained in [SciPy's permutation documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).
Two-sided conventions differ; this tool explicitly uses the absolute mean gap.


## Submission font policy

| Source | Requirement recorded by the existing audit | Scope |
| --- | --- | --- |
| [IEEE iWEM 2026 submission page](https://attend.ieee.org/iwem-2026/paper-submission) | “Type 3 fonts (bitmaps) will not be accepted.” | One conference's submission page; the original audit recorded this quote. A fresh retrieval during implementation was blocked by robots.txt. |

This is one IEEE conference's page, not the IEEE Xplore PDF specification. The
verified claim in the original audit is that at least one IEEE venue rejects
Type 3 fonts in submitted PDFs. The general claim about all IEEE venues is not
verified here; consult the IEEE Author Center before making a broader claim.

Both generator presets now request embedded TrueType output through
`pdf.fonttype = 42` and `ps.fonttype = 42`. [Matplotlib's font documentation](https://matplotlib.org/stable/users/explain/text/fonts.html)
describes the supported PDF/PostScript font formats and subsetting. Every render
smoke case writes a PDF, checks for an embedded FontFile2 program, and rejects
Type 3 dictionaries. The check was exercised against a deliberately reverted
font configuration before committing.

## Composition contracts

Composition guards enforce implemented behavior: two-key facets and repeat sharing
are exercised on real figures; unsupported table/cut/panel combinations are rejected
instead of silently dropping fields. Reshape validation distinguishes input columns
from generated series/value columns. These are implementation correctness constraints,
not additional claims derived from visualization literature.
