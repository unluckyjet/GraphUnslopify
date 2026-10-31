# Retain source-free PDF inspections in a paper project

Current source after 0.8.0 adds persistent PDF visual-inspection history to an
existing [paper project](project-management.md). Install the source package with
its optional PDF renderer:

```sh
python -m pip install './python[pdf]'
graphunslopify project-inspections paper
```

Copy the returned `revision`, then prepare the actual selected pages:

```sh
graphunslopify project-inspect-pdf paper --id external-figure --pdf paper.pdf --expected-revision REVISION --pages 1 --dpi 144
graphunslopify project-inspections paper
```

The `--pdf` path is resolved from the current working directory.
Use the revision from `project-inspections`. It guards the current native inputs,
inspection history, source PDF hashes and saved asset state. A stale revision is
rejected. Inspection IDs must differ from native figure IDs. Reusing an inspection
ID records a new immutable attempt; a failed attempt does not fall back to an
older successful preparation.

The command reuses the existing [PDF visual review engine](pdf-review.md) in a
bounded subprocess. It measures extractable text size and raster placement
density, retaining the actual report, extracted text, page previews, renderer
version/DPI and original PDF SHA. It performs no OCR, reconstruction, numerical
claim validation or execution of native plotting programs.

The result remains **incomplete with exit code 2**, including successful visual
preparation: original data, numerical claims and general visual interpretation
remain untested. `status: "failed"` means preparation failed; its attempt and
errors remain in history. A successful read of `project-inspections` exits 0 and
does not grant scientific acceptance.

Native source-backed audit acceptance stays separate. The inspection cannot make
a failed native audit pass, and completed visual-only history does not replace
the latest native run. Damaged/incomplete history blocks a current visual label
and further inspections until repaired.

The query independently checks saved asset sizes and hashes, beyond the history
receipt. Changed/missing PDFs and modified previews remain historical or need
inspection. The original PDF is not copied into history. Generated page images
and extracted text do contain its content and stay in the project's ignored
local history. Source paths inside the paper are relative and survive a complete
project move; outside files keep explicit absolute references.

Choose local PDFs up to 50 MiB, DPI 72-300 and at most 50 selected one-based pages.
The existing engine also bounds individual page renders. Default timeout is 120
seconds; the CLI allows positive bounds up to 600 seconds. Original PDFs,
datasets and earlier history remain unchanged.

This is a backend milestone. New browser import/inspection controls, integrated
foreign-figure viewing and genuine review-only initialization remain open.
Current `project-init` still requires a source-backed manifest. Do not create a
dummy verified figure to represent an unknown source-free paper. The existing
history view labels PDF inspections and retains their machine-readable evidence.
