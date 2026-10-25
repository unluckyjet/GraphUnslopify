---
id: 09
slug: embed-type-42-fonts
status: done
priority: P2
title: Every PDF this tool writes uses Type 3 fonts, which IEEE submission portals refuse
source_idea: embed-type-42-fonts.md
---

# Every PDF this tool writes uses Type 3 fonts, which IEEE submission portals refuse

## Problem

`src/codegen/theme.ts` describes itself in its header as "Every presentation decision in one
place." It sets font sizes, line widths, tick widths and axis line widths through
`PRESETS[*].rc`. It does not set `pdf.fonttype` or `ps.fonttype`. I grepped `src/`,
`scripts/` and `python/` for `fonttype`: zero hits anywhere in the repo.

matplotlib's default for both is 3. Checked against this environment's interpreter rather
than the documentation:

```
$ python -c "import matplotlib; print(matplotlib.__version__, matplotlib.rcParams['pdf.fonttype'], matplotlib.rcParams['ps.fonttype'])"
3.11.1 3 3
```

`OutputSpec.formats` defaults to `["png", "svg", "pdf"]` (`src/schema.ts:86`) and `VENUES`
includes `ieee` (`src/schema.ts:68`). So the default output of a tool that advertises "Venue
presets set the column width and the font floor from the real submission guides"
(`README.md:31-32`) is a PDF that IEEE submission portals reject.

This is not hypothetical and it is not an argument from documentation. Every PDF committed
in `examples/baseline/` contains a Type 3 font today:

```
$ grep -a -o "/Subtype */Type[0-9]*" examples/baseline/01-training-curve.pdf
/Subtype /Type3
```

It fails at the submission portal, after the paper is written, and the error names a font
rather than a figure, so the cause is not obvious to the author. `VENUE_RULES`
(`src/codegen/theme.ts:53-60`) already encodes venue column widths and font floors as
first-class requirements. This is the same class of requirement, one field away, unset.

## Change

Two parts.

1. **Set it.** Add `"pdf.fonttype": 42` and `"ps.fonttype": 42` to the `rc` block in **both**
   presets in `src/codegen/theme.ts` (`paper` and `paper_compact`). Type 42 is TrueType,
   which embeds a real font program rather than a bitmap glyph procedure. The cost is a
   slightly larger PDF.

2. **Check it.** Assert in `scripts/render-check.ts` that an emitted PDF carries no Type 3
   font. **`render-check` currently emits PNG only** — `scripts/render-check.ts:30` sets
   `output: { formats: ["png"], dpi: 150 }` — so this change must also make it emit `pdf`
   for at least one spec, or the check runs against a file that does not exist.

   The check reads the PDF bytes and asserts no `/Subtype /Type3` occurs. Do not add a
   dependency for this: `pypdf` and `poppler` are not in this project, and a byte scan
   suffices because matplotlib writes font dictionaries uncompressed. I confirmed the scan
   works against the committed baseline PDFs, quoted above.

## Acceptance criteria

1. `npm run baseline -- --check` fails before regenerating and passes after. The diff to the
   fifteen committed scripts is exactly the two new `rc` entries in each — that narrowness
   is the confirmation the change reached the emitter and nothing else moved.
2. `grep -a -c "/Subtype /Type3" examples/baseline/01-training-curve.pdf` returns 1 on the
   committed PDF before the change and 0 after regenerating. Record both numbers in the
   review; the before-and-after is the whole point.
3. The same grep returns 0 for every regenerated PDF in `examples/baseline/`.
4. `scripts/render-check.ts` emits at least one PDF and fails the run if `/Subtype /Type3`
   appears in it. Verify the check is live by temporarily reverting the `rc` entries and
   confirming `npm run render-check` fails; restore before committing.
5. `npm run render-check` passes: all fifteen still run and still write their formats.
6. `npm run typecheck`, `npm test`, `npm run test:python`, `npm run recipe-check` and
   `npm run compose-check` all pass.
7. `docs/research.md` gains a row under a submission-policy heading carrying the IEEE quote
   and the scope caveat below, since that file is the repo's contract that every rule traces
   to a source.

## Out of scope

- Do **not** change `svg.fonttype`. It defaults to `path`, which converts text to outlines
  and makes SVG text unselectable and unsearchable. The source idea raised it as worth
  deciding deliberately, and it is — in its own spec, with its own evidence about downstream
  editing and accessibility tooling. Changing it here would move glyph rendering in every
  committed SVG under cover of a PDF fix.
- Do **not** add a `verify.ts` warning when `style.venue` is `"ieee"` and `pdf` is not in
  `output.formats`. The source idea proposed it and then withdrew it, saying "I have not
  confirmed that requirement and would leave it out of this idea rather than assert it."
  That was the right call.
- Do **not** write the general claim "IEEE rejects Type 3 fonts" into `docs/research.md`.
  Write the narrow verified claim, with its scope caveat. See Evidence.
- Do **not** add a spec field. This is entirely a generator decision.
- Do **not** add `pypdf`, `poppler` or any other PDF library.
- Do **not** claim a visual regression check. The source idea's fourth criterion was a
  by-eye check that glyph metrics did not shift; that is not runnable and is dropped.

## Evidence

- **[verified] by me, in this repo.** `grep -rn fonttype src/ scripts/ python/` returns
  nothing. `src/codegen/theme.ts:62-70` is the `paper` preset's `rc` block.
  `src/schema.ts:86` is the `formats` default; `src/schema.ts:68` is `VENUES`.
  `scripts/render-check.ts:30` sets `formats: ["png"]`.
- **[verified] by running the interpreter this project targets.** matplotlib 3.11.1,
  `pdf.fonttype = 3`, `ps.fonttype = 3`, `svg.fonttype = path`. Output quoted above. This is
  primary evidence for the exact version in this environment, not a documentation claim.
- **[verified] by inspecting the committed artefacts.**
  `grep -a -o "/Subtype */Type[0-9]*"` on `examples/baseline/01-training-curve.pdf` and on
  `examples/baseline/12-sweep-heatmap.pdf` each return exactly one match, `/Subtype /Type3`.
  This is the defect present in the tree today, and it doubles as proof that the
  dependency-free check in criterion 2 works.
- **[verified] the IEEE requirement, narrowly.** I fetched
  https://attend.ieee.org/iwem-2026/paper-submission — the submission page for the 2026 IEEE
  International Workshop on Electromagnetics (iWEM), which uses IEEE PDF eXpress. It states
  verbatim: "Embedded Type 1 or True Type fonts are required in the submitted PDF file as
  subset fonts. Type 3 fonts (bitmaps) will not be accepted."

  Scope caveat, to be carried into `docs/research.md` verbatim rather than smoothed away:
  this is one IEEE conference's page, not the IEEE Xplore PDF specification. The verified
  claim is that at least one IEEE venue rejects Type 3 fonts in submitted PDFs. The general
  claim about all IEEE venues is not verified here, and the implementer must confirm against
  the IEEE Author Center before writing anything broader.
- **[unverified], carried through and not load-bearing:** the source idea recalls similar
  Type 3 restrictions in ACM and some Elsevier workflows, and that Type 3 is the most common
  cause of font-embedding rejection for matplotlib and MATLAB figures. It found only blog
  posts, not primary policy. Do not write this into `docs/research.md`.

### Why P2

The source idea priced itself honestly and I agree with its pricing: "this is a compliance
fix, not an honesty fix. It does not close a way a figure can mislead a reader. It closes a
way a correct figure gets bounced." The diff is two lines plus a check, so the ratio is
excellent, but it does not outrank the honesty items above it.

## Verification (2026-10-25)

Before: all 14 committed PDFs contained Type 3; example 01 contained one Type 3
dictionary. After: all 14 contain embedded FontFile2 programs and zero Type 3
dictionaries. Every one of 15 generated scripts differs by exactly the two new
rc entries. The pre-regeneration drift check failed, then passed after rebuilding.
A negative control temporarily restored font type 3: all 16 render cases were
rejected by the new guard (exit 1), then the good settings were restored.
All seven local gates passed (176 Node / 74 Python, 16 PNG/PDF render cases,
25 recipes, 7 composition cases). SVG timestamp/ID-only noise was discarded.

The cited conference page could not be freshly retrieved (robots.txt/cache
restriction); research documentation attributes its short quote to the existing
audit and retains the narrow one-conference scope. No broader policy claim is
made. GitHub CI is checked after pushing.
