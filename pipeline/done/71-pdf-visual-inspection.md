---
id: 71
slug: pdf-visual-inspection
status: done
priority: P0
title: Inspect physical text size and raster resolution in extracted PDF figures
source_idea: review2026-10-28 item3 extracting and inspecting figures from PDFs with visual versus source-data checks distinguished
---

# Inspect physical text size and raster resolution in extracted PDF figures

1. Extend the existing PDF page/selected-crop packet with actual text-size and
   embedded-image-resolution evidence, context-bearing visual warnings and reviewed
   consequence/correction guidance. Account for text/form transforms, page rotation,
   cropping and declared UserUnit; do not confuse render DPI or nominal font size
   with the source figure's physical properties.
2. Bounded scans disclose truncation, unresolved/absent text and unsupported
   capabilities. Raster text/OCR, complex clipping/layers, experimental design and
   numerical/source-data claims remain explicitly unverified. Preserve default
   incomplete/exit2 and explicit preparation-only policy; never certify arbitrary
   chart semantics or identify an embedded image as a figure automatically.
3. Exercise actual PDF scaling/rotation/nested forms, raster/vector/scanned content,
   selected-region membership, unavailable metrics and correction/recheck with
   unchanged source bytes. Inspect real public manuscript output and actual HTML.
4. Refresh canonical diagnostic resources/generated references as necessary; prove
   existing figure pixels unchanged, seven gates, fresh offline installed behavior
   and exact pushed main/Figure CI before advancing. Public0.8.0 is immutable.

## Implementation and local evidence,2026-10-29

- PDF text metrics use nominal font x complete character-matrix y scale x
  resolved declared UserUnit. Image DPI uses source pixel counts and full image/
  parent-form transforms; geometric polygon/selection intersection excludes empty
  rotated bounding-box corners. PDFium viewport projection handles rotation/crops.
  Render scale includes UserUnit and guards finite/30MP output dimensions.
- Source PDF extra now requires tested pypdfium2>=5.14,<6. Bounded character/object/
  depth scans, unresolved metrics, invisible text, absent extractable text and
  capped samples stay explicit. Three new reviewed PDF codes bring shared catalog
  to139. Broad/numerical/source verification remains incomplete; prepare-only
  still reports incomplete with exit0 only for successful preparation.
-25 new independent primitive-PDF controls cover8/4pt, nested transforms, direct/
  indirect units, actual rendered red/blue pixel membership under4 rotations and
  crop,45-degree empty placement corners, raster density independent of preview
  DPI, invisible/raster-only content, thresholds, caps, missing metrics, malformed
  units and literal HTML. Existing30 PDF/7 diagnostic controls also pass.
- Exact public Gorman PDF SHA from docs: selected page8/Figure3 measures243
  extractable characters,8 small5.3127pt caption isotope superscripts and one
 2068x1623 raster at about299.9dpi. These are review candidates, not paper defects;
  internal raster labels/scientific claims remain unverified. Actual crop and
  desktop/mobile HTML visually checked, no overflow/external requests/JS errors.
  A resized full-page mobile capture repeated tiles despite one DOM heading;
  reused the vault's fresh-viewport/reload method and inspected viewport output.
- Seven local gates225 Node/1363 Python (zero skips/one upstream SQLAlchemy warning),
  Ruff90,15 baselines/16 renders/25 recipes/7 compositions and15/15 strict gallery
  pass. All60 tracked PNG pixel identities and52 README graphic placements match.
  Generated scripts/owned reference provenance and shipped translator/catalog
  refreshed. Final wheel's5 relevant source/resource files match current checkout.
- Real final fresh source-wheel base/extras/agent/PDF/context/comparison/workspace/
  tracking/editor/project/diagnostic/PDF-visual checks pass with external networking
  blocked. Installed native8pt→4pt reduction, unchanged PDFs, default exit2 and
  prepare-only exit0/incomplete measured by durable scripts/check-pdf-visual.py;
  all four installed CI variants now require this proof. No new PyPI release.
- Prior70 exact c99658f main40828774334 all9/Figure40828774194 passed before71.
  Exact new pushed main/Figure CI must pass before benchmarking advances.

Exact e8c6f7d695b3c43c2088bbfacf3357c7e6f4f1e6 main40835074311 all9 and
Figure40835074261 passed before certified-reference corpus72.
