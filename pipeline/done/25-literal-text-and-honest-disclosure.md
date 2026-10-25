---
id: 25
slug: literal-text-and-honest-disclosure
status: done
priority: P0
title: Preserve literal author text in LaTeX and avoid certifying unknown data origin
source_idea: focused export/disclosure defect found during independent scientific references 24
---

# Literal text and honest disclosure

The baseline compiler inserts caption/description/table labels directly into TeX. A real fixture
containing all ten TeX special characters fails pdflatex with a runaway caption argument. It also
prints “the underlying data were not” generated, although input origin is unknown and its own demo
is synthetic. These are concrete, bounded defects split from spec 24's broader reference matrix.

Escape literal text once in figure caption/description and table heading/row/cell text. Keep raw
spec/metadata/data and numeric interval/highlight semantics unchanged. Disclose code generation
and tool/spec identity without certifying how the input data were collected/created. Document the
plain-text contract and manuscript font/template responsibilities.

Verify with actual generated Python/TeX, an actual compiled PDF containing all ten literal
characters, extracted expected labels/mean/range and visual inspection. Retain a mandatory real
compiler gate in rendering CI. Regenerate changed baseline sources/provenance and prove unchanged
gallery RGBA pixels. Pass the seven gates, strict gallery, updated bundled compiler and both CI
workflows. Keep spec 24 open for the independent numeric/domain/description/layout matrix.

## Measured result

Four integration regressions execute the canonical bundled Python emitter and generated files.
The baseline fails all four, including actual pdflatex compilation with a runaway caption argument.
The fixed artifact compiles and extracts all ten literal characters from caption, description,
table column/row names; the mean/range remains 4.00 [2.00, 6.00] with intended bold formatting.
A literal input command appears in the PDF without reading the sentinel TeX file. Original
spec/metadata strings and dataset bytes remain intact. Both compiled pages were rendered and
visually inspected. Disclosure retains tool/spec identity and code-generation attribution while
explicitly leaving input origin unestablished.

All seven local gates pass: 215 Node (zero skipped), 144 Python, 15 matching baselines, 16 renders,
25 recipes and seven compositions. Ruff passes. Strict gallery passes 15/15 and all regenerated
PNG RGBA pixels/dimensions match their previous published copies. Sources/provenance and the
bundled local translator are refreshed. Actual browser/edit/export reproduction also passes.
Render CI now requires real TeX compilation/PDF text verification and retains the proof document,
source and logs. Python jobs without TeX retain text checks and explicitly skip the compile test;
missing compilation is a failure in the required render gate. Spec 24 remains open.
