# Future ideas

The [workspace roadmap](../pipeline/visual-workspace-roadmap.md) tracks the current
bounded work. Its remaining item is the fair comparative evaluation and complete
delivery audit. Ideas on this page are unscheduled; they do not extend that queue.

## Capabilities that are already implemented

The [README](../README.md) describes current source and distinguishes it from the
fixed PyPI 0.8.0 release. Current source includes:

- A local visual editor with dataset profiling, direct text editing, reviewed
  model proposals, diagnostic overlays, templates and export presets.
- A bundled canonical translator. Python uses local translation by default;
  HTTP is an explicit alternative. There is one emitter implementation.
- Paper projects with scientific/PDF review, selective regeneration, source-bound
  history, claim and visual comparisons, and auditable review exports.
- All 21 documented chart kinds, including forest, paired difference, ECDF,
  confusion matrix, calibration, ridgeline, survival, Q-Q and scaling fits.

These are no longer proposals. Their existence does not establish general human
productivity, adoption, model quality or superiority over validated Matplotlib
workflows. The current comparison keeps failed and slower outcomes visible.

## Unscheduled possibilities

**Co-author comments attached to figure evidence.** A reviewer could attach a
comment to a visible label or finding and the author could review it alongside
automated checks. Comment ownership, stale targets after edits and the relationship
to immutable history need a design before implementation.

**Optional collaboration across machines.** Shared review would need an explicit
choice about which specifications, figures and datasets leave the local machine.
There is no live synchronization or multi-user comment service today.

**Dimensional analysis for derived quantities.** Declared labels and units are
already editable and reviewable. Propagating units through arbitrary transforms
would need explicit mathematical rules and independent reference tests; changing
a label alone must not be treated as a numerical conversion.

**Reviewed changes of encoding.** An overplotting finding could propose another
encoding. It should explain the changed representation and require review rather
than silently replace the author's figure.

Evaluate these ideas after the current roadmap and evidence audit. Adding more
chart kinds is not the priority of the present initiative.
