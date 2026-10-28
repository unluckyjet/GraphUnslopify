# Visual figure comparisons

**Current source after 0.8.0.** Install the source checkout for this feature.
The existing PyPI0.8.0 release keeps its earlier machine/Markdown comparisons.

A source-linked audit now automatically creates a portable HTML before/after
report whenever `--baseline` is supplied. It shows saved images alongside actual
changes to inputs, settings, claims, findings, validation status and recorded
creation context. It does not execute earlier programs or reconstruct data from
pictures.

```sh
graphunslopify audit paper/ --out-dir audit-output
cp audit-output/audit.report.json before.json
# Edit your results or figure specifications, then:
graphunslopify audit paper/ --out-dir audit-output --baseline before.json
```

Open the HTML path in the returned `visual_comparison.html` field. The Markdown
summary links to it. Each audit preserves its own packet under
`runs/<run-id>/comparison/`:

- `index.html`: self-contained, offline before/after pictures, visible difference
  map, optional blend slider, status and explanations with expandable evidence.
- `comparison.report.json`: [version1 machine evidence](comparison.schema.json).
- `images/`: verified-source previews and difference maps with their own hashes.

HTML embeds its images and needs no adjacent files to view or share. The JSON
packet's preview references remain relative to its own folder. Original source
programs and raw dataset files are not copied into the comparison packet.
Pictures and included claim/settings evidence may still contain your research.

## Compare existing saved runs

```sh
graphunslopify compare before.json after.json --out-dir figure-comparison
```

This command loads the two saved reports and their exported files. It does not run
programs, import their code or reread datasets. Output must be a new/empty folder,
so prior evidence survives. Both reports must satisfy the audit contract, with
unique stable figure IDs and finite JSON values.

New audits record an absolute `artifact_root` locator, making a copied baseline
JSON useful on the same computer while the original run images still exist.
For a moved archive, put reports beside the original relative `runs/` tree, or set
roots explicitly:

```sh
graphunslopify compare before.json after.json --out-dir comparison \
  --before-root archived-before --after-root archived-after
# During a fresh audit:
graphunslopify audit paper/ --baseline before.json --baseline-root archived-before
```

An explicit root is exclusive. Without one, the report's folder and recorded root
are tried; automatic audits also try their current output root for older copied
baselines. Every image must match its saved byte count and SHA256. PNGs also check
any recorded decoded-pixel fingerprint. Traversal, absolute output paths and
symlink escapes are refused. Missing, changed or corrupt files stay unavailable;
they never become evidence that two figures match. Preserve saved run directories
for visual review; copying JSON alone retains only the earlier nonvisual facts.

## Images and measurements

The preview chooses one shared format per stable figure ID, preferring PNG, then
SVG, then PDF. Renamed stems still match by ID/format. If no shared format exists,
each side can show its own supported preview, without a cross-format pixel score.
All recorded export-byte changes remain available separately. A representative
PNG does not establish equivalence of every SVG/PDF/HTML export.

- **PNG:** decode the exact saved static image. Previews strip original metadata;
  original byte hashes and decoded RGBA fingerprints remain separate evidence.
- **PDF:** with `graphunslopify[pdf]`, rasterize a one-page figure at144DPI using
  pypdfium2. Multi-page manuscripts belong in `audit-pdf`. This is a selected
  raster view, not PDF font, vector-structure or accessibility equivalence.
- **SVG:** show a verified UTF-8 SVG as a passive browser image. Entity declarations and other encodings are refused. Server-side pixel
  metrics remain unknown. Browser image mode disables document scripting and
  external resources; the HTML also restricts resource access with CSP.
  See the [SVG image processing requirements](https://www.w3.org/TR/SVG/latest/conform.html).
- HTML/animation-only records receive an explicit static-export recommendation.
  Previews are bounded to20MiB per saved/encoded image and30million raster pixels.

Comparable PNG/PDF pairs use their native dimensions. The report records counts
of changed **RGBA pixels**, and separately changed **visible RGB pixels over a
white background**, with maximum and mean absolute RGB channel deltas on0–255.
RGB hidden under full transparency can change the first count without changing
the visible picture. The magenta difference map marks locations, not severity.

Unequal canvases show both dimensions and no pixel score. No automatic resizing,
registration or cropping hides such a change. These are exact decoded-pixel
comparisons of decoded channels, not perceptual-similarity, ICC color-managed
equivalence or statistical-equivalence measures. Original color profiles are not
applied to the channel measurements or normalized PNG previews.

## Meaning and exit policy

Explanations show actual before/after claim verdicts, setting paths, errors,
findings and creation-context differences. Changed numeric fingerprints can
reflect column/type/row-order changes; a changed file hash alone cannot identify
changed values. Context changes are possible explanations, not established causes
of image differences. Identical pixels do not establish scientific validity.

Current figure verification remains strict, and
`--fail-on-change` additionally rejects recorded changes. A partial visual packet
is explicitly marked `preview_status: partial` and rejects the automatic audit
with exit2. The current figure's check status is preserved: `status: passed` with
exit2 can mean its source checks passed but requested comparison evidence was
unavailable. The policy records `require_visual_comparison: true`; the packet
records the same final exit. Its own exit is2 when previews are incomplete or
the after audit's status/policy failed. The standalone
`compare` command returns that exit:0 for complete previews with an accepted after
run,2 for missing previews or an unaccepted after run. A successful comparison can
still describe substantial changes. Input/command errors also exit2.

Implementation: `python/graphunslopify/comparison.py`, `comparison_html.py`,
`audit.py`, `cli.py`. Verification: `test_visual_comparison.py`, actual CLI helper
`scripts/check-visual-comparison.py`, and `npm run comparison-check` for browser
controls, passive SVG, network isolation and narrow-screen layout. Installed-wheel
CI enables `scripts/install-smoke.py --require-comparison` on all four platforms;
omit the flag when checking an older released wheel.

For nonvisual-only saved-fact comparison, `graphunslopify.audit.compare_audits(before, after)` remains available; it does not load images.
