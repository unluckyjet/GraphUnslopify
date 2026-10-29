---
id: 68
slug: portable-project-artifact-check
status: done
priority: P1
title: Target recorded current exports in installed project verification
source_idea: exact21bf7d1 Linux and Windows distribution failures expose unordered PNG selection
---

# Target recorded current exports in installed project verification

The new installed project recipe selected the first recursive PNG to damage.
An audit also contains derived before/after preview PNGs. Filesystem enumeration
can select one of those rather than a current figure export, so the status check
correctly continues to verify the unchanged current export and the test fails.
Actual21bf7d1 jobs123250674088/123250674251/123250674112 fail at that assertion;
macOS123250674099 passes. Product rendering/verification is unchanged by this fix.

1. Select the newest saved audit's figure/output record by format and use its exact
   relative path, not recursive filename order. Verify its original SHA before
   corruption and require that specific figure's freshness/artifact check to fail.
2. Preserve the original source/old-record/move/strict-recovery assertions and all
   four installed-platform requirements. A local actual counterexample distinguishes
   a derived preview from the recorded current export; changing the latter requires
   an audit, independent of directory enumeration.
3. Repeat all seven local gates, Ruff and real offline fresh-wheel verification.
   Exact pushed main/Figure CI must pass before advancing to project interface67.
   Full review item10 remains incomplete. No new PyPI release or source change
   to the producer/project acceptance model is implied by this fixture repair.

## Local acceptance

Repeated seven gates222 Node/1302 Python, zero skips/one upstream SQLAlchemy
warning, Ruff81/baseline15/render16/recipes25/compositions7 pass. Actual corrected
CLI and full fresh outside-checkout wheel agent/PDF/environment/comparison/
workspace/tracking/editor/project checks pass with external runtime networking
blocked after installation. Original product module/CLI/bundle bytes are identical
to the21bf7d1 wheel. Actual two-target counterexample distinguishes a derived
comparison after-preview from a recorded current export. Exact repaired push/CI
is pending; interface67 and full review10 remain open.

Exact0ae6cf878a568885f139b8da7104f032ff97b92e main40815063294 passed all nine
jobs; Figure40815063397 passed. Linux3.10/3.12, Windows and macOS installed
checks all pass; downloaded Linux3.12 job123254085545 confirms actual offline
two-figure/five-event project evidence. Interface67 remains the next required work.
