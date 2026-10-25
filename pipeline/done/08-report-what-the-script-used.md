---
id: 08
slug: report-what-the-script-used
status: done
priority: P1
title: The script records what it was asked to do, never what it actually used
source_idea: report-sample-size.md, account-for-dropped-rows.md
---

# The script records what it was asked to do, never what it actually used

Two inbox ideas — `report-sample-size.md` and `account-for-dropped-rows.md` — proposed the
same printed accounting block from the same two functions. Shipping them as separate specs
would have the second implementer either duplicate the first one's block or restructure it,
so they are merged here. One spec, one function, one block.

## Problem

`docs/research.md:62-72` states the repo's reproducibility argument: "the tool emits a script
instead of an image, so the script is the reproducibility record", and each script carries
its tool version, a spec hash and a data hash. The script records what it was *asked* to do.
It does not record what it actually *used*, and the two differ in two ways.

**One. Rows disappear and nothing counts them.** Grepping `src/codegen` for `dropna` and
`isfinite` finds row loss at eight sites, all verified:

| Where | What drops |
| --- | --- |
| `data.ts:209` | `bootstrap_interval` drops non-finite values per group before resampling |
| `decorate.ts:37` | the trendline fit keeps only `np.isfinite(x) & np.isfinite(y)` |
| `decorate.ts:54` | the Pareto frontier drops rows with `dropna()` |
| `decorate.ts:159-160` | `compare()` filters both arms to finite values before the test |
| `decorate.ts:247` | the annotation locator drops rows |
| `draw.ts:42, 346` | series names and box/violin groups drop NaN |
| `index.ts:276, 313` | facet names and series names drop NaN |

`emitPrepare` at `src/codegen/data.ts:46` reacts to row loss only in the total case:

```python
if df.empty:
    raise SystemExit("every row was filtered out")
```

So a `filter` clause removing 90% of the rows produces a figure with no note, and a column
with 40% missing values produces a figure computed from 60% of the data with no note. None
of it is visible in the PNG, the alt text, or the printed output.

**Two. The sample size is never stated.** `emitSummarise` collapses repeats with
`grouped.mean()` (`src/codegen/data.ts`) and never counts what it collapsed. `emitAltText`
(`src/alttext.ts:110` onward) generates level 2 statistics — "Values run from ... to ...",
"the mean is ..." — and never states *n*. A mean over two seeds and a mean over fifty render
identically. `README.md:71-73` describes its own showcase as "mean of five seeds with 95%
bootstrap intervals"; the figure does not say five, and neither does the alt text, the
caption block, or the LaTeX output.

Related, and cheap while the code is open: `mark_significance` at
`src/codegen/decorate.ts:206-207` does a bare `continue` when `compare()` returns `None`,
so a pair with too few observations vanishes from the figure with no note.

## Change

One function, `report_counts()`, emitted from `src/codegen/data.ts` and called from the
generated `main()` before drawing — next to where the spec hash and data hash are already
printed (`src/codegen/index.ts`, around the `DISCLOSURE` and `data sha256` prints). It
prints one block:

```
data: results.csv, sha256 3f2a1c...
  2400 rows read
  1200 rows after filter (dataset == "cifar")
  1188 rows with a finite accuracy (12 dropped)
  n = 5 per point
```

Four requirements on the block:

1. **Rows read, rows surviving `filter`, and rows with a finite y.** Threaded through
   `emitLoad` and `emitPrepare` in `src/codegen/data.ts` with a small counter. The filter
   line names the clause that removed the rows.
2. **Per-group *n*, printed whenever `aggregation` is not `"none"`.** `n = 5 per point` when
   uniform; `n ranges from 1 to 5 across 20 points` when ragged. Nothing is printed for this
   line when `aggregation` is `"none"`.
3. ***n* in the generated alt text**, as part of level 2, since level 2 is statistics
   computed from the data and *n* is one. Add it to the parts list in `emitAltText`
   (`src/alttext.ts`) for the aggregated cases only.
4. **A warning when *n* is unequal across groups.** An unbalanced comparison is a real thing
   an author may intend, so it is disclosed rather than refused. The script exits 0.

And one line elsewhere: `mark_significance` (`src/codegen/decorate.ts:206-207`) prints which
pair it skipped and why, instead of a bare `continue`.

This spec **owns** `report_counts()`. Any later spec that wants to add an accounting line
adds it to this block rather than printing its own.

## Acceptance criteria

1. `npm run render-check` passes: all fifteen baseline scripts still run to completion, and
   each prints a `report_counts()` block whose "rows read" equals `wc -l` on its CSV minus
   the header line. Check at least three of the fifteen explicitly.
2. Render `examples/specs/09-uncertainty-band.json` (mean over seeds with bootstrap
   intervals). The run prints a line naming the per-point *n*, and the alt text written into
   the PNG metadata contains that number. Read it back out of the PNG metadata to confirm.
3. Render `examples/specs/03-single-run.json` (no group, no aggregation). The block prints
   the row counts but **no** *n* line and the alt text contains no *n*, proving the sample
   size report is scoped to aggregated figures.
4. Take any spec carrying a `filter`, poison its CSV by blanking 10% of the y column, and
   render. The printed block names the exact number of rows dropped for a non-finite y, and
   the run exits 0.
5. Feed a CSV where one series has a single observation per x. The block reports the ragged
   range (`n ranges from 1 to ...`) and the run exits 0.
6. A `bar` spec with `significance` over a pair where one arm has fewer than two finite
   values prints a line naming that pair and the reason, instead of silently omitting the
   bracket.
7. `npm run baseline -- --check` passes after regenerating. The diff must be additive and
   confined to the load, prepare, alt-text and `main()` paths; the *n* lines must appear only
   in scripts whose spec has `aggregation` other than `"none"`.
8. `npm run typecheck`, `npm test`, `npm run test:python`, `npm run recipe-check` and
   `npm run compose-check` all pass.

## Out of scope

Cut from the source ideas, deliberately:

- **The six local `dropna` sites in `draw.ts` and `decorate.ts` do not report into the
  counter.** `account-for-dropped-rows.md` named this "the largest part of the diff and the
  part most likely to be cut to scope", and said "the load-and-filter accounting alone is
  worth shipping on its own". Agreed. Account for load, `filter`, and non-finite y. Leave
  the trendline fit, the Pareto frontier, the annotation locator, the series-name and
  facet-name enumerations alone.
- **No error when a group ends up empty but is still named in `series_order`, `claims` or
  `significance.pairs`.** Proposed by `account-for-dropped-rows.md`. It is a reasonable rule
  and it needs its own spec, because deciding whether to fail the render is a separate
  argument from deciding to print a count.
- **No count of the points a log axis refuses to draw.** Proposed as "related and cheap"; it
  is a different mechanism (matplotlib silently dropping non-positive values at draw time)
  and needs its own check.
- **No hard failure anywhere.** `report-sample-size.md` asked for a non-zero exit when
  *n* = 1. Spec 02 already removes the misleading artefact that made *n* = 1 dangerous — the
  fabricated zero-width band — so all that remains here is disclosure.
- **No `n = 5` annotation drawn on the figure.** The source idea explicitly declined it for
  a first pass; it costs space at column width and the printed line plus the alt text close
  the gap.
- Do **not** change `bootstrap_interval`'s `len(values) < 2` branch or the `_low`/`_high`
  assignment. That is spec 02, which lands first.

## Evidence

- **[verified] by me, in this repo.** Every file and line in the table above was confirmed
  by grep. `src/codegen/data.ts:46` is the only row-loss reaction in the emitter.
  `src/alttext.ts` contains no *n*, count or sample-size clause — I read the function.
  `src/codegen/decorate.ts:206-207` is the bare `continue`.
- **[verified] Cumming, Fidler and Vaux, "Error bars in experimental biology", *Journal of
  Cell Biology* 177(1):7-11, 2007.** I fetched
  https://pmc.ncbi.nlm.nih.gov/articles/PMC2064100/ and confirmed the authors, journal,
  volume, issue, pages and year. Rule 2 verbatim: "the value of *n* (i.e., the sample size,
  or the number of independently performed experiments) must be stated in the figure
  legend." Rule 1, "when showing error bars, always describe in the figure legends what they
  are", is already satisfied by `encodingSentence` (`src/alttext.ts:78-91`), which names the
  interval kind and its level. Rule 2 is not. Rule 3, confirmed verbatim as "error bars and
  statistics should only be shown for independently repeated experiments, and never for
  replicates", is the argument for reporting the number rather than only its existence: a
  reader cannot tell repeats from replicates without it.
- **no source, reasoning only, for the row accounting.** `account-for-dropped-rows.md`
  offered none and did not need one — the argument is that this repo already decided the
  script is the reproducibility record, and a record that omits its denominator is not one.
  Every fact supporting it is a file and line in this tree, listed above.
- **[unverified] and not load-bearing:** both source ideas recall publisher reporting
  checklists requiring exclusion criteria, excluded counts, and exact per-group sample sizes
  (Nature was named). Neither could fetch a primary policy page, and neither leaned on it.
  Do not write these into `docs/research.md`. Cumming's Rule 2 is the load-bearing citation
  for the *n* half; the repo's own stated goal is the load-bearing argument for the row half.

## Fixture correction discovered during implementation

The existing 03-single-run spec actually declared aggregation mean and pooled
all models/seeds. To satisfy its documented single-run purpose and criterion 3,
it now explicitly selects model ours / seed 0 and sets aggregation none. The
training CSV has three seeds, not the five used by the separate README showcase;
accounting reports the measured three for examples 01/09. PNG metadata assignment
is repaired as a prerequisite for criterion 2 (the computed description was not
previously assigned to ALT_TEXT).

## Verification (2026-10-25)

All seven local gates passed: 176 Node tests without skips, 74 Python tests,
15 generated baseline scripts, 16 render cases, 25 recipes, and 7 composition
cases. Three gallery inputs were checked against their physical CSV row counts.
The band PNG metadata contains N = 3 per point; the corrected single-run PNG
contains no summary n. A 20-row fixture with two missing values and a filter
reports 16 retained rows, 14 finite values, and n ranging 1–2; an insufficient
significance pair names its missing observations. Facet/repeat counts are
checked independently of summary calls.

Read back all 15 baseline PNG descriptions and compared RGB pixels against
HEAD: only the intentionally corrected single-run figure changed visually.
Timestamp-only regenerated PDFs were discarded except that corrected figure.
The metadata assignment fix is the necessary exception to the original purely
additive expectation, because without it the required PNG metadata was empty.
Replicate independence and other local drop sites remain separate roadmap work.
GitHub CI is checked on the pushed commit.
