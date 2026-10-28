---
id: 61
slug: visual-figure-comparison
status: done
priority: P1
title: Explain audit changes with portable before after and difference reports
source_idea: review2026-10-28 item8 automatic figure comparisons
---

# Visual audit comparisons

Extend existing compare_audits and strict batch auditing without replacing either.

1. Automatically create portable offline HTML and versioned machine comparison
   evidence for --baseline audits. Also compare two saved reports without executing
   programs or rereading datasets. Match stable IDs, retaining additions/removals,
   unchanged entries and failed/incomplete states.
2. Resolve saved artifacts against explicit or recorded roots, including a copied
   baseline JSON and moved report/artifact archives. Verify hashes/sizes before
   display; reject escaped/symlinked paths. Missing/stale/corrupt artifacts are
   unavailable, never unchanged or evidence of scientific equivalence. A requested
   incomplete visual comparison rejects audit acceptance with exit2 while preserving
   current scientific-check status and recording the same final policy in the packet.
3. Show verified PNG/SVG/PDF previews, with a meaningful static-format preference.
   PNG/PDF raster pairs have native-dimension RGBA and white-composited RGB change
   counts, maximum/mean channel differences and a visible difference image. Never
   resample unequal canvases to invent a score. SVG is passive image preview with
   explicitly unknown server-side pixel metrics; optional PDF renderer absence
   and unsupported-only outputs have actionable fallback messages.
4. Explain actual changed data/semantic settings/claims/findings/status/environment
   using before/after evidence. Distinguish observed changes from inferred causes
   and visual differences from scientific validity. Report every exported format's
   byte evidence even when a representative static image is shown.
5. Portable HTML has no external dependencies or raw active user markup; readable
   narrow-screen layout, accessible image labels and working blend control where
   dimensions/modes permit. Actual browser tests prove network isolation, escaped
   text/passive SVG, responsive layout and controls. Verify known pixel fixtures,
   dimension/alpha/metadata-only changes, tampering/missing evidence, real audit
   change and installed CLI offline. Run seven gates and exact pushed CI; document
   source-only availability after immutable0.8.0 and maintain Obsidian.

## Measured acceptance (2026-10-28)

- 38 new controls:37 visual comparison cases plus an actual consumer-stage case;
  combined visual/audit/consumer controls59 pass. Known2x2 answer:1 changed pixel,
  fraction0.25, max255/mean42.5; hidden RGB vs alpha/white composite controls pass.
- Real source audit/installed CLI changes a data value and reverses a claim;
  before/after values,3154 locally changed pixels and retained failed/exit2 status
  are observed. Identical-picture/reversed-claim consumer packet also passes.
- Missing/stale/corrupt/escaped/oversize evidence, moved archives, no data/code
  execution, metadata-only changes, unequal canvases, PNG/SVG/PDF and optional
  renderer fallback pass. Actual passed-source/partial-preview gate exits2 with
  consistent packet/audit policy. UTF16/UTF32-without-BOM and inherited ICC probes
  found real guard/sanitization gaps; fixed and covered before landing.
- Seven gates:222 Node/1227 Python, zero local skips/warnings;15 baselines,
  16 renders,25 recipes/seven compositions; Ruff72 lint/format pass. No emitter,
  generated figure or original graphic changes. Bundle/schema copies current.
- Fresh outside-checkout source-wheel agent/PDF/required-environment/comparison
  checks pass with runtime network blocking. Actual browser desktop/mobile,
  blend controls, passive malicious SVG/escaped text and no overflow pass with
  zero external requests/errors; rendered screenshots inspected.
- Figure CI stages complete current-run comparison packets, supports pdf extra;
  exact pushed main/Figure CI (including actual pdf installation) checked next.
  Public0.8.0 remains immutable; other review items stay open.
