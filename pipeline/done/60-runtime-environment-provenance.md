---
id: 60
slug: runtime-environment-provenance
status: done
priority: P1
title: Record dependency rendering and execution context in reports and exports
source_idea: review2026-10-28 item12 reproducibility environment tracking
---

# Environment evidence

Extend the existing version1 provenance/report envelope; do not replace the emitter
or turn environment metadata into an assertion of scientific validity.

1. Capture actual loaded core versions, selected installed optional dependencies,
Python/OS/architecture, Matplotlib backend, default font identity/hash and relevant
render/CLI/seed settings. Use a documented allowlist without cwd, hostnames, arbitrary
environment dumps, credentials or dataset rows. Unknown information remains null.
2. Freeze one snapshot before export, shared by report and PNG/SVG/PDF/HTML, including
tables and repeated executions. Early runtime failures retain honestly scoped context.
Direct main calls must not invent CLI policy; import alone must not inspect the host.
3. Preserve old schema1/schema0 reads without backfilling current-host facts. Validate
new environment records consistently/offline, with malformed records rejected.
Capture only stable values, retain same-environment deterministic static rerenders.
4. Actual export/CLI controls prove cross-format parity, different policy/DPI/settings,
missing optional metadata, failure/direct-call behavior, safe scope and legacy reads.
Verify a fresh installed source wheel offline, rebuild bundle/baselines/owned reference
fingerprints and confirm legacy PNG pixels unchanged.
5. Run seven gates/gallery/lint, push this milestone, verify exact CI and maintain
Obsidian; other review items remain explicit. Published0.8.0 remains immutable.

## Measured acceptance (2026-10-28)

- 31 new context controls, including actual four-format/table/report parity,
  malformed typed records, NaN/infinity, lifecycle/privacy/optional metadata and
  report/artifact mismatch; 43 environment/provenance controls pass.
- Seven local gates:222 Node/1189 Python, no local skips/warnings;15 baseline
  matches,16 renders,25 recipes and seven compositions. Gallery15/15 and Ruff68
  lint/format pass. Translator/schema bundle and owned fingerprints rebuilt.
- All60 prior PNG decoded pixels/dimensions remain identical after metadata-only
  refreshes. Existing deterministic PNG/SVG/PDF rerender controls pass.
- Fresh outside-checkout source-wheel agent/PDF smoke passes with runtime network
  blocking and --require-environment, including the actual strict0/2/0 tour.
- Selected context is not a full lockfile, all-font inventory or scientific
  certificate. Existing version1/schema0 reads preserve absent context. Published
  0.8.0 is untouched; this is source-only. Exact pushed CI is checked next.
