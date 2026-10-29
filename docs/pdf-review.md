# Review figures in an ordinary PDF

Version 0.8.0 adds `audit-pdf` for existing manuscripts, including PDFs
without GraphUnslopify metadata or original figure source files. It prepares
local page previews, extracted text and explicitly selected figure crops in an
offline HTML packet plus a JSON evidence report. This is visual review
preparation; numerical/source-data verification remains **incomplete**.

The published0.7.0 wheel does not include this command. Install the optional renderer (or use `python -m pip install -e './python[pdf]'` from a checkout):

```sh
python -m pip install 'graphunslopify[pdf]==0.8.0'
graphunslopify audit-pdf paper.pdf --pages 3 8 --out-dir pdf-review
```

Open `pdf-review/pdf-review.html`. Full-page PNG links support zooming; extracted
text can help locate captions. Text extraction is not OCR and can miss text in
scanned images. Rendering supports vector content as well as raster page images;
the tool does not assume that an embedded image is a scientific figure.

## Select a figure region

Use normalized coordinates `[left, top, right, bottom]` measured from the top-left
of the rendered page, with values between0 and1. Page numbers start at1. A
regions JSON file contains IDs unique ignoring case and explicit page selections:

```json
[{"id":"figure-3","page":8,"box":[0.07,0.07,0.93,0.62]}]
```

```sh
graphunslopify audit-pdf paper.pdf --pages 8 --regions regions.json --out-dir figure-review
```

The JSON report records the requested normalized rectangles and actual rounded
pixel bounds, PNG hashes/dimensions, text extraction availability/truncation,
source PDF hash and renderer version/resolution. The source PDF is never edited
or copied into the packet. Existing nonempty output directories are refused.
No URLs or scripts from the PDF are executed.

By default, successful extraction still exits **2** because scientific
verification is incomplete. For a workflow that only wants to prepare review
artifacts, explicitly pass `--prepare-only`: preparation succeeds with exit0,
but `status` remains `incomplete` and all unavailable checks remain `untested`.
Malformed PDFs, invalid selections, missing dependencies and preparation errors
remain nonzero even with that flag. Embedded provenance is identified when
available; it is neither authenticated nor a substitute for recalculating data.

Use the ordinary [manifest audit](paper-audits.md) when source specs/scripts and
data are available. This command does not infer numerical claims from paper
prose, reconstruct arbitrary datasets, decide whether a chart is misleading,
or certify a paper's experimental design. Selected crops are human annotations,
not automatic figure detection. Limits:50 selected pages,200 regions,72–300 DPI
and30 megapixels per rendered page; select fewer pages/lower DPI as needed.

## Current source: visual measurements

Source after0.8.0 adds physical text-size and embedded-raster-resolution inspection
in pages and selected figure crops. Install the source `./python[pdf]` extra;
it requires pypdfium2>=5.14. The published0.8.0 package retains preparation-only
behavior and does not have these new threshold options.

```sh
python -m pip install -e './python[pdf]'
graphunslopify audit-pdf paper.pdf --pages 8 --regions regions.json --out-dir inspected --min-text-pt 6 --min-image-dpi 150
```

The defaults are review thresholds, not universal journal requirements. Text size
uses the PDF font size and complete character transform, including nested form
scaling and declared UserUnit. Raster density uses original embedded pixel counts
and complete physical placement transforms. Raising preview DPI does not add
source detail. Rotation/cropped-page coordinates are mapped through PDFium;
normalized selections refer to the actual rendered page. JSON records physical
page points, canvas units and each coordinate unit's point size.

`pages[].visual` and `regions[].visual` hold separate checks, coverage and findings.
`checked` means the listed extractable metrics were measured; it does not mean a
figure passed readability or scientific review. Raster-only labels are not OCR-
inspected. Invisible/clip-only text is excluded when identified, but complex
clipping, optional layers and annotation appearances are not certified. An image
placement is not automatically identified as a scientific figure.

Warnings name the problem, scientific/visual consequence and recommended
correction. Small-text samples include size and location within the selection;
image samples retain source dimensions, x/y DPI and page-bitmap bounds. These
can locate a component for review without changing the PDF. Intentional scientific
subscripts may be flagged; warnings are candidates for inspection, not allegations
that the paper is wrong. A pixel-density check cannot detect prior upscaling.

Scans cap at50,000 characters/5,000 objects per page and15 form levels. Caps,
unresolved metrics and absent text remain explicit. Samples are bounded and
truncation is recorded. `not_applicable` raster checks mean no relevant embedded
page-content image placement was measured, not that raster-only labels were read.

The overall scientific status stays `incomplete`/exit2 even when these visual
metrics are available. `--prepare-only` still returns0 only for successful packet
preparation; it does not certify the visual or numerical checks. Invalid thresholds,
nonpositive/nonfinite UserUnit, unrenderable dimensions and extraction errors stay
nonzero. Source bytes are hashed before parsing and checked again after inspection.

The implementation is in `python/graphunslopify/pdf_visual.py`; independent
primitive-PDF tests cover declared sizes, nesting, physical units, cropping,
rotation, real rendered image membership and invisible content.
`scripts/check-pdf-visual.py` checks a fresh installed package outside the checkout
with external networking blocked by `scripts/install-smoke.py --pdf --require-pdf-visual`.

## Tested public manuscript

The actual [Gorman et al.2014 paper](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0090081&type=printable)
contains14 pages. Its downloaded PDF SHA-256 is
`cc2e8e08db55a110d5e849db35f7665e9c18c0c06cd7fce49dd3007846f3820f`.
Page8/Figure3 was rendered and visually checked using the committed
[selection](../examples/published-papers/gorman-2014.regions.json). It includes
the plotted panels, legend, axes and caption. The PDF report correctly leaves
source-data and numerical checks untested. This does not reproduce the paper's
isotope models; the separate [public-data examples](validation/published-papers.md)
document the descriptive computations actually tested.


Current source visual probe (2026-10-29) on that exact page8/Figure3 selection:
243 extractable characters measured,8 below6pt (minimum5.3127pt), and one
2068x1623 raster placement at about299.90-299.92 source DPI. Located small-text
samples are13/15 isotope superscripts in the caption; these are review candidates,
not an allegation of a scientific or typographic error. Labels inside the raster
remain unmeasured. Desktop1280/mobile390 HTML loaded both images without overflow,
external requests or script errors; numerical checks remained incomplete/exit2.
