---
id: 47
slug: strict-verification-default
status: done
priority: P0
title: Reject failed or incomplete verification by default across execution entry points
source_idea: user 2026-10-28 follow-up review item1
---

# Strict verification by default

1. Newly generated standalone scripts reject failed/incomplete checks by default
   with exit2, preserve output artifacts/reports, and retain runtime errors as exit1.
2. CLI render/run/check and Figure.render enforce the same default. Explicit
   --no-strict / strict=False retain legacy verification exit behavior while the
   report still records failed/incomplete status. --strict remains accepted.
3. --fail-on-warning always implies strict verification, including when combined
   with the legacy opt-out. --strict and --no-strict are mutually exclusive.
4. Real generated/CLI/SDK tests cover passed, failed, incomplete, runtime-error,
   opt-out and warning policies; schema/output evidence stays consistent.
5. Rebuild the packaged translator and baseline code/provenance; confirm existing
   rendered pixels remain unchanged. Current docs distinguish main behavior from
   the immutable released0.7.0 wheel. Older generated scripts must be regenerated
   to expose the new opt-out flag; CLI default --strict also enforces their
   existing strict implementation.
6. Run the required seven checks, applicable gallery/bundle/lint controls and an
   independent emitter-policy audit. Commit/push this item separately and check CI
   for its exact revision before moving on.

## Verification (2026-10-28)

All seven gates pass:217 Node/1003 Python, zero local skips/warnings;15 matching
baselines,16 render cases,25 recipes and seven compositions. Strict gallery15/15
and Ruff lint/format55 pass. The47 new Python controls exercise actual generated,
CLI and SDK defaults, explicit opt-out, runtime failures and conflicting flags.

Independent audit1 passed all47 controls, separately checked SDK runtime-error
policies and compared all52 tracked PNGs: identical decoded pixels/dimensions.
Audit2 passed80 focused Node controls, the missing-inspector Python control and
all seven composition cases; neither review found an actionable policy defect.

The new default exposed old negative controls and smoke-layout defects. Negative
controls now assert exit2 plus specific untested evidence and retained artifacts.
Accounting fixtures retain original layout settings; the Pareto recipe's legend
moves outside data; the valid axis-break fixture uses double-column width.
Empty-facet and singleton-table composition controls remain deliberately incomplete,
with strict status/exit checks. No gate uses a blanket legacy-policy opt-out.

The bundled compiler and generated baseline code/provenance are refreshed. Owned
reference fingerprints match current code; all52 existing PNG pixels/dimensions
remain unchanged. Published0.7.0 artifacts/tag are unchanged and current docs
explicitly distinguish their legacy default. CI must be checked for the pushed
checkpoint before the next review-list item.
