---
id: 07
slug: axis-break-panels-false-positive
status: done
priority: P1
title: The render checker reports panels_disagree_on_y on every axis-break figure
source_idea: axis-break-on-bars.md
---

# The render checker reports panels_disagree_on_y on every axis-break figure

## Problem

`_check_panel_consistency` in `python/graphunslopify/inspect.py:452-490` collects every
visible axes that has data and is not labelled `<colorbar>`, then warns when they do not
share limits:

```python
for name, getter in (("y", "get_ylim"), ("x", "get_xlim")):
    spans = {tuple(round(v, 6) for v in getattr(ax, getter)()) for ax in axes}
    if len(spans) > 1:
        report.add("warning", f"panels_disagree_on_{name}", ...)
```

`emitAxisBreak` in `src/codegen/compose.ts:176-211` builds a cut axis out of two stacked
axes and then, by construction, gives them different y limits:

```python
lower.set_ylim(top=30)
upper.set_ylim(bottom=60)
```

Both halves are visible, both have data, and neither is a colourbar. So every axis-break
figure reports `panels_disagree_on_y`, saying "the panels use 2 different y ranges, so they
cannot be compared by eye. Set share_x or share_y, or say so in the caption." There are no
panels. The two halves are one axis with a gap in it, the different limits are the entire
mechanism, and `share_y` is not a field that exists on `BreakSpec`.

This is a standing false positive against a feature `README.md:158-165` showcases. It is the
same class of bug as the two `README.md:296-341` already records — a colourbar counted as a
panel, and tick labels measured that were never drawn — where the checker measured something
real and drew the wrong conclusion from it. A checker that cries wolf on a documented
feature trains its users to skim its output, which costs more than the finding is worth.

## Change

Give the break emitter a way to say what those two axes are, and teach the checker to
recognise it. Mirror the `<colorbar>` exclusion that already exists on the same line, rather
than inventing a second mechanism.

1. **`src/codegen/compose.ts`, in `emitAxisBreak`.** Set a matplotlib axes label on both
   halves, for example `upper.set_label("<axis-break>")` and the same on `lower`. Use one
   fixed literal and use it in both places. The break emitter is the only thing in the
   codebase that deliberately creates two axes with different limits, so this label is
   unambiguous.
2. **`python/graphunslopify/inspect.py`, in `_check_panel_consistency`.** Extend the
   existing filter at `:461-466` to exclude axes carrying that label, alongside
   `<colorbar>`.

Only the limits comparison is excluded. The series-colour-drift check in the same function
(`:479-490`) must keep running across break halves — a series changing colour between the
upper and lower half of one cut axis is a real error and stays one.

## Acceptance criteria

1. A Python test run by `npm run test:python` builds a figure with two axes carrying the
   break label and different y limits, calls `inspect_figure`, and asserts the report
   contains no finding with code `panels_disagree_on_y`.
2. A Python test asserts the same function still reports `panels_disagree_on_y` for two
   axes with different y limits that do **not** carry the label, proving the check was
   narrowed rather than disabled.
3. A Python test asserts `series_colour_drifts_between_panels` is still reported when a
   series has different colours on two axes that **do** carry the break label, proving only
   the limits comparison was excluded.
4. Render the `axis_break` fixture from `scripts/compose-check.ts:99-106`, which is a `line`
   spec, and run `inspect_figure` on the resulting figure. The report contains zero
   `panels_disagree_on_y` findings, where today it contains one. Record the before count in
   the review.
5. `npm run compose-check` passes and the `axis_break` fixture still emits and runs.
6. `npm run baseline -- --check` passes after regenerating. None of the fifteen baseline
   specs uses `axis_break`, so the expected diff to the baseline scripts is empty; the diff
   should appear only in `scripts/compose-check.ts` output if that is committed.
7. `npm run typecheck`, `npm test`, `npm run test:python`, `npm run render-check` and
   `npm run recipe-check` all pass.

## Out of scope

- Do **not** change `_check_truncated_bars` (`python/graphunslopify/inspect.py:410-428`),
  including its message, and do **not** exclude break axes from it. After spec 01 a bar
  cannot carry a break, and on a line chart the truncation rule does not fire.
- Do **not** add a `verify.ts` rule. That is spec 01 and it is already written.
- Do **not** fix the overlapping `"0"` and `"30"` y tick labels at the join, visible in
  `probe-bar-break.png`. That is a separate render-time defect in the break emitter, it is
  not in this queue, and it should stay visible rather than be fixed quietly here.
- Do **not** exclude break axes from any other check in `inspect.py` — text size, tick
  collisions, legend occlusion, overplotting and colour separation all still apply to both
  halves.
- Do **not** change how `inset` axes are treated. An inset deliberately has different limits
  from its parent and may well trip the same check, but that is a separate finding needing
  its own evidence, and this spec does not have it.

## Evidence

- **[verified] by me, in this repo.**
  `python/graphunslopify/inspect.py:452-478` is `_check_panel_consistency`; its filter at
  `:461-466` excludes only `<colorbar>`; the limits comparison at `:469-477` is what fires.
  `src/codegen/compose.ts:189-190` emits `lower.set_ylim(top=...)` and
  `upper.set_ylim(bottom=...)`, which guarantees the two spans differ. `fig.subplots(2, 1,
  ...)` at `src/codegen/compose.ts:179-185` guarantees both are visible and both are drawn
  into by `draw_panel`.
- **no source, reasoning only, and none is needed.** Those two facts are jointly sufficient:
  the emitter creates two axes with different y limits by construction, and the checker
  warns whenever two qualifying axes have different y limits. This is a claim about two
  files in this repo, not about the literature.
- The `<colorbar>` exclusion at `python/graphunslopify/inspect.py:461-466` is the precedent
  being copied, and `README.md:56-60` records why it was added: "a colourbar is an axes, so
  every heatmap looked like two panels disagreeing about their ranges." This is the same bug
  with a different artefact.

## Verification (2026-10-25)

Measured the real composition axis-break fixture before this change: one
panels_disagree_on_y finding. Re-rendered and intercepted inspection afterward:
zero such findings. The composition runner now requires inspection to run and
rejects this false positive. Python regressions prove unmarked ranges still
warn, marked halves still detect series colour drift, and small text still
fails. Seven local gates passed (169 Node / 74 Python, 15 unchanged baselines,
16 renders, 25 recipes, 7 composition cases); Ruff lint/format passed. GitHub
CI is checked on the pushed commit. Insets and other checks were left intact.
