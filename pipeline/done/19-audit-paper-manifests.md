---
id: 19
slug: audit-paper-manifests
status: done
priority: P1
title: Audit paper manifests and compare figures data and claims
source_idea: accepted paper auditing and researcher CI roadmap
---

# Manifest-based paper audits

Connect specs or generated scripts, local data, explicit claims and optional published artifacts.
Regenerate every figure with strict policy, preserve failed/untested results and continue after
individual errors. Verify runtime schemas, exported file hashes/provenance, requested formats,
actual input bytes and script/data mappings. Use fresh owned run directories without deleting
previous evidence or input files. Bound generated-program time and terminate timed-out groups.

Read selected trusted script source directly rather than trusting timestamp/size bytecode caches.
Keep original source hashes and resolve its input paths before moving outputs to the audit folder.

Aggregate machine JSON and human Markdown; compare stable IDs for additions/removals, data bytes,
exact parsed numeric representations, semantic intent, source, claims/significance/descriptions,
findings, existing artifacts and exported files. Separate PNG pixels from file bytes; vector/HTML
pixel comparisons are explicitly unavailable. Published PNG differences warn, while missing/stale
provenance fails. This does not infer claims/data from arbitrary paper prose or unrelated images.

## Verification

18 actual audit tests include repeat-run identity, known claim reversal/numeric/pixel changes,
CSV-quoting-only changes, mixed passed/failed/incomplete entries, missing files, original script
execution with separate outputs, stale PNG/SVG/PDF/HTML, preserved provenance with altered pixels,
malformed manifests/baselines, timeouts, a deliberately stale .pyc and a missing reported export.
Two-figure public curve/table example passes and was visually inspected. Full local gates pass:
214 Node (zero skipped), 127 Python, 15 script baselines, 16 renders, 25 recipes and 7 compositions.
Ruff/typecheck/diff checks pass. A newly built wheel passes fresh isolated offline spec and script
audits with packaged schemas and existing install smoke checks. CI is checked after pushing.
