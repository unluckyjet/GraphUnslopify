---
id: 64
slug: portable-workflow-tex-verification
status: ready
priority: P0
title: Supply searchable manuscript text fonts and retain portable CI PDF evidence
source_idea: observed render CI40795880690 job123192123806 exact heading extraction failure
---

# Portable manuscript verification

The actual TeX compilation succeeded, but an exact heading substring assertion
failed on Ubuntu's extracted text. Retained PDF/font/compiler evidence identifies
unmapped bitmap text fonts; keep the complete heading requirement while repairing
the generated example's searchable text.

1. Keep the complete expected heading and its order before the caption, allowing
   Unicode compatibility ligatures and PDF whitespace differences only in this
   text assertion. Preserve literal-caption and sentinel/nonexecution checks.
2. Select outline fonts and explicit pdfTeX Unicode maps in the generated example,
   while leaving existing manuscript fonts unchanged. Compiled output must expose
   mapped non-Type3 text fonts. Retain original PDF, compiler products and raw/normalized extracted text under
   an explicit CI evidence root and upload even after rejection, so failures can
   be inspected. Existing manuscript font choices remain unchanged.
3. Actual local TeX cases and all seven gates pass. Push separately, inspect
   exact-commit CI and download/render its PDF to verify actual layout and explain
   any previous extraction mismatch from evidence. Keep tracking63 unimplemented
   until the failed CI is corrected. Maintain Obsidian without inventing success.

## First diagnostic checkpoint (2026-10-28, 0b48b89)

Full expected heading/order is retained after compatibility Unicode/whitespace
normalization. Raw text and PDFs are saved before assertion and uploaded under
research-workflow-verification even after failure. Four actual local TeX cases
and all seven gates222 Node/1259 Python/Ruff75 pass, zero local skips/warnings.
Production code/package/emitter/graphics unchanged. This spec remains ready until
new exact-commit CI and downloaded PDF/text inspection establish final evidence;
previous0a5c44e main had eight green jobs and one extraction assertion failure.

## Downloaded evidence and revised repair

The0b48b89 retained PDF renders its heading correctly, but both pypdf/PDFium
extract Checked \x1cgure exports. Its outer text fonts are Type3 EC bitmap fonts
without ToUnicode maps; normalized whitespace/ligatures alone cannot invent fi.
Source example now selects Latin Modern outline fonts and explicit pdfTeX Unicode
maps; CI installs lmodern. The actual compiled-output regression requires mapped
non-Type3 text fonts as well as the entire heading/order. Existing manuscript
fonts and generated figure pixels are not changed. Verify new exact CI and PDF.

The revised repair passes all seven local gates:222 Node/1259 Python, no skipped
tests; baseline15/render16/recipes25/compositions7 and Ruff75 pass. Four actual
TeX controls pass. Local extracted heading is complete, text fonts are Type1
Latin Modern with ToUnicode, and the rendered page retains the correct layout.
A fresh source wheel passes agent/PDF/getting-started/visual-comparison/workflow
checks with external runtime connections blocked. Exact pushed CI and downloaded
CI PDF inspection remain required before closing this spec.
