# Review PDFs beside source-backed figures

Current source after immutable public0.8.0 includes PDF visual review in the local
paper workspace. Install the source package with its optional renderer:

```sh
python -m pip install './python[pdf]'
```

Open an existing [paper project](project-management.md), or create a genuine
PDF-only project without a plotting manifest:

```sh
mkdir paper
graphunslopify project-init paper --review-only
graphunslopify project-preview paper --open
```

A review-only project has no native figures or scientific acceptance. Native
audit/definition/shared-setting actions are unavailable; it does not create a
dummy verified figure or relax the source-backed audit manifest requirements.
Existing source-backed projects keep their original format.

## Browser workflow

1. Choose or drop a PDF in **PDF visual review**. Choose a source ID, one-based
   pages such as `1,2,5`, and preview DPI. Reusing a PDF source ID records a new
   attempt; choose a different ID from the native figure bindings.
2. Select the PDF in the figure list or scientific review selector. Browse actual
   saved pages and the four claims/uncertainty/legibility/reproduction groups.
   Claims, source data and uncertainty calculations remain untested. Legibility
   shows extractable text-size and raster-density measurements, with their scope.
3. Download the recorded page images, extracted text or JSON report. Asset bytes
   are checked independently against their recorded size/hash before serving.
4. **Inspect selected page again** records a new bounded attempt for the current
   registered PDF. Use the upload controls to replace a source or inspect a
   different page set. A failed attempt stays visible and does not borrow an
   earlier successful preparation.
5. Choose an explicit saved inspection in **Evidence to review** to inspect its
   historical report/pages. Saved native audits and saved PDF inspections retain
   separate scopes. **Saved runs & changes** also opens inspections in this pane.

An uploaded source copy stays in the project's ignored local `sources/` folder.
The original PDF is excluded from inspection history; page images and extracted
text still contain its content. Native definitions, datasets and prior history
remain unchanged. Back up the complete paper folder to retain uploaded sources
and local evidence. Native audits and PDF inspections share one owned job; wait
for it to finish before another write.

Changed or missing PDFs make saved measurements historical. Missing/modified
assets disable their preview/downloads even if the event receipt is intact.
Polling refreshes these states. Late requests/images cannot replace a newer
selection, and failed project transport clears the current preview/actions.

## CLI and revision guards

```sh
graphunslopify project-inspections paper
# Copy the returned inspection revision into REVISION:
graphunslopify project-inspect-pdf paper --id external --pdf input.pdf --expected-revision REVISION --pages 1 2 --dpi 144
graphunslopify project-inspections paper
graphunslopify project-review paper
```

The `--pdf` path resolves from the shell's working directory. Inspection queries
have their own revision, covering native inputs, inspection history, current PDF
hashes and saved asset state. The captured native snapshot must match its reviewed
revision, and the full inspection revision is checked again before event creation.
External edits during capture are refused without a new event. Locks preserve
other writers' ownership.

Both `project-review` and `project-inspections` accept `--event EVENT_ID` for
explicit saved evidence; the latter requires a PDF inspection. Its returned
revision still describes the current collection, not a historical write token.
Inside-paper source paths are relative and survive a complete project move;
outside CLI references retain their explicit absolute location.

`project-review` now returns a schema2 collection: native rows retain their IDs,
PDF rows have `source_type: "pdf"` and a typed `key` of `pdf:ID`. A selected native
audit never borrows later PDF evidence, and a selected PDF event supplies no
native scientific acceptance.

## Strict results and limits

The existing [PDF visual review engine](pdf-review.md) renders selected pages,
extracts available text and measures text size/raster placement density. It
performs no OCR, automatic figure location, chart reconstruction, numerical claim
validation or native plotting-program execution.

Successful visual preparation remains **incomplete with exit code2**. Original
data, numerical claims and general visual interpretation stay untested. Operation
`status: "failed"` means preparation failed, with the attempt/errors retained.
Read-query exit0 means the query succeeded; it does not grant scientific
acceptance. Completed visual-only events do not replace the latest native audit.
Incomplete/damaged history blocks current visual labels and further inspections.

Limits:50MiB PDFs, DPI72–300, at most50 selected pages, existing30-megapixel page
render bound, default120-second timeout and positive bounds up to600 seconds.
Reduce DPI for oversized page renders. Hashes/versions are consistency evidence,
not author authentication or verification of all dependencies, original data or
experimental validity.

Reviewed batch changes/guarded undo, selective native regeneration and consolidated
auditable review export remain separate open milestone87 work. Public0.8.0 does
not contain this source interface; no new package release is implied.
