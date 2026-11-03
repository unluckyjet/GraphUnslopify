# Check an exported figure for a journal

Current source adds offline technical checks against dated official-source
profiles. This inspects the exported file, including its physical dimensions;
choosing `style.venue` or a publication preset does not establish compliance.

```sh
graphunslopify journal-profiles
graphunslopify journal-check figure.pdf --profile nature-final-graphs \
  --target-width-mm 89 --output journal-report.json
graphunslopify journal-check Fig1.tif --profile plos-one-main --json
```

Use the current checkout's Python package. Public0.8.0 does not contain these
commands. No account, uploaded data, network lookup, program execution or format
conversion occurs. The input is unchanged and the report cannot overwrite it.

## Use either local workspace

In the figure editor, render a figure and open **Journal technical checks** in
Settings & checks. In the paper workspace, choose an intact saved audit and
figure under Saved runs & changes, then open the same journal section.

1. Choose a journal and submission stage. Read its scope, official source and
   checked UTC date.
2. Choose an actual saved export. Optionally enter your requested physical width
   in millimetres; the browser uses a0.5mm tolerance.
3. Select **Check this export**. Review each observed measurement, failure or
   unavailable check, followed by the manual-review list.
4. Download the JSON report to retain the exact source/rule hashes and the saved
   render or history context.

For a Nature format failure,choose an existing saved PDF if one is available.
Otherwise **Review adding a PDF export** opens a proposal that retains existing
formats. Review its before/after formats,check the author-review box and apply.
The figure editor uses normal undo and renders again. In the paper workspace,
save the proposed current definition and regenerate/audit,then check its new PDF.
No corrected verdict is transferred from the old export. Changed journal/editor
selections invalidate the proposal; a historical figure cannot modify another
selected definition. Authored scripts retain their own source controls.

The figure editor checks only exports registered by that local session. The
paper editor checks native exports from intact recorded audit history,using the
existing20MiB artifact boundary. Imported manuscript-PDF inspection events do
not yet supply journal exports through this panel. The CLI can inspect supported
single-figure files up to64MiB separately.

Editing a specification, changing the data or choosing another render/history
selection invalidates displayed evidence. Pending replies for old inputs cannot
replace a newer report. Dirty paper definitions and changed project revisions
cannot be presented as current journal checks. A saved historical export remains
explicitly historical; its technical result does not update the paper's
scientific acceptance. Journal/profile/width changes require a new check.

## Profiles and their scope

| Profile | Applicable context | Supported technical evidence |
| --- | --- | --- |
| `nature-final-graphs` | Nature final print graphs/line art after acceptance in principle; excludes photographs and Extended Data | Preferred vector formats; conditional fallbacks require manual confirmation. Physical PDF/EPS metadata, supported PDF glyph minimum and explicit author width. Standard89/183mm widths remain guidance. |
| `plos-one-main` | PLOS One main-article figures after provisional editorial acceptance; excludes supporting information | TIFF/EPS format, physical width2.63–7.5in, height at most8.75in, raster density300–600dpi on both axes, and the strict summary file-size bound below10,000,000bytes. |

Sources reviewed2026-11-03UTC:
[Nature final submission](https://www.nature.com/nature/for-authors/final-submission),
[PLOS One figures](https://journals.plos.org/plosone/s/figures).
Nature's official indexed page text was available; a direct request redirected
to its identity service. That access limitation is included in the profile.
PLOS waives these formatting rules before provisional acceptance; choosing this
profile does not turn them into initial-submission requirements. Its summary
says below10MB while later prose says10MB or less; this checker uses the stricter
summary boundary and records it explicitly.

Profiles are policy snapshots, not live publisher verification. The report gives
the source URL, checked date, stage, all rules and their SHA256. A snapshot older
than180days, or dated after the inspection date, makes technical acceptance
incomplete until the source is rechecked. Future source updates need a new dated
profile revision; old reports retain their rules and evidence.

Nature's current indexed official guidance distinguishes preferred AI/Postscript/
vector EPS/PDF from JPEG,Office and CorelDraw fallbacks when preferred formats
cannot be supplied. This profile leaves fallback format acceptance incomplete
until those conditions are reviewed; it checks actual JPEG300–600DPI and retains
the CorelDraw version8 limit for manual review. An unlisted format in this scoped
profile is not a claim about every publisher/artwork context.

## What is measured

Raster files must decode and have explicit physical resolution. TIFF resolution
tags require their units; missing DPI never becomes an assumed72 or300dpi. Both
horizontal and vertical density are checked. Multi-image TIFFs are unsupported
rather than silently reduced to their first image.

PDF measurement uses the visible page box intersected with its media box, actual
UserUnit and orthogonal rotation. Protected or multi-page PDFs remain incomplete.
SVG inspection requires absolute dimensions. EPS inspection reads numeric DSC
header bounds only, preferring high-resolution bounds; PostScript is never run.
EPS bounds do not prove actual ink bounds or embedded-raster density. Other
officially allowed formats without a local inspector remain incomplete.

With the optional `[pdf]` extra,PDF checks measure a bounded subset of non-invisible
extractable glyphs at their transformed physical size,including UserUnit/rotation.
Nature's5pt minimum is checked for those glyphs. No glyphs,raster-only text,
partial extraction or missing PDFium remains unavailable. A minimum-size pass
does not establish font family,ordinary-text versus panel-label roles,outlined
labels,complete visibility or readability. The7pt ordinary maximum and8pt panel
labels need role-aware manual review; the checker does not apply a universal7pt
maximum to valid panel labels. Page/object/character bounds stay explicit.

`--target-width-mm` is the author's explicit requested final width. It checks the
file with a default0.5mm tolerance, configurable with `--width-tolerance-mm`.
It never substitutes a nominal canvas width. A tightly cropped seven-inch figure
can fail a177.8mm target even if its original figsize was seven inches. This is a
new production check; it neither edits old benchmark files nor weakens their
frozen tolerance.

## Read the result correctly

Exit0 means the **supported technical subset** passed. Exit2 means a technical
failure, missing evidence, stale profile or invalid request. JSON retains every
check, the exact input SHA256/size, profile SHA256, date, observed dimensions and
missing measurements. Changed input during inspection cannot reuse an earlier
snapshot's technical acceptance.

Every result retains manual review items. Unmeasured font sizes/families,panel lettering,
editable text, strokes, embedded-image originals, white space, content, captions,
image integrity and current publisher instructions require further evidence or
author review. `submission_ready` is unknown and `scientific_verification` is
`not_performed`, even when the technical subset passes. This command does not
grant a manuscript acceptance or scientific certificate.

The native generator currently exports PNG/SVG/PDF. It does not automatically
produce PLOS TIFF/EPS; the checker reports that format mismatch rather than
renaming a file or claiming a conversion occurred.

## Python and verification

```python
from graphunslopify.journal import check_journal, journal_profiles

profiles = journal_profiles()
report = check_journal("figure.pdf", profile="nature-final-graphs", target_width_mm=89)
print(report["status"], report["checks"], report["manual_review"])
```

The first checkpoints provide the API/CLI foundation and both public workspace
panels; the next adds supported PDF glyph evidence,conditional format scope and
reviewed PDF-export corrections. Acceptance and measured evidence are tracked in
[spec90](../../pipeline/done/90-journal-compliance.md). The complete new initiative
retains [all thirty requested ideas](../../pipeline/research-platform-roadmap.md).
Real-artifact controls live in `python/tests/test_journal.py`, including tight
exports, missing/anisotropic DPI, PDF rotation/units/crops, false extensions,
multi-image/page files, EPS nonexecution, changed snapshots and source overwrite
refusal. No experiment on researcher adoption is implied by these checks.

`npm run journal-check` drives both real browser workspaces,checks actual export
hashes and identical report downloads,and holds replies while width or editor
inputs change. It also checks dirty-paper history navigation,wrong-figure
correction refusal,author review/undo/save/audit,new real PDF checks and rejected
stale proposals,while preserving the separate scientific status. Set `PYTHON`
to the intended Python executable.
`GRAPHUNSLOPIFY_JOURNAL_EVIDENCE` selects a new evidence directory;
`GRAPHUNSLOPIFY_JOURNAL_INSTALLED=1` exercises an installed wheel without a source
PYTHONPATH. Current/minimum/fresh evidence and exact-commit CI are required before
publishing each checkpoint; code or a proposed test is not a successful run.
