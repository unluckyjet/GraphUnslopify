---
id: 64
slug: portable-workflow-tex-verification
status: ready
priority: P0
title: Keep manuscript heading checks portable and preserve CI PDF evidence
source_idea: observed render CI40795880690 job123192123806 exact heading extraction failure
---

# Portable manuscript verification

The actual TeX compilation succeeded, but an exact heading substring assertion
failed on Ubuntu's extracted text. Do not claim the cause before inspecting the
retained new-run evidence or relax the requirement to an arbitrary partial title.

1. Keep the complete expected heading and its order before the caption, allowing
   Unicode compatibility ligatures and PDF whitespace differences only in this
   text assertion. Preserve literal-caption and sentinel/nonexecution checks.
2. Retain original PDF, compiler products and raw/normalized extracted text under
   an explicit CI evidence root and upload even after rejection, so failures can
   be inspected. Production workspace behavior is unchanged.
3. Actual local TeX cases and all seven gates pass. Push separately, inspect
   exact-commit CI and download/render its PDF to verify actual layout and explain
   any previous extraction mismatch from evidence. Keep tracking63 unimplemented
   until the failed CI is corrected. Maintain Obsidian without inventing success.

## Implementation checkpoint (2026-10-28)

Full expected heading/order is retained after compatibility Unicode/whitespace
normalization. Raw text and PDFs are saved before assertion and uploaded under
research-workflow-verification even after failure. Four actual local TeX cases
and all seven gates222 Node/1259 Python/Ruff75 pass, zero local skips/warnings.
Production code/package/emitter/graphics unchanged. This spec remains ready until
new exact-commit CI and downloaded PDF/text inspection establish final evidence;
previous0a5c44e main had eight green jobs and one extraction assertion failure.
