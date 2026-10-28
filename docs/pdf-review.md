# Review figures in an ordinary PDF

Current development adds `audit-pdf` for existing manuscripts, including PDFs
without GraphUnslopify metadata or original figure source files. It prepares
local page previews, extracted text and explicitly selected figure crops in an
offline HTML packet plus a JSON evidence report. This is visual review
preparation; numerical/source-data verification remains **incomplete**.

The published0.7.0 wheel does not include this command. From a current checkout:

```sh
python -m pip install -e './python[pdf]'
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
