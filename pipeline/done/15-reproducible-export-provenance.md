---
id: 15
slug: reproducible-export-provenance
status: done
priority: P1
title: Shared recoverable provenance and stable accessible exports
source_idea: accepted reproducibility, accessibility and figure-comparison roadmap
---

# Reproducible export provenance

PNG/SVG/PDF now carry the same version 1 envelope: full spec, spec hash,
computed description, data SHA-256 prefix, generator version and executed-source
SHA-256. Existing PNG Description/Comment and PDF Subject spec fields are retained.
SVG adds native title/description with ARIA links as well as Dublin Core metadata.
PDF preserves descriptions in metadata; tagged-PDF production remains a manuscript
pipeline responsibility.

Remove SVG/PDF creation timestamps and salt SVG resource IDs from the spec hash.
Normalize path formatting without altering meaningful metadata whitespace. A
fresh process rendering the same inputs must produce identical bytes in all
three formats within the same renderer/font environment.

Add read_provenance and a read-only CLI command. Legacy generated PNG/PDF specs
remain readable as schema 0; absent evidence remains unknown. Missing, malformed
or unsupported metadata fails explicitly. Reading metadata neither authenticates
it nor rechecks the experimental data.

## Verification

Eight gates passed: 204 Node / 89 Python tests, 15 matching scripts, 16 PNG/PDF
renders, 25 recipes, 7 composition cases and 15/15 strict gallery examples.
Twelve provenance tests exercise actual emitted programs, all export readers,
Unicode/escaping/meaningful whitespace, native SVG descriptions, data/source
hashes, identical-byte rerenders, legacy/missing/corrupt versions, and the CLI.
All 43 current gallery PNG/SVG/PDF files were independently read back with their
source hashes checked. Gallery RGBA pixel changes: zero. Vector ID/timestamp and
metadata differences are intentional; future identical rerenders are stable.
Ruff and diff checks pass. GitHub CI is checked after pushing.
