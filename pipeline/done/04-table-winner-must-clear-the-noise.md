---
id: 04
slug: table-winner-must-clear-the-noise
status: done
priority: P0
title: The table bolds a winner by idxmax alone, and its uncertainty field is dead code
source_idea: table-highlight-inside-the-noise.md
---

# The table bolds a winner by idxmax alone, and its uncertainty field is dead code

## Problem

Two defects, both confirmed in the tree.

**One. The bold cell is decided by a bare argmax.** `mark_winners`, generated in
`src/codegen/compose.ts:269-285`, picks the winner with nothing but

```python
best = values.idxmax() if HIGHER_IS_BETTER else values.idxmin()
```

so 82.41 beats 82.40 and gets bold in the markdown, in the LaTeX and in the rendered image.
A results table is read for exactly that bold cell. `README.md:193-196` says so: "`highlight`
bolds the winner in each row or column", and "a printed number is exact rather than
estimated, so it outranks every graphical channel for reading one value." An exact number
0.01 ahead, presented as the winner, is the most emphatic assertion this tool can currently
make on the reader's behalf.

**Two. `TableSpec.uncertainty` is accepted and silently ignored.** `src/schema.ts:440`
declares `uncertainty: UncertaintySpec.optional()` on `TableSpec`. Grep
`src/codegen/compose.ts` for `uncertainty`, `_low` or `_high`: zero hits. `build_table`
(`src/codegen/compose.ts:250-267`) builds its own `groupby(...).mean()` and never calls
`summarise()`, which is the only place `_low`/`_high` are produced.

The two defects compound, and the second one lies to an agent. The `uncertainty` rule in
`src/verify.ts:267` matches on `"uncertainty" in spec`, which is true for `TableSpec`. So an
agent that sets `uncertainty` on a table with `aggregation: "none"` gets an
`uncertainty_without_aggregation` **error** telling it to set an aggregation — the linter
enforcing a contract for a feature that does not exist. The agent complies, satisfies the
linter, and receives a table with no intervals in it.

`docs/research.md:74-77` states the repo's position: the tool "could plot a mean over seeds
and throw the spread away silently, which is arguably worse than not aggregating at all."
The table is the one kind where it still does, and it is the kind that states its numbers
most emphatically.

## Change

Implement the field, then let it govern the bolding. All of this is in
`src/codegen/compose.ts`; no schema change.

1. **Compute the spread.** `build_table` returns three frames rather than one: the centre
   table it returns today, plus a low table and a high table, computed by the same rules
   `emitSummarise` uses for each `uncertainty.kind` (`src/codegen/data.ts:150-193`). Reuse
   the existing emitters rather than writing a second implementation of `sem`, `std`, `iqr`,
   `range` and the bootstrap; two implementations drift, which is the argument
   `README.md:218-221` already makes about the emitter.
2. **Render the spread.** `write_table` and `render_table_image` format a cell as its centre
   and its interval. Symmetric kinds (`std`, `sem`) may render as `82.41 ± 0.31`; asymmetric
   kinds (`ci`, `iqr`, `range`) render the interval. The exact glyph, spacing and LaTeX
   macro are presentation decisions the generator owns — pick them in `compose.ts`, not in
   the schema.
3. **Do not bold a winner that is not separated.** When `uncertainty` is present,
   `mark_winners` bolds the leader only if its interval clears every other cell's interval
   in that row (for `best_per_row`) or column (for `best_per_column`). When it does not
   clear them, bold every cell tied with the leader — a shared best. Bolding nothing would
   hide the finding; "these are indistinguishable" is itself the finding.
4. **Say which rows tied.** The script prints, before drawing, which rows or columns had a
   clear winner and which were ties, so the author writing the caption knows not to write
   "ours is best on every benchmark".

When `uncertainty` is absent, behaviour is unchanged: `idxmax`/`idxmin`, one bold cell, no
interval in the cell, no printed tie report.

## Acceptance criteria

1. `npm run compose-check` passes. Its `table` fixture (`scripts/compose-check.ts:124`) and
   `table_plain` fixture (`scripts/compose-check.ts:137`) both still emit and run.
2. The `table` fixture in `scripts/compose-check.ts` gains an `uncertainty` block and a CSV
   with several observations per cell, so the new path is exercised by the check suite. The
   `table_plain` fixture keeps no `uncertainty` and is the regression guard for unchanged
   behaviour.
3. Rendering the `table` fixture writes a `.md` in which every populated cell contains the
   interval (a `±` or a bracketed interval), and a `.tex` carrying the LaTeX equivalent.
   Grepping the two files for that marker is the check.
4. Two fixtures over the same spec, differing only in their CSV: in the first the leader's
   interval clears every other interval in each row, and exactly one cell per row is bold in
   the emitted markdown. In the second the leader's interval overlaps the runner-up's, and
   both are bold in the emitted markdown.
5. On the second fixture, the script prints a line naming that row as a tie. On the first it
   prints that the row had a clear winner.
6. Rendering `table_plain` (no `uncertainty`) produces markdown byte-identical to a
   committed expected-output fixture, proving the no-uncertainty path is untouched. Capture
   the current markdown as that fixture — a file under `test/` or a string literal in the
   test — **before** making any change, so the comparison does not depend on the reviewer
   having the pre-change tree.
7. `npm test` passes, and a test asserts `verify()` no longer promises unimplemented
   behaviour for tables: a `table` spec with `uncertainty` and a valid `aggregation`
   produces no error, and the emitted script for it references `_low` or the interval
   frames.
8. `npm run typecheck`, `npm run test:python`, `npm run recipe-check`,
   `npm run render-check` pass, and `npm run baseline -- --check` passes after regenerating.

## Out of scope

- Do **not** add a `tie` policy field, or any other field, to `TableSpec`. Hard-code "bold
  the tied set". If it needs to be configurable, that is a later spec with its own argument.
- Do **not** take the fallback the source idea offered — making `verify.ts` error that
  `uncertainty` is unsupported on tables. That was the minimum shippable version if this
  change proved too large. It is not; implement the field.
- Do **not** change the `uncertainty` rule in `src/verify.ts:267` or any of its four
  sub-checks. Once the feature exists, the contract it enforces is real.
- Do **not** add a `table` entry to `src/recipes.ts`. Reasonable companion change, not
  required here, and it would make the diff harder to review.
- Do **not** change how any non-table kind computes or draws its spread.
- Do **not** re-derive the interval maths. Share the emitters in `src/codegen/data.ts`.

## Evidence

- **[verified] by me, in this repo.** `src/codegen/compose.ts:269-285` is `mark_winners`
  with the bare `idxmax`. `src/codegen/compose.ts` contains zero occurrences of
  `uncertainty`, `_low` or `_high`, which I checked by grep — the field is dead.
  `src/schema.ts:440` declares it. `src/verify.ts:267-268` matches `"uncertainty" in spec`
  with no kind guard, so the rule does apply to tables. `src/codegen/data.ts:150-193` is
  where the interval maths already lives.
- **no source, reasoning only, and the reasoning is the repo's own.**
  `docs/research.md:74-86` already argues that discarding the spread silently is worse than
  not aggregating, and four lint rules exist to keep `uncertainty` honest for the other
  kinds. This spec applies a position the repo already took to the one kind it was never
  applied to. It asserts no new empirical claim, so it needs no new citation.
- Downgrade note: the source idea offered "[unverified] I recall the 'no bold without
  separation' convention being standard practice in ML results tables and stated explicitly
  in some venue author guides." I did not find a primary guideline saying it either, so it
  stays unverified and is **not** load-bearing here. Do not write it into
  `docs/research.md`. The argument for this change is the dead field plus the repo's own
  stated position on discarded spread, both of which are verified.

## Implementation clarification (2026-10-25)

The accepted external review correctly warns that overlapping intervals are not
proof of equivalence. Acceptance criteria referring to ties/shared best are
implemented as explicitly **overlapping intervals / no uniquely separated leader**,
with an equivalence caveat. Missing bounds receive no winner highlight. The
center values and bounds are computed through the shared summarizer.

## Verification (2026-10-25)

156 Node tests passed without skips, including numeric answers for all five
interval kinds, higher/lower row/column highlighting, missing intervals, overlap
wording, and byte-identical plain markdown captured before editing. A renderer
bounding-box check verifies interval text fits its cells; the composed table
image was opened and inspected. All seven local gates passed (60 Python tests,
15 unchanged baselines, 16 renders, 25 recipes, 7 composition cases).

Clarification above replaces the unsupported equivalence/tie interpretation in
the original proposed criteria; no p-values or equivalence verdicts are inferred
from overlapping intervals. GitHub CI is checked after the milestone push.
