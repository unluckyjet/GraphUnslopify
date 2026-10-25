---
id: 05
slug: correct-for-multiple-comparisons
status: done
priority: P0
title: Every significance pair is tested against a flat alpha, so five categories buy ten chances at a star
source_idea: correct-for-multiple-comparisons.md
---

# Every significance pair is tested against a flat alpha, so five categories buy ten chances at a star

## Problem

`SignificanceSpec` in `src/schema.ts:190-197` takes `pairs` with `.min(1)` and no maximum,
plus a single `alpha` defaulting to 0.05. `mark_significance`, generated at
`src/codegen/decorate.ts:193-226`, then draws inside the loop:

```python
for left_name, right_name in SIGNIFICANCE_PAIRS:
    ...
    p = compare(...)
    ...
    mark = "n.s." if p > SIGNIFICANCE_ALPHA else ("***" if p < 0.001 else "**" if p < 0.01 else "*")
```

Each pair is compared against the same nominal threshold, independently, with no reference
to how many comparisons are on the figure. An author who lists all pairs among five
categories gets ten tests. The figure then carries a star drawn by a tool whose entire
premise is that it will not let a figure assert what the data does not support.

This is worse than an ordinary uncorrected analysis, because bracket-and-star notation reads
as a verdict rather than as a number. `docs/research.md:53-60` argues `truncated_bar_axis`
is an error rather than a warning because readers keep misreading truncated bars even after
being taught about them. An uncorrected star is the same species: a strong signal with an
invisible caveat.

`src/verify.ts:398-404` has exactly one rule about `significance`,
`significance_without_uncertainty`, and it says nothing about how many pairs there are.

There is also an asymmetry to repair. `ClaimSpec` forces `within_tolerance` to declare its
tolerance — `claim_without_tolerance` is an **error** (`src/verify.ts:500-506`).
`SignificanceSpec` lets a figure declare ten hypotheses and defines none of the bookkeeping.

## Change

1. **A `correction` field on `SignificanceSpec`** in `src/schema.ts`: an enum of
   `"none" | "holm" | "benjamini_hochberg"`, defaulting to `"holm"`.

   The default is the point. Current behaviour is `"none"`, and leaving `"none"` as the
   default would make the honest path opt-in. Holm controls the family-wise error rate and
   is the conservative default; Benjamini-Hochberg controls the false discovery rate and is
   the right choice when the figure is exploratory and the author wants power. `"none"`
   stays available so that choosing it is a decision rather than an omission.

   This is meaning, not presentation: it states what "significant" is being taken to mean on
   this figure, in the same family as `uncertainty.kind` saying what the band means. The
   generator keeps owning the bracket geometry, the star glyphs and the stacking.

2. **Split the loop in `emitSignificance`** (`src/codegen/decorate.ts:191-226`). Today it
   tests and draws in one pass, which cannot work: an adjustment needs every p-value before
   any mark is chosen. Collect all p-values for the pairs that produced one, adjust, then
   draw in a second pass.

3. **Implement both procedures in numpy.** Each is a sort and a running comparison over the
   p-values. No scipy, so the `bootstrap` method keeps the "needs numpy and nothing else"
   property `docs/research.md:80-82` claims for it.

4. **Print both p-values, so the adjustment is auditable.** Replace the current
   `print(f"  {left_name} vs {right_name}: p = {p:.4g} ({mark})")` with a line carrying the
   raw value, the adjusted value, the procedure and the number of comparisons:

   ```
   baseline vs ours: p = 0.021, holm-adjusted p = 0.084 (n.s., 4 comparisons)
   ```

   With `correction: "none"` the line reports the raw p-value and says no correction was
   applied.

5. **One warning in `src/verify.ts`.** Code `uncorrected_multiple_comparisons`, severity
   `warning`, fires when `significance.correction` is `"none"` and `pairs.length > 1`. The
   message names the number of pairs.

## Acceptance criteria

1. `npm test` passes, and a test asserts `verify()` returns a `warning` with code
   `uncorrected_multiple_comparisons` for a `bar` spec whose `significance` has three pairs
   and `correction: "none"`, and returns no such finding with `correction: "holm"` or with a
   single pair.
2. A test asserts a `bar` spec whose `significance` omits `correction` parses with
   `correction === "holm"`, confirming the default.
3. A Python test run by `npm run test:python` asserts the emitted Holm and
   Benjamini-Hochberg implementations against a hardcoded input vector of p-values with
   hardcoded expected outputs, computed by hand from the published procedures and written
   into the test as literals. At least one vector must contain a tie and one must contain a
   value that Holm rejects but Benjamini-Hochberg does not, so the two procedures are
   distinguished rather than both passing a vector where they agree.
4. Render a `bar` spec with four pairs against a CSV drawn from a single distribution, so
   every true difference is zero. With `correction: "holm"` every printed pair line reads
   `n.s.`, and each line shows the raw and the adjusted p-value side by side.
5. On that same data with `correction: "none"`, the printed lines show the raw p-value and
   state that no correction was applied, and the figure still draws whatever stars the raw
   p-values earn — proving `"none"` preserves today's behaviour exactly.
6. `npm run typecheck` passes and `npm run compose-check` passes.
7. `npm run baseline -- --check` passes after regenerating. State in the review whether any
   baseline script changed: none of the fifteen baseline specs uses `significance`, so the
   expected diff is empty.
8. `npm test`, `npm run render-check` and `npm run recipe-check` all pass.

## Out of scope

- Do **not** add a warning or a cap for a large `pairs` count. The bracket stacking at
  `reach * 0.06` intervals (`src/codegen/decorate.ts:197`) does run off the top of the axes
  past roughly six brackets, but that is a render-time geometry defect and belongs in its
  own spec with its own threshold argument.
- Do **not** add a dependency. Holm and Benjamini-Hochberg are a sort and a cumulative
  minimum or maximum in numpy. **statsmodels is not available in this project** — the source
  idea suggested cross-checking against `statsmodels.stats.multitest.multipletests`, which
  is not a permissible check here. Use hardcoded expected values instead.
- Do **not** touch `src/recipes.ts`. No recipe uses `significance`; I grepped. Adding one is
  a separate change.
- Do **not** change `compare()` (`src/codegen/decorate.ts:158-188`), the choice of test, or
  the `bootstrap`/`ttest`/`mannwhitney` methods.
- Do **not** change `significance_without_uncertainty` in `src/verify.ts:398-404`.
- Do **not** change the star thresholds (`***`, `**`, `*`) or the bracket drawing.
- Do **not** make `mark_significance` print a line when it skips a pair for having too few
  observations. That is spec 08.

## Evidence

- **[verified] by me, in this repo.** `src/schema.ts:190-197` is `SignificanceSpec` with
  `.min(1)` and no maximum. `src/codegen/decorate.ts:193-226` is `mark_significance`,
  testing and drawing in one loop against a flat `SIGNIFICANCE_ALPHA`. `src/verify.ts`
  contains exactly one rule naming `significance`. No file in `src/recipes.ts` references
  `significance`; the only reference in the test suite is
  `test/features.test.ts:189-195`.
- **[verified] Zgraggen, Zhao, Zeleznik and Kraska, "Investigating the Effect of the
  Multiple Comparisons Problem in Visual Analysis", CHI 2018, doi 10.1145/3173574.3174053.**
  I confirmed the title, full author list, venue and year against dblp
  (https://dblp.org/rec/conf/chi/ZgraggenZZK18.html) and the ACM Digital Library, and
  confirmed the finding "over 60% of user insights were false" appears in the abstract.

  Scope caveat, carried through from the source idea and endorsed: this paper is about
  interactive visual exploration, not about star-annotated bar charts. It is evidence that
  the multiple comparisons problem is real and under-addressed in visualisation tooling
  specifically. It is not evidence about significance brackets. Do not stretch it further
  when writing the `docs/research.md` row.
- **[verified] Holm, S. (1979), "A Simple Sequentially Rejective Multiple Test Procedure",
  *Scandinavian Journal of Statistics* 6(2):65-70.** The source idea marked this
  `[unverified]` from recall. I checked the author, year, title, journal, volume, issue and
  pages and they are correct, so I have upgraded it to verified.
- **[verified] Benjamini, Y. and Hochberg, Y. (1995), "Controlling the False Discovery Rate:
  A Practical and Powerful Approach to Multiple Testing", *Journal of the Royal Statistical
  Society Series B* 57(1):289-300, doi 10.1111/j.2517-6161.1995.tb02031.x.** Also marked
  `[unverified]` in the source idea; author, year, title, journal, volume, issue, pages and
  DOI all confirmed, so upgraded to verified.

  Verified citations are not verified algorithms. I confirmed that these papers exist and
  say what they are said to say; I did not derive the procedures. Criterion 3 exists
  precisely so the implementation is checked against hand-computed values rather than
  against recall.
- **no source, reasoning only, for the illustrative 40% figure** in the source idea:
  1 - 0.95^10 = 0.401 assumes ten independent tests under the null. Pairwise comparisons
  among five groups are not independent, so the true family-wise error rate is lower. The
  number is illustrative and must not be written into `docs/research.md` as a result.

## Verification (2026-10-25)

Holm defaults and explicit no-correction warnings are checked through the schema
and verifier. Python tests execute actual emitter output against hand-calculated
vectors with ties, clipping, original-order restoration, and differing Holm/BH
decisions. A real null-data figure renders four adjusted n.s. comparisons; the
same figure with correction none prints raw values and explicitly says so.
The Python CI job installs Node dependencies so these numeric emitter checks
execute there rather than skipping. All seven local gates passed: 164 Node,
70 Python, 15 baselines, 16 renders, 25 recipes, and 7 composition cases. Ruff
lint and formatting also passed. GitHub CI is checked after pushing.

Adjustment families are per panel and include the pairs with usable p-values.
The raw permutation bug was fixed separately in spec 11 before this change.
