---
id: 06
slug: disclose-composition-in-alt-text
status: done
priority: P1
title: Alt text describes a continuous axis on a figure whose axis is cut
source_idea: disclose-composition-in-alt-text.md
---

# Alt text describes a continuous axis on a figure whose axis is cut

## Problem

`encodingSentence` in `src/alttext.ts:36-104` builds level 1 of the alt text from the spec.
Its `parts` list covers, in order: the kind and axis labels with units, `group` and
`series_order`, log and symlog scales, `uncertainty`, `emphasis`, `reference_lines`, and
`facet`. I read the whole function. It covers nothing else.

Five fields that change what a sighted reader sees never reach it: `axis_break`
(`src/schema.ts:333`), `inset` (`:334`), `layers` (`:331`), `repeat` (`:332`) and
`series_from_columns` (`:303`).

The source idea ran it rather than reading it. A spec carrying
`"axis_break": { "axis": "y", "from": 30, "to": 60 }` printed:

```
alt text: Bar chart of Accuracy in % against Model. Values run from 8.48 to 82. The mean is 59.2.
```

A sighted reader sees the slanted marks at the join and knows the axis is cut. A
screen-reader user is told the values run from 8.48 to 82 on an axis that is not
continuous, with no signal that anything is missing. `src/codegen/compose.ts:169-174` states
the repo's own reasoning for drawing those marks: "without them a reader takes the axis for
continuous and misreads every distance across the gap, which is the failure the whole
truncation literature is about." The alt text is the same disclosure for the reader who
cannot see the marks, and it is absent.

The same holds, less acutely, for the rest. An inset is a magnified duplicate of one region;
alt text that omits it describes a chart with a stray rectangle. A layer adds observations
or a rug over the figure's own marks. `repeat` produces one panel per metric and, unlike
`facet` which *is* disclosed, nothing announces it.

`docs/research.md:133-137` records that PNAS and others now require alternative text, and
that levels 1 to 3 are derivable while level 4 is left to the author. A cut axis is an axis
fact, so it is level 1 by that model's own division. It is sitting in the spec, unread.

## Change

Extend `encodingSentence` in `src/alttext.ts` with one clause per feature, pushed into the
existing `parts` list in the same declarative style as the `facet` and `reference_lines`
clauses. Four clauses:

- **`axis_break`**: name the axis, the bounds, and the consequence. The consequence is the
  load-bearing half and is the sentence equivalent of the slanted marks — something of the
  form "the vertical axis is cut between 30 and 60, so distances across the gap are not
  comparable."
- **`inset`**: name the magnified region and the corner it sits in, both of which are in
  `InsetSpec` (`src/schema.ts:273-278`).
- **`layers`**: one clause naming each layer's mark and its `label`, skipping unlabelled
  layers the way the legend does (`LayerSpec.label` is optional and documented as "Omit to
  keep it out of the legend", `src/schema.ts:246`).
- **`repeat`**: mirror the existing `facet` clause — one panel per named field, listing the
  fields.

Position the composition clauses before the statistics rather than after, so that if length
becomes a problem the disclosure is not what gets truncated.

This is transcription, not inference. Every value comes from a field already in the spec.
Invent nothing.

## Acceptance criteria

1. `npm test` passes, and a new test asserts `encodingSentence()` returns a string
   containing the break bounds for a `line` spec carrying
   `axis_break: { axis: "y", from: 30, to: 60 }`, and containing a phrase stating that
   distances across the gap are not comparable.
2. Separate tests assert the clause is present for a spec carrying `inset`, for one carrying
   `layers`, and for one carrying `repeat`.
3. A negative test asserts that for each of the four fields, a spec without it yields a
   sentence not containing that clause.
4. A regression test asserts `encodingSentence()` for a plain `line` spec carrying none of
   the four fields returns a string byte-identical to the current output. Capture the
   current string as a literal in the test before making the change.
5. `npm run compose-check` passes, and the `axis_break`, `inset`, `layers` and `repeat`
   fixtures (`scripts/compose-check.ts:87-123`) each print an `alt text:` line containing
   their own clause.
6. `npm run baseline -- --check` passes with **no** diff to the fifteen baseline scripts.
   None of the fifteen baseline specs uses any of the four fields, so an empty diff is the
   regression guard. A non-empty diff means a clause is firing when it should not.
7. `npm run typecheck`, `npm test`, `npm run test:python`, `npm run render-check` and
   `npm run recipe-check` all pass.

## Out of scope

- Do **not** add a clause for `series_from_columns`. The source idea itself left it out of
  the first pass, on the grounds that it produces an ordinary grouped figure and may not
  change what the reader perceives at all. That judgement is correct; leave it.
- Do **not** change levels 2 and 3 (`emitAltText`, `src/alttext.ts:110` onward), which run
  in the emitted script against the data.
- Do **not** change `src/codegen/index.ts` or `src/codegen/compose.ts`. They embed whatever
  `encodingSentence` returns as `ENCODING_SENTENCE` and need no edit.
- Do **not** add a spec field, and do **not** make the wording configurable.
- Do **not** restructure the sentence-joining at `src/alttext.ts:103`. Each clause stays its
  own sentence so a screen reader pauses between them.

## Evidence

- **[verified] by me, in this repo.** I read `encodingSentence` in full
  (`src/alttext.ts:36-104`). The `parts` list covers kind, `group`/`series_order`,
  log/symlog, `uncertainty`, `emphasis`, `reference_lines` and `facet`, and nothing else.
  `axis_break`, `inset`, `layers`, `repeat` and `series_from_columns` do not appear in the
  file.
- **[verified] by the source idea, by running it.** The quoted `alt text:` line above is the
  actual output of an emitted script for a spec carrying `axis_break`. It is a measurement,
  not an argument.
- **no source, reasoning only, for the standard applied.** It is the repo's own: the
  four-level model behind MatplotAlt, already cited at `docs/research.md:165`, under which
  level 1 is the encoding and the axes. A cut axis is an axis fact. This applies a model the
  repo already adopted rather than making a new claim about it, so it needs no new citation.
- **[unverified] and explicitly not load-bearing:** the source idea states it did not
  confirm any journal policy requiring alt text to disclose axis discontinuities, and is not
  aware of one. I did not find one either. Do not write such a policy claim into
  `docs/research.md`. The argument is internal consistency, which is sufficient.

### Why P1 rather than P0

Only the `axis_break` clause closes a path by which a reader is actively misled; `inset`,
`layers` and `repeat` are disclosure gaps. After spec 01 lands, `axis_break` is legal only
on `line`, `scatter` and `heatmap` — and for line charts the repo's own position, stated at
`python/graphunslopify/inspect.py:415-417`, is that "Line charts are exempt; the same
truncation is defensible there." So the remaining misleading surface is narrow and bounded
to the kinds where the repo has already judged truncation defensible. Real, worth fixing,
not ahead of the five P0s.

### Interaction with spec 01

Spec 01 rejects `axis_break` on `bar`, `box` and `violin`. The example quoted above is a bar
spec, which will be unrepresentable once spec 01 lands. Write the tests in this spec against
`line` specs so they survive spec 01 regardless of merge order.

## Verification (2026-10-25)

169 Node tests passed without skips; 70 Python tests passed. Tests cover the
exact pre-change plain description and independent composition clauses. Real
composition renders assert and print their own break/inset/layer/repeat
disclosures. All seven gates passed; all 15 baseline scripts remain byte
identical because their specs use none of these composition features.
GitHub CI is checked after the milestone push.
